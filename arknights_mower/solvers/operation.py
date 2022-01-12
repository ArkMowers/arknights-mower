import time
import traceback

import string

from ..ocr import ocrhandle
from ..utils import config
from ..utils.log import logger
from ..utils.recognize import Scene, RecognizeError
from ..utils.solver import BaseSolver, StrategyError
from ..data.level import level_list, zone_list, theme_list, weekly_zones


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
        :param level: str, 指定关卡，默认为前往上一次关卡或当前界面关卡
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
                if x[0] not in level_list.keys() or level_list[x[0]]['ap_cost'] == 0:
                    logger.error(f'不支持关卡 {x[0]}，请重新指定')
                    return
        if level is not None:
            if level not in level_list.keys() or level_list[level]['ap_cost'] == 0:
                logger.error(f'不支持关卡 {level}，请重新指定')
                return
            plan = [[level, times]]
        if plan is None:
            plan = [['pre_ope', times]]  # 上一次作战关卡
        logger.debug(f'plan: {plan}')

        recover_state = 0  # 有关体力恢复的状态，0 为未知，1 为体力药剂恢复中，2 为源石恢复中（防止网络波动）
        eliminate_state = 0  # 有关每周剿灭的状态，0 为未知，1 为未完成，2 为已完成
        wait_pre = 10  # 作战时每次等待的时长，普通关卡为 10s，剿灭关卡为 60s
        wait_start = 0  # 作战时第一次等待的时长
        wait_total = 0  # 作战时累计等待的时长
        level_choosed = plan[0][0] == 'pre_ope'  # 是否已经选定关卡
        unopen = []

        retry_times = config.MAX_RETRYTIME
        while retry_times > 0:
            try:
                while len(plan) > 0 and plan[0][1] == 0:
                    plan = plan[1:]
                    wait_start = 0
                    level_choosed = False
                if len(plan) == 0:
                    return unopen
                if self.scene() == Scene.INDEX:
                    self.tap_element('index_terminal')
                elif self.scene() == Scene.TERMINAL_MAIN:
                    eliminate_todo = self.recog.find('terminal_eliminate')
                    if eliminate_todo is not None:
                        eliminate_state = 1
                    else:
                        eliminate_state = 2
                    if eliminate and eliminate_todo is not None:
                        self.tap(eliminate_todo)
                    else:
                        self.choose_level(plan[0][0])
                        level_choosed = True
                elif self.scene() == Scene.OPERATOR_BEFORE:
                    if not level_choosed:
                        self.get_navigation()
                        self.tap_element('nav_terminal')
                        continue
                    agency = self.recog.find('ope_agency')
                    if agency is not None:
                        self.tap(agency)
                    else:
                        if wait_pre != 10:
                            wait_start = 0
                            wait_pre = 10
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
                    if eliminate_state == 0:
                        self.get_navigation()
                        self.tap_element('nav_terminal')
                        continue
                    if eliminate_state == 2:
                        logger.warning('检测到关卡为剿灭，但每周剿灭任务已完成')
                        break
                    agency = self.recog.find('ope_agency')
                    if agency is not None:
                        self.tap(agency)
                    else:
                        if wait_pre != 60:
                            wait_start = 0
                            wait_pre = 60
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
                    if wait_total < wait_start:
                        if wait_total == 0:
                            logger.info(f'等待 {wait_start} 秒')
                        wait_total += wait_pre
                        if wait_total == wait_start:
                            self.sleep(wait_pre)
                        else:
                            time.sleep(wait_pre)
                    else:
                        logger.info(f'等待 {wait_pre} 秒')
                        wait_total += wait_pre
                        self.sleep(wait_pre)
                elif self.scene() == Scene.OPERATOR_FINISH:
                    if wait_total > 0:
                        if wait_start == 0:
                            wait_start = wait_total - wait_pre
                        else:
                            wait_start = min(wait_start + wait_pre, wait_total - wait_pre)
                        wait_total = 0
                    if level_choosed:
                        plan[0][1] -= 1
                    self.tap((self.recog.w // 2, 10))
                elif self.scene() == Scene.OPERATOR_ELIMINATE_FINISH:
                    eliminate_state = 0
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
                                return plan + unopen
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
                                return plan + unopen
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
                unopen.append(plan[0])
                plan = plan[1:]
                wait_start = 0
                level_choosed = False
                continue
            except RecognizeError as e:
                logger.warning(f'识别出了点小差错 qwq: {e}')
                retry_times -= 1
                self.sleep(3)
                continue
            except StrategyError as e:
                logger.error(e)
                logger.debug(traceback.format_exc())
                return plan + unopen
            except Exception as e:
                raise e
            retry_times = config.MAX_RETRYTIME

    def choose_level(self, level):
        if level == 'pre_ope':
            logger.info(f'前往上一次关卡')
            self.tap_element('terminal_pre')
            return

        zone = level_list[level]['zone_id']
        zone = zone_list[zone]
        logger.info(f'关卡：{level}')
        logger.info(f'章节：{zone[0]}')

        BOTTOM_TAP_NUMER = 8

        nav = self.recog.nav_button()
        nav[1][1] = self.recog.h
        bottom = self.recog.h - 10
        if zone[1] == 0:
            self.tap((self.recog.w // BOTTOM_TAP_NUMER // 2 * 3, bottom))
            ocr = []
            act_id = 999
            while act_id != zone[2]:
                _act_id = act_id
                act_id = -1
                for x in ocr:
                    if zone[2] < _act_id:
                        if x[1].upper().replace(' ', '') == theme_list[_act_id-1]:
                            self.tap(x[2])
                            break
                    else:
                        if x[1].upper().replace(' ', '') == theme_list[_act_id+1]:
                            self.tap(x[2])
                            break
                ocr = ocrhandle.predict(
                    self.recog.img[nav[0][1]:nav[1][1], nav[0][0]:nav[1][0]])
                for x in ocr:
                    if x[1][:7].upper() == 'EPISODE' and len(x[1]) == 9:
                        try:
                            episode = int(x[1][-2:])
                            act_id = zone_list[f'main_{episode}'][2]
                            break
                        except:
                            raise RecognizeError
                if act_id == -1 or _act_id == act_id:
                    raise RecognizeError
            cover = self.recog.find(f'main_{episode}')
            while zone[3] < episode:
                self.swipe((cover[0][0], cover[0][1]),
                           (cover[1][0] - cover[0][0], 0), 200)
                episode -= 1
            while episode < zone[3]:
                self.swipe((cover[1][0], cover[0][1]),
                           (cover[0][0] - cover[1][0], 0), 200)
                episode += 1
            self.tap(cover)
        elif zone[1] == 1:
            self.tap((self.recog.w // BOTTOM_TAP_NUMER // 2 * 5, bottom))
            ocr = ocrhandle.predict(
                self.recog.img[nav[0][1]:nav[1][1], nav[0][0]:nav[1][0]])
            for x in ocr:
                if x[1] == zone[0]:
                    self.tap(x[2])
            self.tap_element('enter')
        elif zone[1] == 2:
            self.tap((self.recog.w // BOTTOM_TAP_NUMER // 2 * 7, bottom))
            ocr = ocrhandle.predict(
                self.recog.img[nav[0][1]:nav[1][1], nav[0][0]:nav[1][0]])
            for x in ocr:
                if x[1] == zone[0]:
                    self.tap(x[2])
            self.tap_element('enter')
        elif zone[1] == 3:
            self.tap((self.recog.w // BOTTOM_TAP_NUMER // 2 * 9, bottom))
            ocr = ocrhandle.predict(self.recog.img)
            unable = list(filter(lambda x: x[1] == '不可进入', ocr))
            ocr = list(filter(lambda x: x[1] in weekly_zones, ocr))
            weekly = sorted([x[1] for x in ocr])
            while zone[0] not in weekly:
                _weekly = weekly
                self.swipe((self.recog.w // 4, self.recog.h // 4),
                           (self.recog.w // 16, 0))
                ocr = ocrhandle.predict(self.recog.img)
                unable = list(filter(lambda x: x[1] == '不可进入', ocr))
                ocr = list(filter(lambda x: x[1] in weekly_zones, ocr))
                weekly = sorted([x[1] for x in ocr])
                if _weekly == weekly:
                    break
            while zone[0] not in weekly:
                _weekly = weekly
                self.swipe((self.recog.w // 4, self.recog.h // 4),
                           (-self.recog.w // 16, 0))
                ocr = ocrhandle.predict(self.recog.img)
                unable = list(filter(lambda x: x[1] == '不可进入', ocr))
                ocr = list(filter(lambda x: x[1] in weekly_zones, ocr))
                weekly = sorted([x[1] for x in ocr])
                if _weekly == weekly:
                    break
            if zone[0] not in weekly:
                raise RecognizeError
            for x in ocr:
                if x[1] == zone[0]:
                    for item in unable:
                        if x[2][0][0] < item[2][0][0] < x[2][1][0]:
                            raise LevelUnopenError
                    self.tap(x[2])
                    break
        else:
            raise RecognizeError

        ocr = ocrhandle.predict(self.recog.img)
        ocr = list(
            filter(lambda x: x[1] in level_list.keys(), ocr))
        levels = sorted([x[1] for x in ocr])
        retry_times = 3
        while level not in levels:
            _levels = levels
            self.swipe((self.recog.w // 4, self.recog.h // 4),
                       (self.recog.w // 16, 0))
            ocr = ocrhandle.predict(self.recog.img)
            ocr = list(
                filter(lambda x: x[1] in level_list.keys(), ocr))
            levels = sorted([x[1] for x in ocr])
            if _levels == levels:
                retry_times -= 1
                if retry_times == 0:
                    break
            else:
                retry_times = 3
        retry_times = 3
        while level not in levels:
            _levels = levels
            self.swipe((self.recog.w // 4, self.recog.h // 4),
                       (-self.recog.w // 16, 0))
            ocr = ocrhandle.predict(self.recog.img)
            ocr = list(
                filter(lambda x: x[1] in level_list.keys(), ocr))
            levels = sorted([x[1] for x in ocr])
            if _levels == levels:
                retry_times -= 1
                if retry_times == 0:
                    break
            else:
                retry_times = 3
        for x in ocr:
            if x[1] == level:
                self.tap(x[2])
                return
        raise RecognizeError
