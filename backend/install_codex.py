"""Verified first-run Codex installation for the small Windows distribution."""
import base64
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import shutil
import tarfile
import tempfile
from urllib.request import urlopen

from .tls import client_context

VERSION = '0.164.0'
URL = 'https://registry.npmjs.org/@openai/codex/-/codex-0.164.0-win32-x64.tgz'
SHA512 = 'urWPhwh9YavuoAPIkmVYKBTtd5OtGVL4Ki0Fb28dhK/Mz6Pt4LSy+gbRrZFz5+RXrw9ubvXuXDCcd8beYcWhDg=='
PREFIX = 'package/vendor/x86_64-pc-windows-msvc/'


def digest(path):
    with path.open('rb') as f:
        return base64.b64encode(hashlib.file_digest(f, 'sha512').digest()).decode()


def safe_relative(name):
    rel = PurePosixPath(name)
    if not name or rel.is_absolute() or '..' in rel.parts or '\\' in name or ':' in name:
        raise ValueError('Unsafe archive path')
    return Path(*rel.parts)


def ready(destination):
    try:
        receipt = json.loads((destination/'install-receipt.json').read_text())
        files = receipt['files']
        return (receipt['archive_sha512'] == SHA512 and 'bin/codex.exe' in files
                and all(digest(destination/safe_relative(name)) == expected for name, expected in files.items()))
    except (OSError, ValueError, KeyError, TypeError, AttributeError):
        return False


def install_archive(archive_path, destination, expected=SHA512):
    if digest(archive_path) != expected:
        raise ValueError('Codex download checksum mismatch. Installation stopped.')
    destination.parent.mkdir(parents=True, exist_ok=True)
    # Never extract directly into the application or a user data directory.
    with tempfile.TemporaryDirectory(prefix='codex-stage-', dir=destination.parent) as directory:
        stage = Path(directory)
        files = {}
        with tarfile.open(archive_path, 'r:gz') as archive:
            for member in archive:
                if not member.name.startswith(PREFIX) or member.isdir():
                    continue
                if not member.isfile():
                    raise ValueError('Unsupported Codex archive entry')
                relative = safe_relative(member.name[len(PREFIX):])
                name = relative.as_posix()
                if name in files:
                    raise ValueError('Duplicate Codex archive entry')
                target = stage/relative
                target.parent.mkdir(parents=True, exist_ok=True)
                with archive.extractfile(member) as source, target.open('wb') as out:
                    shutil.copyfileobj(source, out)
                files[name] = digest(target)
        if 'bin/codex.exe' not in files:
            raise ValueError('Codex executable missing from archive')
        receipt = {'archive_sha512': expected, 'version': VERSION, 'files': files}
        (stage/'install-receipt.json').write_text(json.dumps(receipt), encoding='utf-8')
        for name in [*files, 'install-receipt.json']:
            target = destination/safe_relative(name)
            target.parent.mkdir(parents=True, exist_ok=True)
            os.replace(stage/safe_relative(name), target)


def ensure(destination):
    if ready(destination):
        print('Codex components verified. Reusing the existing installation.', flush=True)
        return
    destination.parent.mkdir(parents=True, exist_ok=True)
    print('Downloading official Codex components (about 173 MB). Please keep this window open.', flush=True)
    with tempfile.TemporaryDirectory(prefix='codex-download-', dir=destination.parent) as directory:
        archive_path = Path(directory)/'codex.tgz'
        with urlopen(URL, timeout=90, context=client_context()) as response, archive_path.open('wb') as out:
            total = 0
            progress = 0
            while block := response.read(1024*1024):
                total += len(block)
                if total > 250*1024*1024:
                    raise ValueError('Unexpected download size')
                out.write(block)
                if total//(20*1024*1024) > progress:
                    progress = total//(20*1024*1024)
                    print(f'Downloaded {total//(1024*1024)} MB...', flush=True)
        print('Verifying and preparing Codex...', flush=True)
        install_archive(archive_path, destination)
    print('Codex is ready.', flush=True)


if __name__ == '__main__':
    local = os.getenv('LOCALAPPDATA')
    if not local:
        raise SystemExit('Windows LOCALAPPDATA is unavailable.')
    try:
        ensure(Path(local)/'Yeobaek'/'runtime'/f'codex-{VERSION}')
    except Exception:
        raise SystemExit('Codex setup failed. Check your connection, close other Yeobaek/Codex windows, and run START-Yeobaek.cmd again. Your schedules were not changed. TLS and checksum verification remain enabled.') from None
