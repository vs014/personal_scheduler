"""Build a clean Windows ZIP; bundle official uv binaries verified against pinned SHA256."""
import argparse
import base64
import tarfile
import shutil
import tempfile
import hashlib
import io
import json
import urllib.request
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
UV_VERSION = "0.12.23"
CODEX_VERSION = "0.164.0"
CODEX_URL = "https://registry.npmjs.org/@openai/codex/-/codex-0.164.0-win32-x64.tgz"
CODEX_SHA512 = "urWPhwh9YavuoAPIkmVYKBTtd5OtGVL4Ki0Fb28dhK/Mz6Pt4LSy+gbRrZFz5+RXrw9ubvXuXDCcd8beYcWhDg=="


def codex_archive():
    path = Path(tempfile.gettempdir()) / "yeobaek-codex-0.164.0-win32-x64.tgz"
    if not path.exists():
        with urllib.request.urlopen(CODEX_URL, timeout=90) as response, path.open("wb") as out:
            shutil.copyfileobj(response, out)
    with path.open("rb") as source:
        digest = hashlib.file_digest(source, "sha512").digest()
    if base64.b64encode(digest).decode() != CODEX_SHA512:
        raise SystemExit("Codex checksum mismatch; refusing to package")
    return path

# Official release checksums are verified at packaging time; runtime uv preserves TLS/hash checks.
ARTIFACTS = {
    "x64": ("x86_64-pc-windows-msvc", "75d05de6762778c31ee183398de7dd15093fad0ed90b1f236d8205ea5ec00c90"),
}
INSTRUCTIONS = """여백 — Windows에서 실행하기

1. ZIP을 마우스 오른쪽 버튼으로 눌러 '모두 압축 풀기'를 선택하세요.
2. 압축을 푼 Yeobaek-Windows 폴더 안의 START-Yeobaek.cmd를 더블클릭하세요.
3. 첫 실행은 인터넷 연결이 필요하며 몇 분 걸릴 수 있습니다.
   Python과 앱에 필요한 구성 요소를 자동으로 준비합니다.
   Node.js, WSL, 관리자 권한은 필요하지 않습니다.
4. 준비가 끝나면 브라우저가 열립니다. 나만 사용할 12자 이상의 비밀번호를 만드세요.
5. 실행 창은 사용하는 동안 열어 두세요. 창을 닫으면 앱도 종료됩니다.

브라우저가 자동으로 열리지 않으면 실행 창에 표시된 주소를 입력하세요.
기본 포트 8000이 사용 중이면 다른 빈 포트로 실행하므로 창의 실제 주소를 확인하세요.
이 주소는 앱을 실행한 노트북에서만 사용할 수 있습니다. 휴대폰 접속은 아직 지원하지 않습니다.
개발 환경에서 만든 계정이나 내용은 이 노트북으로 자동 이동하지 않습니다.

내 데이터 위치
Windows 탐색기 주소창에 %LOCALAPPDATA%\\Yeobaek\\data 를 입력하면 찾을 수 있습니다.
일정·피드백·비밀번호 정보는 이 폴더에 저장됩니다. 앱 ZIP에는 포함되지 않습니다.
새 버전은 새 폴더에 풀고 기존 실행 창을 닫은 뒤 실행하세요. 같은 데이터가 유지됩니다.
압축을 푼 앱 폴더를 삭제해도 위 사용자 데이터 폴더는 남습니다.

문제가 생겼다면
- ZIP 안에서 바로 실행하지 말고 전체 파일을 먼저 압축 해제하세요.
- 설치 실패 시 인터넷 연결을 확인하고 다시 실행하세요.
- ChatGPT 로그인 후 오류가 나면 대화로 등록 메뉴의 인증 서버 연결 확인을 누르세요.
  [TLS-CERT], [PROXY-CONNECT] 등의 오류 문구를 Codex 대화에 알려주세요.
  로그인 주소, 비밀번호, 인증 코드는 보내지 마세요.
- 실행 창의 오류 문구를 Codex 대화에 알려주세요. 데이터를 먼저 삭제하지 마세요.
- Windows나 회사 보안 정책이 실행을 차단하면 차단 문구를 알려주세요.
  보안 프로그램을 끄거나 실행 정책을 변경할 필요는 없습니다.

제약
Intel/AMD x64 Windows 10/11용 실행 스크립트입니다.
ARM64 Windows 11에서는 x64 호환 실행을 사용합니다. ARM64 Windows 10은 지원하지 않습니다. 서명된 설치 EXE가 아닙니다.
패키지는 Linux에서 구성·검사했습니다. 실제 Windows 실행은 아직 검증하지 못했습니다.
대화로 등록 메뉴에서 Continue with ChatGPT로 연결한 뒤 모델을 선택하세요.
구독 사용 권한과 한도가 적용됩니다. 실제 계정의 첫 AI 응답은 로그인 후 확인해야 합니다.
개선 기록에서 Codex 로그인과 환경 설정 후 선택한 피드백을 클라우드 검토 작업으로 보낼 수 있습니다.
실제 계정 전송은 로그인 후 확인해야 합니다. 기존 Codex 대화에 추가되거나 앱이 자동 업데이트되는 것은 아닙니다.
휴대폰 푸시는 아직 연결되지 않았습니다.

다운로드 구성 요소: Astral uv 0.12.23 (MIT/Apache-2.0),
uv가 설치하는 Python과 pyproject.toml/uv.lock에 명시된 앱 의존성.
설치 과정에서는 외부 AI를 호출하지 않습니다. ChatGPT 연결 후 대화를 보내면 해당 대화가 OpenAI로 전송됩니다. 별도의 유료 API로 자동 전환하지 않습니다.
"""


