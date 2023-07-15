from __future__ import annotations

import shutil
import sys
try:
    from collections.abc import Mapping
except ImportError:
    from collections import Mapping
from pathlib import Path
from typing import Any

from ruamel.yaml.comments import CommentedSeq

from .. import __pyinstall__, __rootdir__, __system__
from . import typealias as tp
from .yaml import yaml

# The lowest version supported
VERSION_SUPPORTED_MIN = 1
VERSION_SUPPORTED_MAX = 1


__ydoc = None

BASE_CONSTRUCT_PLAN: dict[str, tp.BasePlan]
OPE_PLAN: list[tp.OpePlan]


def __dig_mapping(path: str):
    path = path.split('/')
    parent_maps = path[:-1]
    current_map = __ydoc
    for idx, k in enumerate(parent_maps):
        if k not in current_map:
            raise KeyError(path)
        current_map = current_map[k]
        if not isinstance(current_map, Mapping):
            raise TypeError(
                'config key %s is not a mapping' % '/'.join(path[: idx + 1])
            )
    return current_map, path[-1]


def __get(path: str, default: Any = None):
    try:
        current_map, k = __dig_mapping(path)
    except (KeyError, TypeError) as e:
        return default
    if current_map is None or k not in current_map or current_map[k] is None:
        return default
    return current_map[k]


def __get_list(path: str, default: Any = list()):
    item = __get(path)
    if item is None:
        return default
    elif not isinstance(item, CommentedSeq):
        return [item]
    else:
        return list(item)


def __set(path: str, value: Any):
    try:
        current_map, k = __dig_mapping(path)
    except (KeyError, TypeError):
        return
    current_map[k] = value


def build_config(path: str, module: bool) -> None:
    """ build config via template """
    global __ydoc
    with Path(f'{__rootdir__}/templates/config.yaml').open('r', encoding='utf8') as f:
        loader = yaml.load_all(f)
        next(loader)  # discard first document (used for comment)
        __ydoc = next(loader)
    init_debug(module)
    __set('debug/logfile/path', str(LOGFILE_PATH.resolve()))
    __set('debug/screenshot/path', str(SCREENSHOT_PATH.resolve()))
    with Path(path).open('w', encoding='utf8') as f:
        yaml.dump(__ydoc, f)


def load_config(path: str) -> None:
    """ load config from PATH """
    global __ydoc, PATH
    PATH = Path(path)
    with PATH.open('r', encoding='utf8') as f:
        __ydoc = yaml.load(f)
    if not VERSION_SUPPORTED_MIN <= __get('version', 1) <= VERSION_SUPPORTED_MAX:
        raise RuntimeError('The current version of the config file is not supported')
    init_config()


def save_config() -> None:
    """ save config into PATH """
    global PATH
    with PATH.open('w', encoding='utf8') as f:
        yaml.dump(__ydoc, f)


