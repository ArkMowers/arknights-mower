import time

from utils.log import logger
from utils.adb import KeyCode
from utils.recognize import Recognizer, Status


def get_pos(poly, x_rate=0.5, y_rate=0.5):
    x = poly[0][0] * (1-x_rate) + poly[1][0] * (1-x_rate) + \
        poly[2][0] * x_rate + poly[3][0] * x_rate
    y = poly[0][1] * (1-y_rate) + poly[3][1] * (1-y_rate) + \
        poly[1][1] * y_rate + poly[2][1] * y_rate
    return (int(x/2), int(y/2))


def tap(adb, pos, recog):
    adb.touch_tap(pos)
    time.sleep(1)
    recog.update()


def start_game(adb):
    adb.start_app('com.hypergryph.arknights/com.u8.sdk.U8UnityContext')
    time.sleep(10)


def login(adb, recog=None):
    """
    启动游戏
    """
    if recog is None:
        recog = Recognizer(adb)
    retry_times = 5
    while retry_times and recog.is_index() == False:
        if recog.status == Status.LOGIN_START:
            tap(adb, get_pos(recog.find('start')), recog)
        elif recog.status == Status.LOGIN_QUICKLY:
            tap(adb, get_pos(recog.find('login_awake')), recog)
        elif recog.status == Status.LOGIN_MAIN:
            tap(adb, get_pos(recog.find('login_account')), recog)
        elif recog.status == Status.LOGIN_INPUT:
            input_area = recog.find('login_username')
            if input_area is not None:
                logger.debug(input_area)
                adb.touch_tap(get_pos(input_area))
                adb.send_text(input('Enter username: ').strip())
                adb.touch_tap((0, 0))
            input_area = recog.find('login_password')
            if input_area is not None:
                logger.debug(input_area)
                adb.touch_tap(get_pos(input_area))
                adb.send_text(input('Enter password: ').strip())
                adb.touch_tap((0, 0))
            tap(adb, get_pos(recog.find('login_button')), recog)
        elif recog.status == Status.LOGIN_LOADING:
            time.sleep(3)
            recog.update()
        elif recog.status == Status.LOADING:
            time.sleep(3)
            recog.update()
        elif recog.status == Status.MATERIEL:
            tap(adb, get_pos(recog.find('materiel')), recog)
        elif recog.status == Status.YES:
            tap(adb, get_pos(recog.find('yes')), recog)
        else:
            retry_times -= 1
            time.sleep(3)
            recog.update()
            continue
        retry_times = 5
    assert recog.is_index()


def has_nav(adb, recog):
    """
    判断是否存在导航栏，若存在则打开
    """
    if recog.get_status() == Status.NAVIGATION_BAR:
        return True
    navbutton = recog.find('navbutton')
    if navbutton is not None:
        tap(adb, get_pos(navbutton), recog)
        return True
    return False


def back_to_index(adb, recog=None):
    """
    返回主页
    """
    logger.info('back to index')
    if recog is None:
        recog = Recognizer(adb)
    retry_times = 5
    while retry_times and recog.get_status() != Status.INDEX:
        if has_nav(adb, recog):
            tap(adb, get_pos(recog.find('nav_index')), recog)
        elif recog.status == Status.ANNOUNCEMENT:
            tap(adb, get_pos(recog.find('index_close')), recog)
        elif recog.status == Status.MATERIEL:
            tap(adb, get_pos(recog.find('materiel')), recog)
        elif recog.status // 100 == 1:
            login(adb)
        elif recog.status == Status.YES:
            tap(adb, get_pos(recog.find('yes')), recog)
        elif recog.status == Status.LOADING:
            time.sleep(3)
            recog.update()
        else:
            retry_times -= 1
            time.sleep(3)
            recog.update()
            continue
        retry_times = 5

    assert recog.get_status() == Status.INDEX


