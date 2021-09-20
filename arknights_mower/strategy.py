import time

from .utils.log import logger
from .utils.adb import ADBConnector, KeyCode
from .utils.recognize import Recognizer, Scene, RecognizeError
from .utils import segment, detector

APP = 'com.hypergryph.arknights/com.u8.sdk.U8UnityContext'


def get_pos(poly, x_rate=0.5, y_rate=0.5):
    if poly is None:
        raise RecognizeError
    elif len(poly) == 4:
        x = (poly[0][0] * (1-x_rate) + poly[1][0] * (1-x_rate) +
             poly[2][0] * x_rate + poly[3][0] * x_rate) / 2
        y = (poly[0][1] * (1-y_rate) + poly[3][1] * (1-y_rate) +
             poly[1][1] * y_rate + poly[2][1] * y_rate) / 2
    elif len(poly) == 2 and type(poly[0]).__name__ == 'list':
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
        if self.adb.current_focus() != APP:
            self.adb.start_app(APP)
            time.sleep(10)

    def sleep(self, interval=1):
        time.sleep(interval)
        self.recog.update()

    def tap(self, poly, x_rate=0.5, y_rate=0.5, interval=1):
        pos = get_pos(poly, x_rate, y_rate)
        self.adb.touch_tap(pos)
        self.sleep(interval)

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
                    self.tap(detector.confirm(self.img))
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
                    trust = self.recog.find('infra_collect_trust')
                    if trust is not None:
                        self.tap(trust)
                    bill = self.recog.find('infra_collect_bill')
                    if bill is not None:
                        self.tap(bill)
                    factory = self.recog.find('infra_collect_factory')
                    if factory is not None:
                        self.tap(factory)
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
                    friend_next = self.recog.find('friend_next')
                    x = (friend_next[0][0] + friend_next[3][0]) // 2
                    y = friend_next[0][1]
                    if self.recog.color(x, y)[0] > 100:
                        self.tap(friend_next)
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

    def fight(self, potion=0, originite=0):
        """
        自动前往上一次作战刷体力
        :param potion: 最多使用药剂恢复体力的次数，-1 为无限制
        :param originite: 最多使用源石恢复体力的次数，-1 为无限制
        """
        self.run_once = True
        recovering = 0
        retry_times = 5
        while retry_times > 0:
            try:
                if self.recog.scene == Scene.UNDEFINED:
                    self.recog.get_scene()
                if self.recog.scene == Scene.INDEX:
                    self.tap(self.recog.find('index_terminal'))
                elif self.recog.scene == Scene.TERMINAL_MAIN:
                    self.tap(self.recog.find('terminal_pre'))
                elif self.recog.scene == Scene.OPERATOR_BEFORE:
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
                elif self.recog.scene == Scene.OPERATOR_SELECT:
                    self.tap(self.recog.find('ope_select_start'))
                elif self.recog.scene == Scene.OPERATOR_ONGOING:
                    self.sleep(10)
                elif self.recog.scene == Scene.OPERATOR_FINISH:
                    self.adb.touch_tap((10, 10))
                    self.sleep(1)
                elif self.recog.scene == Scene.OPERATOR_INTERRUPT:
                    self.tap(self.recog.find('ope_interrupt_no'))
                elif self.recog.scene == Scene.OPERATOR_RECOVER_POTION:
                    if potion == 0:
                        if originite != 0:
                            self.tap(self.recog.find('ope_recover_originite'))
                        else:
                            self.tap(self.recog.find('ope_recover_potion_no'))
                            break
                    elif recovering:
                        self.sleep(3)
                    else:
                        self.tap(self.recog.find('ope_recover_potion_yes'))
                        recovering = 1
                elif self.recog.scene == Scene.OPERATOR_RECOVER_ORIGINITE:
                    if originite == 0:
                        if potion != 0:
                            self.tap(self.recog.find('ope_recover_potion'))
                        else:
                            self.tap(self.recog.find('ope_recover_originite_no'))
                            break
                    elif recovering:
                        self.sleep(3)
                    else:
                        self.tap(self.recog.find('ope_recover_originite_yes'))
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
            except RecognizeError:
                retry_times -= 1
                self.sleep(3)
                continue
            except Exception as e:
                raise e
            retry_times = 5

    def shop(self):
        """
        自动购买物资清空信用
        """
        self.run_once = True
        sold = 0
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
                        sold = False
                        for seg in segments[sold:]:
                            if self.recog.find('shop_sold', scope=seg) is None:
                                self.tap(seg)
                                break
                            else:
                                sold += 1
                        if sold == 10:
                            break
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

    def recruit(self):
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
                # elif self.recog.scene == Scene.RECRUIT_MAIN:
                #     segments = segment.recruit(self.recog.img)
                #     for seg in segments:
                #         finished = self.recog.find('recruit_finish', scope=seg)
                #         if finished is not None:
                #             self.tap(finished)
                #             break
                #         else:
                #             sold += 1
                #     if sold == 10:
                #         break
                # elif self.recog.scene == Scene.SHOP_OTHERS:
                #     self.tap(self.recog.find('shop_credit'))
                # elif self.recog.scene == Scene.SHOP_CREDIT:
                #     collect = self.recog.find('shop_collect')
                #     if collect is not None:
                #         self.tap(collect)
                #     else:
                #         segments = segment.credit(bytes2img(self.recog.screencap))
                #         sold = False
                #         for seg in segments[sold:]:
                #             if self.recog.find('shop_sold', scope=seg) is None:
                #                 self.tap(seg)
                #                 break
                #             else:
                #                 sold += 1
                #         if sold == 10:
                #             break
                # elif self.recog.scene == Scene.SHOP_CREDIT_CONFIRM:
                #     if self.recog.find('shop_credit_not_enough') is None:
                #         self.tap(self.recog.find('shop_cart'))
                #     else:
                #         break
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
