"""Explicit key recovery uses isolated files and simulated system key services."""

import base64
import json
import os
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from types import SimpleNamespace

import pytest
from cryptography.exceptions import UnsupportedAlgorithm

from arknights_mower.utils import credential_store as store


@pytest.fixture(autouse=True)
def isolated_user_home(tmp_path, monkeypatch):
    home = tmp_path / "home"
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: home))
    return home


@pytest.fixture(params=["local-key", "dpapi"])
def file_provider(request, tmp_path, monkeypatch):
    provider = request.param
    if provider == "dpapi" and sys.platform != "win32":
        pytest.skip("Native Windows DPAPI")
    directory = tmp_path / "private-keys"
    monkeypatch.delenv("MOWER_CREDENTIAL_KEY_FILE")
    monkeypatch.setattr(store, "_private_directory", lambda: directory)
    monkeypatch.setattr(store, "_provider", lambda: provider)
    private_path = directory / (
        "private.dpapi" if provider == "dpapi" else "private.key"
    )
    return provider, directory, private_path


def test_recovery_keeps_shared_healthy_key_and_other_instance_credentials(
    tmp_path, file_provider
):
    provider, _, private_path = file_provider
    first, other = tmp_path / "first.secrets.json", tmp_path / "other.secrets.json"
    store.write_credentials(first, {"token": "first-token"})
    store.write_credentials(other, {"token": "other-token"})
    original_key, other_ciphertext = private_path.read_bytes(), other.read_bytes()
    first.write_bytes(b"damaged credential file")

    result = store.recover_private_key()

    assert result["provider"] == provider
    assert result["changed"] is False
    assert result["created"] is False
    assert result["quarantine_path"] is None
    assert result["key_id"] == json.loads(other_ciphertext)["key_id"]
    assert private_path.read_bytes() == original_key
    assert other.read_bytes() == other_ciphertext
    assert store.read_credentials(other) == {"token": "other-token"}
    assert first.read_bytes() == b"damaged credential file"
    assert "共用" in result["warning"]


@pytest.mark.parametrize("damage", ["missing", "corrupt"])
def test_only_explicit_recovery_can_replace_a_lost_default_key(
    tmp_path, file_provider, damage
):
    provider, directory, private_path = file_provider
    old = tmp_path / "old.secrets.json"
    store.write_credentials(old, {"token": "original"})
    old_ciphertext = old.read_bytes()
    if damage == "missing":
        private_path.unlink()
        original = None
    else:
        original = b"corrupt-private-key-preserved-verbatim"
        private_path.write_bytes(original)
    new = tmp_path / "new.secrets.json"
    with pytest.raises(store.CredentialStoreError):
        store.write_credentials(new, {"token": "new"})

    result = store.recover_private_key()

    assert result["changed"] is True
    assert result["created"] is (damage == "missing")
    assert (directory / f"{provider}.initialized").is_file()
    assert old.read_bytes() == old_ciphertext
    with pytest.raises(store.CredentialStoreError):
        store.read_credentials(old)
    store.write_credentials(new, {"token": "new"})
    assert store.read_credentials(new) == {"token": "new"}
    assert json.loads(new.read_bytes())["key_id"] == result["key_id"]
    if original is not None:
        quarantine = Path(result["quarantine_path"])
        assert quarantine.read_bytes() == original
        assert quarantine in store.protected_key_paths()
        if os.name != "nt":
            assert quarantine.stat().st_mode & 0o777 == 0o600
    else:
        assert result["quarantine_path"] is None
    assert "其他" in result["warning"]
    assert "original" not in json.dumps(result)


@pytest.mark.parametrize(
    "stage", ["quarantine", "quarantine-readback", "write", "readback", "marker"]
)
def test_failed_file_recovery_retains_original_private_bytes(
    file_provider, monkeypatch, stage
):
    provider, directory, private_path = file_provider
    directory.mkdir()
    original = b"original-damaged-private-key"
    private_path.write_bytes(original)
    private_path.chmod(0o600)
    atomic = store._atomic_bytes
    failed = False

    def fail_once(path, raw):
        nonlocal failed
        matches = (
            (stage.startswith("quarantine") and path.suffix == ".quarantined")
            or (stage in ("write", "readback") and path == private_path)
            or (stage == "marker" and path.suffix == ".initialized")
        )
        if matches and not failed:
            failed = True
            if stage in ("readback", "quarantine-readback"):
                return atomic(path, b"damaged-new-private-key")
            raise OSError("synthetic persistence failure")
        return atomic(path, raw)

    monkeypatch.setattr(store, "_atomic_bytes", fail_once)
    with pytest.raises(store.CredentialStoreError):
        store.recover_private_key()
    assert failed
    assert private_path.read_bytes() == original
    assert not (directory / f"{provider}.initialized").exists()
    for path in directory.glob("*.quarantined"):
        assert path.read_bytes() == (
            b"damaged-new-private-key" if stage == "quarantine-readback" else original
        )


