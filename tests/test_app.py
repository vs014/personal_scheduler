import json
import secrets
import sqlite3

import pytest
from fastapi.testclient import TestClient

from backend.app import create_app
from backend.feedback import backup, run

HEADERS = {"X-Scheduler-Client": "web"}
PASSWORD = "isolated-test-password-2026"


@pytest.fixture
def database(tmp_path):
    return tmp_path / "test.sqlite3"


@pytest.fixture
def client(database):
    with TestClient(create_app(database), headers=HEADERS) as client:
        assert client.post("/api/setup", json={"password": PASSWORD}).status_code == 200
        yield client


def task(client, **kwargs):
    response = client.post("/api/items", json={"title": "침대 구매하기", "request_id": secrets.token_hex(16), **kwargs})
    assert response.status_code == 200, response.text
    return response.json()


def item_payload(item):
    return {k: v for k, v in item.items() if k not in ("id", "created_at", "updated_at")}


def feedback(client, **kwargs):
    response = client.post("/api/feedback", json={"title": "추천 기능", "kind": "기능 제안", "content": "아침에 할 일 세 개를 추천해 주세요.", "page": "오늘의 여백", "request_id": secrets.token_hex(16), **kwargs})
    assert response.status_code == 200, response.text
    return response.json()


def test_private_routes_and_no_second_registration(client, database):
    outsider = TestClient(create_app(database), headers=HEADERS)
    for path in ("/api/items", "/api/feedback", "/api/docs/overview", "/api/guide"):
        assert outsider.get(path).status_code == 401
    assert outsider.post("/api/feedback-export", json={"ids": ["any"]}).status_code == 401
    assert outsider.post("/api/setup", json={"password": PASSWORD}).status_code == 409
    assert client.get("/api/session").json()["authenticated"]
    login = client.post("/api/login", json={"password": PASSWORD})
    assert "HttpOnly" in login.headers["set-cookie"]
    assert "SameSite=strict" in login.headers["set-cookie"]
    assert client.post("/api/logout", json={}).status_code == 200
    assert client.get("/api/items").status_code == 401
    assert client.post("/api/login", json={"password": PASSWORD}).status_code == 200


def test_nonlocal_setup_denied(database):
    remote = TestClient(create_app(database), client=("203.0.113.5", 50000), headers=HEADERS)
    assert not remote.get("/api/session").json()["local_setup"]
    assert remote.post("/api/setup", json={"password": PASSWORD}).status_code == 403


def test_origin_header_host_and_validation_do_not_leak_password(client):
    assert client.post("/api/logout", headers={"X-Scheduler-Client": ""}, json={}).status_code == 403
    assert client.post("/api/logout", headers={"Origin": "https://attacker.example"}, json={}).status_code == 403
    assert client.get("/api/items", headers={"Host": "attacker.example"}).status_code == 400
    response = client.post("/api/login", json={"password": "private"})
    assert response.status_code == 422
    assert "private" not in response.text
    assert client.get("/api/items").headers["Cache-Control"] == "no-store"


def test_login_throttles_repeated_failures(client):
    for _ in range(10):
        assert client.post("/api/login", json={"password": "incorrect-password"}).status_code == 401
    assert client.post("/api/login", json={"password": PASSWORD}).status_code == 429


def test_task_save_restart_and_today_does_not_change_deadline(client, database):
    first = task(client, deadline="2026-11-20")
    assert first["planned_date"] is None and first["start_time"] is None
    body = {**item_payload(first), "planned_date": "2026-10-25"}
    response = client.put(f"/api/items/{first['id']}", json=body)
    assert response.status_code == 200
    planned = response.json()
    assert planned["deadline"] == "2026-11-20"
    response = client.put(f"/api/items/{first['id']}", json={**item_payload(planned), "planned_date": None})
    assert response.json()["deadline"] == "2026-11-20"
    restarted = TestClient(create_app(database), headers=HEADERS)
    assert restarted.post("/api/login", json={"password": PASSWORD}).status_code == 200
    assert restarted.get("/api/items").json()[0]["title"] == "침대 구매하기"


@pytest.mark.parametrize("title", ["쿠팡에서 섬유유연제 사기", "SK브로드밴드 계약 호실 수정하기", "침대 구매하기"])
def test_examples_require_no_date(client, title):
    saved = task(client, title=title)
    assert saved["title"] == title
    assert saved["planned_date"] is None and saved["deadline"] is None


def test_duplicate_retries_and_edit_conflicts(client):
    request_id = secrets.token_hex(16)
    first = task(client, request_id=request_id)
    retry = task(client, request_id=request_id)
    assert retry["id"] == first["id"]
    assert len(client.get("/api/items").json()) == 1
    assert client.post("/api/items", json={"title": "다른 내용", "request_id": request_id}).status_code == 409
    updated = client.put(f"/api/items/{first['id']}", json={**item_payload(first), "status": "완료"})
    assert updated.status_code == 200
    assert client.put(f"/api/items/{first['id']}", json=item_payload(first)).status_code == 409
    assert client.request("DELETE", f"/api/items/{first['id']}?revision=1", json={}).status_code == 409
    undone = client.put(f"/api/items/{first['id']}", json={**item_payload(updated.json()), "status": "미시작"})
    assert undone.json()["status"] == "미시작"