def init_config() -> None:
    """ init config from __ydoc """
    global ADB_BINARY, ADB_DEVICE, ADB_CONNECT
    ADB_BINARY = __get('device/adb_binary', [])
    ADB_DEVICE = __get('device/adb_device', [])
    ADB_CONNECT = __get('device/adb_connect', [])
    if shutil.which('adb') is not None:
        ADB_BINARY.append(shutil.which('adb'))

    global ADB_BUILDIN
    ADB_BUILDIN = None

    global ADB_SERVER_IP, ADB_SERVER_PORT, ADB_SERVER_TIMEOUT
    ADB_SERVER_IP = __get('device/adb_server/ip', '127.0.0.1')
    ADB_SERVER_PORT = __get('device/adb_server/port', 5037)
    ADB_SERVER_TIMEOUT = __get('device/adb_server/timeout', 5)

    global ADB_CONTROL_CLIENT
    ADB_CONTROL_CLIENT = __get('device/adb_control_client', 'scrcpy')

    global MNT_TOUCH_DEVICE
    MNT_TOUCH_DEVICE = __get('device/mnt_touch_device', None)

    global MNT_PORT
    MNT_PORT = __get('device/mnt_port', 20937)

    global MNT_COMPATIBILITY_MODE
    MNT_COMPATIBILITY_MODE = __get('device/mnt_compatibility_mode', False)

    global USERNAME, PASSWORD
    USERNAME = __get('account/username', None)
    PASSWORD = __get('account/password', None)

    global APPNAME
    APPNAME = __get('app/package_name', 'com.hypergryph.arknights') 

    global APP_ACTIVITY_NAME
    APP_ACTIVITY_NAME = __get('app/activity_name','com.u8.sdk.U8UnityContext')

    global DEBUG_MODE, LOGFILE_PATH, LOGFILE_AMOUNT, SCREENSHOT_PATH, SCREENSHOT_MAXNUM
    DEBUG_MODE = __get('debug/enabled', False)
    LOGFILE_PATH = __get('debug/logfile/path', None)
    LOGFILE_AMOUNT = __get('debug/logfile/amount', 3)
    SCREENSHOT_PATH = __get('debug/screenshot/path', None)
    SCREENSHOT_MAXNUM = __get('debug/screenshot/max_total', 20)

    global MAX_RETRYTIME
    MAX_RETRYTIME = __get('behavior/max_retry', 5)

    global OCR_APIKEY
    OCR_APIKEY = __get('ocr/ocr_space_api', 'c7431c9d7288957')

    global BASE_CONSTRUCT_PLAN
    BASE_CONSTRUCT_PLAN = __get('arrangement', None)

    global SCHEDULE_PLAN
    SCHEDULE_PLAN = __get('schedule', None)

    global RECRUIT_PRIORITY, SHOP_PRIORITY
    RECRUIT_PRIORITY = __get('priority/recruit', None)
    SHOP_PRIORITY = __get('priority/shop', None)

    global OPE_TIMES, OPE_POTION, OPE_ORIGINITE, OPE_ELIMINATE, OPE_PLAN
    OPE_TIMES = __get('operation/times', -1)
    OPE_POTION = __get('operation/potion', 0)
    OPE_ORIGINITE = __get('operation/originite', 0)
    OPE_ELIMINATE = int(__get('operation/eliminate', 0))  # convert bool to int
    OPE_PLAN = __get('operation/plan', None)
    if OPE_PLAN is not None:
        OPE_PLAN = [x.split(',') for x in OPE_PLAN]
        OPE_PLAN = [[x[0], int(x[1])] for x in OPE_PLAN]

    global TAP_TO_LAUNCH
    TAP_TO_LAUNCH = {}


def update_ope_plan(plan: list[tp.OpePlan]) -> None:
    """ update operation plan """
    global OPE_PLAN
    OPE_PLAN = plan
    print([f'{x[0]},{x[1]}' for x in OPE_PLAN])
    __set('operation/plan', [f'{x[0]},{x[1]}' for x in OPE_PLAN])
    # TODO 其他参数也应该更新
    save_config()


def init_debug(module: bool) -> None:
    """ init LOGFILE_PATH & SCREENSHOT_PATH """
    global LOGFILE_PATH, SCREENSHOT_PATH
    if __pyinstall__:
        LOGFILE_PATH = Path(sys.executable).parent.joinpath('log')
        SCREENSHOT_PATH = Path(sys.executable).parent.joinpath('screenshot')
    elif module:
        if __system__ == 'windows':
            LOGFILE_PATH = Path.home().joinpath('arknights-mower')
            SCREENSHOT_PATH = Path.home().joinpath('arknights-mower/screenshot')
        elif __system__ == 'linux':
            LOGFILE_PATH = Path('/var/log/arknights-mower')
            SCREENSHOT_PATH = Path('/var/log/arknights-mower/screenshot')
        elif __system__ == 'darwin':
            LOGFILE_PATH = Path('/var/log/arknights-mower')
            SCREENSHOT_PATH = Path('/var/log/arknights-mower/screenshot')
        else:
            raise NotImplementedError(f'Unknown system: {__system__}')
    else:
        LOGFILE_PATH = __rootdir__.parent.joinpath('log')
        SCREENSHOT_PATH = __rootdir__.parent.joinpath('screenshot')


def init_adb_buildin() -> Path:
    """ init ADB_BUILDIN & ADB_BUILDIN_DIR """
    global ADB_BUILDIN_DIR, ADB_BUILDIN
    ADB_BUILDIN = None
    if __pyinstall__:
        ADB_BUILDIN_DIR = Path(sys.executable).parent.joinpath('adb-buildin')
    elif __system__ == 'windows':
        ADB_BUILDIN_DIR = Path.home().joinpath('arknights-mower/adb-buildin')
    elif __system__ == 'linux':
        ADB_BUILDIN_DIR = Path.home().joinpath('.arknights-mower')
    elif __system__ == 'darwin':
        ADB_BUILDIN_DIR = Path.home().joinpath('.arknights-mower')
    else:
        raise NotImplementedError(f'Unknown system: {__system__}')
    return ADB_BUILDIN_DIR


init_config()
