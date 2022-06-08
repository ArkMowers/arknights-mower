from __future__ import annotations

import time
import traceback

from ..data import chapter_list, level_list, weekly_zones, zone_list
from ..ocr import ocrhandle
from ..utils import config
from ..utils import typealias as tp
from ..utils.image import scope2slice
from ..utils.log import logger
from ..utils.recognize import RecognizeError, Scene
from ..utils.solver import BaseSolver, StrategyError

BOTTOM_TAP_NUMER = 8


class LevelUnopenError(Exception):
    pass


class OpeSolver(BaseSolver):
    """
    自动作战策略
    """

    def __init__(self, device=None, recog=None):
        super().__init__(device, recog)

    def run(self, level: str = None, times: int = -1, potion: int = 0, originite: int = 0, eliminate: int = 0, plan: list = None):
        """
        :param level: str, 指定关卡，默认为前往上一次关卡或当前界面关卡
        :param times: int, 作战的次数上限，-1 为无限制，默认为 -1
        :param potion: int, 使用药剂恢复体力的次数上限，-1 为无限制，默认为 0
        :param originite: int, 使用源石恢复体力的次数上限，-1 为无限制，默认为 0
        :param eliminate: int, 是否优先处理未完成的每周剿灭，0 为忽略剿灭，1 为优先剿灭，2 为优先剿灭但只消耗代理卡，默认为 0
        :param plan: [[str, int]...], 指定多个关卡以及次数，优先级高于 level

        :return remain_plan: [[str, int]...], 未完成的计划
        """
        if level is not None and plan is not None:
            logger.error('不可同时指定 level 和 plan')
            return
        if plan is not None:
            for x in plan:
                if x[0] != 'pre_ope' and (x[0] not in level_list.keys() or level_list[x[0]]['ap_cost'] == 0):
                    logger.error(f'不支持关卡 {x[0]}，请重新指定')
                    return
        if level is not None:
            if level not in level_list.keys() or level_list[level]['ap_cost'] == 0:
                logger.error(f'不支持关卡 {level}，请重新指定')
                return
            plan = [[level, times]]
        if plan is None:
            plan = [['pre_ope', times]]  # 上一次作战关卡

        self.level = level
        self.times = times
        self.potion = potion
        self.originite = originite
        self.eliminate = eliminate
        self.plan = plan

        self.recover_state = 0  # 有关体力恢复的状态，0 为未知，1 为体力药剂恢复中，2 为源石恢复中（防止网络波动）
        self.eliminate_state = 0  # 有关每周剿灭的状态，0 为未知，1 为未完成，2 为已完成，3 为未完成但无代理卡可用
        self.wait_pre = 10  # 作战时每次等待的时长，普通关卡为 10s，剿灭关卡为 60s
        self.wait_start = 0  # 作战时第一次等待的时长
        self.wait_total = 0  # 作战时累计等待的时长
        self.level_choosed = plan[0][0] == 'pre_ope'  # 是否已经选定关卡
        self.unopen = []  # 未开放的关卡
        self.failed = False  # 作战代理是否正常运作

        logger.info('Start: 作战')
        logger.debug(f'plan: {plan}')
        super().run()
        return self.plan + self.unopen

    def switch_plan(self) -> None:
        self.plan = self.plan[1:]
        self.wait_start = 0
        self.level_choosed = False

    def transition(self) -> bool:
        # 选择剩余次数不为 0 的任务
        while len(self.plan) > 0 and self.plan[0][1] == 0:
            self.switch_plan()
        # 如果任务列表为空则退出
        if len(self.plan) == 0:
            return True

        if self.scene() == Scene.INDEX:
            self.tap_element('index_terminal')
        elif self.scene() == Scene.TERMINAL_MAIN:
            return self.terminal_main()
        elif self.scene() == Scene.OPERATOR_BEFORE:
            return self.operator_before()
        elif self.scene() == Scene.OPERATOR_ELIMINATE:
            return self.operator_before_elimi()
        elif self.scene() == Scene.OPERATOR_ELIMINATE_AGENCY:
            self.tap_element('ope_elimi_agency_confirm')
        elif self.scene() == Scene.OPERATOR_SELECT:
            self.tap_element('ope_select_start')
        elif self.scene() == Scene.OPERATOR_ONGOING:
            self.ope_ongoing()
        elif self.scene() == Scene.OPERATOR_FINISH:
            self.ope_finish()
        elif self.scene() == Scene.OPERATOR_ELIMINATE_FINISH:
            self.ope_finish_elimi()
        elif self.scene() == Scene.OPERATOR_GIVEUP:  # TODO 得找个稳定复现代理三星变两星的地图
            logger.error('代理出现失误')
            return True
        elif self.scene() == Scene.OPERATOR_FAILED:
            logger.error('代理出现失误')
            self.failed = True
            self.tap((self.recog.w // 2, 10))
        elif self.scene() == Scene.OPERATOR_RECOVER_POTION:
            return self.recover_potion()
        elif self.scene() == Scene.OPERATOR_RECOVER_ORIGINITE:
            return self.recover_originite()
        elif self.scene() == Scene.LOADING:
            self.sleep(3)
        elif self.scene() == Scene.CONNECTING:
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
            raise RecognizeError('Unknown scene')

    def terminal_main(self) -> bool:
        if self.eliminate_state != 3:
            eliminate_todo = self.find('terminal_eliminate')
            # 检查每周剿灭完成情况
            if eliminate_todo is not None:
                self.eliminate_state = 1
            else:
                self.eliminate_state = 2
            # 如果每周剿灭未完成且设定为优先处理
            if self.eliminate and eliminate_todo is not None:
                self.tap(eliminate_todo)
                return
        try:
            # 选择关卡
            self.choose_level(self.plan[0][0])
        except LevelUnopenError:
            logger.error(f'关卡 {self.plan[0][0]} 未开放，请重新指定')
            self.unopen.append(self.plan[0])
            self.switch_plan()
            return
        self.level_choosed = True

    def operator_before(self) -> bool:
        # 关卡未选定，退回到终端主界面选择关卡
        if not self.level_choosed:
            self.get_navigation()
            self.tap_element('nav_terminal')
            return
        # 代理出现过失误，终止作战
        if self.failed:
            return True
        # 激活代理作战
        agency = self.find('ope_agency')
        if agency is not None:
            self.tap(agency)
            return
        # 重置普通关卡等待时长
        if self.wait_pre != 10:
            self.wait_start = 0
            self.wait_pre = 10
        self.wait_total = 0
        # 点击开始作战
        # ope_start_SN 对应三周年活动愚人船的 UI
        ope_start = self.find('ope_start', judge=False) or self.find('ope_start_SN', judge=False)
        if ope_start:
            self.tap(ope_start)
            # 确定可以开始作战后扣除相应的消耗药剂或者源石
            if self.recover_state == 1:
                logger.info('use potion to recover sanity')
                self.potion -= 1
            elif self.recover_state == 2:
                logger.info('use originite to recover sanity')
                self.originite -= 1
            self.recover_state = 0
        else:
            # 与预期不符，等待一阵并重新截图
            self.sleep(1)

    def operator_before_elimi(self) -> bool:
        # 如果每周剿灭完成情况未知，退回到终端主界面选择关卡
        if self.eliminate_state == 0:
            self.get_navigation()
            self.tap_element('nav_terminal')
            return
        # 如果每周剿灭已完成但仍然在剿灭关卡前，则只可能是 pre_ope 为剿灭关卡，此时应该退出
        if self.eliminate_state == 2:
            logger.warning('检测到关卡为剿灭，但每周剿灭任务已完成')
            return True
        # 如果剿灭代理卡已经用完但仍然在剿灭关卡前，则只可能是 pre_ope 为剿灭关卡，此时应该退出
        if self.eliminate_state == 3:
            logger.warning('检测到关卡为剿灭，但剿灭代理卡已经用完')
            return True
        # 代理出现过失误，终止作战
        if self.failed:
            return True
        # 激活代理作战
        agency = self.find('ope_elimi_agency')
        if agency is not None:
            self.tap(agency)
            return
        agency = self.find('ope_agency')
        if agency is not None:
            self.tap(agency)
            return
        # 若只想用代理卡，但此时代理卡已经用光，则退回到终端主界面选择关卡
        if self.eliminate == 2 and self.find('ope_elimi_agenct_used') is None:
            self.eliminate_state = 3
            self.get_navigation()
            self.tap_element('nav_terminal')
            return
        # 重置剿灭关卡等待时长
        if self.wait_pre != 60:
            self.wait_start = 0
            self.wait_pre = 60
        self.wait_total = 0
        # 点击开始作战
        self.tap_element('ope_start')
        # 确定可以开始作战后扣除相应的消耗药剂或者源石
        if self.recover_state == 1:
            logger.info('use potion to recover sanity')
            self.potion -= 1
        elif self.recover_state == 2:
            logger.info('use originite to recover sanity')
            self.originite -= 1
        self.recover_state = 0

    def ope_ongoing(self) -> None:
        if self.wait_total < self.wait_start:
            if self.wait_total == 0:
                logger.info(f'等待 {self.wait_start} 秒')
            self.wait_total += self.wait_pre
            if self.wait_total == self.wait_start:
                self.sleep(self.wait_pre)
            else:
                time.sleep(self.wait_pre)
        else:
            logger.info(f'等待 {self.wait_pre} 秒')
            self.wait_total += self.wait_pre
            self.sleep(self.wait_pre)

    def ope_finish(self) -> None:
        # 更新 wait_start
        if self.wait_total > 0:
            if self.wait_start == 0:
                self.wait_start = self.wait_total - self.wait_pre
            else:
                self.wait_start = min(
                    self.wait_start + self.wait_pre, self.wait_total - self.wait_pre)
            self.wait_total = 0
        # 如果关卡选定则扣除任务次数
        if self.level_choosed:
            self.plan[0][1] -= 1
        # 若每周剿灭未完成则剿灭完成状态变为未知
        if self.eliminate_state == 1:
            self.eliminate_state = 0
        # 随便点击某处退出结算界面
        self.tap((self.recog.w // 2, 10))

    def ope_finish_elimi(self) -> None:
        # 每周剿灭完成情况变为未知
        self.eliminate_state = 0
        # 随便点击某处退出结算界面
        self.tap((self.recog.w // 2, 10))

    def recover_potion(self) -> bool:
        if self.potion == 0:
            if self.originite != 0:
                # 转而去使用源石恢复
                self.tap_element('ope_recover_originite')
                return
            # 关闭恢复界面
            self.back()
            return True
        elif self.recover_state:
            # 正在恢复中，防止网络波动
            self.sleep(3)
        else:
            # 选择药剂恢复体力
            if self.find('ope_recover_potion_empty') is not None:
                # 使用次数未归零但已经没有药剂可以恢复体力了
                logger.info('The potions have been used up.')
                self.potion = 0
                return
            self.tap_element('ope_recover_potion_choose', 0.9, 0.75, judge=False)
            # 修改状态
            self.recover_state = 1

    def recover_originite(self) -> bool:
        if self.originite == 0:
            if self.potion != 0:
                # 转而去使用药剂恢复
                self.tap_element('ope_recover_potion')
                return
            # 关闭恢复界面
            self.back()
            return True
        elif self.recover_state:
            # 正在恢复中，防止网络波动
            self.sleep(3)
        else:
            # 选择源石恢复体力
            if self.find('ope_recover_originite_empty') is not None:
                # 使用次数未归零但已经没有源石可以恢复体力了
                logger.info('The originites have been used up.')
                self.originite = 0
                return
            self.tap_element('ope_recover_originite_choose', 0.9, 0.85, judge=False)
            # 修改状态
            self.recover_state = 2

    def ocr_level(self) -> list:
        ocr = ocrhandle.predict(self.recog.img)
        ocr = list(filter(lambda x: x[1] in level_list.keys(), ocr))
        levels = sorted([x[1] for x in ocr])
        return ocr, levels

    def choose_level(self, level: str) -> None:
        """ 在终端主界面选择关卡 """
        if level == 'pre_ope':
            logger.info(f'前往上一次关卡')
            self.tap_element('terminal_pre')
            return

        zone_name = level_list[level]['zone_id']
        zone = zone_list[zone_name]
        logger.info(f'关卡：{level}')
        logger.info(f'章节：{zone["name"]}')

        # 识别导航栏，辅助识别章节
        scope = self.recog.nav_button()
        scope[1][1] = self.recog.h

        # 选择章节/区域
        if zone['type'] == 'MAINLINE':
            self.switch_bottom(1)
            self.choose_zone_theme(zone, scope)
        elif zone['type'] == 'BRANCHLINE':
            self.switch_bottom(2)
            self.choose_zone_supple(zone, scope)
        elif zone['type'] == 'SIDESTORY':
            self.switch_bottom(3)
            self.choose_zone_supple(zone, scope)
        elif zone['type'] == 'WEEKLY':
            self.switch_bottom(4)
            self.choose_zone_resource(zone)
        else:
            raise RecognizeError('Unknown zone')

        # 关卡选择核心逻辑
        ocr, levels = self.ocr_level()

        # 先向左滑动
        retry_times = 3
        while level not in levels:
            _levels = levels
            self.swipe_noinertia((self.recog.w // 2, self.recog.h // 4),
                                 (self.recog.w // 3, 0), 100)
            ocr, levels = self.ocr_level()
            if _levels == levels:
                retry_times -= 1
                if retry_times == 0:
                    break
            else:
                retry_times = 3

        # 再向右滑动
        retry_times = 3
        while level not in levels:
            _levels = levels
            self.swipe_noinertia((self.recog.w // 2, self.recog.h // 4),
                                 (-self.recog.w // 3, 0), 100)
            ocr, levels = self.ocr_level()
            if _levels == levels:
                retry_times -= 1
                if retry_times == 0:
                    break
            else:
                retry_times = 3

        # 如果正常运行则此时关卡已经出现在界面中
        for x in ocr:
            if x[1] == level:
                self.tap(x[2])
                return
        raise RecognizeError('Level recognition error')

    def switch_bottom(self, id: int) -> None:
        id = id * 2 + 1
        bottom = self.recog.h - 10
        self.tap((self.recog.w//BOTTOM_TAP_NUMER//2*id, bottom))

    def choose_zone_theme(self, zone: list, scope: tp.Scope) -> None:
        """ 识别主题曲区域 """
        # 定位 Chapter 编号
        ocr = []
        act_id = 999
        while act_id != zone['chapterIndex']:
            _act_id = act_id
            act_id = -1
            for x in ocr:
                if zone['chapterIndex'] < _act_id:
                    if x[1].upper().replace(' ', '') == chapter_list[_act_id-1].replace(' ', ''):
                        self.tap(x[2])
                        break
                else:
                    if x[1].upper().replace(' ', '') == chapter_list[_act_id+1].replace(' ', ''):
                        self.tap(x[2])
                        break
            ocr = ocrhandle.predict(self.recog.img[scope2slice(scope)])
            for x in ocr:
                if x[1][:7].upper() == 'EPISODE' and len(x[1]) == 9:
                    try:
                        episode = int(x[1][-2:])
                        act_id = zone_list[f'main_{episode}']['chapterIndex']
                        break
                    except Exception:
                        raise RecognizeError('Unknown episode')
            if act_id == -1 or _act_id == act_id:
                raise RecognizeError('Unknown error')

        # 定位 Episode 编号
        cover = self.find(f'main_{episode}')
        while zone['zoneIndex'] < episode:
            self.swipe_noinertia((cover[0][0], cover[0][1]),
                                 (cover[1][0] - cover[0][0], 0))
            episode -= 1
        while episode < zone['zoneIndex']:
            self.swipe_noinertia((cover[1][0], cover[0][1]),
                                 (cover[0][0] - cover[1][0], 0))
            episode += 1
        self.tap(cover)

    def choose_zone_supple(self, zone: list, scope: tp.Scope) -> None:
        """ 识别别传/插曲区域 """
        try_times = 5
        zoneIndex = {}
        for x in zone_list.values():
            zoneIndex[x['name'].replace('·', '')] = x['zoneIndex']
        while try_times:
            try_times -= 1
            ocr = ocrhandle.predict(self.recog.img[scope2slice(scope)])
            zones = set()
            for x in ocr:
                if x[1] in zoneIndex.keys():
                    zones.add(zoneIndex[x[1]])
            logger.debug(zones)
            if zone['zoneIndex'] in zones:
                for x in ocr:
                    if x[1] == zone['name'].replace('·', ''):
                        self.tap(x[2])
                        self.tap_element('enter')
                        return
                raise RecognizeError
            else:
                st, ed = None, None
                for x in ocr:
                    if x[1] in zoneIndex.keys() and zoneIndex[x[1]] == min(zones):
                        ed = x[2][0]
                    elif x[1] in zoneIndex.keys() and zoneIndex[x[1]] == max(zones):
                        st = x[2][0]
                logger.debug((st, ed))
                self.swipe_noinertia(st, (0, ed[1]-st[1]))

    def choose_zone_resource(self, zone: list) -> None:
        """ 识别资源收集区域 """
        ocr = ocrhandle.predict(self.recog.img)
        unable = list(filter(lambda x: x[1] in ['不可进入', '本日16:00开启'], ocr))
        ocr = list(filter(lambda x: x[1] in weekly_zones, ocr))
        weekly = sorted([x[1] for x in ocr])
        while zone['name'] not in weekly:
            _weekly = weekly
            self.swipe((self.recog.w // 4, self.recog.h // 4),
                       (self.recog.w // 16, 0))
            ocr = ocrhandle.predict(self.recog.img)
            unable = list(filter(lambda x: x[1] in ['不可进入', '本日16:00开启'], ocr))
            ocr = list(filter(lambda x: x[1] in weekly_zones, ocr))
            weekly = sorted([x[1] for x in ocr])
            if _weekly == weekly:
                break
        while zone['name'] not in weekly:
            _weekly = weekly
            self.swipe((self.recog.w // 4, self.recog.h // 4),
                       (-self.recog.w // 16, 0))
            ocr = ocrhandle.predict(self.recog.img)
            unable = list(filter(lambda x: x[1] in ['不可进入', '本日16:00开启'], ocr))
            ocr = list(filter(lambda x: x[1] in weekly_zones, ocr))
            weekly = sorted([x[1] for x in ocr])
            if _weekly == weekly:
                break
        if zone['name'] not in weekly:
            raise RecognizeError('Not as expected')
        for x in ocr:
            if x[1] == zone['name']:
                for item in unable:
                    if x[2][0][0] < item[2][0][0] < x[2][1][0]:
                        raise LevelUnopenError
                self.tap(x[2])
                ocr = ocrhandle.predict(self.recog.img)
                unable = list(filter(lambda x: x[1] == '关卡尚未开放', ocr))
                if len(unable):
                    raise LevelUnopenError
                break
