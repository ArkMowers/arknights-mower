from typing import List, Union
import subprocess
import tempfile
import requests
import socket
import shutil

from .. import config
from ..log import logger
from ... import __system__

ADB_BUILDIN_URL = 'https://oss.nano.ac/arknights_mower/adb-binaries'
ADB_BUILDIN_FILELIST = {
    'linux': ['adb'],
    'windows': ['adb.exe', 'AdbWinApi.dll', 'AdbWinUsbApi.dll'],
}


def run_cmd(cmd: List[str], decode: bool = False) -> Union[bytes, str]:
    logger.debug(f"run command: {cmd}")
    try:
        r = subprocess.check_output(cmd, stderr=subprocess.STDOUT)
    except subprocess.CalledProcessError as e:
        logger.debug(e.output)
        raise e
    if decode:
        return r.decode('utf8')
    return r


def download_file(target_url: str) -> str:
    """ download file to temp path, and return its file path for further usage """
    logger.debug(f'downloading: {target_url}')
    resp = requests.get(target_url)
    with tempfile.NamedTemporaryFile('wb+', delete=False) as f:
        file_name = f.name
        f.write(resp.content)
    return file_name


def is_port_using(host: str, port: int) -> bool:
    """ if port is using by others, return True. else return False """
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.settimeout(1)

    try:
        result = s.connect_ex((host, port))
        # if port is using, return code should be 0. (can be connected)
        return result == 0
    finally:
        s.close()


def adb_buildin() -> None:
    """ download adb_bin """
    folder = config.init_adb_buildin()
    folder.mkdir(exist_ok=True, parents=True)
    if __system__ not in ADB_BUILDIN_FILELIST.keys():
        raise NotImplementedError(f'Unknown system: {__system__}')
    for file in ADB_BUILDIN_FILELIST[__system__]:
        target_path = folder / file
        if not target_path.exists():
            url = f'{ADB_BUILDIN_URL}/{__system__}/{file}'
            logger.debug(f'adb_buildin: {url}')
            tmp_path = download_file(url)
            shutil.copy(tmp_path, str(target_path))
    config.ADB_BUILDIN = folder / ADB_BUILDIN_FILELIST[__system__][0]
    config.ADB_BUILDIN.chmod(0o744)


