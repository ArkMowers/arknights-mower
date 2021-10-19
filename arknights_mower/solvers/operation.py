import time
import traceback

import string

from ..ocr import ocrhandle
from ..utils.log import logger
from ..utils.config import MAX_RETRYTIME
from ..utils.recognize import Scene, RecognizeError
from ..utils.solver import BaseSolver, StrategyError
from ..data.level import level_database, zone_database, theme_database, weekly_zones


class LevelUnopenError(Exception):
    pass


class OpeSolver(BaseSolver):
    """
    自动作战策略
    """

    def __init__(self, adb=None, recog=None):
        super(OpeSolver, self).__init__(adb, recog)

    def run(self, times: int = -1, potion: int = 0, originite: int = 0, level: str = None, plan: list = None, eliminate: bool = False):
        """
        :param times: int, 作战的次数上限，-1 为无限制，默认为 -1
        :param potion: int, 使用药剂恢复体力的次数上限，-1 为无限制，默认为 0
        :param originite: int, 使用源石恢复体力的次数上限，-1 为无限制，默认为 0
        :param level: str, 指定关卡，默认为前往上一次关卡
        :param plan: [[str, int]...], 指定多个关卡以及次数，优先级高于 level
        :param eliminate: bool, 是否优先处理未完成的每周剿灭，默认为 False

        :return remain_plan: [[str, int]...], 未完成的计划
        """
        logger.info('Start: 作战')

        if level is not None and plan is not None:
            logger.error('不可同时指定 level 和 plan')
            return
        if plan is not None:
            for x in plan:
                if x[0] not in level_database.keys() or level_database[x[0]]['ap_cost'] == 0:
                    logger.error(f'不支持关卡 {x[0]}，请重新指定')
                    return
        if level is not None:
            if level not in level_database.keys() or level_database[level]['ap_cost'] == 0:
                logger.error(f'不支持关卡 {level}，请重新指定')
                return
            plan = [[level, times]]
        if plan is None:
            plan = [['pre_ope', times]]
        logger.debug(f'plan: {plan}')

        recover_state = 0
        need_eliminate = False
        wait_start = 10
        wait_total = 0
        choosed = plan[0][0] == 'pre_ope'

        retry_times = MAX_RETRYTIME
        while retry_times > 0:
            try:
                while len(plan) > 0 and plan[0][1] == 0:
                    plan = plan[1:]
                    choosed = False
                if len(plan) == 0:
                    return
                if self.scene() == Scene.INDEX:
                    self.tap_element('index_terminal')
                elif self.scene() == Scene.TERMINAL_MAIN:
                    eliminate_todo = self.recog.find('terminal_eliminate')
                    if eliminate_todo is None:
                        eliminate = False
                    if eliminate and eliminate_todo is not None:
                        need_eliminate = True
                        self.tap(eliminate_todo)
                    else:
                        self.choose_level(plan[0][0])
                        choosed = True
                elif self.scene() == Scene.OPERATOR_BEFORE:
                    if not choosed:
                        self.get_navigation()
                        self.tap_element('nav_terminal')
                        continue
                    agency = self.recog.find('ope_agency')
                    if agency is not None:
                        self.tap(agency)
                    else:
                        self.tap_element('ope_start')
                        if recover_state == 1:
                            logger.info('use potion to recover sanity')
                            potion -= 1
                        elif recover_state == 2:
                            logger.info('use originite to recover sanity')
                            originite -= 1
                        elif recover_state != 0:
                            raise RuntimeError(
                                f'recover_state: unknown type {recover_state}')
                        recover_state = 0
                elif self.scene() == Scene.OPERATOR_ELIMINATE:
                    agency = self.recog.find('ope_agency')
                    if agency is not None:
                        self.tap(agency)
                    elif not (eliminate and need_eliminate):
                        self.get_navigation()
                        self.tap_element('nav_terminal')
                    else:
                        self.tap_element('ope_start')
                        if recover_state == 1:
                            logger.info('use potion to recover sanity')
                            potion -= 1
                        elif recover_state == 2:
                            logger.info('use originite to recover sanity')
                            originite -= 1
                        elif recover_state != 0:
                            raise RuntimeError(
                                f'recover_state: unknown type {recover_state}')
                        recover_state = 0
                elif self.scene() == Scene.OPERATOR_SELECT:
                    self.tap_element('ope_select_start')
                elif self.scene() == Scene.OPERATOR_ONGOING:
                    self.adb.touch_tap((1, 1))  # 保持屏幕常亮
                    if wait_total < wait_start:
                        if wait_total == 0:
                            logger.info(f'等待 {wait_start} 秒')
                        wait_total += 10
                        if wait_total == wait_start:
                            self.sleep(10)
                        else:
                            time.sleep(10)
                    else:
                        logger.info(f'等待 10 秒')
                        wait_total += 10
                        self.sleep(10)
                elif self.scene() == Scene.OPERATOR_FINISH:
                    if wait_total > 0:
                        wait_start = max(10, wait_total - 10)
                        wait_total = 0
                    if choosed:
                        plan[0][1] -= 1
                    self.tap((self.recog.w // 2, 10))
                elif self.scene() == Scene.OPERATOR_ELIMINATE_FINISH:
                    need_eliminate = False
                    self.tap((self.recog.w // 2, 10))
                # elif self.scene() == Scene.DOUBLE_CONFIRM:
                #     self.tap_element('double_confirm', 0.2)
                elif self.scene() == Scene.OPERATOR_GIVEUP:
                    logger.error('代理出现失误')
                    exit()
                elif self.scene() == Scene.OPERATOR_RECOVER_POTION:
                    if potion == 0:
                        if originite != 0:
                            self.tap_element('ope_recover_originite')
                        else:
                            self.tap_element('ope_recover_choose', 0.05)
                            if plan[0][0] != 'pre_ope' and level is None:
                                return plan
                            return
                    elif recover_state:
                        self.sleep(3)
                    else:
                        self.tap_element('ope_recover_choose', 0.95)
                        recover_state = 1
                elif self.scene() == Scene.OPERATOR_RECOVER_ORIGINITE:
                    if originite == 0:
                        if potion != 0:
                            self.tap_element('ope_recover_potion')
                        else:
                            self.tap_element('ope_recover_choose', 0.05)
                            if plan[0][0] != 'pre_ope' and level is None:
                                return plan
                            return
                    elif recover_state:
                        self.sleep(3)
                    else:
                        self.tap_element('ope_recover_choose', 0.95)
                        recover_state = 2
                elif self.scene() == Scene.LOADING:
                    self.sleep(3)
                elif self.scene() == Scene.UPGRADE:
                    self.tap_element('upgrade')
                elif self.scene() == Scene.OPERATOR_DROP:
                    self.tap_element('nav_button', 0.2)
                elif self.get_navigation():
                    self.tap_element('nav_terminal')
                elif self.scene() != Scene.UNKNOWN:
                    self.back_to_index()
                else:
                    raise RecognizeError
            except LevelUnopenError:
                logger.error(f'关卡 {plan[0][0]} 未开放，请重新指定')
                plan = plan[1:]
                choosed = False
                continue
            except RecognizeError:
                logger.warn('识别出了点小差错 qwq')
                retry_times -= 1
                self.sleep(3)
                continue
            except StrategyError as e:
                logger.error(e)
                logger.debug(traceback.format_exc())
                return
            except Exception as e:
                raise e
            retry_times = MAX_RETRYTIME

    def choose_level(self, level):
        if level == 'pre_ope':
            logger.info(f'前往上一次关卡')
            self.tap_element('terminal_pre')
            return

        zone = level_database[level]['zone_id']
        zone = zone_database[zone]
        logger.info(f'关卡：{level}')
        logger.info(f'章节：{zone[0]}')

        nav = self.recog.nav_button()
        nav[1][1] = self.recog.h
        bottom = self.recog.h - 10
        if zone[1] == 0:
            self.tap((self.recog.w // 14 * 3, bottom))
            predict = []
            act_id = 999
            while act_id != zone[2]:
                _act_id = act_id
                act_id = -1
                for x in predict:
                    if zone[2] < _act_id:
                        if x[1].upper().replace(' ', '') == theme_database[_act_id-1]:
                            self.tap(x[2])
                            break
                    else:
                        if x[1].upper().replace(' ', '') == theme_database[_act_id+1]:
                            self.tap(x[2])
                            break
                predict = ocrhandle.predict(
                    self.recog.img[nav[0][1]:nav[1][1], nav[0][0]:nav[1][0]])
                for x in predict:
                    if x[1][:7].upper() == 'EPISODE' and len(x[1]) == 9:
                        try:
                            episode = int(x[1][-2:])
                            act_id = zone_database[f'main_{episode}'][2]
                            break
                        except:
                            raise RecognizeError
                if act_id == -1 or _act_id == act_id:
                    raise RecognizeError
            cover = self.recog.find(f'main_{episode}')
            while zone[3] < episode:
                self.swipe((cover[0][0], cover[0][1]),
                           (cover[1][0] - cover[0][0], 0))
                episode -= 1
            while episode < zone[3]:
                self.swipe((cover[1][0], cover[0][1]),
                           (cover[0][0] - cover[1][0], 0))
                episode += 1
            self.tap(cover)
        elif zone[1] == 1:
            self.tap((self.recog.w // 14 * 5, bottom))
            predict = ocrhandle.predict(
                self.recog.img[nav[0][1]:nav[1][1], nav[0][0]:nav[1][0]])
            for x in predict:
                if x[1] == zone[0]:
                    self.tap(x[2])
            self.tap_element('enter')
        elif zone[1] == 2:
            self.tap((self.recog.w // 14 * 7, bottom))
            predict = ocrhandle.predict(
                self.recog.img[nav[0][1]:nav[1][1], nav[0][0]:nav[1][0]])
            for x in predict:
                if x[1] == zone[0]:
                    self.tap(x[2])
            self.tap_element('enter')
        elif zone[1] == 3:
            self.tap((self.recog.w // 14 * 9, bottom))
            predict = ocrhandle.predict(self.recog.img)
            unable = list(filter(lambda x: x[1] == '不可进入', predict))
            predict = list(filter(lambda x: x[1] in weekly_zones, predict))
            weekly = sorted([x[1] for x in predict])
            while zone[0] not in weekly:
                _weekly = weekly
                self.swipe((self.recog.w // 4, self.recog.h // 4),
                           (self.recog.w // 16, 0))
                predict = ocrhandle.predict(self.recog.img)
                unable = list(filter(lambda x: x[1] == '不可进入', predict))
                predict = list(filter(lambda x: x[1] in weekly_zones, predict))
                weekly = sorted([x[1] for x in predict])
                if _weekly == weekly:
                    break
            while zone[0] not in weekly:
                _weekly = weekly
                self.swipe((self.recog.w // 4, self.recog.h // 4),
                           (-self.recog.w // 16, 0))
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
        predict = list(
            filter(lambda x: x[1] in level_database.keys(), predict))
        levels = sorted([x[1] for x in predict])
        retry_times = 3
        while level not in levels:
            _levels = levels
            self.swipe((self.recog.w // 4, self.recog.h // 4),
                       (self.recog.w // 16, 0))
            predict = ocrhandle.predict(self.recog.img)
            predict = list(
                filter(lambda x: x[1] in level_database.keys(), predict))
            levels = sorted([x[1] for x in predict])
            if _levels == levels:
                retry_times -= 1
                if retry_times == 0:
                    break
            retry_times = 3
        retry_times = 3
        while level not in levels:
            _levels = levels
            self.swipe((self.recog.w // 4, self.recog.h // 4),
                       (-self.recog.w // 16, 0))
            predict = ocrhandle.predict(self.recog.img)
            predict = list(
                filter(lambda x: x[1] in level_database.keys(), predict))
            levels = sorted([x[1] for x in predict])
            if _levels == levels:
                retry_times -= 1
                if retry_times == 0:
                    break
            retry_times = 3
        for x in predict:
            if x[1] == level:
                self.tap(x[2])
                return
        raise RecognizeError
