"""Local desktop entry point: own a loopback socket, then open the browser when ready."""
import argparse
import os
import socket
import threading
import webbrowser
from pathlib import Path

import uvicorn

from .app import ROOT, create_app


def bind_socket(preferred_port: int):
    listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        if os.name == "nt":
            listener.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
        try:
            listener.bind(("127.0.0.1", preferred_port))
        except OSError:
            if preferred_port == 0:
                raise
            # Never terminate an unrelated service or open its page.
            listener.bind(("127.0.0.1", 0))
        listener.listen(128)
        return listener
    except BaseException:
        listener.close()
        raise


def open_when_ready(server, url, stop, opener=webbrowser.open):
    while not stop.wait(0.1):
        if server.started:
            print(f"\n여백이 준비되었습니다. 브라우저 주소: {url}", flush=True)
            try:
                if not opener(url):
                    print("브라우저가 열리지 않으면 위 주소를 직접 입력해 주세요.", flush=True)
            except Exception:
                print("브라우저를 열지 못했습니다. 위 주소를 직접 입력해 주세요.", flush=True)
            return


def main(argv=None):
    parser = argparse.ArgumentParser(description="여백 개인용 데스크톱 실행")
    parser.add_argument("--no-browser", action="store_true", help="검증용: 브라우저 자동 열기 생략")
    parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args(argv)
    if not (ROOT / "web/dist/index.html").is_file():
        raise SystemExit("화면 파일이 없습니다. Windows 실행 묶음을 다시 압축 해제해 주세요.")
    if not 0 <= args.port <= 65535:
        raise SystemExit("포트 번호가 올바르지 않습니다.")
    # The Windows wrapper uses the same path. Direct launches also preserve data outside app files.
    if os.name == "nt" and not os.environ.get("SCHEDULER_DB"):
        local = os.environ.get("LOCALAPPDATA")
        if not local:
            raise SystemExit("Windows 사용자 데이터 폴더를 확인할 수 없습니다.")
        os.environ["SCHEDULER_DB"] = str(Path(local) / "Yeobaek/data/scheduler.sqlite3")
    listener = bind_socket(args.port)
    stop = threading.Event()
    try:
        url = f"http://127.0.0.1:{listener.getsockname()[1]}"
        app = create_app()
        server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=listener.getsockname()[1], proxy_headers=False, access_log=False, log_level="warning"))
        print("여백을 시작합니다. 이 창을 닫으면 앱이 종료됩니다.", flush=True)
        if not args.no_browser:
            threading.Thread(target=open_when_ready, args=(server, url, stop), daemon=True).start()
        else:
            print(f"검증용 서버 주소: {url}", flush=True)
        server.run(sockets=[listener])
    finally:
        stop.set()
        listener.close()


if __name__ == "__main__":
    main()
