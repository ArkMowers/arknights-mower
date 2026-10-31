"""Application failure paths reach shared sinks without import-order dependencies."""

import os
import subprocess
import sys
from pathlib import Path

import pytest


def run_probe(tmp_path, source, *arguments):
    (tmp_path / "data").mkdir()
    script = tmp_path / "probe.py"
    script.write_text(source, encoding="utf-8")
    root = Path(__file__).parents[2]
    result = subprocess.run(
        [sys.executable, str(script), *arguments],
        cwd=root,
        env={
            **os.environ,
            "MOWER_DATA_DIR": str(tmp_path / "data"),
            "PYTHONPATH": str(root),
            "PYTHONUTF8": "1",
        },
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=30,
    )
    assert result.returncode == 0, result.stdout + result.stderr


@pytest.mark.parametrize("first", ["config", "log", "screenshot", "network_settings"])
def test_import_orders_preserve_config_migration_log(tmp_path, first):
    run_probe(
        tmp_path,
        r"""
import importlib
import os
import sys
from pathlib import Path

root = Path(os.environ['MOWER_DATA_DIR'])
(root / 'conf.yml').write_text('theme: dark\n')
replace = os.replace
def concurrent_move(source, target):
    replace(source, target)
    if Path(source) == root / 'conf.yml':
        raise FileNotFoundError('another process completed migration')
os.replace = concurrent_move
importlib.import_module('arknights_mower.utils.' + sys.argv[1])
from arknights_mower.utils import config, log
assert config.conf.theme == 'dark'
assert '配置已由另一进程迁移' in config.log_queue.get(timeout=3)
assert log.fhlr is None
assert log.get_screenshot_store() is None
log.close_logging()
""",
        first,
    )


def test_config_load_failure_keeps_logging_alive(tmp_path):
    run_probe(
        tmp_path,
        r"""
import importlib
import os
from pathlib import Path
from unittest.mock import patch

import yaml
from arknights_mower.utils import log

root = Path(os.environ['MOWER_DATA_DIR'])
original = 'theme: [invalid]\n'
(root / 'conf.yml').write_text(original)
replace = os.replace
def concurrent_move(source, target):
    replace(source, target)
    if Path(source) == root / 'conf.yml':
        raise FileNotFoundError('another process completed migration')

with patch.object(os, 'replace', concurrent_move), patch.object(
    yaml, 'load', side_effect=ValueError('invalid configuration')
):
    try:
        importlib.import_module('arknights_mower.utils.config')
    except ValueError as exc:
        assert str(exc) == 'invalid configuration'
    else:
        raise AssertionError('invalid config was accepted')
    log.logger.error('config-load-failure-probe')
    with log.log_queue.all_tasks_done:
        assert log.log_queue.all_tasks_done.wait_for(
            lambda: log.log_queue.unfinished_tasks == 0, timeout=3
        ), 'config load failure stopped the logging listener'
    assert log.listener._thread.is_alive()
    assert (root / 'config/conf.yml').read_text() == original

(root / 'config/conf.yml').write_text('theme: dark\n')
from arknights_mower.utils import config
messages = [config.log_queue.get(timeout=3) for _ in range(2)]
assert any('配置已由另一进程迁移' in message for message in messages), messages
assert any('config-load-failure-probe' in message for message in messages), messages
assert config.conf.theme == 'dark'
log.close_logging()
""",
    )


def test_logging_during_concurrent_config_initialization(tmp_path):
    run_probe(
        tmp_path,
        r"""
import importlib
import os
from pathlib import Path
from threading import Event, Thread
from unittest.mock import patch

root = Path(os.environ['MOWER_DATA_DIR'])
(root / 'conf.yml').write_text('theme: dark\n')
entered, release = Event(), Event()
errors = []
replace = os.replace
def concurrent_move(source, target):
    replace(source, target)
    if Path(source) == root / 'conf.yml':
        entered.set()
        assert release.wait(5)
        raise FileNotFoundError('another process completed migration')
def load():
    try:
        importlib.import_module('arknights_mower.utils.config')
    except BaseException as exc:
        errors.append(exc)

with patch.object(os, 'replace', concurrent_move):
    worker = Thread(target=load, daemon=True)
    worker.start()
    try:
        assert entered.wait(5)
        from arknights_mower.utils import log
        log.logger.info('concurrent-config-probe')
        with log.log_queue.all_tasks_done:
            assert log.log_queue.all_tasks_done.wait_for(
                lambda: log.log_queue.unfinished_tasks == 0, timeout=3
            ), 'logging blocked on config initialization'
        assert worker.is_alive()
    finally:
        release.set()
        worker.join(5)
    assert not worker.is_alive()
    assert not errors, errors

from arknights_mower.utils import config
messages = [config.log_queue.get(timeout=3) for _ in range(2)]
assert any('concurrent-config-probe' in message for message in messages), messages
assert any('配置已由另一进程迁移' in message for message in messages), messages
assert config.conf.theme == 'dark'
assert config.logger is log.logger
assert log.fhlr is None
assert log.get_screenshot_store() is None
log.close_logging()
""",
    )


