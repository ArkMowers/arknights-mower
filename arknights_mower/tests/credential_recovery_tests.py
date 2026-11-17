"""Offline recovery preserves configuration and requires explicit authenticated consent."""

import builtins
import json
import os
import runpy
import subprocess
import sys
import threading
from pathlib import Path
from queue import Queue
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from arknights_mower.utils import credential_recovery as recovery
from arknights_mower.utils import credential_store as store


@pytest.fixture
def environment(tmp_path, monkeypatch):
    monkeypatch.delenv("MOWER_CREDENTIAL_KEY_FILE", raising=False)
    monkeypatch.setattr(store, "_provider", lambda: "local-key")
    key_dir = tmp_path / "keys"
    monkeypatch.setattr(store, "_private_directory", lambda: key_dir)
    monkeypatch.setattr(recovery.update_runtime, "instances", lambda **kwargs: [])
    shared = tmp_path / "data"
    instance = shared / "instance"
    instance.mkdir(parents=True)
    app = recovery.create_app(instance, shared, token="recovery-session-token")
    return SimpleNamespace(
        app=app,
        client=app.test_client(),
        service=app.extensions["credential_recovery"],
        shared=shared,
        instance=instance,
        key_dir=key_dir,
        headers={"token": app.token},
    )


def _reset(environment, **changes):
    data = dict(
        generation=environment.service.inspect()["generation"],
        confirmation=recovery.CONFIRMATION,
    )
    data.update(changes)
    return environment.client.post(
        "/recovery/reset", headers=environment.headers, json=data
    )


@pytest.mark.parametrize(
    "method,path",
    [
        ("GET", "/status"),
        ("HEAD", "/status"),
        ("GET", "/recovery/status"),
        ("HEAD", "/recovery/status"),
        ("POST", "/recovery/reset"),
        ("POST", "/recovery/close"),
    ],
)
@pytest.mark.parametrize("token", [None, "wrong-token"])
def test_auth_precedes_parsing_file_reads_and_actions(
    environment, monkeypatch, method, path, token
):
    def forbidden(*args, **kwargs):
        pytest.fail("Unauthenticated recovery performed work")

    monkeypatch.setattr(environment.service, "inspect", forbidden)
    monkeypatch.setattr(environment.service, "reset", forbidden)
    response = environment.client.open(
        path,
        method=method,
        headers={} if token is None else {"token": token},
        data=b"{invalid",
        content_type="application/json",
    )
    assert response.status_code == 403
    assert not environment.app.extensions["recovery_stop"].is_set()


def test_static_shell_contains_no_session_or_instance_data(environment):
    response = environment.client.get("/")
    assert response.status_code == 200
    assert environment.app.token.encode() not in response.data
    assert str(environment.instance).encode() not in response.data
    assert response.headers["Cache-Control"] == "no-store"
    assert response.headers["Referrer-Policy"] == "no-referrer"
    assert "frame-ancestors 'none'" in response.headers["Content-Security-Policy"]
    assert b"location.hash" in response.data
    assert b"history.replaceState" in response.data
    assert b"sessionStorage" not in response.data


@pytest.mark.parametrize("token", ["", " ", 123])
def test_recovery_cannot_use_empty_or_nonstring_auth(tmp_path, token):
    with pytest.raises(ValueError, match="非空访问令牌"):
        recovery.create_app(tmp_path, tmp_path, token=token)


def test_random_token_and_authenticated_close(environment):
    one = recovery.create_app(environment.instance, environment.shared)
    two = recovery.create_app(environment.instance, environment.shared)
    assert len(one.token) >= 32
    assert one.token != two.token
    response = environment.client.post("/recovery/close", headers=environment.headers)
    assert response.status_code == 200
    assert environment.app.extensions["recovery_stop"].is_set()


