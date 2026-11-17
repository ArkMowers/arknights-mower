"""System credential providers preserve their original key across new files."""

import base64
import json
import os
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

from arknights_mower.utils import credential_store as store


@pytest.fixture(autouse=True)
def isolated_user_home(tmp_path, monkeypatch):
    home = tmp_path / "home"
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: home))
    return home


@pytest.fixture(params=["keychain", "secret-service"])
def system_provider(request, tmp_path, monkeypatch):
    monkeypatch.delenv("MOWER_CREDENTIAL_KEY_FILE")
    provider = request.param
    directory = tmp_path / "private-keys"
    state = {"key": None, "created": 0}

    def lookup(create):
        if state["key"] is None:
            if not create:
                raise store.CredentialStoreError("synthetic system key unavailable")
            state["key"] = base64.b64encode(os.urandom(96))
            state["created"] += 1
        return state["key"]

    monkeypatch.setattr(store, "_private_directory", lambda: directory)
    monkeypatch.setattr(store, "_provider", lambda: provider)
    monkeypatch.setattr(
        store,
        "_mac_key" if provider == "keychain" else "_secret_service_key",
        lookup,
    )
    return provider, directory, state


def test_first_system_key_is_reused_for_all_credential_files(tmp_path, system_provider):
    provider, directory, state = system_provider
    first = tmp_path / "mower.secrets.json"
    second = tmp_path / "network.secrets.json"
    store.write_credentials(first, {"token": "first-token"})
    original_key = state["key"]
    store.write_credentials(second, {"token": "second-token"})
    assert state["created"] == 1
    assert state["key"] == original_key
    assert (directory / f"{provider}.initialized").is_file()
    assert store.read_credentials(first) == {"token": "first-token"}
    assert store.read_credentials(second) == {"token": "second-token"}
    assert b"first-token" not in first.read_bytes()
    assert b"second-token" not in second.read_bytes()
    assert not (directory / "private.key").exists()


def test_existing_system_key_gets_marker_without_replacement(tmp_path, system_provider):
    provider, directory, state = system_provider
    original_key = base64.b64encode(os.urandom(96))
    state["key"] = original_key
    path = tmp_path / "mower.secrets.json"
    store.write_credentials(path, {"token": "existing-key-token"})
    assert state["key"] == original_key
    assert state["created"] == 0
    assert (directory / f"{provider}.initialized").is_file()
    assert store.read_credentials(path) == {"token": "existing-key-token"}


def test_missing_system_key_cannot_be_recreated_by_a_new_file(
    tmp_path, system_provider
):
    _, _, state = system_provider
    first = tmp_path / "mower.secrets.json"
    second = tmp_path / "network.secrets.json"
    store.write_credentials(first, {"token": "original-token"})
    original_ciphertext = first.read_bytes()
    original_key = state["key"]
    state["key"] = None
    for path in (first, second):
        with pytest.raises(store.CredentialStoreError, match="unavailable"):
            store.write_credentials(path, {"token": "replacement-token"})
    assert state["created"] == 1
    assert state["key"] is None
    assert first.read_bytes() == original_ciphertext
    assert not second.exists()
    state["key"] = original_key
    assert store.read_credentials(first) == {"token": "original-token"}


def test_initialization_markers_are_separate_for_each_provider(
    tmp_path, system_provider
):
    provider, directory, state = system_provider
    directory.mkdir()
    other = "secret-service" if provider == "keychain" else "keychain"
    (directory / f"{other}.initialized").write_text("initialized")
    path = tmp_path / "mower.secrets.json"
    store.write_credentials(path, {"token": "provider-token"})
    assert state["created"] == 1
    assert (directory / f"{provider}.initialized").exists()
    assert store.read_credentials(path) == {"token": "provider-token"}


def test_concurrent_system_provider_initialization_keeps_one_key(
    tmp_path, system_provider
):
    _, _, state = system_provider
    paths = [tmp_path / f"worker-{index}.secrets.json" for index in range(8)]
    with ThreadPoolExecutor(max_workers=8) as executor:
        list(
            executor.map(
                lambda path: store.write_credentials(path, {"token": path.name}), paths
            )
        )
    assert state["created"] == 1
    assert len({json.loads(path.read_bytes())["key_id"] for path in paths}) == 1
    for path in paths:
        assert store.read_credentials(path) == {"token": path.name}


def test_invalid_system_key_does_not_mark_provider_initialized(
    tmp_path, system_provider
):
    provider, directory, state = system_provider
    state["key"] = base64.b64encode(os.urandom(32))
    path = tmp_path / "mower.secrets.json"
    with pytest.raises(store.CredentialStoreError):
        store.write_credentials(path, {"token": "value"})
    assert state["created"] == 0
    assert not path.exists()
    assert not (directory / f"{provider}.initialized").exists()


