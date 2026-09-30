# Responsive web migration

Goal: Run on phones, tablets and desktop browsers without Streamlit or paid AI APIs. Preserve existing Google Sheets quizzes and records.

Architecture: FastAPI same-origin API serves a vanilla JavaScript responsive application. Python retains parsing and grading. Google Sheets remains the existing storage. No answer keys go to the browser before submission. One server worker holds short-lived attempts and admin sessions; retrying a submission uses the same attempt ID.

Tech stack: Python 3.12, FastAPI, Uvicorn, gspread, HTML/CSS/JavaScript. No frontend build service or AI SDK.

Spec: User authorized substantial UI changes, mobile/tablet workflow, removal of paid generation/grading, and replacement of Streamlit. Existing Streamlit improvements are preserved in local commit 143f88c.

Global constraints: Never expose credentials, call AI APIs, or write production sheets from tests. Neutral secrets.toml with temporary legacy config fallback. All writes use RAW. Escape user text. Server validates admin writes. Handle disconnected storage explicitly. Preserve legacy sheet column meanings.

Review focus: server-only grading; authentication; retries; mobile overflow; drafts; no Streamlit runtime dependency.

## Shared API contract
All errors JSON {detail: Korean message}. All endpoints synchronous handlers unless needed; API prefix /api. Quiz ids stable hash of title. Frontend uses fetch same origin.

- GET /bootstrap -> {quizzes:[{id,title,category,count,valid}],admin:boolean,connected:boolean,message:string}
- POST /attempts {quiz_id,user} -> {attempt_id,title,questions:[{p,q,o}],started_at}
- POST /attempts/{id}/submit {answers:[string]} -> {score,duration,correct,total,review:[{question,answer,correct_answer,explanation,correct}],saved:boolean,message:string}. Answers are option text or free text. Retry preserves graded result and attempt id.
- GET /author/template -> {template:string}
- POST /preview {title,category,content} -> {questions:[{p,q,o,a,k,e}],errors:[string],valid:boolean}
- POST /quizzes {title,category,content} -> {message}; admin only
- GET /quizzes/{id}/edit -> {title,category,content}; admin only
- PATCH /quizzes/{id} {title,category,content} -> {message}; admin only, title immutable
- DELETE /quizzes/{id} -> {message}; admin only
- POST /admin/login {password} -> {message}; HttpOnly SameSite strict cookie
- POST /admin/logout -> {message}
- GET /results?user= -> {records:[{quiz,user,score,duration,date}]}
- GET /leaderboard -> {records:[{quiz,user,score,duration,date}]}
- GET /participation -> {quizzes:[string],rows:[{user,completed:[string],scores:object}]}; scores empty for non-admin
- GET /wrongs?user= -> {items:[{id,quiz,question,options:[string],passage,orphan:boolean}]}
- POST /wrongs/{id}/answer {user,answer} -> {correct:boolean,correct_answer,explanation,message}
- POST /wrongs/{id}/archive {user} -> {message}; only orphan
- GET /chat -> {messages:[{user,message,time}]}; POST /chat {user,message} -> {message}
- GET /admin/settings -> {settings:object}; PUT /admin/settings {settings:object}
- GET /admin/backups -> {files:[string]}; POST /admin/backups {name} -> {message}; POST /admin/restore {name,confirmation} requires confirmation equal name.

## Tasks
- [x] Preserve original improvement checkpoint and extract pure quiz_core.py.
- [x] Backend: independent settings/cache/storage/API, fake-store tests for grading/auth/idempotency, requirements.
- [x] Frontend: responsive navigation, quiz runner, prompt/paste preview/registration, local draft persistence, records/review/chat/admin.
- [x] Integrate: configure neutral secrets privately; README and launch scripts; no Streamlit required by active entry point.
- [x] Verify: pure/core/API tests, isolated end-to-end browser fixture, mobile/tablet/desktop screenshots, production read only.

Run: .venv/Scripts/python -X utf8 -m unittest discover -s tests_web -v
Run server: .venv/Scripts/python -m uvicorn web_app:app --host 0.0.0.0 --port 8000 --workers 1

## Verification outcome

2026-09-30: 51 new web tests pass; JavaScript syntax check passes; web entry imports without Streamlit. Independent review identified five P2 issues, all fixed and re-reviewed. Fake browser workflow covered objective/subjective submission, missing-answer blocking, wrong-answer resolution, author copy/preview/login/create/edit, refresh persistence, math rendering, and settings save. Real Google Sheets read-only bootstrap returns13 valid quiz sets. Viewports390,768,1440 have no horizontal document overflow. Windows MIME association issue found in actual elevated server and fixed with regression test. Screenshots saved under ignored artifacts/.

Local production preview: http://127.0.0.1:8000/ . LAN exposure was rejected by automatic approval review; explicit user choice pending. No production quiz/result writes, backup operations or external deployment performed.
