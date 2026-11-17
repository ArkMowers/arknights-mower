import base64
import json
import os
import sys

import pytest

from arknights_mower.utils import credential_store as store


@pytest.fixture
def private_key(tmp_path, monkeypatch):
    key = tmp_path / "private" / "private.key"
    key.parent.mkdir()
    key.write_bytes(base64.b64encode(os.urandom(96)))
    key.chmod(0o600)
    monkeypatch.setenv("MOWER_CREDENTIAL_KEY_FILE", str(key))
    return key


def test_encrypted_round_trip_preserves_values_and_clear(tmp_path, private_key):
    path = tmp_path / "mower.secrets.json"
    values = {
        "password": "secret-test-value",
        "accounts": [{"name": "user", "enabled": False}],
        "empty": "",
    }
    store.write_credentials(path, values)
    raw = path.read_bytes()
    assert b"secret-test-value" not in raw
    assert b"password" not in raw
    assert store.read_credentials(path) == values
    store.write_credentials(path, {})
    assert path.exists()
    assert store.read_credentials(path) == {}


@pytest.mark.parametrize("damage", ["remove", "replace", "corrupt"])
def test_lost_key_never_replaced_and_ciphertext_retained(tmp_path, private_key, damage):
    path = tmp_path / "mower.secrets.json"
    store.write_credentials(path, {"token": "original-access-token"})
    before = path.read_bytes()
    if damage == "remove":
        private_key.unlink()
    else:
        private_key.write_bytes(
            base64.b64encode(os.urandom(96)) if damage == "replace" else b"invalid"
        )
    for operation in (
        lambda: store.read_credentials(path),
        lambda: store.write_credentials(path, {}),
    ):
        with pytest.raises(store.CredentialStoreError):
            operation()
        assert path.read_bytes() == before
    if damage == "remove":
        assert not private_key.exists()


def test_corrupt_ciphertext_is_not_empty_configuration(tmp_path, private_key):
    path = tmp_path / "mower.secrets.json"
    store.write_credentials(path, {"token": "access-token"})
    envelope = json.loads(path.read_bytes())
    envelope["ciphertext"] = envelope["ciphertext"][:-8] + "AAAAAAAA"
    path.write_text(json.dumps(envelope), encoding="utf-8")
    before = path.read_bytes()
    with pytest.raises(store.CredentialStoreError):
        store.write_credentials(path, {})
    assert path.read_bytes() == before


def test_failed_atomic_replace_keeps_original_and_removes_temporary(
    tmp_path, private_key, monkeypatch
):
    path = tmp_path / "mower.secrets.json"
    store.write_credentials(path, {"token": "original"})
    before = path.read_bytes()

    def fail(*args):
        raise OSError("disk failure")

    monkeypatch.setattr(store.update_runtime, "replace_with_retry", fail)
    with pytest.raises(OSError):
        store.write_credentials(path, {"token": "new"})
    assert path.read_bytes() == before
    assert not list(tmp_path.glob(".mower.secrets.json.*"))


def test_missing_local_key_is_not_regenerated_on_read(tmp_path, monkeypatch):
    monkeypatch.delenv("MOWER_CREDENTIAL_KEY_FILE")
    monkeypatch.setattr(
        store, "_private_directory", lambda: tmp_path / "persistent-keys"
    )
    monkeypatch.setattr(store, "_provider", lambda: "local-key")
    path = tmp_path / "mower.secrets.json"
    store.write_credentials(path, {"token": "access-token"})
    key = tmp_path / "persistent-keys/private.key"
    if os.name != "nt":
        assert key.stat().st_mode & 0o777 == 0o600
        assert key.parent.stat().st_mode & 0o777 == 0o700
    key.unlink()
    with pytest.raises(store.CredentialStoreError):
        store.read_credentials(path)
    assert not key.exists()


def test_keychain_failure_does_not_switch_provider(tmp_path, private_key, monkeypatch):
    envelope = json.loads(store.encode_credentials({"token": "original"}))
    envelope["provider"] = "keychain"
    monkeypatch.delenv("MOWER_CREDENTIAL_KEY_FILE")
    monkeypatch.setattr(store, "_private_directory", lambda: tmp_path / "keys")

    def unavailable(create):
        raise store.CredentialStoreError("keychain locked")

    monkeypatch.setattr(store, "_mac_key", unavailable)
    with pytest.raises(store.CredentialStoreError, match="keychain locked"):
        store.decode_credentials(json.dumps(envelope).encode())
    assert not (tmp_path / "keys/private.key").exists()


def test_missing_credentials_are_empty_but_directory_is_rejected(tmp_path):
    path = tmp_path / "mower.secrets.json"
    assert store.read_credentials(path) == {}
    path.mkdir()
    with pytest.raises(store.CredentialStoreError, match="普通文件"):
        store.read_credentials(path)


