"""共享 OCR 测试支撑：服务进程、端点和状态目录约定。

本模块只承载测试基础设施，不包含行为回归，供家具 OCR 测试与
共享 OCR 服务测试共同使用。服务启动、等待和清理语义的回归保留在
shared_ocr_tests.py；本模块只提取两处测试都需要的最小边界。记录调用或注入
失败的测试引擎属于使用它的测试模块，不在此处复制。
"""

import multiprocessing as mp
import os
import time
from contextlib import contextmanager
from pathlib import Path

from arknights_mower.utils import ocr_service
from arknights_mower.utils import update_runtime as runtime
from arknights_mower.utils.device.owned import close_process

READY_TIMEOUT = 8


def wait_for(predicate, timeout=READY_TIMEOUT):
    """轮询测试条件直到其为真，超时则让用例失败。"""
    deadline = time.monotonic() + timeout
    while not (result := predicate()):
        assert time.monotonic() < deadline, "fixture wait expired"
        time.sleep(0.01)
    return result


def endpoint_path(directory):
    """返回使用 directory 的服务发布端点的路径。"""
    return Path(directory) / "endpoint.json"


def read_endpoint(directory):
    """读取已发布的端点；尚未发布时返回 None。"""
    return runtime.read_json(endpoint_path(directory))


def wait_for_endpoint(directory, timeout=READY_TIMEOUT):
    """等待服务发布端点并返回其内容。"""
    return wait_for(lambda: read_endpoint(directory), timeout)


def state_directory(data_root=None):
    """返回使用 data_root 的服务所对应的更新状态目录。

    runtime.state_dir() 固定解析当前进程的数据根；源码服务子进程可以带着
    另一个 MOWER_DATA_DIR 运行，因此这里保留同一安装键，只替换数据根。
    清理这类子进程登记的测试使用本函数定位实例记录。
    """
    if data_root is None:
        return runtime.state_dir()
    return Path(data_root) / "tmp/updates" / runtime.state_dir().name


@contextmanager
def service(directory, *, factory, idle=3, max_requests=256, wait_for_idle=False):
    """在自有进程中运行共享 OCR 协调服务。

    directory 存放端点、服务锁和模型监督目录，directory / "updates" 隔离
    本次测试的更新登记。factory 必须显式传入，让调用方在测试引擎与生产
    引擎之间主动选择。只有空闲退出回归设置 wait_for_idle，其他用例在
    断言结束后通过服务登记请求正常关闭。
    """
    directory = Path(directory)
    process = mp.get_context("spawn").Process(
        target=ocr_service.serve,
        args=(directory,),
        kwargs={
            "idle_timeout": idle,
            "factory": factory,
            "state_directory": directory / "updates",
            "max_requests": max_requests,
        },
    )
    process.start()
    try:
        wait_for_endpoint(directory)
        yield process
    finally:
        try:
            if not wait_for_idle and process.is_alive():
                state = directory / "updates"
                for record in runtime.instances(state):
                    if (
                        record.get("kind") == "ocr-service"
                        and record["pid"] == process.pid
                    ):
                        runtime.write_json(
                            state / "shutdown" / f"{record['id']}.json", {}
                        )
            process.join(idle + 3 if wait_for_idle else READY_TIMEOUT)
        finally:
            # 失败或关闭超时才强制回收自有协调进程，EOF 仍由模型进程负责处理。
            close_process(process, os.getpid(), timeout=0.5)
