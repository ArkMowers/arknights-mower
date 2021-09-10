from utils.adb import ADBConnector
from utils.recognize import Recognizer
import task


if __name__ == '__main__':
    adb = ADBConnector()
    # task.start_game(adb)
    # task.login(adb)
    # task.collect_credit(adb)
    # task.complete_tasks(adb)
    # task.infra_collect(adb)
    # task.recruit(adb)
    task.auto_operate(adb)

    # adb.save_screenshot()
    # adb.touch_tap((40, 40))
    # devices = adb.get_devices()
    # adb.connect_device(devices[0])
    # adb.send_keyevent(KeyCode.KEYCODE_BACK)
    # adb.touch_swipe((820, 366), (-500, 366))
    # f = Recognizer(adb)
    # f.find('friend_unvisited', draw=True)
    # Recognizer(adb).get_status()
