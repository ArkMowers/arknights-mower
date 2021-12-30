import time
import socket
import subprocess
import numpy as np
from random import randint

from . import config
from .log import logger, save_screenshot


class ADBSocket:

    def __init__(self, server, timeout):
        logger.debug(f'server={server}, timeout={timeout}')
        try:
            self.sock = socket.create_connection(server, timeout=timeout)
            self.sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
        except ConnectionRefusedError:
            logger.error('ConnectionRefusedError')
            print('ADB Server 未开启。请运行 `adb server` 以启动 ADB Server。')
            exit()

    def recv_all(self, chunklen=65536, return_buffer=False):
        bufs = []
        cur_buf = np.empty(chunklen, dtype=np.uint8)
        pos = 0
        while True:
            if pos >= chunklen:
                bufs.append(cur_buf)
                cur_buf = np.empty(chunklen, dtype=np.uint8)
                pos = 0
            rcvlen = self.sock.recv_into(cur_buf[pos:])
            pos += rcvlen
            if rcvlen == 0:
                break
        bufs.append(cur_buf[:pos])
        result = np.concatenate(bufs)
        if return_buffer:
            return result.data
        else:
            return result.tobytes()

    def recv_exactly(self, len):
        buf = np.empty(len, dtype=np.uint8)
        pos = 0
        while pos < len:
            rcvlen = self.sock.recv_into(buf[pos:])
            pos += rcvlen
            if rcvlen == 0:
                break
        if pos != len:
            raise EOFError('recv_exactly %d bytes failed' % len)
        return buf.tobytes()

    def recv_response(self):
        """read a chunk of length indicated by 4 hex digits"""
        len = int(self.recv_exactly(4), 16)
        if len == 0:
            return b''
        return self.recv_exactly(len)

    def check_okay(self):
        result = self.recv_exactly(4)
        if result != b'OKAY':
            raise RuntimeError(self.recv_response())

    def close(self):
        self.sock.close()

    def send(self, data):
        self.sock.send(data)
        return self


class ADBClientSession:

    def __init__(self, server=None, timeout=None):
        if server is None:
            server = ('127.0.0.1', 5037)
        if (server[0] == '127.0.0.1' or server[0] == '::1') and timeout is None:
            timeout = 5
        self.server = server
        self.timeout = timeout
        self.sock = ADBSocket(self.server, self.timeout)

    def close(self):
        self.sock.close()

    def service(self, cmd):
        """make a service request to ADB server, consult ADB sources for available services"""
        cmdbytes = cmd.encode()
        data = b'%04X%b' % (len(cmdbytes), cmdbytes)
        self.sock.send(data).check_okay()
        return self

    def read_response(self):
        """read a chunk of length indicated by 4 hex digits"""
        return self.sock.recv_response()

    def devices(self):
        """returns list of devices that the adb server knows"""
        resp = self.service('host:devices').read_response()
        resp = resp.decode(errors='ignore')
        devices = [tuple(line.split('\t')) for line in resp.splitlines()]
        if not resp:
            logger.error('Connection Failure, check abd devices to see if your destination device is attached')
            print('未检测到 ADB Devices。请运行 `adb devices` 确认列表中列出了目标模拟器或设备。')
            exit()
        return devices

    def connect(self, device):
        resp = self.service('host:connect:%s' %
                            device).read_response().decode(errors='ignore')
        logger.debug('adb connect %s: %s', device, resp)
        if 'unable' in resp or 'cannot' in resp:
            raise RuntimeError(resp)

    def disconnect(self, device):
        resp = self.service('host:disconnect:%s' %
                            device).read_response().decode(errors='ignore')
        logger.debug('adb disconnect %s: %s', device, resp)
        if 'unable' in resp or 'cannot' in resp:
            raise RuntimeError(resp)

    def device(self, devid=None):
        """switch to a device"""
        if devid is None:
            return self.service('host:transport-any')
        return self.service('host:transport:' + devid)

    def usbdevice(self):
        """switch to a USB-connected device"""
        return self.service('host:transport-usb')

    def emulator(self):
        """switch to an (SDK) emulator device"""
        return self.service('host:transport-local')

    def exec_stream(self, cmd=''):
        """run command in device, with stdout/stdin attached to the socket returned"""
        self.service('exec:' + cmd)
        return self.sock

    def exec(self, cmd):
        """run command in device, returns stdout content after the command exits"""
        if len(cmd) == 0:
            raise ValueError('no command specified for blocking exec')
        while True:
            try:
                sock = self.exec_stream(cmd)
                data = sock.recv_all()
                sock.close()
                return data
            except socket.timeout:
                sock.close()
                logger.warning(f'socket.timeout: {self.timeout}s')
                self.timeout += 5
                if self.timeout > 60:
                    logger.error('socket.timeout too many times')
                    exit()
                self.sock = ADBSocket(self.server, self.timeout)

    def shell_stream(self, cmd=''):
        """run command in device, with pty attached to the socket returned"""
        self.service('shell:' + cmd)
        return self.sock

    def shell(self, cmd):
        """run command in device, returns pty output after the command exits"""
        if len(cmd) == 0:
            raise ValueError('no command specified for blocking shell')
        sock = self.shell_stream(cmd)
        data = sock.recv_all()
        sock.close()
        return data