def test_missing_private_key_archives_only_known_current_and_shared_credentials(
    environment,
):
    selected = [
        environment.instance / "mower.secrets.json",
        environment.instance / "legacy-mower.secrets.json",
        environment.instance / "yituliu.secrets.json",
        environment.instance / "config-profiles" / ("a" * 32 + ".secrets.json"),
        environment.shared / "network.secrets.json",
        environment.shared / "ai.secrets.json",
    ]
    for path in selected:
        store.write_credentials(path, {"token": "synthetic-private-token"})
    originals = {path: path.read_bytes() for path in selected}
    preserved = [
        environment.instance / "config/conf.yml",
        environment.instance / "plan.json",
        environment.instance / "data.db",
        environment.instance / "config-profiles" / ("a" * 32 + ".zip"),
        environment.instance / "other.secrets.json",
        environment.shared / "another-instance/mower.secrets.json",
        environment.instance / "credential-recovery/older/mower.secrets.json",
    ]
    for path in preserved:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"preserved-user-data")
    (environment.key_dir / "private.key").unlink()
    status = environment.client.get("/recovery/status", headers=environment.headers)
    assert status.status_code == 200
    assert len(status.json["files"]) == len(selected)
    assert all(item["state"] == "unreadable" for item in status.json["files"])
    assert b"synthetic-private-token" not in status.data
    assert not (environment.key_dir / "private.key").exists()
    response = _reset(environment)
    assert response.status_code == 200
    assert response.json["key"]["created"] is True
    assert len(response.json["archived"]) == len(selected)
    for source, raw in originals.items():
        assert not source.exists()
        assert any(
            Path(target).read_bytes() == raw for target in response.json["archived"]
        )
    assert all(path.read_bytes() == b"preserved-user-data" for path in preserved)
    assert environment.service.inspect()["files"] == []


def test_readable_credentials_and_private_key_are_preserved(environment):
    readable = environment.instance / "mower.secrets.json"
    store.write_credentials(readable, {"token": "keep-me"})
    original = readable.read_bytes()
    private = (environment.key_dir / "private.key").read_bytes()
    broken = environment.shared / "network.secrets.json"
    broken.write_bytes(b"damaged encrypted envelope")
    response = _reset(environment)
    assert response.status_code == 200
    assert response.json["key"]["changed"] is False
    assert readable.read_bytes() == original
    assert store.read_credentials(readable) == {"token": "keep-me"}
    assert (environment.key_dir / "private.key").read_bytes() == private
    assert not broken.exists()
    assert len(response.json["archived"]) == 1


@pytest.mark.parametrize("confirmation", [None, "", "yes", "重置"])
def test_explicit_reset_confirmation_required(environment, monkeypatch, confirmation):
    change = Mock(side_effect=AssertionError("private key touched"))
    monkeypatch.setattr(store, "recover_private_key", change)
    response = _reset(environment, confirmation=confirmation)
    assert response.status_code == 400
    change.assert_not_called()
    assert not (environment.instance / "credential-recovery").exists()


def test_generation_change_does_not_reset_key_or_credentials(environment, monkeypatch):
    before = environment.service.inspect()["generation"]
    path = environment.instance / "mower.secrets.json"
    path.write_bytes(b"changed ciphertext")
    change = Mock(side_effect=AssertionError("private key touched"))
    monkeypatch.setattr(store, "recover_private_key", change)
    response = _reset(environment, generation=before)
    assert response.status_code == 409
    assert path.read_bytes() == b"changed ciphertext"
    change.assert_not_called()


def test_key_recovery_failure_keeps_all_original_ciphertext(environment, monkeypatch):
    path = environment.instance / "mower.secrets.json"
    path.write_bytes(b"unreadable encrypted data")
    monkeypatch.setattr(
        store,
        "recover_private_key",
        Mock(side_effect=store.CredentialStoreError("locked")),
    )
    response = _reset(environment)
    assert response.status_code == 400
    assert path.read_bytes() == b"unreadable encrypted data"


def test_key_becomes_available_during_recovery_preserves_newly_readable_ciphertext(
    environment, monkeypatch
):
    path = environment.instance / "mower.secrets.json"
    store.write_credentials(path, {"token": "restored"})
    raw = path.read_bytes()
    private = (environment.key_dir / "private.key").read_bytes()
    (environment.key_dir / "private.key").unlink()
    recover = store.recover_private_key

    def restore_original():
        store._atomic_bytes(environment.key_dir / "private.key", private)
        return recover()

    monkeypatch.setattr(store, "recover_private_key", restore_original)
    response = _reset(environment)
    assert response.status_code == 200
    assert response.json["archived"] == []
    assert path.read_bytes() == raw
    assert store.read_credentials(path) == {"token": "restored"}


