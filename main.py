from utils.adb import ADBConnector, KeyCode
from utils.recognize import Recognizer


def init():
    adb = ADBConnector('127.0.0.1:62026')
    # adb.touch_tap((40, 40))
    # devices = adb.get_devices()
    # adb.connect_device(devices[0])
    # adb.send_keyevent(KeyCode.KEYCODE_BACK)
    # adb.touch_swipe((820, 366), (-500, 366))
    f = Recognizer(adb.screencap())
    if f.is_index():
        f.find_index('friend')
        f.find_index('infrastructure')
        f.find_index('mission')
        f.find_index('shop')
        f.find_index('recruit')
        f.find_index('terminal')

if __name__ == '__main__':
    init()
