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

    task.auto_operate(adb, potion=5)

    # adb.save_screenshot()

    # Recognizer(adb).find('ope_plan', draw=True)

    # Recognizer(adb).get_state()
    
    # with open('./screenshot/20210911123231.png', 'rb') as f:
    #     Recognizer(adb, f.read()).find('yes', draw=True)