def test_archive_move_failure_rolls_back_preceding_files(environment, monkeypatch):
    paths = [
        environment.instance / name
        for name in ("mower.secrets.json", "yituliu.secrets.json")
    ]
    for path in paths:
        path.write_bytes(b"damaged-ciphertext")
    store.recover_private_key()
    replace = os.replace

    def fail_second(source, target):
        if Path(source) == paths[1]:
            raise OSError("archive failed")
        return replace(source, target)

    monkeypatch.setattr(os, "replace", fail_second)
    response = _reset(environment)
    assert response.status_code == 400
    assert all(path.read_bytes() == b"damaged-ciphertext" for path in paths)


def test_rollback_failure_reports_retained_ciphertext_and_restores_remaining_files(
    environment, monkeypatch
):
    paths = [
        environment.instance / name
        for name in (
            "mower.secrets.json",
            "legacy-mower.secrets.json",
            "yituliu.secrets.json",
        )
    ]
    for path in paths:
        path.write_bytes(b"damaged-ciphertext")
    store.recover_private_key()
    replace = os.replace

    def failures(source, target):
        if Path(source) == paths[2] or Path(target) == paths[1]:
            raise OSError("filesystem unavailable")
        return replace(source, target)

    monkeypatch.setattr(os, "replace", failures)
    response = _reset(environment)
    assert response.status_code == 400
    assert "部分密文无法移回原位置" in response.json["error"]
    assert paths[0].read_bytes() == paths[2].read_bytes() == b"damaged-ciphertext"
    assert not paths[1].exists()
    retained = list(
        (environment.instance / "credential-recovery").glob(
            "*/legacy-mower.secrets.json"
        )
    )
    assert len(retained) == 1
    assert retained[0].read_bytes() == b"damaged-ciphertext"
    assert str(retained[0]) in response.json["error"]


def test_different_instance_recovery_uses_shared_reset_lock(environment):
    another = recovery.Recovery(environment.shared / "another", environment.shared)
    lock = environment.shared / "credential-recovery"
    with recovery.update_runtime.supervision_lock(lock, timeout=0):
        for service in (environment.service, another):
            generation = service.inspect()["generation"]
            with pytest.raises(recovery.RecoveryConflict, match="另一个凭据恢复操作"):
                service.reset(generation, recovery.CONFIRMATION)
    assert not environment.key_dir.exists()


def test_recovery_lock_cannot_write_through_symlink(environment, tmp_path):
    outside = tmp_path / "untouched-lock-target"
    outside.write_bytes(b"")
    archive = environment.shared / "credential-recovery"
    archive.mkdir()
    try:
        (archive / "instance.lock").symlink_to(outside)
    except OSError:
        pytest.skip("symbolic links unavailable")
    response = _reset(environment)
    assert response.status_code == 400
    assert outside.read_bytes() == b""
    assert not environment.key_dir.exists()


def test_symbolic_links_never_reset_or_follow_outside_instance(environment, tmp_path):
    outside = tmp_path / "outside"
    outside.write_bytes(b"untouched")
    link = environment.instance / "mower.secrets.json"
    try:
        link.symlink_to(outside)
    except OSError:
        pytest.skip("symbolic links unavailable")
    response = _reset(environment)
    assert response.status_code == 409
    assert outside.read_bytes() == b"untouched"
    assert link.is_symlink()
    assert not environment.key_dir.exists()


@pytest.mark.parametrize("directory", ["config-profiles", "credential-recovery"])
def test_linked_subdirectories_are_refused(environment, tmp_path, directory):
    outside = tmp_path / "outside-dir"
    outside.mkdir()
    try:
        (environment.instance / directory).symlink_to(outside, target_is_directory=True)
    except OSError:
        pytest.skip("symbolic links unavailable")
    if directory == "config-profiles":
        response = environment.client.get(
            "/recovery/status", headers=environment.headers
        )
    else:
        (environment.instance / "mower.secrets.json").write_bytes(b"damaged-ciphertext")
        response = _reset(environment)
    assert response.status_code == 400
    assert list(outside.iterdir()) == []


def test_other_running_instance_blocks_shared_reset(environment, monkeypatch):
    (environment.shared / "network.secrets.json").write_bytes(b"old-encrypted-data")
    monkeypatch.setattr(
        recovery.update_runtime,
        "instances",
        lambda **kwargs: [
            dict(
                kind="instance",
                pid=os.getpid() + 1,
                data_dir=str(environment.shared),
                space="other",
            )
        ],
    )
    response = _reset(environment)
    assert response.status_code == 409
    assert not environment.key_dir.exists()