def test_offline_analysis_survives_shared_logger_import_failure(tmp_path):
    run_probe(
        tmp_path,
        r"""
import builtins
import json
from unittest.mock import patch

from arknights_mower.agent import missed_order
from arknights_mower.agent.tools import analyze_missed_order as analysis

original_import = builtins.__import__
def unavailable(name, *args, **kwargs):
    if name == 'arknights_mower.utils.log':
        raise RuntimeError('application logging unavailable')
    return original_import(name, *args, **kwargs)

with patch.object(builtins, '__import__', unavailable):
    result = {
        'target_task_time': '2026-02-18 22:06:22',
        'detected_time': '2026-02-18 22:11:19',
        'room': 'room_3_1',
        'candidate_reasons': [{'type': 'execution_failed'}],
    }
    report = missed_order.summarize_missed_order_result(result, llm=None)
    assert '目标任务时间：2026-02-18 22:06:22' in report
    missed_order._log_debug_report(report)
    trace = []
    analysis._trace(trace, 'offline-probe', room='room_3_1')
    assert trace == [{'step': 'offline-probe', 'room': 'room_3_1'}]
    error = json.loads(analysis.analyze_missed_order('invalid-offline-mode'))
    assert error['error'] == '未知 mode: invalid-offline-mode'
""",
    )


def test_copied_update_runtime_keeps_stdlib_failure_reporting(tmp_path):
    run_probe(
        tmp_path,
        r"""
import builtins
import importlib.util
import io
import shutil
import sys
from contextlib import redirect_stderr
from pathlib import Path
from unittest.mock import Mock, patch

copied = Path(__file__).with_name('update_runtime.py')
shutil.copyfile(sys.argv[1], copied)
spec = importlib.util.spec_from_file_location('update_runtime', copied)
runtime = importlib.util.module_from_spec(spec)
original_import = builtins.__import__
def no_application(name, *args, **kwargs):
    assert not name.startswith('arknights_mower'), name
    return original_import(name, *args, **kwargs)

with patch.object(builtins, '__import__', no_application):
    spec.loader.exec_module(runtime)
    registration = object.__new__(runtime.RuntimeRegistration)
    registration.closed = Mock(wait=Mock(side_effect=[False, False, True]))
    registration.publish = Mock(side_effect=[OSError('standalone-publication'), None])
    registration.path = Path('registration.json')
    registration._retry_backups()
    errors = io.StringIO()
    with redirect_stderr(errors):
        registration._heartbeat()
    assert registration.publish.call_count == 2
    assert '实例登记发布失败' in errors.getvalue()
    assert 'standalone-publication' in errors.getvalue()
""",
        str(Path(__file__).parents[1] / "utils/update_runtime.py"),
    )