@pytest.mark.parametrize("target_exists", [False, True])
def test_credential_symlinks_are_never_missing_or_writable(
    tmp_path, private_key, target_exists
):
    target = tmp_path / "original.secrets.json"
    if target_exists:
        store.write_credentials(target, {"token": "original"})
    before = target.read_bytes() if target_exists else None
    path = tmp_path / "mower.secrets.json"
    try:
        path.symlink_to(target)
    except OSError:
        pytest.skip("Creating symlinks is unavailable for this user")
    with pytest.raises(store.CredentialStoreError, match="符号链接"):
        store.read_credentials(path)
    with pytest.raises(store.CredentialStoreError, match="符号链接"):
        store.write_credentials(path, {})
    assert path.is_symlink()
    assert (target.read_bytes() if target_exists else None) == before
    assert target.exists() is target_exists


def test_oversized_credentials_fail_before_decoding(tmp_path, monkeypatch):
    path = tmp_path / "mower.secrets.json"
    path.write_bytes(b"x" * 65)
    monkeypatch.setattr(store, "_MAX_BYTES", 32)

    def forbidden_decode(raw):
        pytest.fail("Oversized credentials must not reach decoding")

    monkeypatch.setattr(store, "decode_credentials", forbidden_decode)
    with pytest.raises(store.CredentialStoreError, match="大小限制"):
        store.read_credentials(path)


def test_persisted_credentials_are_verified_before_success(
    tmp_path, private_key, monkeypatch
):
    path = tmp_path / "mower.secrets.json"

    def corrupt_write(destination, raw):
        destination.write_bytes(b"damaged after write")

    monkeypatch.setattr(store, "_atomic_bytes", corrupt_write)
    with pytest.raises(store.CredentialStoreError):
        store.write_credentials(path, {"token": "new-value"})
    assert not path.exists()


def test_failed_readback_restores_original_ciphertext(
    tmp_path, private_key, monkeypatch
):
    path = tmp_path / "mower.secrets.json"
    store.write_credentials(path, {"token": "original"})
    previous = path.read_bytes()
    atomic = store._atomic_bytes
    writes = 0

    def corrupt_once(destination, raw):
        nonlocal writes
        writes += 1
        atomic(destination, b"damaged after write" if writes == 1 else raw)

    monkeypatch.setattr(store, "_atomic_bytes", corrupt_once)
    with pytest.raises(store.CredentialStoreError):
        store.write_credentials(path, {"token": "replacement"})
    assert path.read_bytes() == previous
    assert store.read_credentials(path) == {"token": "original"}


def test_missing_initialized_local_key_cannot_be_replaced_for_new_file(
    tmp_path, monkeypatch
):
    monkeypatch.delenv("MOWER_CREDENTIAL_KEY_FILE")
    directory = tmp_path / "persistent-keys"
    monkeypatch.setattr(store, "_private_directory", lambda: directory)
    monkeypatch.setattr(store, "_provider", lambda: "local-key")
    path = tmp_path / "mower.secrets.json"
    store.write_credentials(path, {"token": "original"})
    original = path.read_bytes()
    key = directory / "private.key"
    key.unlink()
    new_path = tmp_path / "ai.secrets.json"
    with pytest.raises(store.CredentialStoreError, match="密钥已丢失"):
        store.write_credentials(new_path, {"api_key": "another"})
    assert not key.exists()
    assert not new_path.exists()
    assert path.read_bytes() == original


def test_nonregular_key_is_rejected_before_open(tmp_path, monkeypatch):
    path = tmp_path / "private.key"
    path.mkdir()

    def forbidden_open(*args, **kwargs):
        pytest.fail("Nonregular key must be rejected before opening")

    monkeypatch.setattr(store.os, "open", forbidden_open)
    with pytest.raises(store.CredentialStoreError, match="普通文件"):
        store._read_key(path)


@pytest.mark.skipif(not hasattr(os, "mkfifo"), reason="POSIX named pipe")
def test_fifo_key_is_rejected_before_open(tmp_path, monkeypatch):
    path = tmp_path / "private.key"
    os.mkfifo(path)

    def forbidden_open(*args, **kwargs):
        pytest.fail("FIFO key must be rejected before a blocking open")

    monkeypatch.setattr(store.os, "open", forbidden_open)
    with pytest.raises(store.CredentialStoreError, match="普通文件"):
        store._read_key(path)