class ADBConnector:

    def __init__(self, device_id=None):
        self.__device_id = device_id
        if self.__device_id == None:
            devices = self.__available_devices()
            if len(devices) == 0:
                for fixup in config.ADB_FIXUPS:
                    if fixup['run'] == 'adb_connect':
                        for target in fixup['target']:
                            try:
                                ADBClientSession().connect(target)
                            except RuntimeError as e:
                                logger.debug(e)
                                continue
                        devices = self.__available_devices()
                        if len(devices) > 0:
                            break
                    else:
                        logger.warning('Unknown run command: ' + fixup['run'])
                raise RuntimeError('No available device found')
            for x in config.ADB_DEVICE:
                for device in devices:
                    if device[0] == x:
                        self.__device_id = device[0]
                        return
            self.__device_id = devices[0][0]
            
    def __start_server(self):
        logger.info('Starting adb server...')
        for adb_bin in config.ADB_BINARY:
            try:
                logger.debug(f'Try adb_bin: {adb_bin}')
                subprocess.run([adb_bin, 'start-server'], check=True)
                # wait for the newly started ADB server to probe emulators
                time.sleep(0.5)
                if self.__check_server_alive():
                    return
            except FileNotFoundError:
                pass
            except subprocess.CalledProcessError:
                pass
        raise OSError("Can't start adb server")

    def __check_server_alive(self, restart=True):
        try:
            sess = ADBClientSession()
            version = int(sess.service(
                'host:version').read_response().decode(), 16)
            logger.debug('ADB server version %d', version)
            return True
        except (socket.timeout, ConnectionRefusedError, RuntimeError):
            if restart:
                self.__start_server()
            return False

    def __available_devices(self):
        return [x for x in ADBClientSession().devices() if x[1] != 'offline']

    def session(self):
        self.__check_server_alive()
        return ADBClientSession().device(self.__device_id)

    def run(self, cmd, DEBUG_LEVEL=2):
        output = self.session().exec(cmd)
        logger.debug('command: %s', cmd)
        logger.debug('output: %s', repr(output))
        return output

    def start_app(self, app):
        self.run(f'am start -n {app}')

    def touch_tap(self, XY, offsets=(0, 0)):
        final_X = XY[0] + randint(-offsets[0], offsets[0])
        final_Y = XY[1] + randint(-offsets[1], offsets[1])
        logger.debug(f'tap: ({final_X},{final_Y})')
        command = f'input tap {final_X} {final_Y}'
        self.run(command)

    def touch_swipe(self, start, movement, duration=100):
        x1, y1, x2, y2 = start[0], start[1], start[0] + \
            movement[0], start[1] + movement[1]
        logger.debug(
            f'swipe: from ({x1}, {y1}) to ({x2}, {y2}), duration: {duration}')
        command = f'input swipe {x1} {y1} {x2} {y2} {duration}'
        self.run(command)

    def send_keyevent(self, keycode):
        """
        发送一个按键事件
        https://developer.android.com/reference/android/view/KeyEvent.html
        """
        logger.debug(f'keyevent: {keycode}')
        command = f'input keyevent {keycode}'
        self.run(command)

    def send_text(self, text):
        command = f'input text "{text}"'
        self.run(command)

    def screencap(self):
        command = 'screencap -p'
        return self.session().exec(command)

    def save_screenshot(self):
        save_screenshot(self.screencap())

    def current_focus(self):
        command = 'dumpsys window | grep mCurrentFocus'
        line = str(self.session().exec(command), encoding='utf8')
        return line.strip()[:-1].split(' ')[-1]


