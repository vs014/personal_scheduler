"""Local developer handoff. Never contacts an external service or executes feedback text."""
import argparse
import os
import sqlite3
from pathlib import Path

from .app import ROOT, now
from .models import FeedbackUpdate
from .storage import Store, new_id


def backup(source: Path, destination: Path):
    if not source.is_file():
        raise ValueError("원본 DB가 없습니다.")
    destination.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    fd = os.open(destination, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    os.close(fd)
    try:
        with sqlite3.connect(f"file:{source}?mode=ro", uri=True) as src, sqlite3.connect(destination) as dst:
            src.backup(dst)
            if dst.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
                raise ValueError("백업 무결성 검사 실패")
    except Exception:
        destination.unlink(missing_ok=True)
        raise


def run(argv=None):
    parser = argparse.ArgumentParser(description="피드백 개발 기록과 안전한 DB 백업")
    parser.add_argument("--db", type=Path, default=Path(os.getenv("SCHEDULER_DB", str(ROOT / ".data/scheduler.sqlite3"))))
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("list")
    reply = commands.add_parser("reply")
    reply.add_argument("thread_id")
    reply.add_argument("--file", type=Path, required=True)
    status = commands.add_parser("status")
    status.add_argument("thread_id")
    status.add_argument("--status", required=True)
    status.add_argument("--version", default="")
    status.add_argument("--file", type=Path, required=True)
    export = commands.add_parser("backup")
    export.add_argument("destination", type=Path)
    args = parser.parse_args(argv)
    if not args.db.is_file():
        parser.error("DB가 없습니다. 올바른 서버의 SCHEDULER_DB를 확인하세요.")
    if args.command == "backup":
        backup(args.db, args.destination)
        print("백업 완료 · SQLite 무결성 검사 통과. 개인정보를 포함한 파일이므로 안전하게 보관하세요.")
        return
    store = Store(args.db)
    with store.connect() as db:
        if args.command == "list":
            for row in db.execute("SELECT id,kind,status,title FROM threads ORDER BY updated_at DESC"):
                print(f"{row['id']} | {row['kind']} | {row['status']} | {row['title']}")
            return
        content = args.file.read_text(encoding="utf-8").strip()
        if not content or len(content) > 10000:
            parser.error("기록은 1~10000자여야 합니다.")
        db.execute("BEGIN IMMEDIATE")
        thread = db.execute("SELECT * FROM threads WHERE id=?", (args.thread_id,)).fetchone()
        if not thread:
            parser.error("피드백을 찾을 수 없습니다.")
        stamp = now()
        if args.command == "reply":
            db.execute("INSERT INTO messages VALUES (?,?,?,?,?,?)", (new_id(), args.thread_id, new_id(), "개발 기록", content, stamp))
            db.execute("UPDATE threads SET revision=revision+1,updated_at=? WHERE id=?", (stamp, args.thread_id))
            detail = "개발 답변 기록 · 자동 AI 응답 아님"
        else:
            body = FeedbackUpdate(status=args.status, priority=thread["priority"], resolution=content, release_version=args.version, revision=thread["revision"])
            db.execute("UPDATE threads SET status=?,resolution=?,release_version=?,revision=revision+1,updated_at=? WHERE id=?", (body.status, body.resolution, body.release_version, stamp, args.thread_id))
            detail = f"개발 기록: {thread['status']} → {body.status} · {body.release_version}: {body.resolution}"
        db.execute("INSERT INTO history (thread_id,detail,created_at) VALUES (?,?,?)", (args.thread_id, detail, stamp))
    print("기록했습니다. 앱에서 새로 불러오면 확인할 수 있습니다. 코드 변경·배포는 별도입니다.")


if __name__ == "__main__":
    run()