def test_module_and_cli_help_do_not_import_application_config(tmp_path):
    source = """
import builtins, sys
original = builtins.__import__
def guarded(name, *args, **kwargs):
    if name == 'server' or name.startswith('arknights_mower.utils.config'):
        raise AssertionError('application configuration imported')
    return original(name, *args, **kwargs)
builtins.__import__ = guarded
from arknights_mower.utils.credential_recovery import create_app, main
app = create_app(sys.argv[1], sys.argv[1])
assert app.test_client().get('/').status_code == 200
assert app.test_client().get('/recovery/status').status_code == 403
assert 'arknights_mower.utils.config' not in sys.modules
main(['--help'])
"""
    result = subprocess.run(
        [sys.executable, "-c", source, str(tmp_path)],
        capture_output=True,
        text=True,
        timeout=20,
        env={**os.environ, "MOWER_DATA_DIR": str(tmp_path)},
    )
    assert result.returncode == 0, result.stderr
    assert "--host" in result.stdout


def test_cli_requires_explicit_remote_bind_and_resolves_instance(
    environment, monkeypatch
):
    serve = Mock()
    monkeypatch.setattr(recovery, "serve", serve)
    recovery.main(["--instance", str(environment.instance)])
    assert serve.call_args.kwargs == dict(host="127.0.0.1", port=0, desktop=False)
    recovery.main(
        [
            "--instance",
            str(environment.instance),
            "--host",
            "0.0.0.0",
            "--port",
            "58123",
        ]
    )
    assert serve.call_args.kwargs == dict(host="0.0.0.0", port=58123, desktop=False)


def test_manual_windows_frozen_entry_opens_recovery_window_without_stdout(
    environment, monkeypatch
):
    class ClosedEvent:
        def __init__(self):
            self.handlers = []

        def __iadd__(self, callback):
            self.handlers.append(callback)
            return self

        def emit(self):
            for handler in self.handlers:
                handler()

    closed = ClosedEvent()
    window = SimpleNamespace(events=SimpleNamespace(closed=closed), destroy=Mock())
    webview = SimpleNamespace(
        create_window=Mock(return_value=window), start=closed.emit
    )
    monkeypatch.setitem(sys.modules, "webview", webview)
    monkeypatch.setattr(sys, "platform", "win32")
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "stdout", None)
    monkeypatch.setattr(
        builtins,
        "print",
        Mock(side_effect=AssertionError("windowed launcher must open a window")),
    )
    launcher = Path(__file__).resolve().parents[2] / "webview_ui.py"
    monkeypatch.setattr(
        sys,
        "argv",
        [
            str(launcher),
            "--credential-recovery",
            "--instance",
            str(environment.instance),
        ],
    )
    with pytest.raises(SystemExit) as error:
        runpy.run_path(str(launcher), run_name="__main__")
    assert error.value.code is None
    webview.create_window.assert_called_once()
    title, url = webview.create_window.call_args.args
    assert title == "Mower 凭据恢复"
    assert url.startswith("http://127.0.0.1:")
    assert "/#token=" in url
    assert len(url.split("#token=", 1)[1]) >= 32


@pytest.mark.parametrize(
    "platform_name,display,expected",
    [
        ("darwin", None, True),
        ("linux", "DISPLAY", True),
        ("linux", "WAYLAND_DISPLAY", True),
        ("linux", None, False),
    ],
)
def test_manual_entry_selects_desktop_only_when_available(
    environment, monkeypatch, platform_name, display, expected
):
    monkeypatch.setattr(sys, "platform", platform_name)
    monkeypatch.delenv("DISPLAY", raising=False)
    monkeypatch.delenv("WAYLAND_DISPLAY", raising=False)
    if display:
        monkeypatch.setenv(display, "test-display")
    serve = Mock()
    monkeypatch.setattr(recovery, "serve", serve)
    launcher = Path(__file__).resolve().parents[2] / "webview_ui.py"
    monkeypatch.setattr(
        sys,
        "argv",
        [
            str(launcher),
            "--credential-recovery",
            "--instance",
            str(environment.instance),
        ],
    )
    with pytest.raises(SystemExit):
        runpy.run_path(str(launcher), run_name="__main__")
    assert serve.call_args.kwargs["desktop"] is expected


