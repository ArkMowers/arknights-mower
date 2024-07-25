from queue import Queue
from threading import Event

import requests
import yaml
from yamlcore import CoreDumper, CoreLoader

from arknights_mower.utils.config.model import Conf
from arknights_mower.utils.path import get_path

conf_path = get_path("@app/conf.yml")


def save():
    with conf_path.open("w", encoding="utf8") as f:
        yaml.dump(
            conf.model_dump(),
            f,
            Dumper=CoreDumper,
            encoding="utf-8",
            default_flow_style=False,
            allow_unicode=True,
        )


def load():
    global conf
    if not conf_path.is_file():
        conf_path.parent.mkdir(exist_ok=True)
        conf = Conf()
        save(conf)
    with conf_path.open("r", encoding="utf-8") as f:
        conf = Conf(**yaml.load(f, Loader=CoreLoader))

    global APPNAME
    APPNAME = (
        "com.hypergryph.arknights"
        if conf.package_type == 1
        else "com.hypergryph.arknights.bilibili"
    )
    global rg
    rg = conf.maa_rg_enable == 1 and conf.maa_long_task_type == "rogue"
    global sss
    sss = conf.maa_rg_enable == 1 and conf.maa_long_task_type == "sss"
    global ra
    ra = conf.maa_rg_enable == 1 and conf.maa_long_task_type == "ra"
    global sf
    sf = conf.maa_rg_enable == 1 and conf.maa_long_task_type == "sf"


conf: Conf
load()


stop_mower = Event()

# 日志
log_queue = Queue()
wh = None


droidcast = {"session": requests.Session(), "port": 0, "process": None}

# 常量
APP_ACTIVITY_NAME = "com.u8.sdk.U8UnityContext"
MAX_RETRYTIME = 5
MNT_COMPATIBILITY_MODE = False
MNT_PORT = 20937
