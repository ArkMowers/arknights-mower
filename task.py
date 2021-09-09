import time

from numpy import array

from utils.log import logger
from utils.recognize import Recognizer


def get_pos(poly, x_rate=0.5, y_rate=0.5):
    x = poly[0][0] * (1-x_rate) + poly[1][0] * (1-x_rate) + \
        poly[2][0] * x_rate + poly[3][0] * x_rate
    y = poly[0][1] * (1-y_rate) + poly[3][1] * (1-y_rate) + \
        poly[1][1] * y_rate + poly[2][1] * y_rate
    return (int(x/2), int(y/2))


def tap(adb, pos, recog, cut=None):
    adb.touch_tap(pos)
    time.sleep(1)
    recog.update(cut)


def retry(recog, call, cut=None, times=3):
    ret = call()
    if ret is not None and ret != False:
        return ret
    while times:
        times -= 1
        logger.debug('retrying...(remain %d times)' % times)
        time.sleep(1)
        recog.update(cut)
        ret = call()
        if ret is not None and ret != False:
            return ret
    return ret


def back_to_index(adb, recog=None):
    """
    返回主页
    """
    if recog is None:
        recog = Recognizer(adb)
    navbutton = recog.find('navbutton')
    if navbutton is not None:
        navhome_index = recog.find('navhome_index')
        if navhome_index is None:
            tap(adb, get_pos(navbutton), recog)
            navhome_index = recog.find('navhome_index')
        tap(adb, get_pos(navhome_index), recog)
    assert retry(recog, recog.is_index)


def complete_tasks(adb, recog=None):
    """
    点击确认完成每日任务和每周任务
    """
    if recog is None:
        recog = Recognizer(adb)
    back_to_index(adb, recog)
    tap(adb, get_pos(recog.find('index_mission')), recog)
    collect = recog.find('mission_collect')
    if collect is not None:
        tap(adb, get_pos(collect), recog)
    tap(adb, get_pos(recog.find('mission_weekly')), recog)
    collect = recog.find('mission_collect')
    if collect is not None:
        tap(adb, get_pos(collect), recog)


def collect_credit(adb, recog=None):
    """
    走亲访友收信用
    """
    if recog is None:
        recog = Recognizer(adb)
    back_to_index(adb, recog)
    tap(adb, get_pos(recog.find('index_friend')), recog)
    friend_list = recog.find('friend_list')
    tap(adb, get_pos(friend_list), recog, ((0.5, 1.0), (0, friend_list[1][1])))
    friend_visit = retry(recog, recog.find_friend_visit,
                         cut=((0.5, 1.0), (0, friend_list[1][1])))
    tap(adb, get_pos(friend_visit), recog)
    friend_next = retry(recog, recog.find_friend_next)
    x = (friend_next[0][0] + friend_next[3][0]) // 2
    y = (3 * friend_next[0][1] + friend_next[1][1]) // 4
    while friend_next is not None and recog.color(x, y)[2] > 100:
        tap(adb, get_pos(friend_next), recog)
        friend_next = retry(recog, recog.find_friend_next)


def recruit(adb, recog=None):
    """
    公招自动化
    """
    if recog is None:
        recog = Recognizer(adb)
    back_to_index(adb, recog)
    tap(adb, get_pos(recog.find('index_recruit')), recog)