def test_existing_failure_paths_reach_file_and_frontend_once(tmp_path):
    run_probe(
        tmp_path,
        r"""
import json
import re
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from flask import Flask
from arknights_mower.agent import missed_order
from arknights_mower.agent.tools import analyze_missed_order as analysis
from arknights_mower.utils import config, lifecycle, log, maa_backup
from arknights_mower.utils import network_settings as network
from arknights_mower.utils import software_update_worker, update_runtime as runtime
from arknights_mower.utils import window_shell
from arknights_mower.utils.screenshot import ScreenshotStore
from arknights_mower.utils.config_backup import export_archive
from arknights_mower.views.config_backup import config_backup_bp
with patch('ctypes.WinDLL', create=True):
    from arknights_mower.utils import windows_frameless

log.init_file_logging()
assert missed_order._get_logger() is log.logger
assert analysis._get_logger() is log.logger
app = Flask(__name__)
app.register_blueprint(config_backup_bp)
app.config['CONFIG_BACKUP_BUSY'] = lambda: False
raw = export_archive()
with patch.object(config, 'atomic_write', side_effect=OSError('backup-write-probe')):
    response = app.test_client().post(
        '/config-backup/import', data=raw, headers={'X-Mower-Settings': '1'}
    )
assert response.status_code == 500
assert response.json['ok'] is False

bridge = object.__new__(window_shell.WindowShellBridge)
bridge._window = SimpleNamespace(maximize=Mock(side_effect=RuntimeError('window')))
assert bridge._call_window('maximize') is False

class Event:
    def __init__(self):
        self.callbacks = []
    def __iadd__(self, callback):
        self.callbacks.append(callback)
        return self
window = SimpleNamespace(events=SimpleNamespace(shown=Event(), loaded=Event()))
with patch.object(windows_frameless, 'is_windows', return_value=True), patch.object(
    windows_frameless, '_install_hook', side_effect=RuntimeError('frameless')
):
    windows_frameless.install_windows_frameless_resize(window, None, None)
    window.events.shown.callbacks[0]()

target = Path(log.get_path('@app/MAA'))
target.mkdir()
(target / '.old').mkdir()
checkpoint = maa_backup.BackupCheckpoint(target)
with patch.object(maa_backup.shutil, 'rmtree', side_effect=OSError('backup')):
    assert checkpoint.retire() is False

with patch.object(network, '_sync_stop', Mock(wait=Mock(side_effect=[False, True]))), patch.object(
    network, 'apply_http_proxy', side_effect=[None, RuntimeError('proxy')]
):
    network.start_proxy_sync()
    network._sync_thread.join(3)
    assert not network._sync_thread.is_alive()

registration = object.__new__(runtime.RuntimeRegistration)
registration.directory = Path(log.get_path('@app/update'))
registration.record = {'root': str(target)}
with patch.object(software_update_worker, 'retry_backup_cleanup', side_effect=OSError('update')):
    registration._retry_backups()
manifest = registration.directory / 'jobs/one/cleanup.json'
manifest.parent.mkdir(parents=True)
saved = target.with_name(target.name + '.backup-one')
saved.mkdir()
identity = saved.stat()
manifest.write_text(json.dumps({
    'id': 'one', 'verified': True, 'root': str(target), 'deployment': 'source',
    'paths': [{'path': str(saved), 'identity': [identity.st_dev, identity.st_ino]}],
}))
with patch.object(software_update_worker.shutil, 'rmtree', side_effect=PermissionError('locked')):
    registration._retry_backups()
assert saved.is_dir()
assert json.loads(manifest.read_text())['paths'][0]['path'] == str(saved)
registration.closed = Mock(wait=Mock(side_effect=[False, True]))
registration.publish = Mock(side_effect=OSError('publication'))
registration.path = Path('registration.json')
registration._heartbeat()

shutdown = lifecycle.Shutdown()
shutdown.release(SimpleNamespace(name='probe-resource', close=Mock(side_effect=RuntimeError('close'))))
assert len(shutdown.errors) == 1
assert 'error' in analysis.analyze_missed_order('logger-routing-probe')
missed_order._log_debug_report('missed-debug-probe')
analysis._trace([], 'analysis-debug-probe')

store = ScreenshotStore(
    Path(log.get_path('@app/frames')), lambda: 1,
    writer=Mock(side_effect=OSError('screenshot-write-probe')),
)
store.start()
store.submit(b'jpeg')
store.close(timeout=3)
assert store.stats()['failed'] == 1

log.logger.info('routing-probe-finished')
messages = []
while True:
    message = config.log_queue.get(timeout=3)
    messages.append(message)
    if 'routing-probe-finished' in message:
        break
contents = Path(log.fhlr.baseFilename).read_text(encoding='utf-8')
entries = [line for line in contents.splitlines() if re.match(r'\d{4}-\d{2}-\d{2} ', line)]
for message in (
    '档案导入写入失败',
    'Desktop window command failed: maximize',
    'Failed to install Windows frameless resize support',
    'MAA 任务已完成，旧备份暂无法清理',
    '同步网络代理设置失败',
    '历史更新备份暂无法清理',
    '新版本已验证，更新备份或临时文件暂无法清理，下次启动重试',
    '实例登记发布失败，下次心跳将重试',
    '关闭自有资源失败：probe-resource',
    '未知 mode: logger-routing-probe',
    'screenshot-write-probe',
):
    assert sum(message in entry for entry in entries) == 1, (message, contents)
    assert sum(message in entry for entry in messages) == 1, (message, messages)
for message in ('missed-debug-probe', 'analysis-debug-probe'):
    assert contents.count(message) == 1
    assert not any(message in entry for entry in messages)
log.close_logging()
""",
    )


def test_spawned_window_failure_reaches_parent_runtime_log_once(tmp_path):
    run_probe(
        tmp_path,
        r"""
import multiprocessing as mp
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

def child(queue):
    from arknights_mower.utils import log
    from arknights_mower.utils.window_shell import WindowShellBridge
    log.bind_mp_queue(queue)
    assert log.fhlr is None
    bridge = object.__new__(WindowShellBridge)
    bridge._window = SimpleNamespace(maximize=Mock(side_effect=RuntimeError('child-window')))
    assert bridge._call_window('maximize') is False
    log.close_logging()

if __name__ == '__main__':
    from arknights_mower.utils import log
    context = mp.get_context('spawn')
    queue = context.Queue()
    log.start_mp_listener(queue)
    worker = context.Process(target=child, args=(queue,))
    worker.start()
    worker.join(10)
    if worker.is_alive():
        worker.kill()
        worker.join(3)
        raise AssertionError('child did not stop')
    assert worker.exitcode == 0
    log.close_logging()
    contents = Path(log.get_path('@app/log/runtime.log')).read_text(encoding='utf-8')
    assert contents.count('Desktop window command failed: maximize') == 1, contents
    assert 'child-window' in contents
    queue.close()
    queue.join_thread()
""",
    )
