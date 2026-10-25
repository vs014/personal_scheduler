import json
import os
import queue
import socket
import subprocess
import sys
import threading
import time
from contextlib import contextmanager
from http.cookiejar import CookieJar
from urllib.error import HTTPError, URLError
from urllib.request import HTTPCookieProcessor, ProxyHandler, Request, build_opener

from backend.desktop import bind_socket, open_when_ready


def test_occupied_port_is_left_alone():
    with socket.socket() as occupied:
        occupied.bind(("127.0.0.1", 0))
        occupied.listen()
        original_port = occupied.getsockname()[1]
        with bind_socket(original_port) as chosen:
            assert chosen.getsockname()[0] == "127.0.0.1"
            assert chosen.getsockname()[1] != original_port
            with socket.create_connection(("127.0.0.1", original_port)):
                connection, _ = occupied.accept()
                connection.close()


def test_browser_opens_only_after_startup_and_never_after_failed_start():
    class Server:
        started = False

    server = Server()
    stop = threading.Event()
    opened = threading.Event()
    urls = []

    def opener(url):
        urls.append(url)
        opened.set()
        return True

    thread = threading.Thread(target=open_when_ready, args=(server, "http://127.0.0.1:12345", stop, opener))
    thread.start()
    assert not opened.wait(0.2)
    server.started = True
    assert opened.wait(2)
    thread.join(2)
    assert urls == ["http://127.0.0.1:12345"]

    stop.set()
    open_when_ready(server, "http://127.0.0.1:9999", stop, opener)
    assert len(urls) == 1


@contextmanager
def desktop(db_path):
    environment = {**os.environ, "SCHEDULER_DB": str(db_path), "SCHEDULER_ORIGIN": "", "PYTHONUTF8": "1"}
    process = subprocess.Popen([sys.executable, "-m", "backend.desktop", "--no-browser", "--port", "0"], env=environment, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, encoding="utf-8")
    lines = queue.Queue()
    threading.Thread(target=lambda: [lines.put(line) for line in process.stdout], daemon=True).start()
    client = build_opener(ProxyHandler({}), HTTPCookieProcessor(CookieJar()))
    try:
        url = None
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline:
            line = lines.get(timeout=10)
            if "http://127.0.0.1:" in line:
                url = line[line.index("http://"):].strip()
                break
        assert url
        while time.monotonic() < deadline:
            try:
                with client.open(url + "/api/health", timeout=0.5) as response:
                    assert json.load(response)["status"] == "ok"
                break
            except (URLError, TimeoutError):
                time.sleep(0.05)
        else:
            raise AssertionError("Desktop server did not become ready")

        def request(path, data=None):
            body = None if data is None else json.dumps(data).encode()
            req = Request(url + path, data=body, headers={"Content-Type": "application/json", "X-Scheduler-Client": "web"})
            with client.open(req, timeout=3) as response:
                return json.load(response)

        yield request, client, url
    finally:
        process.terminate()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=5)
        process.stdout.close()


def test_desktop_real_startup_and_data_survive_restart(tmp_path):
    db = tmp_path / "사용자 데이터 with spaces" / "scheduler.sqlite3"
    password = "desktop-test-password-only"
    with desktop(db) as (request, client, url):
        assert request("/api/session")["configured"] is False
        with client.open(url) as response:
            assert response.status == 200
            assert "<html" in response.read().decode()
        request("/api/setup", {"password": password})
        created = request("/api/items", {"title": "재실행 후 남아야 하는 할 일", "request_id": "desktop-restart-test-0001"})
    with desktop(db) as (request, _, _):
        assert request("/api/session")["configured"] is True
        request("/api/login", {"password": password})
        assert request("/api/items")[0]["id"] == created["id"]