@pytest.mark.parametrize("provider", ["local-key", "dpapi"])
def test_processes_initialize_one_private_key_and_keep_it(
    tmp_path, monkeypatch, provider
):
    if provider == "dpapi" and sys.platform != "win32":
        pytest.skip("Native Windows DPAPI")
    monkeypatch.delenv("MOWER_CREDENTIAL_KEY_FILE")
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "private-data"))
    monkeypatch.setattr(store, "_provider", lambda: provider)
    root = Path(store.__file__).resolve().parents[2]
    script = """
import json
import sys
from pathlib import Path
sys.path.insert(0, sys.argv[1])
from arknights_mower.utils import credential_store as store
store._provider = lambda: sys.argv[2]
sys.stdin.readline()
target = Path(sys.argv[3])
store.write_credentials(target, {'token': target.name})
print(json.loads(target.read_bytes())['key_id'])
"""
    paths = [tmp_path / f"process-{index}.secrets.json" for index in range(6)]
    children = []
    try:
        for path in paths:
            children.append(
                subprocess.Popen(
                    [
                        sys.executable,
                        "-I",
                        "-c",
                        script,
                        str(root),
                        provider,
                        str(path),
                    ],
                    stdin=subprocess.PIPE,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                    cwd=tmp_path,
                    env=dict(os.environ),
                    creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
                )
            )
        with ThreadPoolExecutor(max_workers=len(children)) as executor:
            outputs = list(
                executor.map(
                    lambda child: child.communicate("start\n", timeout=30), children
                )
            )
        assert all(child.returncode == 0 for child in children), [
            error for _, error in outputs
        ]
        assert len({out.strip() for out, _ in outputs}) == 1
        key_file = store._private_directory() / (
            "private.dpapi" if provider == "dpapi" else "private.key"
        )
        original = key_file.read_bytes()
        for path in paths:
            assert store.read_credentials(path) == {"token": path.name}
        store.write_credentials(paths[0], {"token": "replacement"})
        assert key_file.read_bytes() == original
        assert (key_file.parent / f"{provider}.initialized").exists()
        if os.name != "nt":
            assert key_file.stat().st_mode & 0o777 == 0o600
            assert key_file.parent.stat().st_mode & 0o777 == 0o700
        key_file.unlink()
        new_file = tmp_path / "new.secrets.json"
        with pytest.raises(store.CredentialStoreError, match="密钥已丢失"):
            store.write_credentials(new_file, {"token": "must-not-save"})
        assert not new_file.exists()
        assert not key_file.exists()
    finally:
        for child in children:
            if child.poll() is None:
                child.kill()
            child.wait(timeout=10)


def test_private_marker_symlink_cannot_authorize_key_initialization(
    tmp_path, monkeypatch
):
    directory = tmp_path / "private-data"
    directory.mkdir()
    marker = directory / "local-key.initialized"
    try:
        marker.symlink_to(tmp_path / "absent-marker")
    except OSError:
        pytest.skip("Creating symlinks is unavailable for this user")
    monkeypatch.delenv("MOWER_CREDENTIAL_KEY_FILE")
    monkeypatch.setattr(store, "_private_directory", lambda: directory)
    monkeypatch.setattr(store, "_provider", lambda: "local-key")
    with pytest.raises(store.CredentialStoreError, match="符号链接"):
        store.write_credentials(tmp_path / "mower.secrets.json", {"token": "value"})
    assert not (directory / "private.key").exists()
    assert marker.is_symlink()


def test_explicit_private_key_restores_system_ciphertext_without_rewriting(
    tmp_path, system_provider, monkeypatch
):
    _, _, state = system_provider
    path = tmp_path / "mower.secrets.json"
    store.write_credentials(path, {"token": "restorable"})
    original = path.read_bytes()
    private_file = tmp_path / "restored.key"
    private_file.write_bytes(state["key"])
    private_file.chmod(0o600)
    state["key"] = None
    monkeypatch.setenv("MOWER_CREDENTIAL_KEY_FILE", str(private_file))
    assert store.read_credentials(path) == {"token": "restorable"}
    assert path.read_bytes() == original
    private_file.write_bytes(base64.b64encode(os.urandom(96)))
    with pytest.raises(store.CredentialStoreError, match="不匹配"):
        store.read_credentials(path)
    assert path.read_bytes() == original
    assert state["key"] is None


@pytest.mark.parametrize("provider", ["keychain", "secret-service"])
def test_system_key_read_does_not_create_lock_directory(
    tmp_path, isolated_user_home, monkeypatch, provider
):
    monkeypatch.delenv("MOWER_CREDENTIAL_KEY_FILE")
    private = os.urandom(96)
    monkeypatch.setattr(store, "_private_directory", lambda: tmp_path / "metadata")
    monkeypatch.setattr(
        store,
        "_mac_key" if provider == "keychain" else "_secret_service_key",
        lambda create: base64.b64encode(private),
    )
    assert store._key(provider) == private
    assert not isolated_user_home.exists()
    assert not (tmp_path / "metadata").exists()