class KeyCode:
    KEYCODE_CALL = 5  # 拨号键
    KEYCODE_ENDCALL = 6  # 挂机键
    KEYCODE_HOME = 3  # Home键
    KEYCODE_MENU = 82  # 菜单键
    KEYCODE_BACK = 4  # 返回键
    KEYCODE_SEARCH = 84  # 搜索键
    KEYCODE_CAMERA = 27  # 拍照键
    KEYCODE_FOCUS = 80  # 对焦键
    KEYCODE_POWER = 26  # 电源键
    KEYCODE_NOTIFICATION = 83  # 通知键
    KEYCODE_MUTE = 91  # 话筒静音键
    KEYCODE_VOLUME_MUTE = 164  # 扬声器静音键
    KEYCODE_VOLUME_UP = 24  # 音量+键
    KEYCODE_VOLUME_DOWN = 25  # 音量-键
    KEYCODE_ENTER = 66  # 回车键
    KEYCODE_ESCAPE = 111  # ESC键
    KEYCODE_DPAD_CENTER = 23  # 导航键 >> 确定键
    KEYCODE_DPAD_UP = 19  # 导航键 >> 向上
    KEYCODE_DPAD_DOWN = 20  # 导航键 >> 向下
    KEYCODE_DPAD_LEFT = 21  # 导航键 >> 向左
    KEYCODE_DPAD_RIGHT = 22  # 导航键 >> 向右
    KEYCODE_MOVE_HOME = 122  # 光标移动到开始键
    KEYCODE_MOVE_END = 123  # 光标移动到末尾键
    KEYCODE_PAGE_UP = 92  # 向上翻页键
    KEYCODE_PAGE_DOWN = 93  # 向下翻页键
    KEYCODE_DEL = 67  # 退格键
    KEYCODE_FORWARD_DEL = 112  # 删除键
    KEYCODE_INSERT = 124  # 插入键
    KEYCODE_TAB = 61  # Tab键
    KEYCODE_NUM_LOCK = 143  # 小键盘锁
    KEYCODE_CAPS_LOCK = 115  # 大写锁定键
    KEYCODE_BREAK = 121  # Break / Pause键
    KEYCODE_SCROLL_LOCK = 116  # 滚动锁定键
    KEYCODE_ZOOM_IN = 168  # 放大键
    KEYCODE_ZOOM_OUT = 169  # 缩小键
    KEYCODE_0 = 7
    KEYCODE_1 = 8
    KEYCODE_2 = 9
    KEYCODE_3 = 10
    KEYCODE_4 = 11
    KEYCODE_5 = 12
    KEYCODE_6 = 13
    KEYCODE_7 = 14
    KEYCODE_8 = 15
    KEYCODE_9 = 16
    KEYCODE_A = 29
    KEYCODE_B = 30
    KEYCODE_C = 31
    KEYCODE_D = 32
    KEYCODE_E = 33
    KEYCODE_F = 34
    KEYCODE_G = 35
    KEYCODE_H = 36
    KEYCODE_I = 37
    KEYCODE_J = 38
    KEYCODE_K = 39
    KEYCODE_L = 40
    KEYCODE_M = 41
    KEYCODE_N = 42
    KEYCODE_O = 43
    KEYCODE_P = 44
    KEYCODE_Q = 45
    KEYCODE_R = 46
    KEYCODE_S = 47
    KEYCODE_T = 48
    KEYCODE_U = 49
    KEYCODE_V = 50
    KEYCODE_W = 51
    KEYCODE_X = 52
    KEYCODE_Y = 53
    KEYCODE_Z = 54
    KEYCODE_PLUS = 81  # +
    KEYCODE_MINUS = 69  # -
    KEYCODE_STAR = 17  # *
    KEYCODE_SLASH = 76  # /
    KEYCODE_EQUALS = 70  # =
    KEYCODE_AT = 77  # @
    KEYCODE_POUND = 18  # #
    KEYCODE_APOSTROPHE = 75  # '
    KEYCODE_BACKSLASH = 73  # \
    KEYCODE_COMMA = 55  # ,
    KEYCODE_PERIOD = 56  # .
    KEYCODE_LEFT_BRACKET = 71  # [
    KEYCODE_RIGHT_BRACKET = 72  # ]
    KEYCODE_SEMICOLON = 74  # ;
    KEYCODE_GRAVE = 68  # `
    KEYCODE_SPACE = 62  # 空格键
    KEYCODE_MEDIA_PLAY = 126  # 多媒体键 >> 播放
    KEYCODE_MEDIA_STOP = 86  # 多媒体键 >> 停止
    KEYCODE_MEDIA_PAUSE = 127  # 多媒体键 >> 暂停
    KEYCODE_MEDIA_PLAY_PAUSE = 85  # 多媒体键 >> 播放 / 暂停
    KEYCODE_MEDIA_FAST_FORWARD = 90  # 多媒体键 >> 快进
    KEYCODE_MEDIA_REWIND = 89  # 多媒体键 >> 快退
    KEYCODE_MEDIA_NEXT = 87  # 多媒体键 >> 下一首
    KEYCODE_MEDIA_PREVIOUS = 88  # 多媒体键 >> 上一首
    KEYCODE_MEDIA_CLOSE = 128  # 多媒体键 >> 关闭
    KEYCODE_MEDIA_EJECT = 129  # 多媒体键 >> 弹出
    KEYCODE_MEDIA_RECORD = 130  # 多媒体键 >> 录音
