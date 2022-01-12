import shutil
import ruamel.yaml
from ruamel.yaml.comments import CommentedSeq
from pathlib import Path
from collections import Mapping

from ..__init__ import __rootdir__

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


def create_config(config_file):
    with Path(f'{__rootdir__}/template/config.yaml').open('r', encoding='utf8') as f:
        loader = yaml.load_all(f)
        next(loader)  # discard first document (used for comment)
        ydoc = next(loader)
    with Path(config_file).open('w', encoding='utf8') as f:
        yaml.dump(ydoc, f)


def load_config(config_file):
    global __ydoc
    with Path(config_file).open('r', encoding='utf8') as f:
        __ydoc = yaml.load(f)
    init_config()


def save_config(config_file):
    with Path(config_file).open('w', encoding='utf8') as f:
        yaml.dump(__ydoc, f)


def init_config():

    global ADB_BINARY, ADB_DEVICE, ADB_FIXUPS
    ADB_BINARY = __get_list('device/adb_binary')
    ADB_DEVICE = __get_list('device/adb_device')
    ADB_FIXUPS = __get_list('device/adb_no_device_fixups')
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

    global BASE_CONSTRUCT_PLAN
    BASE_CONSTRUCT_PLAN = __get('base_construct', None)

    global SCHEDULE_PLAN
    SCHEDULE_PLAN = __get('schedule', None)

    global RECRUIT_PRIORITY, SHOP_PRIORITY
    RECRUIT_PRIORITY = __get('priority/recruit', None)
    SHOP_PRIORITY = __get('priority/shop', None)


init_config()