@pytest.mark.parametrize("operation", ["initialize", "recover"])
def test_linked_system_lock_directory_never_reaches_key_service(
    tmp_path, isolated_user_home, monkeypatch, operation
):
    lock = isolated_user_home / ".local/share/arknights-mower/credential-service-lock"
    lock.parent.mkdir(parents=True)
    outside = tmp_path / "outside"
    outside.mkdir()
    try:
        lock.symlink_to(outside, target_is_directory=True)
    except OSError:
        pytest.skip("Creating symlinks is unavailable for this user")
    monkeypatch.delenv("MOWER_CREDENTIAL_KEY_FILE")
    monkeypatch.setattr(store, "_provider", lambda: "secret-service")
    monkeypatch.setattr(store, "_private_directory", lambda: tmp_path / "metadata")

    def forbidden(create):
        raise AssertionError("Unsafe lock must not reach the system key service")

    monkeypatch.setattr(store, "_secret_service_key", forbidden)
    with pytest.raises(store.CredentialStoreError, match="符号链接"):
        if operation == "recover":
            store.recover_private_key()
        else:
            store._key("secret-service", create=True)
    assert list(outside.iterdir()) == []


@pytest.mark.parametrize("first_operation", ["initialize", "recover"])
@pytest.mark.parametrize("second_operation", ["initialize", "recover"])
def test_system_key_creation_is_exclusive_across_processes_with_different_xdg_roots(
    tmp_path, isolated_user_home, monkeypatch, first_operation, second_operation
):
    import cryptography

    monkeypatch.delenv("MOWER_CREDENTIAL_KEY_FILE")
    root = Path(store.__file__).resolve().parents[2]
    crypto_root = Path(cryptography.__file__).parent.parent
    service = tmp_path / "simulated-service.key"
    script = """
import base64
import os
import sys
from pathlib import Path
sys.path[:0] = [sys.argv[1], sys.argv[2]]
from arknights_mower.utils import credential_store as store
home, service = Path(sys.argv[3]), Path(sys.argv[4])
Path.home = classmethod(lambda cls: home)
os.environ['XDG_DATA_HOME'] = sys.argv[5]
operation, mode = sys.argv[6:8]
store._provider = lambda: 'secret-service'

def lookup(create):
    if service.exists():
        return service.read_bytes()
    if not create:
        raise store._MissingPrivateKey('synthetic missing service entry')
    if mode == 'hold':
        print('waiting-for-release', flush=True)
        sys.stdin.readline()
    key = base64.b64encode(os.urandom(96))
    service.write_bytes(key)
    return key

store._secret_service_key = lookup
if mode == 'probe':
    original_lock = store.update_runtime.supervision_lock
    store.update_runtime.supervision_lock = lambda directory, **kw: original_lock(directory, timeout=0)
try:
    if operation == 'recover':
        key_id = store.recover_private_key()['key_id']
    else:
        key_id = store._hybrid_private(store._key('secret-service', create=True))[2]
except RuntimeError:
    if mode != 'probe':
        raise
    print('blocked', flush=True)
else:
    print(key_id, flush=True)
"""

    def command(operation, mode, data):
        return [
            sys.executable,
            "-I",
            "-c",
            script,
            str(root),
            str(crypto_root),
            str(isolated_user_home),
            str(service),
            str(data),
            operation,
            mode,
        ]

    options = dict(
        text=True,
        cwd=tmp_path,
        env=dict(os.environ),
        creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
    )
    holder = subprocess.Popen(
        command(first_operation, "hold", tmp_path / "first-xdg"),
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        **options,
    )
    try:
        with ThreadPoolExecutor(max_workers=1) as executor:
            ready = executor.submit(holder.stdout.readline)
            try:
                assert ready.result(timeout=15).strip() == "waiting-for-release"
            except BaseException:
                holder.kill()
                raise
        probe = subprocess.run(
            command(second_operation, "probe", tmp_path / "second-xdg"),
            capture_output=True,
            timeout=15,
            **options,
        )
        assert probe.returncode == 0, probe.stderr
        assert probe.stdout.strip() == "blocked"
        assert not service.exists()
        output, error = holder.communicate("release\n", timeout=15)
        assert holder.returncode == 0, error
        original = service.read_bytes()
        resumed = subprocess.run(
            command(second_operation, "resume", tmp_path / "second-xdg"),
            capture_output=True,
            timeout=15,
            **options,
        )
        assert resumed.returncode == 0, resumed.stderr
        assert resumed.stdout.strip() == output.strip()
        assert service.read_bytes() == original
        for name in ("first-xdg", "second-xdg"):
            assert (
                tmp_path
                / name
                / "arknights-mower/credentials/secret-service.initialized"
            ).is_file()
        if os.name != "nt":
            lock = (
                isolated_user_home
                / ".local/share/arknights-mower/credential-service-lock"
            )
            assert lock.stat().st_mode & 0o777 == 0o700
    finally:
        if holder.poll() is None:
            holder.kill()
        holder.wait(timeout=10)
