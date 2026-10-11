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


def test_existing_failure_paths_reach_file_and_frontend_once(tmp_path):
    run_probe(
        tmp_path,
        r"""
import re
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from arknights_mower.agent import missed_order
from arknights_mower.agent.tools import analyze_missed_order as analysis
from arknights_mower.utils import config, lifecycle, log, maa_backup
from arknights_mower.utils import network_settings as network
from arknights_mower.utils import software_update_worker, update_runtime as runtime
from arknights_mower.utils import window_shell
from arknights_mower.utils.screenshot import ScreenshotStore
with patch('ctypes.WinDLL', create=True):
    from arknights_mower.utils import windows_frameless

log.init_file_logging()
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
target.with_name('MAA.old').mkdir()
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
    'Desktop window command failed: maximize',
    'Failed to install Windows frameless resize support',
    'MAA 任务已完成，旧备份暂无法清理',
    '同步网络代理设置失败',
    '历史更新备份暂无法清理',
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
