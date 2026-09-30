"""Pure quiz parsing and deterministic grading, without network calls."""
import re

def natural_sort_key(s):
    """문자열 내의 숫자를 숫자로 인식하여 정렬 (퀴즈2 < 퀴즈11)"""
    return [int(text) if text.isdigit() else text.lower()
            for text in re.split('([0-9]+)', str(s))]


def clean_text(text):
    if not text: return ""
    text = text.replace(r"^{\circ}", "°").replace(r"^\circ", "°").replace(r"\circ", "°")
    text = text.replace("`", "").replace(r"\$", "$")
    text = text.replace(r"\(", "$").replace(r"\)", "$")
    text = text.replace(r"\[", "$$").replace(r"\]", "$$")
    text = text.replace("**", "").strip()
    return text

def check_subjective_answer(user_ans, correct_ans_raw):
    """Deterministic local grading. Separate accepted alternatives with |."""
    import unicodedata

    def normalize(value):
        text = re.sub(r"\s+", "", unicodedata.normalize("NFKC", str(value))).casefold()
        return {"참": "true", "거짓": "false", "1": "true", "0": "false"}.get(text, text)

    if user_ans is None or not str(user_ans).strip():
        return False
    raw = str(correct_ans_raw).strip()
    candidates = [part.strip() for part in raw.split("|") if part.strip()]
    # Preserve old word aliases, but never split fractions or function arguments.
    if "|" not in raw and re.fullmatch(r"[A-Za-z가-힣 ]+(?:/[A-Za-z가-힣 ]+)+", raw):
        candidates.extend(raw.split("/"))
    return any(normalize(user_ans) == normalize(answer) for answer in candidates)


def validate_quiz_text(text):
    """Parse pasted Q/O/A/K/E text and report every malformed question."""
    text = re.sub(r"(?m)^\s*```[^\n]*$", "", str(text or "")).strip()
    markers = list(re.finditer(r"\[Q\s*\d*\]", text, re.I))
    if not markers:
        return [], ["[Q1]로 시작하는 문제를 찾지 못했습니다. 요청문의 형식을 확인해 주세요."]
    parsed, errors = [], []
    for index, marker in enumerate(markers):
        chunk = text[marker.end():markers[index + 1].start() if index + 1 < len(markers) else len(text)]
        fields = {}
        tags = list(re.finditer(r"\[(O|A|K|E)\]", chunk, re.I))
        question = chunk[:tags[0].start()].strip() if tags else chunk.strip()
        for i, tag in enumerate(tags):
            fields[tag.group(1).upper()] = chunk[tag.end():tags[i + 1].start() if i + 1 < len(tags) else len(chunk)].strip()
        problem = None
        if not question or not fields.get("O") or not fields.get("A"):
            problem = "질문, [O] 보기, [A] 정답이 모두 필요합니다."
        passage = re.search(r"<지문>(.*?)</지문>", question, re.S)
        question_text = clean_text(re.sub(r"<지문>.*?</지문>", "", question, flags=re.S))
        options, answer = [], None
        if not problem and "주관식" in fields["O"]:
            options, answer = ["주관식"], clean_text(fields["A"])
        elif not problem:
            raw_options = fields["O"]
            symbols = list(re.finditer(r"[①-⑤]", raw_options))
            if symbols:
                numbers = ["①②③④⑤".index(match.group()) + 1 for match in symbols]
                options = [clean_text(raw_options[m.end():symbols[i+1].start() if i+1 < len(symbols) else len(raw_options)]) for i, m in enumerate(symbols)]
            else:
                symbols = list(re.finditer(r"(?:^|\n)\s*([1-5])[.)]\s*", raw_options))
                numbers = [int(m.group(1)) for m in symbols]
                options = [clean_text(raw_options[m.end():symbols[i+1].start() if i+1 < len(symbols) else len(raw_options)]) for i, m in enumerate(symbols)]
            raw_answer = clean_text(fields["A"])
            match = re.fullmatch(r"([①-⑤1-5])(?:번)?(?:[.)])?(?:\s+.*)?", raw_answer)
            if match:
                token = match.group(1)
                number = "①②③④⑤".index(token) + 1 if token in "①②③④⑤" else int(token)
                answer = numbers.index(number) if number in numbers else None
            elif raw_answer in options:
                answer = options.index(raw_answer)
            if len(options) < 2 or not all(options) or numbers != list(range(1, len(options)+1)):
                problem = "객관식 보기는 ①부터 순서대로 2~5개 입력해 주세요."
            elif answer is None:
                problem = "정답 번호가 보기와 일치하지 않습니다."
        if not question_text:
            problem = "지문 외에 질문을 입력해 주세요."
        if problem:
            errors.append(f"{index + 1}번 문제: {problem}")
            continue
        parsed.append({"p": clean_text(passage.group(1)) if passage else "", "q": question_text,
                       "o": options, "a": answer, "k": clean_text(fields.get("K", "")),
                       "e": clean_text(fields.get("E", "제공된 해설이 없습니다."))})
    return parsed, errors


def robust_parse(text):
    return validate_quiz_text(text)[0]