class KeyCode:
    """ https://developer.android.com/reference/android/view/KeyEvent.html """

    KEYCODE_CALL = 5                 # 拨号键
    KEYCODE_ENDCALL = 6              # 挂机键
    KEYCODE_HOME = 3                 # Home 键
    KEYCODE_MENU = 82                # 菜单键
    KEYCODE_BACK = 4                 # 返回键
    KEYCODE_SEARCH = 84              # 搜索键
    KEYCODE_CAMERA = 27              # 拍照键
    KEYCODE_FOCUS = 80               # 对焦键
    KEYCODE_POWER = 26               # 电源键
    KEYCODE_NOTIFICATION = 83        # 通知键
    KEYCODE_MUTE = 91                # 话筒静音键
    KEYCODE_VOLUME_MUTE = 164        # 扬声器静音键
    KEYCODE_VOLUME_UP = 24           # 音量 + 键
    KEYCODE_VOLUME_DOWN = 25         # 音量 - 键
    KEYCODE_ENTER = 66               # 回车键
    KEYCODE_ESCAPE = 111             # ESC 键
    KEYCODE_DPAD_CENTER = 23         # 导航键 >> 确定键
    KEYCODE_DPAD_UP = 19             # 导航键 >> 向上
    KEYCODE_DPAD_DOWN = 20           # 导航键 >> 向下
    KEYCODE_DPAD_LEFT = 21           # 导航键 >> 向左
    KEYCODE_DPAD_RIGHT = 22          # 导航键 >> 向右
    KEYCODE_MOVE_HOME = 122          # 光标移动到开始键
    KEYCODE_MOVE_END = 123           # 光标移动到末尾键
    KEYCODE_PAGE_UP = 92             # 向上翻页键
    KEYCODE_PAGE_DOWN = 93           # 向下翻页键
    KEYCODE_DEL = 67                 # 退格键
    KEYCODE_FORWARD_DEL = 112        # 删除键
    KEYCODE_INSERT = 124             # 插入键
    KEYCODE_TAB = 61                 # Tab 键
    KEYCODE_NUM_LOCK = 143           # 小键盘锁
    KEYCODE_CAPS_LOCK = 115          # 大写锁定键
    KEYCODE_BREAK = 121              # Break / Pause 键
    KEYCODE_SCROLL_LOCK = 116        # 滚动锁定键
    KEYCODE_ZOOM_IN = 168            # 放大键
    KEYCODE_ZOOM_OUT = 169           # 缩小键
    KEYCODE_0 = 7                    # 0
    KEYCODE_1 = 8                    # 1
    KEYCODE_2 = 9                    # 2
    KEYCODE_3 = 10                   # 3
    KEYCODE_4 = 11                   # 4
    KEYCODE_5 = 12                   # 5
    KEYCODE_6 = 13                   # 6
    KEYCODE_7 = 14                   # 7
    KEYCODE_8 = 15                   # 8
    KEYCODE_9 = 16                   # 9
    KEYCODE_A = 29                   # A
    KEYCODE_B = 30                   # B
    KEYCODE_C = 31                   # C
    KEYCODE_D = 32                   # D
    KEYCODE_E = 33                   # E
    KEYCODE_F = 34                   # F
    KEYCODE_G = 35                   # G
    KEYCODE_H = 36                   # H
    KEYCODE_I = 37                   # I
    KEYCODE_J = 38                   # J
    KEYCODE_K = 39                   # K
    KEYCODE_L = 40                   # L
    KEYCODE_M = 41                   # M
    KEYCODE_N = 42                   # N
    KEYCODE_O = 43                   # O
    KEYCODE_P = 44                   # P
    KEYCODE_Q = 45                   # Q
    KEYCODE_R = 46                   # R
    KEYCODE_S = 47                   # S
    KEYCODE_T = 48                   # T
    KEYCODE_U = 49                   # U
    KEYCODE_V = 50                   # V
    KEYCODE_W = 51                   # W
    KEYCODE_X = 52                   # X
    KEYCODE_Y = 53                   # Y
    KEYCODE_Z = 54                   # Z
    KEYCODE_PLUS = 81                # +
    KEYCODE_MINUS = 69               # -
    KEYCODE_STAR = 17                # *
    KEYCODE_SLASH = 76               # /
    KEYCODE_EQUALS = 70              # =
    KEYCODE_AT = 77                  # @
    KEYCODE_POUND = 18               # #
    KEYCODE_APOSTROPHE = 75          # '
    KEYCODE_BACKSLASH = 73           # \
    KEYCODE_COMMA = 55               # ,
    KEYCODE_PERIOD = 56              # .
    KEYCODE_LEFT_BRACKET = 71        # [
    KEYCODE_RIGHT_BRACKET = 72       # ]
    KEYCODE_SEMICOLON = 74           # ;
    KEYCODE_GRAVE = 68               # `
    KEYCODE_SPACE = 62               # 空格键
    KEYCODE_MEDIA_PLAY = 126         # 多媒体键 >> 播放
    KEYCODE_MEDIA_STOP = 86          # 多媒体键 >> 停止
    KEYCODE_MEDIA_PAUSE = 127        # 多媒体键 >> 暂停
    KEYCODE_MEDIA_PLAY_PAUSE = 85    # 多媒体键 >> 播放 / 暂停
    KEYCODE_MEDIA_FAST_FORWARD = 90  # 多媒体键 >> 快进
    KEYCODE_MEDIA_REWIND = 89        # 多媒体键 >> 快退
    KEYCODE_MEDIA_NEXT = 87          # 多媒体键 >> 下一首
    KEYCODE_MEDIA_PREVIOUS = 88      # 多媒体键 >> 上一首
    KEYCODE_MEDIA_CLOSE = 128        # 多媒体键 >> 关闭
    KEYCODE_MEDIA_EJECT = 129        # 多媒体键 >> 弹出
    KEYCODE_MEDIA_RECORD = 130       # 多媒体键 >> 录音