def test_time_modes_and_detach_preserve_task(client):
    dateless = task(client, kind="일정")
    dateonly = task(client, kind="일정", planned_date="2026-10-25")
    allday = task(client, kind="일정", planned_date="2026-10-25", time_mode="종일")
    timed = task(client, planned_date="2026-10-25", time_mode="시간 확정", start_time="14:00", end_time="15:00", deadline="2026-11-01")
    assert dateless["planned_date"] is None
    assert dateonly["time_mode"] == "미정" and dateonly["start_time"] is None
    assert allday["time_mode"] == "종일" and allday["start_time"] is None
    detached = client.put(f"/api/items/{timed['id']}", json={**item_payload(timed), "planned_date": None, "time_mode": "미정", "start_time": None, "end_time": None}).json()
    assert detached["title"] == timed["title"] and detached["deadline"] == "2026-11-01"
    assert len(client.get("/api/items").json()) == 4


@pytest.mark.parametrize("bad", [
    {"time_mode": "時間"}, {"time_mode": "시간 확정", "start_time": "12:00"},
    {"time_mode": "미정", "start_time": "00:00"}, {"time_mode": "종일"},
    {"planned_date": "2026-10-25", "time_mode": "시간 확정", "start_time": "15:00", "end_time": "14:00"},
    {"planned_date": "2026-10-25", "time_mode": "시간 확정", "start_time": "15:00+05:00"},
    {"title": "   "}, {"planned_date": "2026-02-30"},
])
def test_invalid_input_rejected(client, bad):
    assert client.post("/api/items", json={"title": "검증", "request_id": secrets.token_hex(16), **bad}).status_code == 422
    assert client.get("/api/items").json() == []


def test_feedback_conversation_restart_export_privacy_and_delete(client, database):
    task(client, title="내 비공개 일정")
    thread = feedback(client)
    other = feedback(client, title="내보내지 않을 의견", content="선택하지 않은 비공개 대화")
    assert thread["status"] == "접수"
    assert thread["messages"][1]["role"] == "앱 안내"
    key = secrets.token_hex(16)
    message = {"content": "중요도가 높은 일부터 보고 싶어요.", "request_id": key}
    result = client.post(f"/api/feedback/{thread['id']}/messages", json=message)
    assert result.status_code == 200
    assert len(result.json()["messages"]) == 4
    assert len(client.post(f"/api/feedback/{thread['id']}/messages", json=message).json()["messages"]) == 4
    assert client.post(f"/api/feedback/{other['id']}/messages", json=message).status_code == 409
    restarted = TestClient(create_app(database), headers=HEADERS)
    restarted.post("/api/login", json={"password": PASSWORD})
    export = restarted.post("/api/feedback-export", json={"ids": [thread["id"]]}).json()
    assert len(export["feedback"]) == 1
    assert len(export["feedback"][0]["messages"]) == 4
    encoded = json.dumps(export, ensure_ascii=False)
    assert "내 비공개 일정" not in encoded and "선택하지 않은 비공개 대화" not in encoded
    assert "password" not in encoded and "token" not in encoded
    assert client.request("DELETE", f"/api/feedback/{thread['id']}?revision=2", json={}).status_code == 200
    with sqlite3.connect(database) as db:
        assert db.execute("SELECT count(*) FROM messages WHERE thread_id=?", (thread["id"],)).fetchone()[0] == 0
        assert db.execute("SELECT count(*) FROM history WHERE thread_id=?", (thread["id"],)).fetchone()[0] == 0


def test_feedback_duplicate_and_completion_evidence(client):
    key = secrets.token_hex(16)
    thread = feedback(client, request_id=key)
    assert feedback(client, request_id=key)["id"] == thread["id"]
    body = {"status": "반영 완료", "revision": 1}
    assert client.put(f"/api/feedback/{thread['id']}", json=body).status_code == 422
    response = client.put(f"/api/feedback/{thread['id']}", json={**body, "resolution": "동작 검증 완료", "release_version": "0.2.0"})
    assert response.status_code == 200
    assert response.json()["status"] == "반영 완료"
    assert len(response.json()["history"]) == 2
    assert client.put(f"/api/feedback/{thread['id']}", json={"status": "예정", "revision": 1}).status_code == 409


def test_question_has_no_fake_ai_answer_and_docs_are_available(client):
    thread = feedback(client, kind="질문", content="내일 날씨는?")
    assert "이 피드백 창은 자동 AI 답변을 제공하지 않습니다" in thread["messages"][1]["content"]
    assert client.get("/api/health").json()["ai"] == "미연결"
    assert "오늘 하기와 마감일" in client.get("/api/guide").json()
    assert "사용자용 한 장" in client.get("/api/docs/overview").json()["content"]
    assert "상세 기록" in client.get("/api/docs/development").json()["content"]
    assert client.get("/api/docs/secrets").status_code == 422
    original = client.get("/api/docs-download/original")
    assert original.status_code == 200
    assert "attachment" in original.headers["content-disposition"]


def test_developer_reply_status_and_consistent_backup(client, database, tmp_path):
    thread = feedback(client)
    note = tmp_path / "reply.txt"
    note.write_text("이 변경을 구현하고 검증했습니다.")
    run(["--db", str(database), "reply", thread["id"], "--file", str(note)])
    run(["--db", str(database), "status", thread["id"], "--status", "확인 요청", "--version", "0.2.0", "--file", str(note)])
    recorded = client.get("/api/feedback").json()[0]
    assert recorded["messages"][-1]["role"] == "개발 기록"
    assert recorded["status"] == "확인 요청" and recorded["release_version"] == "0.2.0"
    destination = tmp_path / "backup.sqlite3"
    backup(database, destination)
    with pytest.raises(FileExistsError):
        backup(database, destination)
    restored = TestClient(create_app(destination), headers=HEADERS)
    assert restored.post("/api/login", json={"password": PASSWORD}).status_code == 200
    assert restored.get("/api/feedback").json()[0]["status"] == "확인 요청"
