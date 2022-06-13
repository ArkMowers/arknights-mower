from __future__ import annotations

from ..data import recruit_agent, recruit_tag
from ..ocr import ocr_rectify, ocrhandle
from ..utils import segment
from ..utils.device import Device
from ..utils.log import logger
from ..utils.recognize import RecognizeError, Recognizer, Scene
from ..utils.solver import BaseSolver


class RecruitPoss(object):
    """ 记录公招标签组合的可能性数据 """

    def __init__(self, choose: int, max: int = 0, min: int = 7) -> None:
        self.choose = choose  # 标签选择（按位），第 6 个标志位表示是否选满招募时限，0 为选满，1 为选 03:50
        self.max = max  # 等级上限
        self.min = min  # 等级下限
        self.poss = 0  # 可能性
        self.lv2a3 = False  # 是否包含等级为 2 和 3 的干员
        self.ls = []  # 可能的干员列表

    def __lt__(self, another: RecruitPoss) -> bool:
        return (self.poss) < (another.poss)

    def __str__(self) -> str:
        return "%s,%s,%s,%s,%s" % (self.choose, self.max, self.min, self.poss, self.ls)

    def __repr__(self) -> str:
        return "%s,%s,%s,%s,%s" % (self.choose, self.max, self.min, self.poss, self.ls)


