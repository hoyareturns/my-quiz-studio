"use strict";
const $ = (selector, root = document) => root.querySelector(selector);
const $$ = (selector, root = document) => [...root.querySelectorAll(selector)];
const esc = (value) =>
  String(value ?? "").replace(
    /[&<>"']/g,
    (c) =>
      ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[
        c
      ],
  );
const storage = {
  get(k, fallback = "") {
    try {
      return localStorage.getItem(k) ?? fallback;
    } catch {
      return fallback;
    }
  },
  set(k, v) {
    try {
      localStorage.setItem(k, v);
      return true;
    } catch {
      return false;
    }
  },
  remove(k) {
    try {
      localStorage.removeItem(k);
    } catch {}
  },
};
const paths = {
  learn:
    "M4 4h6a3 3 0 0 1 3 3v14a4 4 0 0 0-4-2H4z M20 4h-4a3 3 0 0 0-3 3v14a4 4 0 0 1 4-2h3z",
  review: "M4 10a8 8 0 1 1 1 8 M4 4v6h6 M12 8v5l3 2",
  records: "M4 20h17 M7 16v-5 M12 16V5 M17 16V8",
  author: "M14 4l6 6 M4 20l5-1L21 7a2 2 0 0 0-4-4L5 15z",
  more: "M5 5h4v4H5z M15 5h4v4h-4z M5 15h4v4H5z M15 15h4v4h-4z",
  leaderboard:
    "M8 4h8v5a4 4 0 0 1-8 0z M8 6H4v3a4 4 0 0 0 4 4 M16 6h4v3a4 4 0 0 1-4 4 M12 13v6 M8 20h8",
  participation:
    "M8 10a3 3 0 1 0 0-6 3 3 0 0 0 0 6 M2 20v-3a6 6 0 0 1 12 0v3 M17 4a3 3 0 0 1 0 6 M17 14a5 5 0 0 1 5 5",
  chat: "M4 4h16v13H9l-5 4z M8 8h8 M8 12h5",
  admin: "M12 3l8 4v5c0 5-8 9-8 9s-8-4-8-9V7z M8 12l3 3 5-6",
  search: "M10 17a7 7 0 1 1 0-14 7 7 0 0 1 0 14 M15 15l6 6",
};
const icon = (name) =>
  `<svg viewBox="0 0 24 24" aria-hidden="true"><path d="${paths[name] || paths.learn}"/></svg>`;
const navs = [
  ["learn", "문제 풀기"],
  ["review", "오답 노트"],
  ["records", "학습 기록"],
  ["author", "문제 만들기"],
];
const moreNavs = [
  ["leaderboard", "성취 순위"],
  ["participation", "참여 현황"],
  ["chat", "이야기 나누기"],
  ["admin", "관리"],
];
const state = {
  user: storage.get("quiz.user"),
  admin: false,
  quizzes: [],
  connected: false,
  page: "learn",
  category: "전체",
  search: "",
  attempt: null,
  answers: [],
  question: 0,
  result: null,
  preview: null,
  previewIndex: 0,
  revision: 0,
  editId: null,
};
let toastTimer,
  confirmResolve,
  userContinuation,
  template = "",
  defaultsApplied = false;
let draft;
try {
  draft = JSON.parse(storage.get("quiz.draft", "{}"));
} catch {
  draft = {};
}
if (!draft || typeof draft !== "object" || Array.isArray(draft)) draft = {};
state.editId = typeof draft._editId === "string" ? draft._editId : null;
const draftSignature = () =>
  JSON.stringify([
    draft.title || "",
    draft.category || "",
    draft.content || "",
    state.editId,
  ]);
const draftPayload = () => ({
  title: draft.title || "",
  category: draft.category || "",
  content: draft.content || "",
});
const main = $("#main");
// Local math assets; neither quiz content nor formulas leave this server.
const mathObserver = new MutationObserver(() => {
  mathObserver.disconnect();
  if (window.renderMathInElement)
    window.renderMathInElement(main, {
      delimiters: [
        { left: "$$", right: "$$", display: true },
        { left: "$", right: "$", display: false },
      ],
      throwOnError: false,
      trust: false,
      maxExpand: 200,
      maxSize: 10,
      ignoredTags: [
        "script",
        "noscript",
        "style",
        "textarea",
        "pre",
        "code",
        "option",
        "input",
      ],
      ignoredClasses: ["katex"],
    });
  mathObserver.observe(main, { childList: true, subtree: true });
});
mathObserver.observe(main, { childList: true, subtree: true });
async function api(path, options = {}) {
  let response;
  try {
    response = await fetch(`/api${path}`, {
      credentials: "same-origin",
      ...options,
      headers: {
        "Content-Type": "application/json",
        ...(options.headers || {}),
      },
      body:
        options.body === undefined ? undefined : JSON.stringify(options.body),
    });
  } catch {
    throw new Error(
      "서버에 연결하지 못했어요. 인터넷 연결을 확인하고 다시 시도해 주세요.",
    );
  }
  const data = await response.json().catch(() => ({}));
  if (!response.ok)
    throw new Error(
      typeof data.detail === "string"
        ? data.detail
        : "입력 내용을 확인한 뒤 다시 시도해 주세요.",
    );
  return data;
}
function toast(message) {
  clearTimeout(toastTimer);
  const el = $("#toast");
  el.textContent = message;
  el.hidden = false;
  toastTimer = setTimeout(() => (el.hidden = true), 4500);
}
function on(selector, event, handler, root = document) {
  const element = typeof selector === "string" ? $(selector, root) : selector;
  if (element)
    element.addEventListener(event, async (e) => {
      try {
        await handler(e);
      } catch (error) {
        toast(error.message);
      }
    });
}
async function busy(button, action) {
  if (button.disabled) return;
  const label = button.textContent;
  button.disabled = true;
  button.textContent = "처리 중…";
  try {
    return await action();
  } finally {
    button.disabled = false;
    button.textContent = label;
  }
}
function heading(eyebrow, title, description, extra = "") {
  return `<div class="page-heading"><div><div class="eyebrow">${eyebrow}</div><h1>${esc(title)}</h1><p>${esc(description)}</p></div>${extra}</div>`;
}
function empty(title, description, action = "") {
  return `<div class="empty"><div class="empty-icon">◇</div><h2>${esc(title)}</h2><p>${esc(description)}</p>${action}</div>`;
}
function notice(message, type = "") {
  return `<div class="notice ${type}" role="status">${esc(message)}</div>`;
}
function confirmAction(message, options = {}) {
  $("#confirm-title").textContent = options.title || "확인해 주세요";
  $("#confirm-no").textContent = options.cancel || "취소";
  $("#confirm-yes").textContent = options.confirm || "계속";
  $("#confirm-message").textContent = message;
  $("#confirm-dialog").showModal();
  return new Promise((resolve) => (confirmResolve = resolve));
}
function finishConfirm(value) {
  $("#confirm-dialog").close();
  if (confirmResolve) confirmResolve(value);
  confirmResolve = null;
}
on("#confirm-yes", "click", () => finishConfirm(true));
on("#confirm-no", "click", () => finishConfirm(false));
on("#confirm-dialog", "cancel", () => finishConfirm(false));
function requireUser(continuation) {
  if (state.user) {
    continuation();
    return;
  }
  userContinuation = continuation;
  $("#profile-input").value = "";
  $("#profile-dialog").showModal();
}
function updateProfile() {
  $("#profile-name").textContent = state.user || "이름 설정";
  $("#avatar").textContent = state.user ? state.user.slice(0, 1) : "나";
  $$(".admin-trigger").forEach(
    (el) =>
      (el.textContent = state.admin ? "관리자 로그아웃" : "관리자 로그인"),
  );
}
on("#profile-button", "click", () => {
  if (state.attempt && !state.result) {
    toast("풀이 중에는 학습자 이름을 바꿀 수 없어요.");
    return;
  }
  $("#profile-input").value = state.user;
  $("#profile-dialog").showModal();
});
on("#profile-form", "submit", (e) => {
  e.preventDefault();
  const value = $("#profile-input").value.trim();
  if (!value) return;
  state.user = value;
  storage.set("quiz.user", value);
  updateProfile();
  $("#profile-dialog").close();
  if (userContinuation) {
    const next = userContinuation;
    userContinuation = null;
    next();
  } else route();
});
on("#clear-profile", "click", () => {
  state.user = "";
  storage.remove("quiz.user");
  updateProfile();
  $("#profile-dialog").close();
  userContinuation = null;
  route();
  toast("이 기기에서 학습자 이름을 지웠어요.");
});
$$(".close-dialog").forEach((el) =>
  on(el, "click", () => {
    el.closest("dialog").close();
    userContinuation = null;
  }),
);
on("#profile-dialog", "cancel", () => (userContinuation = null));
async function adminAction() {
  if (state.admin) {
    await api("/admin/logout", { method: "POST" });
    state.admin = false;
    updateProfile();
    route();
    toast("로그아웃했어요.");
  } else {
    $("#admin-password").value = "";
    $("#admin-error").textContent = "";
    $("#admin-dialog").showModal();
  }
}
$$(".admin-trigger").forEach((el) => on(el, "click", adminAction));
on("#admin-form", "submit", async (e) => {
  e.preventDefault();
  await busy($("button.primary", e.target), async () => {
    try {
      await api("/admin/login", {
        method: "POST",
        body: { password: $("#admin-password").value },
      });
      state.admin = true;
      $("#admin-password").value = "";
      $("#admin-dialog").close();
      updateProfile();
      route();
      toast("관리자 인증이 완료됐어요.");
    } catch (error) {
      $("#admin-error").textContent = error.message;
    }
  });
});
function renderNav() {
  const link = ([id, label]) =>
    `<a class="nav-item ${state.page === id ? "active" : ""}" href="#${id}" ${state.page === id ? 'aria-current="page"' : ""}>${icon(id)}<span>${label}</span></a>`;
  $("#desktop-nav").innerHTML =
    navs.map(link).join("") +
    '<div class="nav-divider"></div>' +
    moreNavs.map(link).join("");
  $("#mobile-nav").innerHTML = [...navs, ["more", "더보기"]]
    .map(([id, label]) =>
      link([id, label]).replace(
        "nav-item ",
        `nav-item ${id === "more" && moreNavs.some((x) => x[0] === state.page) ? "active " : ""}`,
      ),
    )
    .join("");
}
on(document, "click", async (e) => {
  const anchor = e.target.closest('a[href^="#"]');
  if (!anchor || anchor.classList.contains("skip-link")) return;
  const next = anchor.getAttribute("href").slice(1);
  if (state.attempt && !state.result && next !== state.page) {
    e.preventDefault();
    if (
      await confirmAction("풀이를 나가면 현재 답안이 사라집니다. 나갈까요?")
    ) {
      state.attempt = null;
      state.answers = [];
      location.hash = next;
    }
  }
});
window.addEventListener("beforeunload", (e) => {
  if (state.attempt && !state.result) {
    e.preventDefault();
    e.returnValue = "";
  }
});
window.addEventListener("hashchange", () => {
  route();
  window.scrollTo(0, 0);
});
async function bootstrap() {
  const data = await api("/bootstrap");
  Object.assign(state, {
    quizzes: [...(data.quizzes || [])].sort((a, b) =>
      a.title.localeCompare(b.title, "ko", { numeric: true }),
    ),
    admin: data.admin,
    connected: data.connected,
    connectionMessage: data.message,
    settings: data.settings || {},
  });
  if (!defaultsApplied) {
    defaultsApplied = true;
    if (state.settings.default_category)
      state.category = state.settings.default_category;
    if (!location.hash) {
      const views = {
        "역량 점검": "learn",
        "퀴즈 선택": "learn",
        "오답 정복": "review",
        "개인 기록": "records",
        "우수 성취자": "leaderboard",
        "구역별 최강자": "leaderboard",
        참여현황: "participation",
        토론방: "chat",
        우정파괴채팅: "chat",
        "문제 등록": "author",
        관리자: "admin",
        "관리자 모드": "admin",
      };
      const initial =
        views[state.settings.default_view] || state.settings.default_view;
      if ([...navs, ...moreNavs].some((x) => x[0] === initial))
        history.replaceState(null, "", `#${initial}`);
    }
  }
  updateProfile();
}
function loading() {
  main.innerHTML =
    '<div class="loading" role="status"><span class="spinner"></span>불러오고 있어요.</div>';
}
async function route() {
  stopValueCarousel();
  const page = location.hash.slice(1) || "learn";
  state.page = [...navs, ...moreNavs, ["more", ""]].some((x) => x[0] === page)
    ? page
    : "learn";
  renderNav();
  const revision = ++state.revision;
  try {
    if (state.page === "learn") renderLibrary();
    else if (state.page === "author") renderAuthor();
    else if (state.page === "more") renderMore();
    else {
      loading();
      const renderer = {
        records: renderRecords,
        review: renderWrongs,
        leaderboard: renderLeaderboard,
        participation: renderParticipation,
        chat: renderChat,
        admin: renderAdmin,
      }[state.page];
      await renderer(revision);
    }
  } catch (error) {
    if (revision === state.revision) {
      main.innerHTML = empty(
        "잠시 연결을 확인해 주세요",
        error.message,
        '<button id="retry-page" class="primary">다시 불러오기</button>',
      );
      on("#retry-page", "click", route);
    }
  }
}
// Original artwork: https://www.seonghwa.co.kr/ → About → 가치체계.
const companyValues = [
  {
    title: "미션",
    copy: "우리는 사람들에게<br>더 나은 에너지를 불어 넣는다",
    art: "mission",
  },
  {
    title: "비전",
    copy: "가장 신뢰받는<br>기계시스템 인테그레이터",
    art: "vision",
  },
  { title: "소프트한 하드웨어", art: "hardware" },
  { title: "효과적인 효율", art: "efficiency" },
  { title: "자존적 인간애", art: "humanity" },
  { title: "근본주의", art: "principles" },
];
let stopValueCarousel = () => {};
function valueCarouselMarkup() {
  return `<section class="value-carousel" aria-label="성화 미션·비전·핵심가치" aria-roledescription="슬라이드 쇼">
    <div class="value-slides">${companyValues
      .map(
        (
          item,
          i,
        ) => `<div class="value-slide" role="group" aria-roledescription="슬라이드" aria-label="${i + 1} / ${companyValues.length}" ${i ? "hidden" : ""}>
      <span class="value-art value-art-${item.art}" aria-hidden="true"></span>
      <div class="value-text">${i > 1 ? '<span class="value-kicker">CORE VALUE · 핵심가치</span>' : ""}<h3>${item.title}</h3>${item.copy ? `<p>${item.copy}</p>` : ""}</div>
    </div>`,
      )
      .join("")}</div>
    <div class="value-controls"><div class="value-dots" role="group" aria-label="표시할 가치 선택">${companyValues.map((item, i) => `<button type="button" data-value-slide="${i}" aria-label="${item.title} 보기" aria-pressed="${i === 0}"><span></span></button>`).join("")}</div><button type="button" class="value-pause" aria-label="자동 전환 일시정지">Ⅱ</button></div>
  </section>`;
}
function mountValueCarousel() {
  const root = $(".value-carousel");
  if (!root) return;
  const slides = $$(".value-slide", root);
  const dots = $$("[data-value-slide]", root);
  const pause = $(".value-pause", root);
  const motion = matchMedia("(prefers-reduced-motion: reduce)");
  let current = 0,
    paused = motion.matches,
    hovered = false,
    timer;
  const updatePause = () => {
    pause.textContent = paused ? "▶" : "Ⅱ";
    pause.setAttribute(
      "aria-label",
      paused ? "자동 전환 시작" : "자동 전환 일시정지",
    );
  };
  const show = (index) => {
    current = index;
    slides.forEach((slide, i) => {
      slide.hidden = i !== current;
    });
    dots.forEach((dot, i) =>
      dot.setAttribute("aria-pressed", String(i === current)),
    );
  };
  const schedule = () => {
    clearInterval(timer);
    if (paused) return;
    timer = setInterval(() => {
      if (!root.isConnected) {
        stop();
        return;
      }
      if (
        !document.hidden &&
        !hovered &&
        !root.contains(document.activeElement)
      )
        show((current + 1) % slides.length);
    }, 6000);
  };
  const onMotion = () => {
    paused = motion.matches;
    updatePause();
    schedule();
  };
  const stop = () => {
    clearInterval(timer);
    motion.removeEventListener("change", onMotion);
  };
  stopValueCarousel = stop;
  dots.forEach((dot, i) =>
    on(dot, "click", () => {
      show(i);
      paused = true;
      updatePause();
      schedule();
    }),
  );
  on(pause, "click", () => {
    paused = !paused;
    updatePause();
    schedule();
  });
  on(root, "pointerenter", () => {
    hovered = true;
  });
  on(root, "pointerleave", () => {
    hovered = false;
  });
  motion.addEventListener("change", onMotion);
  updatePause();
  schedule();
}
function renderLibrary() {
  stopValueCarousel();
  if (state.attempt) {
    if (state.result) renderResult();
    else renderQuestion();
    return;
  }
  const cats = [...new Set(state.quizzes.map((q) => q.category))];
  if (!cats.includes(state.category) && state.category !== "전체")
    state.category = "전체";
  main.innerHTML =
    '<h1 class="visually-hidden">직원 교육</h1>' +
    (!state.connected
      ? notice(
          state.connectionMessage ||
            "저장소가 연결되지 않았어요. 문제 만들기의 요청문·미리보기는 사용할 수 있습니다.",
          "warn",
        )
      : "") +
    `${valueCarouselMarkup()}<section aria-labelledby="library-title"><div class="section-heading"><h2 id="library-title">학습 세트 <span class="count" id="quiz-count"></span></h2><label class="search-box"><span class="visually-hidden">문제 검색</span>${icon("search")}<input id="quiz-search" type="search" placeholder="배우고 싶은 주제를 검색하세요" value="${esc(state.search)}"></label></div><div class="filters" role="group" aria-label="분야 필터">${["전체", ...cats].map((c) => `<button class="chip ${c === state.category ? "active" : ""}" data-category="${esc(c)}" aria-pressed="${c === state.category}">${esc(c)}</button>`).join("")}</div><div class="quiz-grid" id="quiz-grid"></div></section>`;
  mountValueCarousel();
  renderCards();
  on("#quiz-search", "input", (e) => {
    state.search = e.target.value;
    renderCards();
  });
  $$("[data-category]").forEach((el) =>
    on(el, "click", () => {
      state.category = el.dataset.category;
      $$("[data-category]").forEach((x) => {
        x.classList.toggle("active", x === el);
        x.setAttribute("aria-pressed", x === el);
      });
      renderCards();
    }),
  );
}
function renderCards() {
  const quizzes = state.quizzes.filter(
    (q) =>
      (state.category === "전체" || q.category === state.category) &&
      `${q.title} ${q.category}`
        .toLocaleLowerCase()
        .includes(state.search.toLocaleLowerCase()),
  );
  $("#quiz-count").textContent = `${quizzes.length}개`;
  $("#quiz-grid").innerHTML = quizzes.length
    ? quizzes
        .map(
          (q) =>
            `<article class="quiz-card"><div class="card-top"><span class="card-icon">${icon("learn")}</span><span class="badge">${q.count}문항</span></div><h3>${esc(q.title)}</h3><p class="category">${esc(q.category)}</p><div class="card-bottom"><span>${q.valid ? "나의 속도로 차근차근" : "문제 형식 확인 필요"}</span><button data-start="${esc(q.id)}" ${!q.valid ? "disabled" : ""} aria-label="${esc(q.title)} 시작하기">시작하기 <span aria-hidden="true">↗</span></button></div></article>`,
        )
        .join("")
    : empty(
        state.search ? "검색 결과가 없어요" : "아직 학습 세트가 없어요",
        state.search
          ? "다른 검색어나 분야를 선택해 보세요."
          : "문제 만들기에서 첫 번째 학습 세트를 준비해 보세요.",
        '<a href="#author" class="secondary">문제 만들기</a>',
      );
  $$("[data-start]").forEach((el) =>
    on(el, "click", () =>
      requireUser(() =>
        busy(el, async () => {
          state.attempt = await api("/attempts", {
            method: "POST",
            body: { quiz_id: el.dataset.start, user: state.user },
          });
          state.answers = new Array(state.attempt.questions.length).fill("");
          state.question = 0;
          state.result = null;
          renderQuestion();
          window.scrollTo(0, 0);
        }).catch((error) => toast(error.message)),
      ),
    ),
  );
}
function renderQuestion() {
  const a = state.attempt,
    q = a.questions[state.question],
    total = a.questions.length;
  main.innerHTML = `<div class="narrow"><div class="quiz-toolbar"><h1>${esc(a.title)}</h1><button class="quiet" id="exit-quiz">나중에 풀기 ×</button></div><div class="progress-meta"><span>${esc(state.user)} 님의 학습</span><span>${state.question + 1} / ${total} 문제</span></div><div class="progress-track"><span style="width:${((state.question + 1) / total) * 100}%"></span></div><section class="panel"><div class="eyebrow">QUESTION ${String(state.question + 1).padStart(2, "0")}</div>${q.p ? `<div class="passage">${esc(q.p)}</div>` : ""}<h2 class="question-text" id="question-title">${esc(q.q)}</h2><div id="answer-area">${q.o.length === 1 && q.o[0] === "주관식" ? `<label>나의 답안<input id="subjective-answer" autocomplete="off" value="${esc(state.answers[state.question])}" placeholder="답을 입력해 주세요"></label>` : `<div class="option-list" role="radiogroup" aria-labelledby="question-title">${q.o.map((o, i) => `<label class="option"><input type="radio" name="answer" value="${esc(o)}" ${state.answers[state.question] === o ? "checked" : ""}><span class="option-letter">${i + 1}</span><span>${esc(o)}</span></label>`).join("")}</div>`}</div><div class="quiz-actions"><button class="secondary" id="previous-question" ${state.question === 0 ? "disabled" : ""}>← 이전</button><button class="primary" id="next-question">${state.question === total - 1 ? "답안 제출하기" : "다음 문제 →"}</button></div></section><div class="question-nav" aria-label="문제로 이동">${a.questions.map((_, i) => `<button data-question="${i}" class="${state.answers[i] ? "answered " : ""}${state.question === i ? "current" : ""}" aria-label="${i + 1}번 문제${state.answers[i] ? ", 답변 완료" : ""}" ${state.question === i ? 'aria-current="step"' : ""}>${i + 1}</button>`).join("")}</div><p class="field-hint">답은 제출 전까지 자유롭게 바꿀 수 있어요. 제출하면 기록에 저장됩니다.</p></div>`;
  on("#exit-quiz", "click", async () => {
    if (
      await confirmAction("풀이를 나가면 현재 답안이 사라집니다. 나갈까요?")
    ) {
      state.attempt = null;
      state.answers = [];
      renderLibrary();
    }
  });
  const saveAnswer = (value) => {
    state.answers[state.question] = value;
    const b = $(`[data-question="${state.question}"]`);
    b.classList.toggle("answered", Boolean(value.trim()));
    b.setAttribute(
      "aria-label",
      `${state.question + 1}번 문제${value.trim() ? ", 답변 완료" : ""}`,
    );
  };
  on("#subjective-answer", "input", (e) => saveAnswer(e.target.value));
  $$('input[name="answer"]').forEach((el) =>
    on(el, "change", () => saveAnswer(el.value)),
  );
  const go = (index) => {
    state.question = index;
    renderQuestion();
    $("#question-title").setAttribute("tabindex", "-1");
    $("#question-title").focus();
    window.scrollTo(0, 0);
  };
  on("#previous-question", "click", () => go(state.question - 1));
  $$("[data-question]").forEach((el) =>
    on(el, "click", () => go(Number(el.dataset.question))),
  );
  on("#next-question", "click", async (e) => {
    if (state.question < total - 1) {
      go(state.question + 1);
      return;
    }
    const missing = state.answers.flatMap((value, index) =>
      value.trim() ? [] : [index],
    );
    if (missing.length) {
      const numbers = missing
        .slice(0, 10)
        .map((index) => index + 1)
        .join(", ");
      const proceed = await confirmAction(
        `아직 답하지 않은 문제가 ${missing.length}개 있어요. (${numbers}${missing.length > 10 ? " 외" : ""}번) 그대로 제출하면 미응답은 모두 오답 처리되고 점수와 오답 노트에 반영됩니다.`,
        {
          title: "미응답 문제가 있어요",
          cancel: "돌아가서 문제 풀기",
          confirm: "미응답을 오답 처리하고 제출",
        },
      );
      if (state.attempt?.attempt_id !== a.attempt_id) return;
      if (!proceed) {
        go(missing[0]);
        return;
      }
    }
    await busy(e.target, async () => {
      const result = await api(`/attempts/${a.attempt_id}/submit`, {
        method: "POST",
        body: {
          answers: [...state.answers],
          allow_unanswered: missing.length > 0,
        },
      });
      if (state.attempt?.attempt_id !== a.attempt_id) return;
      state.result = result;
      if (state.page === "learn") {
        renderResult();
        window.scrollTo(0, 0);
      }
    });
  });
}
function renderResult() {
  const r = state.result;
  main.innerHTML = `<div class="narrow"><section class="panel"><div class="score-hero"><div class="eyebrow">LEARNING COMPLETE</div><h1>${r.score === 100 ? "모든 문제를 맞혔어요!" : "오늘도 한 걸음 나아갔어요."}</h1><p>${esc(state.attempt.title)}</p><div class="score-ring"><strong>${r.score}</strong><span>점 / 100점</span></div><p>${r.total}문제 중 ${r.correct}문제 정답 · ${Math.round(r.duration)}초</p></div>${r.saved ? notice("학습 기록에 저장했어요. 틀린 문제는 오답 노트에서 다시 풀 수 있어요.") : notice(r.message || "기록을 저장하지 못했어요. 아래에서 저장을 다시 시도해 주세요.", "warn")}<div class="actions">${!r.saved ? '<button id="retry-save" class="primary">기록 저장 다시 시도</button>' : ""}<button id="finish-quiz" class="${r.saved ? "primary" : "secondary"}">학습 세트로 돌아가기</button></div></section><section class="panel"><h2>답과 해설 돌아보기</h2>${r.review.map((item, i) => `<details class="review-item" ${!item.correct ? "open" : ""}><summary><span class="verdict ${item.correct ? "" : "wrong"}">${item.correct ? "정답" : "복습"}</span><span>${i + 1}. ${esc(item.question)}</span></summary><div class="answer-detail"><p>내 답: ${esc(item.answer)}</p><p><strong>정답: ${esc(item.correct_answer)}</strong></p><p>${esc(item.explanation)}</p></div></details>`).join("")}</section></div>`;
  on("#retry-save", "click", (e) =>
    busy(e.target, async () => {
      state.result = await api(`/attempts/${state.attempt.attempt_id}/submit`, {
        method: "POST",
        body: { answers: state.answers },
      });
      renderResult();
    }),
  );
  on("#finish-quiz", "click", async () => {
    if (
      !r.saved &&
      !(await confirmAction(
        "아직 기록이 저장되지 않았습니다. 저장을 다시 시도하지 않고 나갈까요?",
      ))
    )
      return;
    state.attempt = null;
    state.result = null;
    renderLibrary();
  });
}
function saveDraft() {
  draft._editId = state.editId;
  const ok = storage.set("quiz.draft", JSON.stringify(draft));
  const label = $("#draft-state");
  if (label)
    label.textContent = ok
      ? "이 기기에 임시 저장됨"
      : "임시 저장 불가 · 내용을 따로 복사해 주세요";
}
function invalidatePreview() {
  state.preview = null;
  const area = $("#preview-area");
  if (area) area.innerHTML = previewPlaceholder();
}
function previewPlaceholder() {
  return `<div class="preview-placeholder">${icon("author")}<h3>등록 전에 한 번 더 확인해요</h3><p>문제를 붙여넣고 ‘문제 확인하기’를 누르면<br>실제 풀이 화면처럼 볼 수 있어요.</p></div>`;
}
function renderAuthor() {
  main.innerHTML =
    heading(
      "QUESTION STUDIO",
      state.editId ? "학습 세트 수정하기" : "좋은 문제를, 더 쉽게.",
      "요청문을 복사하고 답변을 붙여넣으면 준비 끝. 등록 전에 미리 확인하세요.",
    ) +
    `<div class="steps"><div class="step"><b>1</b>요청문 복사</div><div class="step active"><b>2</b>문제 붙여넣기</div><div class="step"><b>3</b>확인하고 등록</div></div><div class="author-layout"><div><section class="panel"><details id="prompt-details" ${!draft.content ? "open" : ""}><summary><h2>ChatGPT에 요청할 내용 만들기</h2></summary><p class="field-hint">원하는 주제를 적고 요청문을 복사해 ChatGPT에 붙여넣으세요.</p><div class="form-grid"><label>주제<input id="prompt-topic" placeholder="예: 엑셀 기본 함수" value="${esc(draft.topic || "")}"></label><label>문제 수<select id="prompt-count">${[5, 10, 15, 20].map((n) => `<option ${Number(draft.count || 10) === n ? "selected" : ""}>${n}</option>`).join("")}</select></label></div><label style="margin-top:16px">추가 요청<input id="prompt-extra" placeholder="예: 초보자 수준, 주관식 2개 포함" value="${esc(draft.extra || "")}"></label><div class="actions"><button id="copy-prompt" class="primary">요청문 복사</button><a href="https://chatgpt.com/" target="_blank" rel="noopener noreferrer" class="secondary">ChatGPT 열기 ↗</a></div><details><summary class="field-hint">요청문 직접 보기</summary><label class="visually-hidden" for="prompt-text">완성된 요청문</label><textarea id="prompt-text" class="prompt-output" readonly></textarea></details><p class="field-hint">이 앱은 AI API를 호출하지 않습니다. 외부 서비스의 이용 조건은 해당 서비스를 따릅니다.</p></details></section><section class="panel"><div class="panel-heading"><h2>${state.editId ? "문제 내용 수정" : "문제 붙여넣기"}</h2><span id="draft-state" class="draft-state">임시 저장 준비</span></div><label>학습 세트 이름<input id="draft-title" maxlength="150" placeholder="예: 엑셀 기본 함수 연습" value="${esc(draft.title || "")}" ${state.editId ? "readonly" : ""}></label><label>분야<input id="draft-category" maxlength="80" list="categories" placeholder="예: 디지털 역량" value="${esc(draft.category || "")}"></label><datalist id="categories">${[
      ...new Set([
        ...state.quizzes.map((q) => q.category),
        ...(state.settings?.custom_categories || "")
          .split(",")
          .map((c) => c.trim())
          .filter(Boolean),
      ]),
    ]
      .map((c) => `<option value="${esc(c)}">`)
      .join(
        "",
      )}</datalist><div class="paste-toolbar"><strong style="font-size:13px">ChatGPT의 문제 답변</strong><div><button id="paste-content" class="quiet">붙여넣기</button><label class="secondary drop-file" style="font-size:11px;margin:0;padding:7px 11px">파일 불러오기<input id="import-file" type="file" accept=".txt,text/plain" aria-label="텍스트 파일 불러오기"></label></div></div><label class="visually-hidden" for="draft-content">문제 원문</label><textarea id="draft-content" class="code-input" spellcheck="false" placeholder="[Q1] 질문 내용\n[O] ① 보기1 ② 보기2\n[A] ①\n[K] 핵심 개념\n[E] 정답 해설">${esc(draft.content || "")}</textarea><p class="field-hint">여러 문제를 한 번에 넣을 수 있어요. [Q1], [O], [A] 형식이 필요합니다.</p><div class="actions"><button id="clear-draft" class="quiet">${state.editId ? "수정 취소" : "비우기"}</button><button id="preview-button" class="primary">문제 확인하기 →</button></div></section></div><section class="panel" id="preview-panel"><div class="panel-heading"><h2>미리보기</h2><span class="badge">등록 전 확인</span></div><div id="preview-area">${previewPlaceholder()}</div></section></div>`;
  ["title", "category", "content"].forEach((key) =>
    on(`#draft-${key}`, "input", (e) => {
      draft[key] = e.target.value;
      saveDraft();
      invalidatePreview();
    }),
  );
  ["topic", "extra", "count"].forEach((key) =>
    on(`#prompt-${key}`, key === "count" ? "change" : "input", (e) => {
      draft[key] = e.target.value;
      saveDraft();
      updatePrompt();
    }),
  );
  saveDraft();
  if (template) updatePrompt();
  else
    api("/author/template")
      .then((data) => {
        template = data.template;
        if (state.page === "author") updatePrompt();
      })
      .catch((e) => toast(e.message));
  on("#copy-prompt", "click", async () => {
    if (!template)
      throw Error("요청문을 불러오는 중입니다. 잠시 후 다시 눌러 주세요.");
    const text = buildPrompt();
    try {
      await navigator.clipboard.writeText(text);
      toast("요청문을 복사했어요. ChatGPT에 붙여넣어 주세요.");
    } catch {
      $("#prompt-text").closest("details").open = true;
      $("#prompt-text").focus();
      $("#prompt-text").select();
      toast("선택된 요청문을 길게 누르거나 Ctrl+C로 복사해 주세요.");
    }
  });
  on("#paste-content", "click", async () => {
    try {
      const text = await navigator.clipboard.readText();
      if (text) {
        draft.content = text;
        $("#draft-content").value = text;
        saveDraft();
        invalidatePreview();
      }
    } catch {
      $("#draft-content").focus();
      toast("입력란을 길게 눌러 붙여넣기하거나 Ctrl+V를 눌러 주세요.");
    }
  });
  on("#import-file", "change", async (e) => {
    const file = e.target.files[0];
    if (!file) return;
    if (file.size > 500000)
      throw Error("500KB 이하의 텍스트 파일을 선택해 주세요.");
    draft.content = await file.text();
    $("#draft-content").value = draft.content;
    saveDraft();
    invalidatePreview();
    toast("파일을 불러왔어요. 문제 확인하기를 눌러 주세요.");
  });
  on("#clear-draft", "click", async () => {
    if (
      await confirmAction(
        state.editId
          ? "수정을 취소할까요?"
          : "이 기기에 임시 저장된 문제를 비울까요?",
      )
    ) {
      draft = {};
      state.editId = null;
      state.preview = null;
      storage.remove("quiz.draft");
      renderAuthor();
    }
  });
  on("#preview-button", "click", (e) =>
    busy(e.target, async () => {
      if (!draft.title?.trim() || !draft.category?.trim())
        throw Error("학습 세트 이름과 분야를 입력해 주세요.");
      const signature = draftSignature();
      const preview = await api("/preview", {
        method: "POST",
        body: draftPayload(),
      });
      if (signature !== draftSignature()) {
        toast("입력 내용이 바뀌었어요. 문제 확인하기를 다시 눌러 주세요.");
        return;
      }
      state.preview = { ...preview, signature };
      state.previewIndex = 0;
      if (state.page === "author") {
        renderPreview();
        if (window.innerWidth < 600)
          $("#preview-panel").scrollIntoView({
            behavior: "smooth",
            block: "start",
          });
      }
    }),
  );
  if (state.preview) renderPreview();
}
function buildPrompt() {
  return `${draft.topic?.trim() ? `출제 주제: ${draft.topic.trim()}\n` : ""}${draft.extra?.trim() ? `추가 요청: ${draft.extra.trim()}\n` : ""}\n${template.replace("10문제", `${Number(draft.count) || 10}문제`)}`;
}
function updatePrompt() {
  const el = $("#prompt-text");
  if (el) el.value = buildPrompt();
}
function renderPreview() {
  const p = state.preview,
    area = $("#preview-area");
  if (!p || !area) return;
  const questions = p.questions || [],
    q = questions[state.previewIndex];
  area.innerHTML =
    (p.errors || []).map((e) => notice(e, "error")).join("") +
    (q
      ? `<div class="preview-pagination"><button class="secondary" id="preview-prev" ${state.previewIndex === 0 ? "disabled" : ""}>← 이전</button><span>${state.previewIndex + 1} / ${questions.length}문제</span><button class="secondary" id="preview-next" ${state.previewIndex === questions.length - 1 ? "disabled" : ""}>다음 →</button></div>${q.p ? `<div class="passage">${esc(q.p)}</div>` : ""}<h3 class="question-text">${esc(q.q)}</h3>${q.o[0] === "주관식" ? '<span class="badge">주관식</span>' : q.o.map((o, i) => `<p style="font-size:13px">${i + 1}. ${esc(o)}</p>`).join("")}<div class="preview-answer"><strong>정답: ${esc(q.o[0] === "주관식" ? q.a : q.o[q.a])}</strong><br>${esc(q.e)}</div>`
      : "") +
    (p.valid
      ? `<div style="margin-top:24px">${notice(`${questions.length}문제의 형식을 확인했어요. 정답과 해설이 맞는지 살펴본 뒤 등록해 주세요.`)}${!state.admin ? '<button id="preview-login" class="secondary full">관리자 로그인</button><p class="field-hint">로그인 후에도 입력한 내용은 유지됩니다.</p>' : ""}<button id="save-quiz" class="primary full" ${!state.admin ? "disabled" : ""}>${state.editId ? "수정 내용 저장" : `${questions.length}문제 등록하기`}</button></div>`
      : notice("표시된 오류를 원문에서 수정하고 다시 확인해 주세요.", "warn"));
  on("#preview-prev", "click", () => {
    state.previewIndex--;
    renderPreview();
  });
  on("#preview-next", "click", () => {
    state.previewIndex++;
    renderPreview();
  });
  on("#preview-login", "click", adminAction);
  on("#save-quiz", "click", (e) =>
    busy(e.target, async () => {
      if (state.preview?.signature !== draftSignature())
        throw Error(
          "입력 내용이 바뀌었어요. 문제 확인하기를 다시 눌러 주세요.",
        );
      const signature = draftSignature(),
        editId = state.editId;
      await api(editId ? `/quizzes/${editId}` : "/quizzes", {
        method: editId ? "PATCH" : "POST",
        body: draftPayload(),
      });
      if (signature === draftSignature()) {
        draft = {};
        state.preview = null;
        state.editId = null;
        storage.remove("quiz.draft");
      }
      try {
        await bootstrap();
      } catch {
        toast("문제는 저장됐지만 목록을 갱신하지 못했어요. 새로고침해 주세요.");
      }
      if (state.page === "author") renderAuthor();
      toast("학습 세트를 저장했어요. 문제 풀기에서 바로 시작할 수 있습니다.");
    }),
  );
}
function renderMore() {
  main.innerHTML =
    heading(
      "YOUR SPACE",
      "함께 배우는 공간",
      "기록을 나누고, 서로의 성장을 응원해요.",
    ) +
    `<div class="more-grid">${moreNavs.map(([id, title]) => `<a href="#${id}" class="more-card">${icon(id)}<div><strong>${title}</strong><small>${{ leaderboard: "주제별 우수 성취 기록", participation: "학습 세트별 참여 여부", chat: "질문과 배움 나누기", admin: "문제·설정·백업 관리" }[id]}</small></div></a>`).join("")}</div>`;
}
function userGate() {
  main.innerHTML = empty(
    "이름을 먼저 알려 주세요",
    "문제를 풀 때 사용한 이름으로 오답과 학습 기록을 찾아드릴게요.",
    '<button id="set-user" class="primary">학습자 이름 설정</button>',
  );
  on("#set-user", "click", () => requireUser(route));
}
const elapsed = (s) =>
  Number(s) >= 60
    ? `${Math.floor(Number(s) / 60)}분 ${Math.round(Number(s) % 60)}초`
    : `${Math.round(Number(s) || 0)}초`;
function recordRows(records) {
  return records
    .map(
      (r) =>
        `<article class="record-row"><div><h3>${esc(r.quiz)}</h3><p>${esc(r.user)} · ${esc(r.date)} · ${elapsed(r.duration)}</p></div><strong class="record-score">${esc(r.score)}<small>점</small></strong></article>`,
    )
    .join("");
}
async function renderRecords(rev) {
  if (!state.user) {
    userGate();
    return;
  }
  const { records } = await api(
    `/results?user=${encodeURIComponent(state.user)}`,
  );
  if (rev !== state.revision) return;
  const average = records.length
    ? Math.round(
        records.reduce((s, r) => s + Number(r.score), 0) / records.length,
      )
    : 0;
  main.innerHTML =
    heading(
      "LEARNING JOURNAL",
      `${state.user} 님의 학습 기록`,
      "한 번의 점수보다, 꾸준히 쌓이는 과정이 중요해요.",
    ) +
    `<div class="metrics"><div class="metric"><span>완료한 학습</span><strong>${records.length}<small>회</small></strong></div><div class="metric"><span>평균 점수</span><strong>${average}<small>점</small></strong></div><div class="metric"><span>학습한 세트</span><strong>${new Set(records.map((r) => r.quiz)).size}<small>개</small></strong></div></div><div class="section-heading"><h2>최근 학습</h2><a class="quiet" href="#review">오답 복습하기 →</a></div><div class="record-list">${records.length ? recordRows(records) : empty("첫 번째 기록을 만들어 볼까요?", "학습 세트를 풀고 제출하면 여기에 기록이 쌓여요.", '<a href="#learn" class="primary">문제 풀러 가기</a>')}</div>`;
}
async function renderLeaderboard(rev) {
  const { records, season_start, top_count } = await api("/leaderboard");
  if (rev !== state.revision) return;
  main.innerHTML =
    heading(
      "GROW TOGETHER",
      "서로의 성장을 응원해요",
      `학습 세트별 상위 ${top_count || 3}명의 기록${season_start ? " · " + season_start.slice(0, 10) + "부터" : ""}입니다.`,
    ) +
    `<label>학습 세트 선택<select id="rank-filter"><option value="">전체 학습 세트</option>${[...new Set(records.map((r) => r.quiz))].map((q) => `<option>${esc(q)}</option>`).join("")}</select></label><div id="rank-list" class="record-list"></div>`;
  const draw = () => {
    const filtered = records.filter(
      (r) => !$("#rank-filter").value || r.quiz === $("#rank-filter").value,
    );
    $("#rank-list").innerHTML = filtered.length
      ? recordRows(filtered)
      : empty("아직 성취 기록이 없어요", "문제를 풀고 첫 기록을 남겨 보세요.");
  };
  on("#rank-filter", "change", draw);
  draw();
}
async function renderParticipation(rev) {
  const filters = (state.participationFilters ||= {
    category: "",
    exclude_guest: true,
    hide_empty: true,
    only_participants: true,
  });
  const initial = await api(`/participation?${new URLSearchParams(filters)}`);
  if (rev !== state.revision) return;
  main.innerHTML =
    heading(
      "LEARNING TOGETHER",
      "함께하는 학습 현황",
      "선택한 퀴즈 그룹에서 실제로 풀이를 제출한 사람을 확인하세요.",
    ) +
    `<section class="panel participation-filters" aria-label="참여 현황 필터">
      <label>퀴즈 그룹 선택<select id="participation-category"><option value="">전체 퀴즈</option>${initial.categories.map((category) => `<option value="${esc(category)}" ${filters.category === category ? "selected" : ""}>${esc(category)}</option>`).join("")}</select></label>
      <div class="participation-checks">
        <label class="inline-label"><input type="checkbox" id="participation-guest" ${filters.exclude_guest ? "checked" : ""}>Guest 제외</label>
        <label class="inline-label"><input type="checkbox" id="participation-empty" ${filters.hide_empty ? "checked" : ""}>모두 미참여인 퀴즈 제외</label>
        <label class="inline-label"><input type="checkbox" id="participation-users" ${filters.only_participants ? "checked" : ""}>참여자만 표시</label>
      </div><p class="field-hint">‘참여자만 표시’를 끄면 등록만 했거나 선택한 그룹을 아직 풀지 않은 사람도 볼 수 있어요. 0점 제출도 참여로 인정하며, 이름에 test가 포함된 기록은 항상 제외합니다.</p>
    </section><div id="participation-results" aria-live="polite"></div>`;
  const draw = (data) => {
    const target = $("#participation-results");
    if (!target) return;
    target.innerHTML =
      !data.rows.length || !data.quizzes.length
        ? empty(
            "선택한 조건에 맞는 참여 기록이 없어요",
            "위의 퀴즈 그룹이나 표시 조건을 바꿔 보세요.",
          )
        : `<section class="panel"><p class="field-hint">${data.rows.length}명 · ${data.quizzes.length}개 퀴즈 · 가로로 밀어서 다른 학습 세트도 확인할 수 있어요.</p><div class="table-wrap" tabindex="0" role="region" aria-label="학습 참여 현황"><table><thead><tr><th>학습자</th>${data.quizzes.map((q) => `<th>${esc(q)}</th>`).join("")}</tr></thead><tbody>${data.rows.map((r) => `<tr><th>${esc(r.user)}</th>${data.quizzes.map((q) => `<td>${r.completed.includes(q) ? `<span class="badge">${state.admin && r.scores?.[q] !== undefined ? `${esc(r.scores[q])}점` : "완료"}</span>` : "—"}</td>`).join("")}</tr>`).join("")}</tbody></table></div></section>`;
  };
  let requestId = 0;
  const refresh = async () => {
    const current = ++requestId;
    filters.category = $("#participation-category").value;
    filters.exclude_guest = $("#participation-guest").checked;
    filters.hide_empty = $("#participation-empty").checked;
    filters.only_participants = $("#participation-users").checked;
    $("#participation-results").innerHTML =
      '<div class="loading" role="status"><span class="spinner"></span>표시 조건을 적용하고 있어요.</div>';
    try {
      const data = await api(`/participation?${new URLSearchParams(filters)}`);
      if (rev === state.revision && current === requestId) draw(data);
    } catch (error) {
      if (rev === state.revision && current === requestId)
        $("#participation-results").innerHTML = notice(error.message, "error");
    }
  };
  ["category", "guest", "empty", "users"].forEach((key) =>
    on(`#participation-${key}`, "change", refresh),
  );
  draw(initial);
}
async function renderWrongs(rev) {
  if (!state.user) {
    userGate();
    return;
  }
  const { items } = await api(`/wrongs?user=${encodeURIComponent(state.user)}`);
  if (rev !== state.revision) return;
  main.innerHTML =
    heading(
      "TRY ONCE MORE",
      "틀렸던 문제, 오늘은 내 것으로.",
      "한 문제씩 다시 풀며 헷갈렸던 개념을 정리해요.",
    ) + `<div id="wrong-area"></div>`;
  let index = 0,
    pending = false;
  const draw = () => {
    const item = items[index];
    if (!item) {
      $("#wrong-area").innerHTML = empty(
        "복습할 문제를 모두 마쳤어요",
        "새로운 학습 세트에 도전해 보세요.",
        '<a href="#learn" class="primary">문제 풀러 가기</a>',
      );
      return;
    }
    $("#wrong-area").innerHTML =
      `<div class="narrow"><div class="preview-pagination"><button id="wrong-prev" class="secondary" ${index === 0 ? "disabled" : ""}>← 이전</button><span>${index + 1} / ${items.length}문제</span><button id="wrong-next" class="secondary" ${index === items.length - 1 ? "disabled" : ""}>다음 →</button></div><section class="panel"><p class="eyebrow">${esc(item.quiz)}</p>${item.passage ? `<div class="passage">${esc(item.passage)}</div>` : ""}<h2 class="question-text">${esc(item.question)}</h2>${item.orphan ? notice("원래 문제가 수정되거나 삭제되어 자동 채점할 수 없어요. 내용을 확인했다면 목록에서 정리할 수 있습니다.", "warn") : `<form id="wrong-form">${item.options.length === 1 && item.options[0] === "주관식" ? '<label>나의 답<input name="answer" required autocomplete="off"></label>' : `<div class="option-list">${item.options.map((o, i) => `<label class="option"><input type="radio" name="answer" required value="${esc(o)}"><span>${i + 1}. ${esc(o)}</span></label>`).join("")}</div>`}<button class="primary full" style="margin-top:22px">정답 확인</button></form>`}<div id="wrong-feedback"></div>${item.orphan ? '<button id="archive-wrong" class="secondary full">확인했어요 · 목록에서 정리</button>' : ""}</section></div>`;
    on("#wrong-prev", "click", () => {
      if (!pending) {
        index--;
        draw();
      }
    });
    on("#wrong-next", "click", () => {
      if (!pending) {
        index++;
        draw();
      }
    });
    const lockNavigation = (value) => {
      pending = value;
      const prev = $("#wrong-prev"),
        next = $("#wrong-next");
      if (prev) prev.disabled = value || index === 0;
      if (next) next.disabled = value || index === items.length - 1;
    };
    const removeCurrent = () => {
      const position = items.findIndex((row) => row.id === item.id);
      if (position >= 0) items.splice(position, 1);
      index = Math.min(index, Math.max(0, items.length - 1));
      draw();
    };
    on("#archive-wrong", "click", (e) =>
      busy(e.target, async () => {
        lockNavigation(true);
        try {
          await api(`/wrongs/${item.id}/archive`, {
            method: "POST",
            body: { user: state.user },
          });
          if (rev === state.revision) removeCurrent();
        } finally {
          if (rev === state.revision) lockNavigation(false);
        }
      }),
    );
    on("#wrong-form", "submit", async (e) => {
      e.preventDefault();
      await busy($("button", e.target), async () => {
        lockNavigation(true);
        let result;
        try {
          result = await api(`/wrongs/${item.id}/answer`, {
            method: "POST",
            body: {
              user: state.user,
              answer: new FormData(e.target).get("answer"),
            },
          });
        } finally {
          if (rev === state.revision) lockNavigation(false);
        }
        if (rev !== state.revision) return;
        $("#wrong-feedback").innerHTML =
          `<div style="margin-top:20px">${notice(result.correct ? "정답이에요! 오답 노트에서 완료 처리했어요." : "아쉽지만 다시 확인해 볼까요?", result.correct ? "" : "warn")}<div class="answer-detail"><p><strong>정답: ${esc(result.correct_answer)}</strong></p><p>${esc(result.explanation)}</p></div>${result.correct ? '<button id="next-wrong-done" class="primary full" style="margin-top:16px">계속 복습하기 →</button>' : ""}</div>`;
        if (result.correct) {
          $("#wrong-form").hidden = true;
          on("#next-wrong-done", "click", removeCurrent);
        }
      });
    });
  };
  draw();
}
async function renderChat(rev) {
  const data = await api("/chat");
  if (rev !== state.revision) return;
  main.innerHTML =
    heading(
      "SHARE & LEARN",
      "배움을 나누는 이야기방",
      "궁금한 점이나 도움이 된 내용을 함께 나눠 보세요.",
    ) +
    `<div class="narrow"><section class="panel"><div class="chat-list" id="chat-list">${data.messages.length ? data.messages.map((m) => `<article class="chat-bubble ${m.user === state.user ? "mine" : ""}"><strong>${esc(m.user)}</strong><time>${esc(m.time)}</time><p>${esc(m.message)}</p></article>`).join("") : '<p class="muted">아직 이야기가 없어요. 첫 인사를 남겨 보세요.</p>'}</div><form id="chat-form"><label style="margin-top:24px">${esc(state.user || "학습자 이름을 먼저 설정해 주세요")}<textarea id="chat-message" maxlength="2000" required placeholder="함께 나누고 싶은 이야기를 적어 주세요." style="min-height:90px"></textarea></label><div class="actions"><button class="primary">이야기 남기기</button></div></form></section></div>`;
  $("#chat-list").scrollTop = $("#chat-list").scrollHeight;
  on("#chat-form", "submit", async (e) => {
    e.preventDefault();
    const message = $("#chat-message").value.trim();
    if (!message) return;
    requireUser(() =>
      busy($("button", e.target), async () => {
        await api("/chat", {
          method: "POST",
          body: { user: state.user, message },
        });
        await route();
      }).catch((error) => toast(error.message)),
    );
  });
}
async function renderAdmin(rev) {
  if (!state.admin) {
    main.innerHTML =
      heading(
        "MANAGE YOUR SPACE",
        "학습 공간 관리",
        "문제와 운영 설정을 관리할 수 있습니다.",
      ) +
      empty(
        "관리자 인증이 필요해요",
        "설정한 관리자 비밀번호로 로그인해 주세요.",
        '<button class="primary" id="admin-login-page">관리자 로그인</button>',
      );
    on("#admin-login-page", "click", adminAction);
    return;
  }
  main.innerHTML =
    heading(
      "MANAGE YOUR SPACE",
      "학습 공간 관리",
      "기존 문제와 기록은 Google Sheets에 보관됩니다.",
      '<button id="logout-page" class="secondary">로그아웃</button>',
    ) +
    `<div class="filters admin-tabs"><button class="chip active" data-admin-tab="quizzes">문제 관리</button><button class="chip" data-admin-tab="settings">운영 설정</button><button class="chip" data-admin-tab="backups">백업·복구</button></div><div id="admin-area"></div>`;
  on("#logout-page", "click", adminAction);
  $$("[data-admin-tab]").forEach((el) =>
    on(el, "click", async () => {
      $$("[data-admin-tab]").forEach((x) =>
        x.classList.toggle("active", x === el),
      );
      await drawAdminTab(el.dataset.adminTab);
    }),
  );
  await drawAdminTab("quizzes");
}
async function drawAdminTab(tab) {
  const area = $("#admin-area");
  if (!area) return;
  if (tab === "quizzes") {
    area.innerHTML = `<section class="panel"><div class="panel-heading"><h2>학습 세트 ${state.quizzes.length}개</h2><a href="#author" class="primary">새 문제 만들기</a></div>${state.quizzes.map((q) => `<div class="admin-quiz-row"><div><strong>${esc(q.title)}</strong><p class="field-hint" style="margin:4px 0 0">${esc(q.category)} · ${q.count}문제</p></div><div class="actions"><button class="secondary" data-edit="${q.id}">수정</button><button class="danger" data-delete="${q.id}">삭제</button></div></div>`).join("")}</section>`;
    $$("[data-edit]").forEach((el) =>
      on(el, "click", (e) =>
        busy(e.target, async () => {
          if (
            draft.content &&
            !(await confirmAction(
              "작성 중인 임시 문제가 있습니다. 선택한 문제로 바꿀까요?",
            ))
          )
            return;
          const data = await api(`/quizzes/${el.dataset.edit}/edit`);
          draft = { ...data };
          state.editId = el.dataset.edit;
          state.preview = null;
          saveDraft();
          location.hash = "author";
        }),
      ),
    );
    $$("[data-delete]").forEach((el) =>
      on(el, "click", async () => {
        const quiz = state.quizzes.find((q) => q.id === el.dataset.delete);
        if (
          await confirmAction(
            `‘${quiz.title}’ 학습 세트를 삭제할까요? 학습 기록은 남지만 해당 문제는 더 이상 풀 수 없습니다.`,
          )
        ) {
          await busy(el, () =>
            api(`/quizzes/${el.dataset.delete}`, { method: "DELETE" }),
          );
          await bootstrap();
          await drawAdminTab("quizzes");
          toast("학습 세트를 삭제했어요.");
        }
      }),
    );
  } else if (tab === "settings") {
    const { settings } = await api("/admin/settings");
    if (!area.isConnected) return;
    area.innerHTML = `<section class="panel"><h2>운영 설정</h2><p class="muted">기존 저장소에 있는 설정 값을 관리합니다.</p><form id="settings-form">${
      Object.entries(settings)
        .map(([k, v]) => {
          const labels = {
            default_view: "처음 열리는 메뉴",
            default_category: "기본 선택 분야",
            custom_categories: "추가 분야 (쉼표로 구분)",
            season_start: "순위 집계 시작일",
            top_achievers_count: "학습 세트별 순위 표시 인원",
          };
          return `<label>${labels[k] || esc(k)}${
            k === "default_view"
              ? `<select data-setting="${k}">${[
                  ["역량 점검", "문제 풀기"],
                  ["오답 정복", "오답 노트"],
                  ["개인 기록", "학습 기록"],
                  ["우수 성취자", "성취 순위"],
                  ["토론방", "이야기 나누기"],
                  ["참여현황", "참여 현황"],
                ]
                  .map(
                    ([id, label]) =>
                      `<option value="${id}" ${id === v ? "selected" : ""}>${label}</option>`,
                  )
                  .join("")}</select>`
              : `<input data-setting="${esc(k)}" ${k === "top_achievers_count" ? 'type="number" min="1" max="1000"' : ""} ${k === "season_start" ? 'placeholder="2026-09-30"' : ""} value="${esc(v)}">`
          }</label>`;
        })
        .join("") || '<p class="muted">저장된 운영 설정이 없습니다.</p>'
    }<button class="primary" ${Object.keys(settings).length ? "" : "disabled"}>설정 저장</button></form></section>`;
    on("#settings-form", "submit", (e) => {
      e.preventDefault();
      return busy($("button", e.target), async () => {
        const next = {};
        $$("[data-setting]").forEach(
          (el) => (next[el.dataset.setting] = el.value),
        );
        await api("/admin/settings", {
          method: "PUT",
          body: { settings: next },
        });
        await bootstrap();
        toast("설정을 저장했어요. 기본 메뉴·분야는 다음 접속부터 적용됩니다.");
      });
    });
  } else {
    area.innerHTML = `<section class="panel"><h2>백업 만들기</h2><p class="muted">연결된 백업 서비스에 현재 자료의 복사본을 만듭니다.</p><form id="backup-form"><label>백업 이름<input id="backup-name" required maxlength="100" value="학습백업_${new Date().toISOString().slice(0, 10)}"></label><button class="primary">백업 만들기</button></form></section><section class="panel"><h2>백업에서 복구</h2>${notice("복구하면 현재 Google Sheets의 데이터가 선택한 백업 내용으로 바뀝니다. 먼저 현재 자료를 백업해 주세요.", "warn")}<button id="load-backups" class="secondary">백업 목록 불러오기</button><div id="backup-list"></div></section>`;
    on("#backup-form", "submit", (e) => {
      e.preventDefault();
      return busy($("button", e.target), async () => {
        const data = await api("/admin/backups", {
          method: "POST",
          body: { name: $("#backup-name").value.trim() },
        });
        toast(data.message || "백업을 만들었어요.");
      });
    });
    on("#load-backups", "click", (e) =>
      busy(e.target, async () => {
        const { files } = await api("/admin/backups");
        $("#backup-list").innerHTML = files.length
          ? `<form id="restore-form"><label style="margin-top:20px">복구할 백업<select id="restore-file">${files.map((f) => `<option>${esc(f)}</option>`).join("")}</select></label><label>복구할 백업 이름을 한 번 더 입력<input id="restore-confirm" required autocomplete="off"></label><button class="danger">이 백업으로 복구</button></form>`
          : '<p class="muted" style="margin-top:20px">사용 가능한 백업이 없습니다.</p>';
        on("#restore-form", "submit", async (e) => {
          e.preventDefault();
          const name = $("#restore-file").value,
            confirmation = $("#restore-confirm").value;
          if (name !== confirmation)
            throw Error("백업 이름을 정확히 입력해 주세요.");
          if (
            !(await confirmAction(
              "현재 데이터가 선택한 백업으로 바뀝니다. 복구할까요?",
            ))
          )
            return;
          await busy($("button", e.target), async () => {
            await api("/admin/restore", {
              method: "POST",
              body: { name, confirmation },
            });
            await bootstrap();
            toast("백업을 복구했어요.");
          });
        });
      }),
    );
  }
}
updateProfile();
renderNav();
bootstrap()
  .then(route)
  .catch((error) => {
    state.connectionMessage = error.message;
    route();
  });