@pytest.mark.skipif(sys.platform != "win32", reason="Native Windows DPAPI")
def test_native_dpapi_round_trip_and_tampering(tmp_path, monkeypatch):
    monkeypatch.delenv("MOWER_CREDENTIAL_KEY_FILE")
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "private-data"))
    path = tmp_path / "mower.secrets.json"
    store.write_credentials(path, {"token": "dpapi-private-value"})
    assert b"dpapi-private-value" not in path.read_bytes()
    assert json.loads(path.read_bytes())["provider"] == "dpapi"
    assert store.read_credentials(path) == {"token": "dpapi-private-value"}
    private_file = store._private_directory() / "private.dpapi"
    protected = private_file.read_bytes()
    private = store._dpapi(protected, decrypt=True)
    assert len(private) == 96
    assert private not in protected
    assert base64.b64encode(private) not in path.read_bytes()
    store.write_credentials(path, {"token": "replacement"})
    assert private_file.read_bytes() == protected
    envelope = json.loads(path.read_bytes())
    damaged = bytearray(base64.b64decode(envelope["ciphertext"]))
    damaged[-1] ^= 1
    envelope["ciphertext"] = base64.b64encode(damaged).decode()
    with pytest.raises(store.CredentialStoreError):
        store.decode_credentials(json.dumps(envelope).encode())
    original = path.read_bytes()
    restored = tmp_path / "restored.key"
    restored.write_bytes(base64.b64encode(private))
    private_file.unlink()
    monkeypatch.setenv("MOWER_CREDENTIAL_KEY_FILE", str(restored))
    assert store.read_credentials(path) == {"token": "replacement"}
    assert path.read_bytes() == original


@pytest.mark.skipif(sys.platform != "win32", reason="Native Windows packaged layout")
def test_collected_layout_without_hybrid_runtime_fails_without_writing(tmp_path):
    import shutil
    import subprocess
    from pathlib import Path

    import build_assets

    names = {"__init__.py", "credential_store.py", "update_runtime.py", "git_rev.py"}
    for source, destination in build_assets._collect_arknights_mower_datas():
        if Path(source).name not in names:
            continue
        target = tmp_path / destination / Path(source).name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)
    script = """
import base64
import json
import sys
from pathlib import Path
sys.path.insert(0, sys.argv[1])
from arknights_mower.utils.credential_store import CredentialStoreError, read_credentials, write_credentials
target = Path(sys.argv[1]) / 'mower.secrets.json'
original = json.dumps({
    'version': 1,
    'suite': 'HPKE-X-Wing-HKDF-SHA256-AES-256-GCM',
    'provider': 'dpapi',
    'key_id': '0' * 64,
    'ciphertext': base64.b64encode(b'synthetic ciphertext').decode('ascii'),
}).encode('ascii')
target.write_bytes(original)
for operation in (lambda: read_credentials(target), lambda: write_credentials(target, {})):
    try:
        operation()
    except CredentialStoreError:
        pass
    else:
        raise AssertionError('A missing hybrid runtime must fail closed')
assert target.read_bytes() == original
assert not (Path(sys.argv[1]) / 'private-data').exists()
"""
    environment = dict(os.environ)
    environment.pop("MOWER_CREDENTIAL_KEY_FILE", None)
    environment["XDG_DATA_HOME"] = str(tmp_path / "private-data")
    completed = subprocess.run(
        [sys.executable, "-I", "-S", "-c", script, str(tmp_path)],
        cwd=tmp_path,
        env=environment,
        capture_output=True,
        text=True,
        timeout=20,
        creationflags=subprocess.CREATE_NO_WINDOW,
    )
    assert completed.returncode == 0, completed.stderr


@pytest.mark.parametrize("target_exists", [False, True])
def test_private_key_symlink_is_rejected(tmp_path, monkeypatch, target_exists):
    target = tmp_path / "target.key"
    if target_exists:
        target.write_bytes(base64.b64encode(os.urandom(96)))
        target.chmod(0o600)
    path = tmp_path / "private.key"
    try:
        path.symlink_to(target)
    except OSError:
        pytest.skip("Creating symlinks is unavailable for this user")
    monkeypatch.setenv("MOWER_CREDENTIAL_KEY_FILE", str(path))
    with pytest.raises(store.CredentialStoreError, match="符号链接"):
        store.write_credentials(tmp_path / "mower.secrets.json", {"token": "value"})
    assert path.is_symlink()


@pytest.mark.skipif(os.name == "nt", reason="POSIX private file permissions")
def test_readable_by_other_users_private_key_is_rejected(tmp_path, private_key):
    private_key.chmod(0o644)
    with pytest.raises(store.CredentialStoreError, match="0600"):
        store.write_credentials(tmp_path / "mower.secrets.json", {"token": "value"})


def test_explicit_xdg_and_windows_persistent_directory(monkeypatch, tmp_path):
    monkeypatch.setattr(store.sys, "platform", "win32")
    monkeypatch.delenv("XDG_DATA_HOME", raising=False)
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "Local"))
    assert store._private_directory() == tmp_path / "Local/arknights-mower/credentials"
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "override"))
    assert (
        store._private_directory() == tmp_path / "override/arknights-mower/credentials"
    )
