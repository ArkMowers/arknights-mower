import json
import subprocess
import sys

from arknights_mower import __system__
from arknights_mower.utils import config

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

print(json.dumps(result, ensure_ascii=False))
"""


def maa_check_params(adb: str | None = None) -> dict[str, str]:
    return {
        "maa_path": str(config.conf.maa_path),
        "maa_adb_path": str(config.conf.maa_adb_path),
        "adb": str(config.conf.adb if adb is None else adb),
        "maa_conn_preset": str(config.conf.maa_conn_preset),
        "maa_touch_option": str(config.conf.maa_touch_option),
    }


def maa_check_command(params: dict[str, str] | None = None) -> list[str]:
    return [
        sys.executable,
        "-c",
        MAA_CHECK_SCRIPT,
        json.dumps(params or maa_check_params(), ensure_ascii=False),
    ]


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


def run_maa_connectivity_check(
    timeout: int = MAA_CHECK_TIMEOUT,
    adb: str | None = None,
) -> dict[str, str]:
    subprocess_options: dict[str, int | bool]
    if __system__ == "windows":
        # Windows 由 CreateProcess 创建检测器，并隐藏控制台窗口。
        subprocess_options = {"creationflags": subprocess.CREATE_NO_WINDOW}
    else:
        # 长期运行的 Mower 已加载 Maa/OpenCV 等原生库，不应再通过 fork
        # 派生检测器。POSIX 会因此走 posix_spawn；Python 文件描述符默认
        # 不可继承。
        subprocess_options = {"close_fds": False}

    try:
        result = subprocess.run(
            maa_check_command(maa_check_params(adb)),
            capture_output=True,
            text=True,
            timeout=timeout,
            **subprocess_options,
        )
    except subprocess.TimeoutExpired:
        return maa_check_timeout_result(timeout)
    except Exception as e:
        return {"status": "error", "message": "Maa测试启动失败：" + str(e)}

    return parse_maa_check_output(result.stdout, result.stderr, result.returncode)


def is_maa_connectivity_check_enabled() -> bool:
    return bool(config.conf.maa_startup_check)
