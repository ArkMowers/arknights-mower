"""Track resource download and installation independently of HTTP requests."""

from threading import RLock, Thread
from uuid import uuid4

from arknights_mower.utils.log import logger


class ResourceUpdateJob:
    def __init__(self):
        self.lock = RLock()
        self.thread = None
        self.job = {
            "id": "",
            "status": "idle",
            "phase": "idle",
            "message": "",
            "progress": None,
            "current": 0,
            "total": 0,
        }

    def snapshot(self):
        with self.lock:
            return dict(self.job)

    def running(self):
        with self.lock:
            return bool(
                self.job["status"] == "running"
                or self.thread
                and self.thread.is_alive()
            )

    def report(self, **values):
        with self.lock:
            self.job.update(values)

    def start(self, after_install=None):
        with self.lock:
            if self.running():
                raise ValueError("资源更新正在进行中")
            self.job = {
                "id": uuid4().hex,
                "status": "running",
                "phase": "downloading",
                "message": "正在连接资源下载地址",
                "progress": None,
                "current": 0,
                "total": 0,
            }
            self.thread = Thread(target=self.run, args=(after_install,), daemon=True)
            self.thread.start()
            return dict(self.job)

    def run(self, after_install):
        from arknights_mower.utils.resource_pkg import (
            download_resource_pkg,
            install_resource_pkg,
        )

        try:
            data = download_resource_pkg(callback=self.report)
            if data is None:
                raise ValueError("资源包下载失败，请检查网络")
            if not install_resource_pkg(data, callback=self.report):
                raise ValueError("资源包安装失败，已保留原版本")
            self.report(
                status="success",
                phase="done",
                progress=100,
                message="资源包已安装，各实例在任务间歇加载，无需重启 Mower",
            )
        except Exception as error:
            self.report(status="error", phase="failed", message=str(error))
            return
        if after_install:
            try:
                after_install()
            except Exception:
                logger.exception("资源已安装，但刷新窗口标题失败")
