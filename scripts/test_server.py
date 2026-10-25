"""A fresh, disposable browser-test server. Never reads the real app database."""
import tempfile
from pathlib import Path

import uvicorn

from backend.app import create_app


with tempfile.TemporaryDirectory(prefix="yeobaek-e2e-") as directory:
    from backend.ai import Proposal
    app = create_app(Path(directory) / "test.sqlite3")
    # Only this isolated browser-test server uses a simulated external AI response.
    def simulated_proposal(history):
        if len(history) == 1:
            return Proposal(reply="주말 중 어느 날인가요?", questions=[{"prompt":"식사 날짜를 골라 주세요", "options":["토요일", "일요일", "미정으로 두기"]}, {"prompt":"시간을 골라 주세요", "options":["오후 6시", "시간 미정"]}, {"prompt":"장소를 골라 주세요", "options":["집", "장소 미정"]}])
        return Proposal(reply="아직 저장하지 않았습니다. 확인해 주세요.", items=[{"title":"친구와 저녁 식사", "kind":"일정", "planned_date":"2026-10-31"}])
    app.state.chatgpt.propose = simulated_proposal
    from types import SimpleNamespace
    codex_creates=[]
    def simulated_codex(args,text=None,timeout=30):
        if args==['login','status']:return SimpleNamespace(returncode=0,stdout='',stderr='Logged in using ChatGPT')
        if args[:2]==['cloud','list']:return SimpleNamespace(returncode=0,stdout='{"tasks": []}',stderr='')
        if args[:2]==['cloud','exec']:
            codex_creates.append(text)
            return SimpleNamespace(returncode=0,stdout='https://chatgpt.com/codex/tasks/task_browser_test',stderr='')
        if args[:2]==['cloud','status']:return SimpleNamespace(returncode=0,stdout='[READY] test review',stderr='')
        raise RuntimeError('unexpected test command')
    app.state.delivery.run=simulated_codex
    @app.get('/test/codex-creates')
    def creates():return {'count':len(codex_creates)}
    uvicorn.run(app, host="127.0.0.1", port=8011, proxy_headers=False, access_log=False)
