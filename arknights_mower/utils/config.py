import sys
import shutil
import ruamel.yaml
from ruamel.yaml.comments import CommentedSeq
from pathlib import Path
from collections import Mapping

from ..__init__ import __rootdir__, __system__, __pyinstall__

yaml = ruamel.yaml.YAML()
__ydoc = None


def __dig_mapping(path):
    path = path.split('/')
    parent_maps = path[:-1]
    current_map = __ydoc
    for idx, k in enumerate(parent_maps):
        if k not in current_map:
            raise KeyError(path)
        current_map = current_map[k]
        if not isinstance(current_map, Mapping):
            raise TypeError('config key %s is not a mapping' %
                            '/'.join(path[:idx+1]))
    return current_map, path[-1]


def __get(path, default=None):
    try:
        current_map, k = __dig_mapping(path)
    except (KeyError, TypeError) as e:
        return default
    if current_map is None or k not in current_map or current_map[k] is None:
        return default
    return current_map[k]


def __get_list(path, default=list()):
    item = __get(path)
    if item is None:
        return default
    elif not isinstance(item, CommentedSeq):
        return [item]
    else:
        return list(item)


def __set(path, value):
    try:
        current_map, k = __dig_mapping(path)
    except (KeyError, TypeError):
        return
    current_map[k] = value


def build_config(path, module):
    global __ydoc
    with Path(f'{__rootdir__}/template/config.yaml').open('r', encoding='utf8') as f:
        loader = yaml.load_all(f)
        next(loader)  # discard first document (used for comment)
        __ydoc = next(loader)
    init_debug(module)
    __set('debug/logfile/path', str(LOGFILE_PATH.resolve()))
    __set('debug/screenshot/path', str(SCREENSHOT_PATH.resolve()))
    with Path(path).open('w', encoding='utf8') as f:
        yaml.dump(__ydoc, f)


def load_config(path):
    global __ydoc, PATH
    PATH = path
    with PATH.open('r', encoding='utf8') as f:
        __ydoc = yaml.load(f)
    init_config()


def save_config():
    global PATH
    with PATH.open('w', encoding='utf8') as f:
        yaml.dump(__ydoc, f)


def init_config():

    global ADB_BINARY, ADB_DEVICE, ADB_FIXUPS
    ADB_BINARY = __get('device/adb_binary', [])
    ADB_DEVICE = __get('device/adb_device', [])
    ADB_FIXUPS = __get('device/adb_no_device_fixups', [])
    if len(ADB_BINARY) == 0:
        ADB_BINARY = [shutil.which('adb')]

    global APPNAME
    APPNAME = __get('app/package_name', 'com.hypergryph.arknights') + \
        '/' + __get('app/activity_name', 'com.u8.sdk.U8UnityContext')

    global DEBUG_MODE, LOGFILE_PATH, SCREENSHOT_PATH, SCREENSHOT_MAXNUM
    DEBUG_MODE = __get('debug/enabled', False)
    LOGFILE_PATH = __get('debug/logfile/path', None)
    SCREENSHOT_PATH = __get('debug/screenshot/path', None)
    SCREENSHOT_MAXNUM = __get('debug/screenshot/max_total', 20)

    global MAX_RETRYTIME
    MAX_RETRYTIME = __get('behavior/max_retry', 5)

    global OCR_APIKEY
    OCR_APIKEY = __get('ocr/ocr_space_api', 'c7431c9d7288957')

    global BASE_CONSTRUCT_PLAN, BASE_CONSTRUCT_CLUE, BASE_CONSTRUCT_DRONE
    BASE_CONSTRUCT_PLAN = __get('arrangement', None)
    BASE_CONSTRUCT_CLUE = __get('base_construct/clue_collect', False)
    BASE_CONSTRUCT_DRONE = __get('base_construct/drone_room', None)

    global SCHEDULE_PLAN
    SCHEDULE_PLAN = __get('schedule', None)

    global RECRUIT_PRIORITY, SHOP_PRIORITY
    RECRUIT_PRIORITY = __get('priority/recruit', ['火神', '因陀罗'])
    SHOP_PRIORITY = __get('priority/shop', None)

    global OPE_TIMES, OPE_POTION, OPE_ORIGINITE, OPE_ELIMINATE, OPE_PLAN
    OPE_TIMES = __get('operation/times', -1)
    OPE_POTION = __get('operation/potion', 0)
    OPE_ORIGINITE = __get('operation/originite', 0)
    OPE_ELIMINATE = __get('operation/eliminate', False)
    OPE_PLAN = __get('operation/plan', None)
    if OPE_PLAN is not None:
        OPE_PLAN = [x.split(',') for x in OPE_PLAN]
        OPE_PLAN = [[x[0], int(x[1])] for x in OPE_PLAN]


def update_ope_plan(plan):
    global OPE_PLAN
    OPE_PLAN = plan
    print([f'{x[0]},{x[1]}' for x in OPE_PLAN])
    __set('operation/plan', [f'{x[0]},{x[1]}' for x in OPE_PLAN])
    save_config()


def init_debug(module):
    global LOGFILE_PATH, SCREENSHOT_PATH
    if __pyinstall__:
        LOGFILE_PATH = Path(sys.executable).parent.joinpath('log')
        SCREENSHOT_PATH = Path(sys.executable).parent.joinpath('screenshot')
    elif module:
        if __system__ == 'windows':
            LOGFILE_PATH = Path.home().joinpath('arknights-mower')
            SCREENSHOT_PATH = Path.home().joinpath('arknights-mower/screenshot')
        elif __system__ == 'linux':
            LOGFILE_PATH = '/var/log/arknights-mower'
            SCREENSHOT_PATH = '/var/log/arknights-mower/screenshot'
        else:
            print(f'Unknown system: {__system__}')
            raise NotImplementedError
    else:
        LOGFILE_PATH = __rootdir__.parent.joinpath('log')
        SCREENSHOT_PATH = __rootdir__.parent.joinpath('screenshot')


init_config()