class RecruitSolver(BaseSolver):
    """
    自动进行公招
    """

    def __init__(self, device: Device = None, recog: Recognizer = None) -> None:
        super().__init__(device, recog)

    def run(self, priority: list[str] = None) -> None:
        """
        :param priority: list[str], 优先考虑的公招干员，默认为高稀有度优先
        """
        self.priority = priority
        self.recruiting = 0
        self.has_ticket = True  # 默认含有招募票
        self.can_refresh = True  # 默认可以刷新

        logger.info('Start: 公招')
        logger.info(f'目标干员：{priority if priority else "无，高稀有度优先"}')
        super().run()

    def transition(self) -> bool:
        if self.scene() == Scene.INDEX:
            self.tap_element('index_recruit')
        elif self.scene() == Scene.RECRUIT_MAIN:
            segments = segment.recruit(self.recog.img)
            tapped = False
            for idx, seg in enumerate(segments):
                if self.recruiting & (1 << idx) != 0:
                    continue
                if self.tap_element('recruit_finish', scope=seg, detected=True):
                    tapped = True
                    break
                if not self.has_ticket and not self.can_refresh:
                    continue
                required = self.find('job_requirements', scope=seg)
                if required is None:
                    self.tap(seg)
                    tapped = True
                    self.recruiting |= (1 << idx)
                    break
            if not tapped:
                return True
        elif self.scene() == Scene.RECRUIT_TAGS:
            return self.recruit_tags()
        elif self.scene() == Scene.SKIP:
            self.tap_element('skip')
        elif self.scene() == Scene.RECRUIT_AGENT:
            return self.recruit_result()
        elif self.scene() == Scene.MATERIEL:
            self.tap_element('materiel_ico')
        elif self.scene() == Scene.LOADING:
            self.sleep(3)
        elif self.scene() == Scene.CONNECTING:
            self.sleep(3)
        elif self.get_navigation():
            self.tap_element('nav_recruit')
        elif self.scene() != Scene.UNKNOWN:
            self.back_to_index()
        else:
            raise RecognizeError('Unknown scene')

    def recruit_tags(self) -> bool:
        """ 识别公招标签的逻辑 """
        if self.find('recruit_no_ticket') is not None:
            self.has_ticket = False
        if self.find('recruit_no_refresh') is not None:
            self.can_refresh = False

        needs = self.find('career_needs', judge=False)
        avail_level = self.find('available_level', judge=False)
        budget = self.find('recruit_budget', judge=False)
        up = needs[0][1] - 80
        down = needs[1][1] + 60
        left = needs[1][0]
        right = avail_level[0][0]

        while True:
            # ocr the recruitment tags and rectify
            img = self.recog.img[up:down, left:right]
            ocr = ocrhandle.predict(img)
            for x in ocr:
                if x[1] not in recruit_tag:
                    x[1] = ocr_rectify(img, x, recruit_tag, '公招标签')

            # recruitment tags
            tags = [x[1] for x in ocr]
            logger.info(f'公招标签：{tags}')

            # choose tags
            choose, best = self.tags_choose(tags, self.priority)
            if best.choose < (1 << 5) and best.min <= 3:
                # refresh
                if self.tap_element('recruit_refresh', detected=True):
                    self.tap_element('double_confirm', 0.8,
                                     interval=3, judge=False)
                    continue
            elif not self.has_ticket and best.choose < (1 << 5) and best.min <= 4:
                # refresh, when no ticket
                if self.tap_element('recruit_refresh', detected=True):
                    self.tap_element('double_confirm', 0.8,
                                     interval=3, judge=False)
                    continue
            break

        # 如果没有招募券则只刷新标签不选人
        if not self.has_ticket:
            logger.debug('OK')
            self.back()
            return

        # tap selected tags
        logger.info(f'选择：{choose}')
        for x in ocr:
            color = self.recog.img[up+x[2][0][1]-5, left+x[2][0][0]-5]
            if (color[2] < 100) != (x[1] not in choose):
                self.device.tap((left+x[2][0][0]-5, up+x[2][0][1]-5))

        if best.choose < (1 << 5):
            # 09:00
            self.tap_element('one_hour', 0.2, 0.8, 0)
        else:
            # 03:50
            [self.tap_element('one_hour', 0.2, 0.2, 0) for _ in range(2)]
            [self.tap_element('one_hour', 0.5, 0.2, 0) for _ in range(5)]

        # start recruit
        self.tap((avail_level[1][0], budget[0][1]), interval=3)

    def recruit_result(self) -> bool:
        """ 识别公招招募到的干员 """
        agent = None
        ocr = ocrhandle.predict(self.recog.img)
        for x in ocr:
            if x[1][-3:] == '的信物':
                agent = x[1][:-3]
                agent_ocr = x
                break
        if agent is None:
            logger.warning('未能识别到干员名称')
        else:
            if agent not in recruit_agent.keys():
                agent_with_suf = [x+'的信物' for x in recruit_agent.keys()]
                agent = ocr_rectify(
                    self.recog.img, agent_ocr, agent_with_suf, '干员名称')[:-3]
            if agent in recruit_agent.keys():
                if 2 <= recruit_agent[agent]['stars'] <= 4:
                    logger.info(f'获得干员：{agent}')
                else:
                    logger.critical(f'获得干员：{agent}')
        self.tap((self.recog.w // 2, self.recog.h // 2))

    def tags_choose(self, tags: list[str], priority: list[str]) -> tuple[list[str], RecruitPoss]:
        """ 公招标签选择核心逻辑 """
        if priority is None:
            priority = []
        if len(priority) and isinstance(priority[0], str):
            priority = [[x] for x in priority]
        possibility: dict[int, RecruitPoss] = {}
        agent_level_dict = {}

        # 挨个干员判断可能性
        for x in recruit_agent.values():
            agent_name = x['name']
            agent_level = x['stars']
            agent_tags = x['tags']
            agent_level_dict[agent_name] = agent_level

            # 高级资深干员需要有特定的 tag
            if agent_level == 6 and '高级资深干员' not in tags:
                continue

            # 统计 9 小时公招的可能性
            valid_9 = None
            if 3 <= agent_level <= 6:
                valid_9 = 0
                if agent_level == 6 and '高级资深干员' in tags:
                    valid_9 |= (1 << tags.index('高级资深干员'))
                if agent_level == 5 and '资深干员' in tags:
                    valid_9 |= (1 << tags.index('资深干员'))
                for tag in agent_tags:
                    if tag in tags:
                        valid_9 |= (1 << tags.index(tag))

            # 统计 3 小时公招的可能性
            valid_3 = None
            if 1 <= agent_level <= 4:
                valid_3 = 0
                for tag in agent_tags:
                    if tag in tags:
                        valid_3 |= (1 << tags.index(tag))

            # 枚举所有可能的标签组合子集
            for o in range(1 << 5):
                if valid_9 is not None and o & valid_9 == o:
                    if o not in possibility.keys():
                        possibility[o] = RecruitPoss(o)
                    possibility[o].ls.append(agent_name)
                    possibility[o].max = max(possibility[o].max, agent_level)
                    possibility[o].min = min(possibility[o].min, agent_level)
                    possibility[o].lv2a3 |= 2 <= agent_level <= 3
                _o = o + (1 << 5)
                if valid_3 is not None and o & valid_3 == o:
                    if _o not in possibility.keys():
                        possibility[_o] = RecruitPoss(_o)
                    possibility[_o].ls.append(agent_name)
                    possibility[_o].max = max(possibility[_o].max, agent_level)
                    possibility[_o].min = min(possibility[_o].min, agent_level)
                    possibility[_o].lv2a3 |= 2 <= agent_level <= 3

        # 检查是否存在无法从公开招募中获得的干员
        for considering in priority:
            for x in considering:
                if agent_level_dict.get(x) is None:
                    logger.error(f'该干员并不能在公开招募中获得：{x}')
                    raise RuntimeError

        best = RecruitPoss(0)

        # 按照优先级判断，必定选中同一星级干员
        # 附加限制：min_level == agent_level
        if best.poss == 0:
            logger.debug('choose: priority, min_level == agent_level')
            for considering in priority:
                for o in possibility.keys():
                    possibility[o].poss = 0
                    for x in considering:
                        if x in possibility[o].ls:
                            agent_level = agent_level_dict[x]
                            if agent_level != 1 and agent_level == possibility[o].min:
                                possibility[o].poss += 1
                            elif agent_level == 1 and agent_level == possibility[o].min == possibility[o].max:
                                # 必定选中一星干员的特殊逻辑
                                possibility[o].poss += 1
                    possibility[o].poss /= len(possibility[o].ls)
                    if best < possibility[o]:
                        best = possibility[o]
                if best.poss > 0:
                    break

        # 按照优先级判断，若目标干员 1 星且该组合不存在 2/3 星的可能，则选择
        # 附加限制：min_level == agent_level == 1 and not lv2a3
        if best.poss == 0:
            logger.debug(
                'choose: priority, min_level == agent_level == 1 and not lv2a3')
            for considering in priority:
                for o in possibility.keys():
                    possibility[o].poss = 0
                    for x in considering:
                        if x in possibility[o].ls:
                            agent_level = agent_level_dict[x]
                            if agent_level == possibility[o].min == 1 and not possibility[o].lv2a3:
                                # 特殊判断：选中一星和四星干员的 Tag 组合
                                possibility[o].poss += 1
                    possibility[o].poss /= len(possibility[o].ls)
                    if best < possibility[o]:
                        best = possibility[o]
                if best.poss > 0:
                    break

        # 按照优先级判断，必定选中星级 >= 4 的干员
        # 附加限制：min_level >= 4
        if best.poss == 0:
            logger.debug('choose: priority, min_level >= 4')
            for considering in priority:
                for o in possibility.keys():
                    possibility[o].poss = 0
                    if possibility[o].min >= 4:
                        for x in considering:
                            if x in possibility[o].ls:
                                possibility[o].poss += 1
                    possibility[o].poss /= len(possibility[o].ls)
                    if best < possibility[o]:
                        best = possibility[o]
                if best.poss > 0:
                    break

        # 按照等级下限判断，必定选中星级 >= 4 的干员
        # 附加限制：min_level >= 4
        if best.poss == 0:
            logger.debug('choose: min_level >= 4')
            for o in possibility.keys():
                possibility[o].poss = 0
                if possibility[o].min >= 4:
                    possibility[o].poss = possibility[o].min
                if best < possibility[o]:
                    best = possibility[o]

        # 按照优先级判断，检查其概率
        if best.poss == 0:
            logger.debug('choose: priority')
            for considering in priority:
                for o in possibility.keys():
                    possibility[o].poss = 0
                    for x in considering:
                        if x in possibility[o].ls:
                            possibility[o].poss += 1
                    possibility[o].poss /= len(possibility[o].ls)
                    if best < possibility[o]:
                        best = possibility[o]
                if best.poss > 0:
                    break

        # 按照等级下限判断，默认高稀有度优先
        if best.poss == 0:
            logger.debug('choose: min_level')
            for o in possibility.keys():
                possibility[o].poss = possibility[o].min
                if best < possibility[o]:
                    best = possibility[o]

        logger.debug(f'poss: {possibility}')
        logger.debug(f'best: {best}')

        # 返回选择的标签列表
        choose = []
        for i in range(len(tags)):
            if best.choose & (1 << i):
                choose.append(tags[i])
        return choose, best
