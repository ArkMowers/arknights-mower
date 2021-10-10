import time

from .utils.log import logger
from .utils.adb import ADBConnector, KeyCode
from .utils.config import APPNAME
from .utils.recognize import Recognizer, Scene, RecognizeError
from .utils import segment, detector
from .ocr import ocrhandle
from .data.recruit import recruit_database
from .data.level import level_database, zone_database, theme_database, weekly_zones


class LevelUnopenError(Exception):
    pass


def get_pos(poly, x_rate=0.5, y_rate=0.5):
    if poly is None:
        raise RecognizeError
    elif len(poly) == 4:
        x = (poly[0][0] * (1-x_rate) + poly[1][0] * (1-x_rate) +
             poly[2][0] * x_rate + poly[3][0] * x_rate) / 2
        y = (poly[0][1] * (1-y_rate) + poly[3][1] * (1-y_rate) +
             poly[1][1] * y_rate + poly[2][1] * y_rate) / 2
    elif len(poly) == 2 and type(poly[0]).__name__ in ['list', 'tuple']:
        x = poly[0][0] * (1-x_rate) + poly[1][0] * x_rate
        y = poly[0][1] * (1-y_rate) + poly[1][1] * y_rate
    else:
        x, y = poly
    return (int(x), int(y))


class Solver:
    def __init__(self, adb=ADBConnector()):
        self.adb = adb
        self.recog = Recognizer(adb)
        self.run_once = False
        if self.adb.current_focus() != APPNAME:
            self.adb.start_app(APPNAME)
            time.sleep(10)

    def sleep(self, interval=1):
        time.sleep(interval)
        self.recog.update()

    def tap(self, poly, x_rate=0.5, y_rate=0.5, interval=1):
        pos = get_pos(poly, x_rate, y_rate)
        self.adb.touch_tap(pos)
        if interval > 0:
            self.sleep(interval)

    def recruit_choose_level1(self, tags, priority):
        if priority is None:
            priority = ['Lancet-2', 'Castle-3', 'THRM-EX']
        possibility = []
        for x in recruit_database:
            if x[1] != 1 or x[0] not in priority:
                continue
            valid = 0
            for tag in x[2]:
                if tag in tags:
                    valid |= (1<<tags.index(tag))
            for o in range(1, 1<<5):
                if o & valid == o:
                    if o not in possibility:
                        possibility.append(o)
        for x in recruit_database:
            if x[1] > 4:
                continue
            valid = 0
            for tag in x[2]:
                if tag in tags:
                    valid |= (1<<tags.index(tag))
            for o in range(1, 1<<5):
                if o & valid == o:
                    if o in possibility:
                        possibility.remove(o)
        logger.debug(possibility)
        if len(possibility) == 0:
            return []
        choose = []
        for i in range(len(tags)):
            if possibility[0] & (1<<i):
                choose.append(tags[i])
        return choose

    def recruit_choose(self, tags, priority):
        if priority is None:
            priority = ['因陀罗', '火神']
        possibility = {}
        for x in recruit_database:
            if x[1] == 6 and '高级资深干员' not in tags:
                continue
            if x[1] < 3:
                continue
            valid = 0
            if x[1] == 6:
                if '高级资深干员' in tags:
                    valid |= (1<<tags.index('高级资深干员'))
            if x[1] == 5:
                if '资深干员' in tags:
                    valid |= (1<<tags.index('资深干员'))
            for tag in x[2]:
                if tag in tags:
                    valid |= (1<<tags.index(tag))
            for o in range(1, 1<<5):
                if o & valid == o:
                    if o not in possibility.keys():
                        possibility[o] = [7, []]
                    possibility[o][0] = min(possibility[o][0], x[1])
                    possibility[o][1].append(x[0])
        for o in possibility.keys():
            minidx = 999
            for x in possibility[o][1]:
                if x in priority:
                    minidx = min(minidx, priority.index(x))
            if minidx != 999:
                possibility[o][0] += 0.5 - 0.5 * minidx / len(priority)
        logger.debug(possibility)
        maxlevel = 0
        maxlevel_choose = 0
        for o in possibility.keys():
            if maxlevel < possibility[o][0]:
                maxlevel = possibility[o][0]
                maxlevel_choose = o
        logger.debug(maxlevel_choose)
        choose = []
        for i in range(len(tags)):
            if maxlevel_choose & (1<<i):
                choose.append(tags[i])
        return choose, maxlevel
            

    def login(self):
        """
        登录进游戏
        """
        retry_times = 5
        while retry_times and self.recog.is_login() == False:
            try:
                if self.recog.scene == Scene.LOGIN_START:
                    self.tap((self.recog.w // 2, self.recog.h - 10))
                    self.sleep(3)
                elif self.recog.scene == Scene.LOGIN_QUICKLY:
                    self.tap(self.recog.find('login_awake'))
                elif self.recog.scene == Scene.LOGIN_MAIN:
                    self.tap(self.recog.find('login_account'))
                elif self.recog.scene == Scene.LOGIN_INPUT:
                    input_area = self.recog.find('login_username')
                    if input_area is not None:
                        logger.debug(f'input_area: {input_area}')
                        self.adb.touch_tap(get_pos(input_area))
                        self.adb.send_text(input('Enter username: ').strip())
                        self.adb.touch_tap((0, 0))
                    input_area = self.recog.find('login_password')
                    if input_area is not None:
                        logger.debug(f'input_area: {input_area}')
                        self.adb.touch_tap(get_pos(input_area))
                        self.adb.send_text(input('Enter password: ').strip())
                        self.adb.touch_tap((0, 0))
                    self.tap(self.recog.find('login_button'))
                elif self.recog.scene == Scene.LOGIN_ANNOUNCE:
                    self.tap(self.recog.find('login_iknow'))
                elif self.recog.scene == Scene.LOGIN_LOADING:
                    self.sleep(3)
                elif self.recog.scene == Scene.LOADING:
                    self.sleep(3)
                elif self.recog.scene == Scene.CONFIRM:
                    self.tap(detector.confirm(self.recog.img))
                else:
                    raise RecognizeError
            except RecognizeError:
                retry_times -= 1
                self.sleep(3)
                continue
            except Exception as e:
                raise e
            retry_times = 5
        assert self.recog.is_login()

    def get_navigation(self):
        """
        判断是否存在导航栏，若存在则打开
        """
        while True:
            if self.recog.get_scene() == Scene.NAVIGATION_BAR:
                return True
            else:
                navbutton = self.recog.find('navbutton')
                if navbutton is not None:
                    self.tap(navbutton)
                else:
                    return False

    def back_to_index(self):
        """
        返回主页
        """
        logger.info('back to index')
        retry_times = 5
        while retry_times and self.recog.get_scene() != Scene.INDEX:
            try:
                if self.get_navigation():
                    self.tap(self.recog.find('nav_index'))
                elif self.recog.scene == Scene.ANNOUNCEMENT:
                    self.tap(detector.announcement_close(self.recog.img))
                elif self.recog.scene == Scene.MATERIEL:
                    self.tap(self.recog.find('materiel'))
                elif self.recog.scene // 100 == 1:
                    self.login()
                elif self.recog.scene == Scene.CONFIRM:
                    self.tap(detector.confirm(self.recog.img))
                elif self.recog.scene == Scene.LOADING:
                    self.sleep(3)
                elif self.recog.scene == Scene.SKIP:
                    self.tap(self.recog.find('skip'))
                else:
                    raise RecognizeError
            except RecognizeError:
                retry_times -= 1
                self.sleep(3)
                continue
            except Exception as e:
                raise e
            retry_times = 5

        assert self.recog.get_scene() == Scene.INDEX

    def base(self):
        """
        收集基建的产物：物资、赤金、信赖
        """
        self.run_once = True
        retry_times = 5
        while retry_times > 0:
            try:
                if self.recog.scene == Scene.UNDEFINED:
                    self.recog.get_scene()
                if self.recog.scene == Scene.INDEX:
                    self.tap(self.recog.find('index_infrastructure'))
                elif self.recog.scene == Scene.INFRA_MAIN:
                    notification = detector.infra_notification(self.recog.img)
                    if notification is not None:
                        self.tap(notification)
                    else:
                        break
                elif self.recog.scene == Scene.INFRA_TODOLIST:
                    tapped = False
                    trust = self.recog.find('infra_collect_trust')
                    if trust is not None:
                        self.tap(trust)
                        tapped = True
                    bill = self.recog.find('infra_collect_bill')
                    if bill is not None:
                        self.tap(bill)
                        tapped = True
                    factory = self.recog.find('infra_collect_factory')
                    if factory is not None:
                        self.tap(factory)
                        tapped = True
                    if not tapped:
                        break
                elif self.recog.scene == Scene.LOADING:
                    self.sleep(3)
                elif self.get_navigation():
                    self.tap(self.recog.find('nav_infrastructure'))
                elif self.recog.scene != Scene.UNKNOWN:
                    self.back_to_index()
                else:
                    raise RecognizeError
            except RecognizeError:
                retry_times -= 1
                self.sleep(3)
                continue
            except Exception as e:
                raise e
            retry_times = 5

    def credit(self):
        """
        通过线索交换自动收集信用
        """
        self.run_once = True
        retry_times = 5
        while retry_times > 0:
            try:
                if self.recog.scene == Scene.UNDEFINED:
                    self.recog.get_scene()
                if self.recog.scene == Scene.INDEX:
                    self.tap(self.recog.find('index_friend'))
                elif self.recog.scene == Scene.FRIEND_LIST_OFF:
                    self.tap(self.recog.find('friend_list'))
                elif self.recog.scene == Scene.FRIEND_LIST_ON:
                    maxy = self.recog.find('friend_list_on')[1][1]
                    scope = [(0, 0), (100000, maxy)]
                    friend_visit = self.recog.find('friend_visit', scope=scope)
                    if friend_visit is not None:
                        self.tap(friend_visit)
                    else:
                        self.sleep(1)
                elif self.recog.scene == Scene.FRIEND_VISITING:
                    visit_next = detector.visit_next(self.recog.img)
                    if visit_next is not None:
                        self.tap(visit_next)
                    else:
                        break
                elif self.recog.scene == Scene.LOADING:
                    self.sleep(3)
                elif self.get_navigation():
                    self.tap(self.recog.find('nav_social'))
                elif self.recog.scene != Scene.UNKNOWN:
                    self.back_to_index()
                else:
                    raise RecognizeError
            except RecognizeError:
                retry_times -= 1
                self.sleep(3)
                continue
            except Exception as e:
                raise e
            retry_times = 5

    def choose_level(self, level):
        zone = level_database[level]['zone_id']
        zone = zone_database[zone]
        logger.info(f'章节：{zone[0]}')

        nav = self.recog.find('navbutton')
        nav[1][1] = self.recog.h
        bottom = self.recog.find('terminal_small')[0][1]
        if zone[1] == 0:
            self.tap((self.recog.w // 14 * 3, bottom))
            predict = []
            act_id = 999
            while act_id != zone[2]:
                _act_id = act_id
                act_id = -1
                for x in predict: 
                    if x[1] in theme_database[:_act_id]:
                        self.tap(x[2])
                        break
                predict = ocrhandle.predict(self.recog.img[nav[0][1]:nav[1][1], nav[0][0]:nav[1][0]])
                for x in predict:
                    if x[1][:7] == 'EPISODE':
                        episode = int(x[1][-2:])
                        act_id = zone_database[f'main_{episode}'][2]
                        break
                if act_id == -1 or _act_id == act_id:
                    raise RecognizeError
            cover = self.recog.find(f'main_{episode}')
            while zone[3] < episode:
                self.adb.touch_swipe((cover[0][0], cover[0][1]), (cover[1][0] - cover[0][0], 0))
                self.sleep(1)
                episode -= 1
            while episode < zone[3]:
                self.adb.touch_swipe((cover[1][0], cover[0][1]), (cover[0][0] - cover[1][0], 0))
                self.sleep(1)
                episode += 1
            self.tap(cover)
        elif zone[1] == 1:
            self.tap((self.recog.w // 14 * 5, bottom))
            predict = ocrhandle.predict(self.recog.img[nav[0][1]:nav[1][1], nav[0][0]:nav[1][0]])
            for x in predict:
                if x[1] == zone[0]:
                    self.tap(x[2])
            self.tap(self.recog.find('enter'))
        elif zone[1] == 2:
            self.tap((self.recog.w // 14 * 7, bottom))
            predict = ocrhandle.predict(self.recog.img[nav[0][1]:nav[1][1], nav[0][0]:nav[1][0]])
            for x in predict:
                if x[1] == zone[0]:
                    self.tap(x[2])
            self.tap(self.recog.find('enter'))
        elif zone[1] == 3:
            self.tap((self.recog.w // 14 * 9, bottom))
            predict = ocrhandle.predict(self.recog.img)
            unable = list(filter(lambda x: x[1] == '不可进入', predict))
            predict = list(filter(lambda x: x[1] in weekly_zones, predict))
            weekly = sorted([x[1] for x in predict])
            while zone[0] not in weekly:
                _weekly = weekly
                self.adb.touch_swipe((self.recog.w // 4, self.recog.h // 4), (self.recog.w // 16, 0))
                self.sleep(1)
                predict = ocrhandle.predict(self.recog.img)
                unable = list(filter(lambda x: x[1] == '不可进入', predict))
                predict = list(filter(lambda x: x[1] in weekly_zones, predict))
                weekly = sorted([x[1] for x in predict])
                if _weekly == weekly:
                    break
            while zone[0] not in weekly:
                _weekly = weekly
                self.adb.touch_swipe((self.recog.w // 4, self.recog.h // 4), (-self.recog.w // 16, 0))
                self.sleep(1)
                predict = ocrhandle.predict(self.recog.img)
                unable = list(filter(lambda x: x[1] == '不可进入', predict))
                predict = list(filter(lambda x: x[1] in weekly_zones, predict))
                weekly = sorted([x[1] for x in predict])
                if _weekly == weekly:
                    break
            if zone[0] not in weekly:
                raise RecognizeError
            for x in predict:
                if x[1] == zone[0]:
                    for item in unable:
                        if x[2][0][0] < item[2][0][0] < x[2][1][0]:
                            raise LevelUnopenError
                    self.tap(x[2])
                    break
        else:
            raise RecognizeError
        
        predict = ocrhandle.predict(self.recog.img)
        predict = list(filter(lambda x: x[1] in level_database.keys(), predict))
        levels = sorted([x[1] for x in predict])
        while level not in levels:
            _levels = levels
            self.adb.touch_swipe((self.recog.w // 4, self.recog.h // 4), (self.recog.w // 16, 0))
            self.sleep(1)
            predict = ocrhandle.predict(self.recog.img)
            predict = list(filter(lambda x: x[1] in level_database.keys(), predict))
            levels = sorted([x[1] for x in predict])
            if _levels == levels:
                break
        while level not in levels:
            _levels = levels
            self.adb.touch_swipe((self.recog.w // 4, self.recog.h // 4), (-self.recog.w // 16, 0))
            self.sleep(1)
            predict = ocrhandle.predict(self.recog.img)
            predict = list(filter(lambda x: x[1] in level_database.keys(), predict))
            levels = sorted([x[1] for x in predict])
            if _levels == levels:
                break
        for x in predict:
            if x[1] == level:
                self.tap(x[2])
                return
        raise RecognizeError

    def fight(self, potion=0, originite=0, times=-1, level=None):
        """
        自动前往上一次作战刷体力
        :param potion: 最多使用药剂恢复体力的次数，-1 为无限制
        :param originite: 最多使用源石恢复体力的次数，-1 为无限制
        """
        if level is not None and level not in level_database.keys():
            logger.info('非法输入')
            return
        self.run_once = True
        recovering = 0
        need_eliminate = False
        retry_times = 5
        while retry_times > 0:
            try:
                if self.recog.scene == Scene.UNDEFINED:
                    self.recog.get_scene()
                if self.recog.scene == Scene.INDEX:
                    self.tap(self.recog.find('index_terminal'))
                elif self.recog.scene == Scene.TERMINAL_MAIN:
                    if level is not None:
                        self.choose_level(level)
                    else:
                        eliminate = self.recog.find('terminal_eliminate')
                        if eliminate is not None:
                            need_eliminate = True
                            self.tap(eliminate)
                        else:
                            self.tap(self.recog.find('terminal_pre'))
                elif self.recog.scene == Scene.OPERATOR_BEFORE:
                    if times == 0:
                        break
                    agency = self.recog.find('ope_agency')
                    if agency is not None:
                        self.tap(agency)
                    else:
                        self.tap(self.recog.find('ope_start'))
                        if recovering == 1:
                            logger.info('use potion to recover sanity')
                            potion -= 1
                        elif recovering == 2:
                            logger.info('use originite to recover sanity')
                            originite -= 1
                        elif recovering != 0:
                            raise RuntimeError(
                                f'recovering: unknown type {recovering}')
                        recovering = 0
                elif self.recog.scene == Scene.OPERATOR_ELIMINATE:
                    agency = self.recog.find('ope_agency')
                    if agency is not None:
                        self.tap(agency)
                    elif need_eliminate == False:
                        self.get_navigation()
                        self.tap(self.recog.find('nav_terminal'))
                    else:
                        self.tap(self.recog.find('ope_start'))
                        if recovering == 1:
                            logger.info('use potion to recover sanity')
                            potion -= 1
                        elif recovering == 2:
                            logger.info('use originite to recover sanity')
                            originite -= 1
                        elif recovering != 0:
                            raise RuntimeError(
                                f'recovering: unknown type {recovering}')
                        recovering = 0
                elif self.recog.scene == Scene.OPERATOR_SELECT:
                    need_eliminate = False
                    self.tap(self.recog.find('ope_select_start'))
                elif self.recog.scene == Scene.OPERATOR_ONGOING:
                    self.sleep(10)
                elif self.recog.scene == Scene.OPERATOR_FINISH:
                    times -= 1
                    self.tap((10, 10))
                elif self.recog.scene == Scene.OPERATOR_ELIMINATE_FINISH:
                    self.tap((10, 10))
                elif self.recog.scene == Scene.DOUBLE_CONFIRM:
                    self.tap(self.recog.find('double_confirm'), 0.2)
                elif self.recog.scene == Scene.OPERATOR_RECOVER_POTION:
                    if potion == 0:
                        if originite != 0:
                            self.tap(self.recog.find('ope_recover_originite'))
                        else:
                            self.tap(self.recog.find('ope_recover_choose'), x_rate=0.05)
                            break
                    elif recovering:
                        self.sleep(3)
                    else:
                        self.tap(self.recog.find('ope_recover_choose'), x_rate=0.95)
                        recovering = 1
                elif self.recog.scene == Scene.OPERATOR_RECOVER_ORIGINITE:
                    if originite == 0:
                        if potion != 0:
                            self.tap(self.recog.find('ope_recover_potion'))
                        else:
                            self.tap(self.recog.find('ope_recover_choose'), x_rate=0.05)
                            break
                    elif recovering:
                        self.sleep(3)
                    else:
                        self.tap(self.recog.find('ope_recover_choose'), x_rate=0.95)
                        recovering = 2
                elif self.recog.scene == Scene.LOADING:
                    self.sleep(3)
                elif self.recog.scene == Scene.UPGRADE:
                    self.tap(self.recog.find('upgrade'))
                elif self.recog.scene == Scene.OPERATOR_DROP:
                    self.tap(self.recog.find('navbutton'), 0.2)
                elif self.get_navigation():
                    self.tap(self.recog.find('nav_terminal'))
                elif self.recog.scene != Scene.UNKNOWN:
                    self.back_to_index()
                else:
                    raise RecognizeError
            except LevelUnopenError:
                logger.info('关卡未开放')
                return
            except RecognizeError:
                retry_times -= 1
                self.sleep(3)
                continue
            except Exception as e:
                raise e
            retry_times = 5

    def shop(self, priority=None):
        """
        自动购买物资清空信用
        """
        self.run_once = True
        retry_times = 5
        while retry_times > 0:
            try:
                if self.recog.scene == Scene.UNDEFINED:
                    self.recog.get_scene()
                if self.recog.scene == Scene.INDEX:
                    self.tap(self.recog.find('index_shop'))
                elif self.recog.scene == Scene.SHOP_OTHERS:
                    self.tap(self.recog.find('shop_credit'))
                elif self.recog.scene == Scene.SHOP_CREDIT:
                    collect = self.recog.find('shop_collect')
                    if collect is not None:
                        self.tap(collect)
                    else:
                        segments = segment.credit(self.recog.img)
                        if segments is None:
                            raise RecognizeError
                        valid = []
                        for seg in segments:
                            if self.recog.find('shop_sold', scope=seg) is None:
                                predict = ocrhandle.predict(self.recog.img[seg[0][1]:seg[0][1]+64, seg[0][0]:seg[1][0]])
                                valid.append((seg, predict[0][1]))
                        logger.debug(valid)
                        if len(valid) == 0:
                            break
                        if priority is not None:
                            valid.sort(key=lambda x: 9999 if x[1] not in priority else priority.index(x[1]))
                            if valid[0][1] not in priority:
                                break
                        self.tap(valid[0][0])
                elif self.recog.scene == Scene.SHOP_CREDIT_CONFIRM:
                    if self.recog.find('shop_credit_not_enough') is None:
                        self.tap(self.recog.find('shop_cart'))
                    else:
                        break
                elif self.recog.scene == Scene.MATERIEL:
                    self.tap(self.recog.find('materiel'))
                elif self.recog.scene == Scene.LOADING:
                    self.sleep(3)
                elif self.get_navigation():
                    self.tap(self.recog.find('nav_shop'))
                elif self.recog.scene != Scene.UNKNOWN:
                    self.back_to_index()
                else:
                    raise RecognizeError
            except RecognizeError:
                retry_times -= 1
                self.sleep(3)
                continue
            except Exception as e:
                raise e
            retry_times = 5

    def recruit(self, priority=None):
        """
        自动完成公招
        """
        self.run_once = True
        retry_times = 5
        while retry_times > 0:
            try:
                if self.recog.scene == Scene.UNDEFINED:
                    self.recog.get_scene()
                if self.recog.scene == Scene.INDEX:
                    self.tap(self.recog.find('index_recruit'))
                elif self.recog.scene == Scene.RECRUIT_MAIN:
                    segments = segment.recruit(self.recog.img)
                    tapped = False
                    for seg in segments:
                        finished = self.recog.find('recruit_finish', scope=seg)
                        if finished is not None:
                            self.tap(finished)
                            tapped = True
                            break
                        required = self.recog.find('job_requirements', scope=seg)
                        if required is None:
                            self.tap(seg)
                            tapped = True
                            break
                    if not tapped:
                        break
                elif self.recog.scene == Scene.RECRUIT_TAGS:
                    needs = self.recog.find('career_needs')
                    avail_level = self.recog.find('available_level')
                    budget = self.recog.find('recruit_budget')
                    up = needs[0][1] - 80
                    down = needs[1][1] + 60
                    left = needs[1][0]
                    right = avail_level[0][0]
                    while True:
                        predict = ocrhandle.predict(self.recog.img[up:down, left:right])
                        choose, maxlevel = self.recruit_choose([x[1] for x in predict], priority)
                        if maxlevel < 4:
                            refresh = self.recog.find('recruit_refresh')
                            if refresh is not None:
                                self.tap(refresh)
                                self.tap(self.recog.find('double_confirm'), 0.8)
                                continue
                            if maxlevel <= 3:
                                choose = []
                        break
                    for x in predict:
                        color = self.recog.img[up+x[2][0][1]-5, left+x[2][0][0]-5]
                        if (color[2] < 100) != (x[1] not in choose):
                            self.adb.touch_tap((left+x[2][0][0]-5, up+x[2][0][1]-5))
                    self.tap(self.recog.find('one_hour'), 0.2, 0.8, 0)
                    self.tap((avail_level[1][0], budget[0][1]), interval=5)
                elif self.recog.scene == Scene.SKIP:
                    self.tap(self.recog.find('skip'))
                elif self.recog.scene == Scene.RECRUIT_AGENT:
                    self.tap((10, 10))
                elif self.recog.scene == Scene.MATERIEL:
                    self.tap(self.recog.find('materiel'))
                elif self.recog.scene == Scene.LOADING:
                    self.sleep(3)
                elif self.get_navigation():
                    self.tap(self.recog.find('nav_recruit'))
                elif self.recog.scene != Scene.UNKNOWN:
                    self.back_to_index()
                else:
                    raise RecognizeError
            except RecognizeError:
                retry_times -= 1
                self.sleep(3)
                continue
            except Exception as e:
                raise e
            retry_times = 5

    def mission(self):
        """
        点击确认完成每日任务和每周任务
        """
        self.run_once = True
        checked = 0
        retry_times = 5
        while retry_times > 0:
            try:
                if self.recog.scene == Scene.UNDEFINED:
                    self.recog.get_scene()
                if self.recog.scene == Scene.INDEX:
                    self.tap(self.recog.find('index_mission'))
                elif self.recog.scene == Scene.MISSION_DAILY:
                    checked |= 1
                    collect = self.recog.find('mission_collect')
                    if collect is None:
                        self.sleep(1)
                        collect = self.recog.find('mission_collect')
                    if collect is not None:
                        self.tap(collect)
                    elif checked & 2 == 0:
                        self.tap(self.recog.find('mission_weekly'))
                    else:
                        break
                elif self.recog.scene == Scene.MISSION_WEEKLY:
                    checked |= 2
                    collect = self.recog.find('mission_collect')
                    if collect is None:
                        self.sleep(1)
                        collect = self.recog.find('mission_collect')
                    if collect is not None:
                        self.tap(collect)
                    elif checked & 1 == 0:
                        self.tap(self.recog.find('mission_daily'))
                    else:
                        break
                elif self.recog.scene == Scene.MATERIEL:
                    self.tap(self.recog.find('materiel'))
                elif self.recog.scene == Scene.LOADING:
                    self.sleep(3)
                elif self.get_navigation():
                    self.tap(self.recog.find('nav_mission'))
                elif self.recog.scene != Scene.UNKNOWN:
                    self.back_to_index()
                else:
                    raise RecognizeError
            except RecognizeError:
                retry_times -= 1
                self.sleep(3)
                continue
            except Exception as e:
                raise e
            retry_times = 5