def test_failed_missing_key_recovery_removes_uncommitted_key(
    file_provider, monkeypatch
):
    _, directory, private_path = file_provider
    atomic = store._atomic_bytes

    def fail_marker(path, raw):
        if path.suffix == ".initialized":
            raise OSError("synthetic marker failure")
        return atomic(path, raw)

    monkeypatch.setattr(store, "_atomic_bytes", fail_marker)
    with pytest.raises(store.CredentialStoreError):
        store.recover_private_key()
    assert not private_path.exists()
    assert not list(directory.glob("*.initialized"))


def test_concurrent_recovery_creates_one_shared_key(file_provider):
    with ThreadPoolExecutor(max_workers=4) as executor:
        results = list(executor.map(lambda _: store.recover_private_key(), range(4)))
    assert sum(result["changed"] for result in results) == 1
    assert len({result["key_id"] for result in results}) == 1


def test_recovery_never_replaces_a_key_blocked_by_file_permissions(
    file_provider, monkeypatch
):
    _, directory, private_path = file_provider
    directory.mkdir()
    original = base64.b64encode(os.urandom(96))
    private_path.write_bytes(original)

    def denied(*args, **kwargs):
        raise store.CredentialStoreError("私钥权限不足")

    monkeypatch.setattr(store, "_read_private_file", denied)
    with pytest.raises(store.CredentialStoreError, match="权限不足"):
        store.recover_private_key()
    assert private_path.read_bytes() == original
    assert not list(directory.glob("*.quarantined"))


@pytest.mark.parametrize("kind", ["directory", "symlink"])
def test_recovery_refuses_nonregular_private_key_path(file_provider, kind):
    _, directory, private_path = file_provider
    directory.mkdir()
    target = directory / "untouched.key"
    target.write_bytes(b"original-target")
    if kind == "directory":
        private_path.mkdir()
    else:
        try:
            private_path.symlink_to(target)
        except OSError:
            pytest.skip("Creating symlinks is unavailable for this user")
    with pytest.raises(store.CredentialStoreError, match="普通文件|符号链接"):
        store.recover_private_key()
    assert target.read_bytes() == b"original-target"
    assert not list(directory.glob("*.quarantined"))


@pytest.mark.parametrize("damage", ["missing", "corrupt", "healthy"])
def test_explicit_deployment_key_is_never_created_or_replaced(
    tmp_path, monkeypatch, damage
):
    path = tmp_path / "external-private.key"
    original = None
    if damage != "missing":
        original = (
            base64.b64encode(os.urandom(96)) if damage == "healthy" else b"corrupt"
        )
        path.write_bytes(original)
        path.chmod(0o600)
    monkeypatch.setenv("MOWER_CREDENTIAL_KEY_FILE", str(path))
    monkeypatch.setattr(
        store, "_private_directory", lambda: tmp_path / "unused-default"
    )
    if damage == "healthy":
        assert store.recover_private_key()["changed"] is False
    else:
        with pytest.raises(
            store.CredentialStoreError, match="管理员.*MOWER_CREDENTIAL_KEY_FILE"
        ):
            store.recover_private_key()
    assert (path.read_bytes() if path.exists() else None) == original
    assert not (tmp_path / "unused-default").exists()


@pytest.mark.parametrize("provider", ["keychain", "secret-service"])
@pytest.mark.parametrize("state", ["missing", "healthy", "corrupt", "locked"])
def test_system_recovery_only_creates_confirmed_missing_entry(
    tmp_path, monkeypatch, isolated_user_home, provider, state
):
    directory = tmp_path / "keys"
    marker_dir = (
        isolated_user_home / ".local/share/arknights-mower/credential-service-lock"
    )
    marker_dir.mkdir(parents=True)
    marker = marker_dir / f"{provider}.initialized"
    marker.write_bytes(b"original-marker")
    original = base64.b64encode(os.urandom(96)) if state == "healthy" else b"corrupt"
    values = {"key": original if state in ("healthy", "corrupt") else None}
    creations = []

    def lookup(create):
        if state == "locked":
            raise store.CredentialStoreError("系统密钥服务已锁定")
        if values["key"] is None:
            if not create:
                raise store._MissingPrivateKey("synthetic missing entry")
            creations.append(True)
            values["key"] = base64.b64encode(os.urandom(96))
        return values["key"]

    monkeypatch.delenv("MOWER_CREDENTIAL_KEY_FILE")
    monkeypatch.setattr(store, "_provider", lambda: provider)
    monkeypatch.setattr(store, "_private_directory", lambda: directory)
    monkeypatch.setattr(
        store, "_mac_key" if provider == "keychain" else "_secret_service_key", lookup
    )
    if state in ("corrupt", "locked"):
        with pytest.raises(store.CredentialStoreError, match="损坏|锁定"):
            store.recover_private_key()
        assert not creations
        assert values["key"] == (original if state == "corrupt" else None)
    else:
        result = store.recover_private_key()
        assert result["changed"] is (state == "missing")
        assert result["created"] is (state == "missing")
        assert len(creations) == (1 if state == "missing" else 0)
        ciphertext = store.encode_credentials({"token": "synthetic"})
        assert store.decode_credentials(ciphertext) == {"token": "synthetic"}
    assert marker.read_bytes() == b"original-marker"