def infra_collect(adb, recog=None):
    """
    基建自动化收集：收物资、赤金、信赖
    """
    if recog is None:
        recog = Recognizer(adb)
    if has_nav(adb, recog):
        tap(adb, get_pos(recog.find('nav_infrastructure')), recog)
    else:
        back_to_index(adb, recog)
    retry_times = 5
    while retry_times:
        recog.get_status()
        if recog.status == Status.INDEX:
            tap(adb, get_pos(recog.find('index_infrastructure')), recog)
        elif recog.status == Status.INFRA_MAIN:
            notification = recog.find('infra_notification')
            if notification is not None:
                tap(adb, get_pos(notification), recog)
            else:
                break
        elif recog.status == Status.INFRA_TODOLIST:
            trust = recog.find('infra_collect_trust')
            if trust is not None:
                tap(adb, get_pos(trust), recog)
            bill = recog.find('infra_collect_bill')
            if bill is not None:
                tap(adb, get_pos(bill), recog)
            factory = recog.find('infra_collect_factory')
            if factory is not None:
                tap(adb, get_pos(factory), recog)
            break
        elif recog.status == Status.LOADING:
            time.sleep(3)
            recog.update()
        elif recog.status != Status.UNKNOWN:
            back_to_index(adb, recog)
        else:
            retry_times -= 1
            time.sleep(3)
            recog.update()
            continue
        retry_times = 5


def complete_tasks(adb, recog=None):
    """
    点击确认完成每日任务和每周任务
    """
    if recog is None:
        recog = Recognizer(adb)
    if has_nav(adb, recog):
        tap(adb, get_pos(recog.find('nav_mission')), recog)
    else:
        back_to_index(adb, recog)
    retry_times = 5
    while retry_times:
        recog.get_status()
        if recog.status == Status.INDEX:
            tap(adb, get_pos(recog.find('index_mission')), recog)
        elif recog.status == Status.MISSION_DAILY:
            collect = recog.find('mission_collect')
            if collect is not None:
                tap(adb, get_pos(collect), recog)
            else:
                tap(adb, get_pos(recog.find('mission_weekly')), recog)
        elif recog.status == Status.MISSION_WEEKLY:
            collect = recog.find('mission_collect')
            if collect is not None:
                tap(adb, get_pos(collect), recog)
            else:
                break
        elif recog.status == Status.MATERIEL:
            tap(adb, get_pos(recog.find('materiel')), recog)
        elif recog.status == Status.LOADING:
            time.sleep(3)
            recog.update()
        elif recog.status != Status.UNKNOWN:
            back_to_index(adb, recog)
        else:
            retry_times -= 1
            time.sleep(3)
            recog.update()
            continue
        retry_times = 5


def collect_credit(adb, recog=None):
    """
    走亲访友收信用
    """
    if recog is None:
        recog = Recognizer(adb)
    if has_nav(adb, recog):
        tap(adb, get_pos(recog.find('nav_social')), recog)
    else:
        back_to_index(adb, recog)
    retry_times = 5
    while retry_times:
        if recog.status == Status.INDEX:
            tap(adb, get_pos(recog.find('index_friend')), recog)
        elif recog.status == Status.FRIEND_LIST_OFF:
            tap(adb, get_pos(recog.find('friend_list')), recog)
        elif recog.status == Status.FRIEND_LIST_ON:
            maxy = recog.find('friend_list_on')[1][1]
            scope = [(0, 0), (100000, maxy)]
            friend_visit = recog.find('friend_visit', scope=scope)
            if friend_visit is not None:
                tap(adb, get_pos(friend_visit), recog)
            else:
                time.sleep(1)
                recog.update()
        elif recog.status == Status.FRIEND_VISITING:
            friend_next = recog.find('friend_next')
            x = (friend_next[0][0] + friend_next[3][0]) // 2
            y = friend_next[0][1]
            if recog.color(x, y)[2] > 100:
                tap(adb, get_pos(friend_next), recog)
            else:
                break
        elif recog.status == Status.LOADING:
            time.sleep(3)
            recog.update()
        elif recog.status != Status.UNKNOWN:
            back_to_index(adb, recog)
        else:
            retry_times -= 1
            time.sleep(3)
            recog.update()
            continue
        retry_times = 5


# def recruit(adb, recog=None):
#     """
#     公招自动化
#     """
#     if recog is None:
#         recog = Recognizer(adb)
#     back_to_index(adb, recog)
#     tap(adb, get_pos(recog.find('index_recruit')), recog)
