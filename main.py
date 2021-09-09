from utils.adb import ADBConnector, KeyCode


def init():
    adb = ADBConnector('127.0.0.1:62026')
    # adb.touch_tap((40, 40))
    # devices = adb.get_devices()
    # adb.connect_device(devices[0])
    # adb.send_keyevent(KeyCode.KEYCODE_BACK)
    # adb.touch_swipe((820, 366), (-500, 366))
    # adb.screencap()


if __name__ == '__main__':
    init()