@pytest.mark.parametrize("desktop,args", [(False, []), (True, ["--headless"])])
def test_python_cli_and_explicit_headless_keep_printed_fragment_url(
    environment, monkeypatch, capsys, desktop, args
):
    environment.app.extensions["recovery_stop"].set()
    monkeypatch.setattr(recovery, "create_app", lambda *args: environment.app)
    webview = SimpleNamespace(
        create_window=Mock(side_effect=AssertionError("headless mode opened a window"))
    )
    monkeypatch.setitem(sys.modules, "webview", webview)
    recovery.main(["--instance", str(environment.instance), *args], desktop=desktop)
    output = capsys.readouterr()
    assert "凭据恢复入口：http://127.0.0.1:" in output.out
    assert "#token=" + environment.app.token in output.out
    assert environment.app.token not in output.err
    webview.create_window.assert_not_called()


def test_desktop_recovery_reports_ready_without_loading_config(
    environment, monkeypatch
):
    import webview_ui
    from arknights_mower.utils import instance_supervisor, path

    report = Mock()
    monkeypatch.setattr(instance_supervisor, "child_report", report)
    monkeypatch.setattr(webview_ui, "close_child", Mock())
    monkeypatch.setattr(webview_ui, "close_channel", Mock())
    monkeypatch.setattr(path, "_data_dir", environment.shared)
    monkeypatch.setattr(path, "global_space", str(environment.instance))
    registration = Mock(record={}, request=environment.instance / "shutdown")

    def serve(instance, shared, **options):
        assert Path(instance) == environment.instance
        assert Path(shared) == environment.shared
        assert options["desktop"] is True
        options["on_ready"](58124, "ephemeral-recovery-token")

    monkeypatch.setattr(recovery, "serve", serve)
    webview_ui.recover_desktop_credentials(registration)
    assert registration.record["ready"] is True
    assert registration.record["credential_recovery"] is True
    assert registration.record["listen_host"] == "127.0.0.1"
    assert "ephemeral-recovery-token" not in str(registration.record)
    assert report.call_args.kwargs["desired_running"] is False


@pytest.mark.parametrize("failure", ["config", "profile"])
def test_docker_bootstrap_preserves_files_and_reports_manual_recovery(
    environment, monkeypatch, capsys, failure
):
    script = Path(__file__).resolve().parents[2] / "docker/entrypoint.sh"
    source = (
        script.read_text(encoding="utf-8")
        .split("python - <<'PY'\n", 1)[1]
        .split("\nPY\n", 1)[0]
    )
    original = builtins.__import__

    def fail_config(name, globals=None, locals=None, fromlist=(), level=0):
        if name == "arknights_mower.utils" and "config" in fromlist:
            if failure == "config":
                raise store.CredentialStoreError("test private key unavailable")
            return SimpleNamespace(config=object())
        if name == "arknights_mower.utils.config_profiles":
            return SimpleNamespace(
                migrate_legacy_profiles=Mock(
                    side_effect=store.CredentialStoreError(
                        "test profile key unavailable"
                    )
                )
            )
        return original(name, globals, locals, fromlist, level)

    monkeypatch.setattr(builtins, "__import__", fail_config)
    with pytest.raises(SystemExit) as error:
        exec(compile(source, str(script), "exec"), {})
    assert error.value.code == 78
    assert (
        "python -m arknights_mower.utils.credential_recovery" in capsys.readouterr().err
    )
    assert list(environment.instance.iterdir()) == []


def test_actual_desktop_config_import_failure_enters_recovery(environment, monkeypatch):
    import webview_ui
    from arknights_mower.utils import lifecycle, log, path

    monkeypatch.setattr(path, "global_space", None)
    monkeypatch.setattr(sys, "argv", ["webview_ui.py", str(environment.instance)])
    monkeypatch.setenv("MOWER_BACKGROUND", "1")
    monkeypatch.setattr(webview_ui, "exit_if_webview_backend_missing", Mock())
    monkeypatch.setattr(lifecycle, "shutdown", lifecycle.Shutdown())
    monkeypatch.setattr(recovery.update_runtime, "read_json", Mock(return_value={}))
    monkeypatch.setattr(recovery.update_runtime, "active_job", Mock(return_value=False))
    registration = Mock(record={})
    monkeypatch.setattr(
        recovery.update_runtime, "RuntimeRegistration", Mock(return_value=registration)
    )
    monkeypatch.setattr(log, "init_file_logging", Mock())
    recover = Mock()
    monkeypatch.setattr(webview_ui, "recover_desktop_credentials", recover)
    original = builtins.__import__

    def fail_config(name, globals=None, locals=None, fromlist=(), level=0):
        if name == "arknights_mower.utils" and "config" in fromlist:
            raise store.CredentialStoreError("missing-private-key")
        assert name != "server", "normal application must not start"
        return original(name, globals, locals, fromlist, level)

    monkeypatch.setattr(builtins, "__import__", fail_config)
    webview_ui._run_desktop()
    recover.assert_called_once_with(registration, None, None)
    assert not environment.key_dir.exists()


