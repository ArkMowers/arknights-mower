import time

from utils.log import logger
from utils.adb import KeyCode
from utils.recognize import Recognizer, State


def get_pos(poly, x_rate=0.5, y_rate=0.5):
    x = poly[0][0] * (1-x_rate) + poly[1][0] * (1-x_rate) + \
        poly[2][0] * x_rate + poly[3][0] * x_rate
    y = poly[0][1] * (1-y_rate) + poly[3][1] * (1-y_rate) + \
        poly[1][1] * y_rate + poly[2][1] * y_rate
    return (int(x/2), int(y/2))


def tap(adb, pos, recog):
    adb.touch_tap(pos)
    recog.skip_sec(1)


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
        if recog.state == State.LOGIN_START:
            tap(adb, get_pos(recog.find('start')), recog)
        elif recog.state == State.LOGIN_QUICKLY:
            tap(adb, get_pos(recog.find('login_awake')), recog)
        elif recog.state == State.LOGIN_MAIN:
            tap(adb, get_pos(recog.find('login_account')), recog)
        elif recog.state == State.LOGIN_INPUT:
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
        elif recog.state == State.LOGIN_LOADING:
            recog.skip_sec(3)
        elif recog.state == State.LOADING:
            recog.skip_sec(3)
        elif recog.state == State.MATERIEL:
            tap(adb, get_pos(recog.find('materiel')), recog)
        elif recog.state == State.YES:
            tap(adb, get_pos(recog.find('yes')), recog)
        else:
            retry_times -= 1
            recog.skip_sec(3)
            continue
        retry_times = 5
    assert recog.is_index()


def has_nav(adb, recog):
    """
    判断是否存在导航栏，若存在则打开
    """
    if recog.get_state() == State.NAVIGATION_BAR:
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
    while retry_times and recog.get_state() != State.INDEX:
        if has_nav(adb, recog):
            tap(adb, get_pos(recog.find('nav_index')), recog)
        elif recog.state == State.ANNOUNCEMENT:
            tap(adb, get_pos(recog.find('announce_close')), recog)
        elif recog.state == State.MATERIEL:
            tap(adb, get_pos(recog.find('materiel')), recog)
        elif recog.state // 100 == 1:
            login(adb)
        elif recog.state == State.YES:
            tap(adb, get_pos(recog.find('yes')), recog)
        elif recog.state == State.LOADING:
            recog.skip_sec(3)
        else:
            retry_times -= 1
            recog.skip_sec(3)
            continue
        retry_times = 5

    assert recog.get_state() == State.INDEX


def infrastructure(adb, recog=None):
    """
    基建自动化收集：收物资、赤金、信赖
    """
    if recog is None:
        recog = Recognizer(adb)
    retry_times = 5
    while retry_times > 0:
        if recog.state == State.UNDEFINED:
            recog.get_state()
        elif recog.state == State.INDEX:
            tap(adb, get_pos(recog.find('index_infrastructure')), recog)
        elif recog.state == State.INFRA_MAIN:
            notification = recog.find('infra_notification')
            if notification is not None:
                tap(adb, get_pos(notification), recog)
            else:
                break
        elif recog.state == State.INFRA_TODOLIST:
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
        elif recog.state == State.LOADING:
            recog.skip_sec(3)
        elif has_nav(adb, recog):
            tap(adb, get_pos(recog.find('nav_infrastructure')), recog)
        elif recog.state != State.UNKNOWN:
            back_to_index(adb, recog)
        else:
            retry_times -= 1
            recog.skip_sec(3)
            continue
        retry_times = 5


def mission(adb, recog=None):
    """
    点击确认完成每日任务和每周任务
    """
    if recog is None:
        recog = Recognizer(adb)
    retry_times = 5
    checked = 0
    while retry_times > 0:
        if recog.state == State.UNDEFINED:
            recog.get_state()
        elif recog.state == State.INDEX:
            tap(adb, get_pos(recog.find('index_mission')), recog)
        elif recog.state == State.MISSION_DAILY:
            checked |= 1
            collect = recog.find('mission_collect')
            if collect is None:
                recog.skip_sec(1)
                collect = recog.find('mission_collect')
            if collect is not None:
                tap(adb, get_pos(collect), recog)
            elif checked & 2 == 0:
                tap(adb, get_pos(recog.find('mission_weekly')), recog)
            else:
                break
        elif recog.state == State.MISSION_WEEKLY:
            checked |= 2
            collect = recog.find('mission_collect')
            if collect is None:
                recog.skip_sec(1)
                collect = recog.find('mission_collect')
            if collect is not None:
                tap(adb, get_pos(collect), recog)
            elif checked & 1 == 0:
                tap(adb, get_pos(recog.find('mission_daily')), recog)
            else:
                break
        elif recog.state == State.MATERIEL:
            tap(adb, get_pos(recog.find('materiel')), recog)
        elif recog.state == State.LOADING:
            recog.skip_sec(3)
        elif has_nav(adb, recog):
            tap(adb, get_pos(recog.find('nav_mission')), recog)
        elif recog.state != State.UNKNOWN:
            back_to_index(adb, recog)
        else:
            retry_times -= 1
            recog.skip_sec(3)
            continue
        retry_times = 5


