"use strict";
self.addEventListener("install", (event) =>
  event.waitUntil(self.skipWaiting()),
);
self.addEventListener("activate", (event) =>
  event.waitUntil(self.clients.claim()),
);
// Always use the live server; no quizzes, identities, admin pages or API results
// are saved in a service-worker cache. Only navigation gets an offline message.
self.addEventListener("fetch", (event) => {
  if (event.request.mode !== "navigate") return;
  event.respondWith(
    fetch(event.request).catch(
      () =>
        new Response(
          `<!doctype html><html lang="ko"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>연결을 확인해 주세요</title><body style="font-family:system-ui;padding:40px 24px;color:#173e38;background:#f5f8f3"><h1>연결을 확인해 주세요</h1><p>인터넷 연결과 교육 서버 실행 상태를 확인한 뒤 다시 접속해 주세요.</p><p><a href="/">다시 연결하기</a></p></body></html>`,
          {
            status: 503,
            headers: {
              "Content-Type": "text/html; charset=utf-8",
              "Cache-Control": "no-store",
            },
          },
        ),
    ),
  );
});