@pytest.mark.parametrize(
    "returncode,stdout,stderr,missing",
    [(1, b"", b"", True), (0, b"", b"", False), (1, b"", b"service locked", False)],
)
def test_secret_service_missing_entry_is_distinct_from_empty_or_locked(
    monkeypatch, returncode, stdout, stderr, missing
):
    calls = []

    def run(command, **kwargs):
        calls.append(command)
        return subprocess.CompletedProcess(command, returncode, stdout, stderr)

    monkeypatch.setattr(store.shutil, "which", lambda _: "synthetic-secret-tool")
    monkeypatch.setattr(store.subprocess, "run", run)
    error = store._MissingPrivateKey if missing else store.CredentialStoreError
    with pytest.raises(error) as caught:
        store._secret_service_key(False)
    assert isinstance(caught.value, store._MissingPrivateKey) is missing
    assert len(calls) == 1
    assert calls[0][1] == "lookup"


@pytest.mark.parametrize("status,missing", [(-25300, True), (-25293, False)])
def test_keychain_missing_entry_is_distinct_from_access_denied(
    monkeypatch, status, missing
):
    calls = []

    class Function:
        def __call__(self, *args):
            calls.append("lookup")
            return status

    security = SimpleNamespace(
        SecKeychainFindGenericPassword=Function(),
        SecKeychainItemFreeContent=Function(),
    )
    monkeypatch.setattr(store.sys, "platform", "darwin")
    monkeypatch.setattr(store.ctypes, "CDLL", lambda _: security)
    with pytest.raises(store.CredentialStoreError) as caught:
        store._mac_key(False)
    assert isinstance(caught.value, store._MissingPrivateKey) is missing
    assert calls == ["lookup"]


@pytest.mark.parametrize("provider", ["keychain", "secret-service"])
def test_failed_system_marker_write_keeps_created_entry_for_retry(
    tmp_path, monkeypatch, provider
):
    values = {"key": None, "created": 0}

    def lookup(create):
        if values["key"] is None:
            if not create:
                raise store._MissingPrivateKey("synthetic missing entry")
            values["key"] = base64.b64encode(os.urandom(96))
            values["created"] += 1
        return values["key"]

    monkeypatch.delenv("MOWER_CREDENTIAL_KEY_FILE")
    monkeypatch.setattr(store, "_provider", lambda: provider)
    monkeypatch.setattr(store, "_private_directory", lambda: tmp_path / "keys")
    monkeypatch.setattr(
        store, "_mac_key" if provider == "keychain" else "_secret_service_key", lookup
    )
    atomic = store._atomic_bytes

    def fail_marker(*args):
        raise OSError("synthetic marker failure")

    monkeypatch.setattr(store, "_atomic_bytes", fail_marker)
    with pytest.raises(store.CredentialStoreError):
        store.recover_private_key()
    original = values["key"]
    assert original is not None
    monkeypatch.setattr(store, "_atomic_bytes", atomic)
    result = store.recover_private_key()
    assert result["changed"] is False
    assert values["key"] == original
    assert values["created"] == 1


def test_missing_hybrid_backend_never_changes_a_damaged_key(file_provider, monkeypatch):
    _, directory, private_path = file_provider
    directory.mkdir()
    private_path.write_bytes(b"original-corrupt-key")
    private_path.chmod(0o600)

    def unavailable(*args):
        raise UnsupportedAlgorithm("synthetic unsupported backend")

    monkeypatch.setattr(store, "_hybrid_private", unavailable)
    with pytest.raises(store.CredentialStoreError, match="运行环境"):
        store.recover_private_key()
    assert private_path.read_bytes() == b"original-corrupt-key"
    assert not list(directory.glob("*.quarantined"))
    assert not list(directory.glob("*.initialized"))
