from utils.adb import ADBConnector
from utils.recognize import Recognizer
import task


if __name__ == '__main__':
    adb = ADBConnector()
    # task.start_game(adb)
    # task.login(adb)
    # task.collect_credit(adb)
    # task.auto_operate(adb)
    # task.infra_collect(adb)
    # task.complete_tasks(adb)
    # task.recruit(adb)

    # adb.save_screenshot()

    Recognizer(adb).find('announce_close', draw=True)
    
    # with open('./screenshot/20210911123231.png', 'rb') as f:
    #     Recognizer(adb, f.read()).find('yes', draw=True)
