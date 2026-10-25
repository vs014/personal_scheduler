import io
import tarfile
from pathlib import Path
import pytest
from backend import install_codex as installer


def archive(tmp_path, entries):
    path=tmp_path/'codex.tgz'
    with tarfile.open(path,'w:gz') as out:
        for name, content in entries:
            info=tarfile.TarInfo(installer.PREFIX+name)
            info.size=len(content)
            out.addfile(info,io.BytesIO(content))
    return path


def test_verified_install_reuse_and_corruption_detection(tmp_path,monkeypatch):
    source=archive(tmp_path,[('bin/codex.exe',b'fake executable'),('codex-resources/helper.dll',b'fake library')])
    expected=installer.digest(source)
    monkeypatch.setattr(installer,'SHA512',expected)
    destination=tmp_path/'runtime'
    installer.install_archive(source,destination,expected)
    assert installer.ready(destination)
    monkeypatch.setattr(installer,'urlopen',lambda *a,**k:pytest.fail('Verified installation must not download again'))
    installer.ensure(destination)
    (destination/'bin/codex.exe').write_bytes(b'corrupted')
    assert not installer.ready(destination)
    installer.install_archive(source,destination,expected)
    assert installer.ready(destination)


def test_hash_mismatch_does_not_replace_existing_files(tmp_path):
    source=archive(tmp_path,[('bin/codex.exe',b'new')])
    destination=tmp_path/'runtime'
    (destination/'bin').mkdir(parents=True)
    (destination/'bin/codex.exe').write_bytes(b'existing')
    with pytest.raises(ValueError,match='checksum'):
        installer.install_archive(source,destination,'incorrect-hash')
    assert (destination/'bin/codex.exe').read_bytes()==b'existing'


@pytest.mark.parametrize('name',['../../outside.exe',r'..\outside.exe','C:/outside.exe'])
def test_archive_cannot_escape_staging_directory(tmp_path,name):
    source=archive(tmp_path,[('bin/codex.exe',b'new'),(name,b'unsafe')])
    with pytest.raises(ValueError,match='Unsafe'):
        installer.install_archive(source,tmp_path/'runtime',installer.digest(source))
    assert not (tmp_path/'runtime/bin/codex.exe').exists()
