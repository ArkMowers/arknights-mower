import json
import os
import pathlib
import sys

from arknights_mower.utils import config
from arknights_mower.utils.update_runtime import frozen

MAA_CHECK_TIMEOUT = 30

MAA_CHECK_SCRIPT = r"""
import json
import pathlib
import sys

params = json.loads(sys.argv[1])
try:
    maa_path = pathlib.Path(params["maa_path"])
    sys.path.append(str(maa_path / "Python"))

    from asst.asst import Asst

    def callback(msg, details, arg):
        pass

    callback_func = Asst.CallBackType(callback)
    Asst.load(path=maa_path, incremental_path=maa_path / "cache")
    asst = Asst(callback=callback_func)
    version = asst.get_version()
    asst.set_instance_option(2, params["maa_touch_option"])
    if asst.connect(params["maa_adb_path"], params["adb"], params["maa_conn_preset"]):
        result = {"status": "success", "message": f"Maa {version} 连接成功"}
    else:
        result = {
            "status": "connection_failed",
            "message": "连接失败，请检查Maa日志！",
        }
except Exception as e:
    result = {"status": "error", "message": "Maa测试异常：" + str(e)}

print(json.dumps(result, ensure_ascii=True))
"""


def maa_check_params(adb: str | None = None) -> dict[str, str]:
    return {
        "maa_path": str(config.conf.maa_path),
        "maa_adb_path": str(config.conf.maa_adb_path),
        "adb": str(config.conf.adb if adb is None else adb),
        "maa_conn_preset": str(config.conf.maa_conn_preset),
        "maa_touch_option": str(config.conf.maa_touch_option),
    }


def run_maa_check(params: dict) -> dict[str, str]:
    """Run the MAA connectivity check against ``params`` and return the result.

    This mirrors ``MAA_CHECK_SCRIPT`` (the source-mode ``-c`` snippet) so the
    frozen launcher's ``--maa-check-worker`` sub-command can reuse the same
    logic through :func:`worker_main` instead of having to spawn a Python
    interpreter that does not exist in a frozen build.
    """
    try:
        python_dir = None
        maa_path = pathlib.Path(params["maa_path"])
        python_dir = str(maa_path / "Python")
        sys.path.append(python_dir)

        from asst.asst import Asst

        def callback(msg, details, arg):
            pass

        callback_func = Asst.CallBackType(callback)
        Asst.load(path=maa_path, incremental_path=maa_path / "cache")
        asst = Asst(callback=callback_func)
        version = asst.get_version()
        asst.set_instance_option(2, params["maa_touch_option"])
        if asst.connect(
            params["maa_adb_path"], params["adb"], params["maa_conn_preset"]
        ):
            return {"status": "success", "message": f"Maa {version} 连接成功"}
        return {"status": "connection_failed", "message": "连接失败，请检查Maa日志！"}
    except Exception as e:
        return {"status": "error", "message": "Maa测试异常：" + str(e)}
    finally:
        # Only needed while loading `asst`; drop it so a process that re-runs the
        # check (or the test runner) does not leak the MAA dir onto sys.path.
        # Guard against python_dir being unset (e.g. params["maa_path"] missing)
        # so a NameError here never masks the real exception above.
        if python_dir is not None:
            try:
                sys.path.remove(python_dir)
            except ValueError:
                pass


def worker_main(payload_json: str) -> None:
    """Entry point for ``webview_ui.py --maa-check-worker``.

    The frozen launcher is the only runnable (``sys.executable`` is ``mower.exe``,
    not a Python interpreter), so a check executed with ``-c`` would spawn a whole
    second desktop window. Routing it here runs in a sub-process that exits before
    opening any window, while still giving the parent a process to time out.
    """
    result = run_maa_check(json.loads(payload_json))
    # ensure_ascii keeps the payload pure-ASCII so it survives a windowed frozen
    # launcher whose console encoding varies with the host locale (e.g. GBK/Win).
    text = json.dumps(result, ensure_ascii=True)
    if sys.stdout is None:
        # Windowed frozen exe may leave sys.stdout unset, but the inherited fd 1
        # (server's pipe) stays valid — write there instead of dropping the result.
        os.write(1, (text + "\n").encode("utf-8"))
    else:
        print(text, flush=True)


def maa_check_command(params: dict[str, str] | None = None) -> list[str]:
    payload = json.dumps(params or maa_check_params(), ensure_ascii=False)
    if frozen():
        # sys.executable is the mower launcher, so "-c <script>" would launch a
        # whole second Mower window (with "-c" read as the config space). Route the
        # check through the launcher's --maa-check-worker sub-command instead.
        return [sys.executable, "--maa-check-worker", payload]
    return [sys.executable, "-c", MAA_CHECK_SCRIPT, payload]


def parse_maa_check_output(
    stdout: str, stderr: str = "", returncode: int | None = None
) -> dict[str, str]:
    for line in reversed(stdout.splitlines()):
        try:
            result = json.loads(line)
            return {
                "status": result.get("status", "error"),
                "message": result.get("message", ""),
            }
        except json.JSONDecodeError:
            pass

    message = "Maa测试进程异常退出"
    if returncode is not None:
        message += f"：{returncode}"
    if stderr.strip():
        message += f"，{stderr.strip().splitlines()[-1]}"
    return {"status": "error", "message": message}


def maa_check_timeout_result(timeout: int = MAA_CHECK_TIMEOUT) -> dict[str, str]:
    return {
        "status": "timeout",
        "message": f"Maa连通性测试超时（{timeout}秒），已终止测试进程",
    }