def build(destination: Path, light: bool = False):
    if not (ROOT / "web/dist/index.html").is_file():
        raise SystemExit("Run npm run build first")
    destination.parent.mkdir(parents=True, exist_ok=True)
    manifest = {"app_version": "0.2.7", "uv_version": UV_VERSION, "artifacts": {"codex": {"version":CODEX_VERSION,"url":CODEX_URL,"sha512":CODEX_SHA512}}}
    manifest["distribution"] = "light" if light else "full"
    codex_tarball = None if light else codex_archive()
    bundled = {}
    for arch, (target, expected) in ARTIFACTS.items():
        name = f"uv-{target}.zip"
        url = f"https://github.com/astral-sh/uv/releases/download/{UV_VERSION}/{name}"
        with urllib.request.urlopen(url, timeout=90) as response:
            binary = response.read()
        digest = hashlib.sha256(binary).hexdigest()
        if digest != expected:
            raise SystemExit(f"Checksum mismatch for {name}; refusing to package")
        with zipfile.ZipFile(io.BytesIO(binary)) as archive:
            candidates = [p for p in archive.namelist() if Path(p).name == "uv.exe"]
            if len(candidates) != 1:
                raise SystemExit(f"Unexpected archive layout: {name}")
            bundled[f"tools/{arch}/uv.exe"] = archive.read(candidates[0])
        manifest["artifacts"][arch] = {"url": url, "sha256": digest}
    # Explicit allowlist: never include a personal DB, credentials, .git, caches, or local environments.
    sources = [ROOT / name for name in ("pyproject.toml", "uv.lock")]
    for directory in ("backend", "docs", "web/dist"):
        sources.extend(p for p in (ROOT / directory).rglob("*") if p.is_file() and "__pycache__" not in p.parts and p.suffix != ".pyc")
    with zipfile.ZipFile(destination, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as out:
        for path in sorted(sources):
            out.write(path, f"Yeobaek-Windows/{path.relative_to(ROOT).as_posix()}")
        script = (ROOT / "scripts/windows-start.cmd").read_text()
        if light:
            marker = r'"%UV_PROJECT_ENVIRONMENT%\Scripts\python.exe" -m backend.desktop'
            bootstrap = r'"%UV_PROJECT_ENVIRONMENT%\Scripts\python.exe" -m backend.install_codex' + '\nif errorlevel 1 goto failed\n' + r'set "SCHEDULER_CODEX_BINARY=%LOCALAPPDATA%\Yeobaek\runtime\codex-0.164.0\bin\codex.exe"' + '\n'
            assert marker in script
            script = script.replace(marker, bootstrap + marker)
        script = script.replace("\n", "\r\n")
        out.writestr("Yeobaek-Windows/START-Yeobaek.cmd", script.encode("ascii"))
        out.writestr("Yeobaek-Windows/먼저-읽어주세요.txt", (("작은 배포본: 첫 실행 때 공식 Codex 구성 요소 약 173MB를 추가로 내려받고 검증합니다. 다음 실행에서는 재사용합니다.\n\n" if light else "") + INSTRUCTIONS).encode("utf-8-sig"))
        for name, content in bundled.items():
            out.writestr(f"Yeobaek-Windows/{name}", content)
        if not light:
            prefix = "package/vendor/x86_64-pc-windows-msvc/"
            with tarfile.open(codex_tarball, "r:gz") as archive:
                for member in archive.getmembers():
                    if not member.isfile() or not member.name.startswith(prefix):
                        continue
                    rel = member.name[len(prefix):]
                    if ".." in Path(rel).parts or Path(rel).is_absolute():
                        raise SystemExit("Unsafe Codex archive member")
                    with archive.extractfile(member) as source, out.open("Yeobaek-Windows/tools/codex/" + rel, "w", force_zip64=True) as target:
                        shutil.copyfileobj(source, target)
        with urllib.request.urlopen("https://raw.githubusercontent.com/openai/codex/rust-v0.164.0/LICENSE", timeout=30) as response:
            out.writestr("Yeobaek-Windows/tools/codex/LICENSE", response.read())
        out.writestr("Yeobaek-Windows/download-manifest.json", json.dumps(manifest, indent=2))
        out.writestr("Yeobaek-Windows/THIRD-PARTY-NOTICES.txt", "Codex CLI 0.164.0: https://github.com/openai/codex (Apache-2.0; tools/codex/LICENSE)\nAstral uv: https://github.com/astral-sh/uv\nLicensed under MIT OR Apache-2.0. See tools/LICENSE-MIT and tools/LICENSE-APACHE.\n")
        for license_name in ("LICENSE-MIT", "LICENSE-APACHE"):
            with urllib.request.urlopen(f"https://raw.githubusercontent.com/astral-sh/uv/{UV_VERSION}/{license_name}", timeout=30) as r:
                out.writestr(f"Yeobaek-Windows/tools/{license_name}", r.read())
    print(f"Created: {destination} ({destination.stat().st_size:,} bytes)")
    print(f"SHA256: {hashlib.sha256(destination.read_bytes()).hexdigest()}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("destination", type=Path)
    parser.add_argument("--light", action="store_true", help="Download verified Codex components on first Windows launch")
    args = parser.parse_args()
    build(args.destination, args.light)