def credit(adb, recog=None):
    """
    走亲访友收信用
    """
    if recog is None:
        recog = Recognizer(adb)
    retry_times = 5
    while retry_times > 0:
        if recog.state == State.UNDEFINED:
            recog.get_state()
        elif recog.state == State.INDEX:
            tap(adb, get_pos(recog.find('index_friend')), recog)
        elif recog.state == State.FRIEND_LIST_OFF:
            tap(adb, get_pos(recog.find('friend_list')), recog)
        elif recog.state == State.FRIEND_LIST_ON:
            maxy = recog.find('friend_list_on')[1][1]
            scope = [(0, 0), (100000, maxy)]
            friend_visit = recog.find('friend_visit', scope=scope)
            if friend_visit is not None:
                tap(adb, get_pos(friend_visit), recog)
            else:
                recog.skip_sec(1)
        elif recog.state == State.FRIEND_VISITING:
            friend_next = recog.find('friend_next')
            x = (friend_next[0][0] + friend_next[3][0]) // 2
            y = friend_next[0][1]
            if recog.color(x, y)[2] > 100:
                tap(adb, get_pos(friend_next), recog)
            else:
                break
        elif recog.state == State.LOADING:
            recog.skip_sec(3)
        elif has_nav(adb, recog):
            tap(adb, get_pos(recog.find('nav_social')), recog)
        elif recog.state != State.UNKNOWN:
            back_to_index(adb, recog)
        else:
            retry_times -= 1
            recog.skip_sec(3)
            continue
        retry_times = 5


def operate(adb, recog=None, potion=0, originite=0):
    """
    自动前往上一次作战刷体力
    :param potion: 最多使用药剂恢复体力的次数，-1 为无限制
    :param originite: 最多使用源石恢复体力的次数，-1 为无限制
    """
    if recog is None:
        recog = Recognizer(adb)
    recovering = 0
    retry_times = 5
    while retry_times > 0:
        if recog.state == State.UNDEFINED:
            recog.get_state()
        elif recog.state == State.INDEX:
            tap(adb, get_pos(recog.find('index_terminal')), recog)
        elif recog.state == State.TERMINAL_MAIN:
            tap(adb, get_pos(recog.find('terminal_pre')), recog)
        elif recog.state == State.OPERATOR_BEFORE:
            agency = recog.find('ope_agency')
            if agency is not None:
                tap(adb, get_pos(agency), recog)
            else:
                tap(adb, get_pos(recog.find('ope_start')), recog)
                if recovering == 1:
                    logger.info('use potion to recover sanity')
                    potion -= 1
                elif recovering == 2:
                    logger.info('use originite to recover sanity')
                    originite -= 1
                elif recovering != 0:
                    raise RuntimeError(f'recovering: unknown type {recovering}')
                recovering = 0
        elif recog.state == State.OPERATOR_SELECT:
            tap(adb, get_pos(recog.find('ope_select_start')), recog)
        elif recog.state == State.OPERATOR_ONGOING:
            recog.skip_sec(10)
        elif recog.state == State.OPERATOR_FINISH:
            tap(adb, (10, 10), recog)
        elif recog.state == State.OPERATOR_INTERRUPT:
            tap(adb, get_pos(recog.find('ope_interrupt_no')), recog)
        elif recog.state == State.OPERATOR_RECOVER_POTION:
            if potion == 0:
                if originite != 0:
                    tap(adb, get_pos(recog.find('ope_recover_originite')), recog)
                else:
                    tap(adb, get_pos(recog.find('ope_recover_potion_no')), recog)
                    break
            elif recovering:
                recog.skip_sec(3)
            else:
                tap(adb, get_pos(recog.find('ope_recover_potion_yes')), recog)
                recovering = 1
        elif recog.state == State.OPERATOR_RECOVER_ORIGINITE:
            if originite == 0:
                if potion != 0:
                    tap(adb, get_pos(recog.find('ope_recover_potion')), recog)
                else:
                    tap(adb, get_pos(recog.find('ope_recover_originite_no')), recog)
                    break
            elif recovering:
                recog.skip_sec(3)
            else:
                tap(adb, get_pos(recog.find('ope_recover_originite_yes')), recog)
                recovering = 2
        elif recog.state == State.LOADING:
            recog.skip_sec(3)
        elif has_nav(adb, recog):
            tap(adb, get_pos(recog.find('nav_terminal')), recog)
        elif recog.state != State.UNKNOWN:
            back_to_index(adb, recog)
        else:
            retry_times -= 1
            recog.skip_sec(3)
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