def test_real_isolated_listener_closes_and_does_not_log_request_tokens(
    environment, capsys
):
    import http.client
    import socket

    ready = Queue()
    failures = []

    def serve():
        try:
            recovery.serve(
                environment.instance,
                environment.shared,
                on_ready=lambda port, token: ready.put((port, token)),
            )
        except BaseException as error:
            failures.append(error)

    thread = threading.Thread(target=serve, daemon=True)
    thread.start()
    port, token = ready.get(timeout=5)
    client = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
    try:
        client.request("GET", "/status?token=never-log-this-query")
        response = client.getresponse()
        assert response.status == 403
        response.read()
        client.request("GET", "/recovery/status", headers={"token": token})
        response = client.getresponse()
        assert response.status == 200
        assert b"files" in response.read()
    finally:
        client.request("POST", "/recovery/close", headers={"token": token})
        response = client.getresponse()
        assert response.status == 200
        response.read()
        client.close()
        thread.join(5)
    assert not failures
    assert not thread.is_alive()
    output = capsys.readouterr()
    assert "#token=" + token in output.out
    assert "never-log-this-query" not in output.err
    assert token not in output.err
    with socket.socket() as probe:
        probe.settimeout(1)
        assert probe.connect_ex(("127.0.0.1", port)) != 0


def test_server_thread_start_failure_closes_bound_listener(environment, monkeypatch):
    import werkzeug.serving

    server = Mock(server_port=58123)
    monkeypatch.setattr(werkzeug.serving, "make_server", Mock(return_value=server))
    monkeypatch.setattr(
        threading.Thread, "start", Mock(side_effect=RuntimeError("thread unavailable"))
    )
    with pytest.raises(RuntimeError, match="thread unavailable"):
        recovery.serve(environment.instance, environment.shared)
    server.server_close.assert_called_once()
    server.shutdown.assert_not_called()


def test_service_close_waits_for_inflight_reset_transaction(environment, monkeypatch):
    import http.client

    source = environment.instance / "mower.secrets.json"
    source.write_bytes(b"old-ciphertext")
    generation = environment.service.inspect()["generation"]
    entered, release = threading.Event(), threading.Event()
    ready = Queue()
    responses = Queue()
    recover = store.recover_private_key

    def paused_key_recovery():
        entered.set()
        assert release.wait(5), "test did not release credential recovery"
        return recover()

    monkeypatch.setattr(store, "recover_private_key", paused_key_recovery)
    monkeypatch.setattr(recovery, "create_app", lambda *args: environment.app)
    server = threading.Thread(
        target=recovery.serve,
        args=(environment.instance, environment.shared),
        kwargs={"on_ready": lambda port, token: ready.put(port)},
        daemon=True,
    )
    server.start()
    port = ready.get(timeout=5)

    def reset_request():
        client = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
        try:
            client.request(
                "POST",
                "/recovery/reset",
                body=json.dumps(
                    dict(generation=generation, confirmation=recovery.CONFIRMATION)
                ),
                headers={**environment.headers, "Content-Type": "application/json"},
            )
            response = client.getresponse()
            responses.put((response.status, response.read()))
        finally:
            client.close()

    reset = threading.Thread(target=reset_request, daemon=True)
    reset.start()
    try:
        assert entered.wait(3)
        client = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
        try:
            client.request("POST", "/recovery/close", headers=environment.headers)
            response = client.getresponse()
            assert response.status == 200
            response.read()
        finally:
            client.close()
        server.join(0.3)
        assert server.is_alive(), "shutdown must wait for the reset transaction"
        assert source.read_bytes() == b"old-ciphertext"
    finally:
        release.set()
        reset.join(5)
        server.join(5)
    assert not server.is_alive()
    assert not reset.is_alive()
    status, raw = responses.get(timeout=1)
    assert status == 200
    assert not source.exists()
    assert Path(json.loads(raw)["archived"][0]).read_bytes() == b"old-ciphertext"
    assert environment.service.closed is True
