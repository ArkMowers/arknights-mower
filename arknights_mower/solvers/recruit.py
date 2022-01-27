from __future__ import annotations

from ..ocr import ocrhandle, ocr_rectify
from ..utils import segment
from ..utils.device import Device
from ..utils.log import logger
from ..utils.recognize import Recognizer, Scene, RecognizeError
from ..utils.solver import BaseSolver
from ..data.recruit import recruit_database, recruit_tag, recruit_agent


class RecruitPoss(object):
    """ 记录公招标签组合的可能性数据 """

    def __init__(self, choose: int, max: int = 0, min: int = 7) -> None:
        self.choose = choose  # 标签选择（按位）
        self.max = max  # 等级上限
        self.min = min  # 等级下限
        self.ls = []  # 可能的干员列表

    def __lt__(self, another: RecruitPoss) -> bool:
        return (self.max, self.min) < (another.max, another.min)

    def __str__(self) -> str:
        return "%s,%s,%s,%s" % (self.choose, self.max, self.min, self.ls)


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
        elif self.get_navigation():
            self.tap_element('nav_recruit')
        elif self.scene() != Scene.UNKNOWN:
            self.back_to_index()
        else:
            raise RecognizeError('Unanticipated scene: Recruit')

    def recruit_tags(self) -> bool:
        """ 识别公招标签的逻辑 """
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
            if best.max < 4 and best.min < 7:
                # refresh
                if self.tap_element('recruit_refresh', detected=True):
                    self.tap_element('double_confirm', 0.8,
                                     interval=3, judge=False)
                    continue
                # when the best result is Lv3, no tag is selected
                if best.max <= 3:
                    choose = []
            break
        logger.info(f'选择：{choose}')

        # tap selected tags
        for x in ocr:
            color = self.recog.img[up+x[2][0][1]-5, left+x[2][0][0]-5]
            if (color[2] < 100) != (x[1] not in choose):
                self.device.tap((left+x[2][0][0]-5, up+x[2][0][1]-5))

        # if best.min < 7, conduct 9 hours of recruitment
        # best.min == 7 当且仅当目标为公招小车
        if best.min < 7:
            self.tap_element('one_hour', 0.2, 0.8, 0)

        # start recruit
        self.tap((avail_level[1][0], budget[0][1]), interval=5)

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
                if 2 <= recruit_agent[agent][1] <= 4:
                    logger.info(f'获得干员：{agent}')
                else:
                    logger.critical(f'获得干员：{agent}')
        self.tap((self.recog.w // 2, self.recog.h // 2))

    def tags_choose(self, tags: list[str], priority: list[str]) -> tuple[list[str], RecruitPoss]:
        """ 公招标签选择核心逻辑 """
        if priority is None:
            priority = []
        possibility: dict[int, RecruitPoss] = {}

        # 挨个干员判断可能性
        for x in recruit_database:
            # 先考虑高级资深干员和小车
            agent_name, agent_level, agent_tags = x
            if agent_level == 6 and '高级资深干员' not in tags:
                continue
            if agent_level < 3 and (agent_level != 1 or agent_name not in priority):
                continue

            # 统计能够将该干员选出的标签，使用 bitset
            valid = 0
            if agent_level == 6 and '高级资深干员' in tags:
                valid |= (1 << tags.index('高级资深干员'))
            if agent_level == 5 and '资深干员' in tags:
                valid |= (1 << tags.index('资深干员'))
            for tag in agent_tags:
                if tag in tags:
                    valid |= (1 << tags.index(tag))

            # 枚举所有可能的标签组合子集
            for o in range(1, 1 << 5):
                if o & valid == o:
                    if o not in possibility.keys():
                        possibility[o] = RecruitPoss(o)
                    # 优先度量化计算
                    weight = agent_level
                    if agent_name in priority:
                        weight += 0.9 * \
                            (1 - priority.index(agent_name) / len(priority))
                    # 更新可能性
                    possibility[o].max = max(possibility[o].max, weight)
                    if agent_level != 1:
                        # 如果是公招小车则不更新等级下限
                        possibility[o].min = min(possibility[o].min, weight)
                    possibility[o].ls.append(agent_name)

        # 小车逻辑选择
        level1 = None
        for o in possibility.keys():
            if possibility[o].min == 7:
                level1 = o  # 该种标签组合可锁定小车

        # 选择最优的公招标签组合
        best = RecruitPoss(0, 0, 0)
        for o in possibility.keys():
            # 虽然有机会高星，但如果出现了低星，则高星可能性很低
            while possibility[o].max - 1 >= possibility[o].min:
                possibility[o].max -= 1
            if best < possibility[o]:
                best = possibility[o]
        # 如果不能锁定五星，且能锁定小车，则选择小车
        if best.max < 5 and level1 is not None:
            best = possibility[level1]

        logger.debug(f'poss: {possibility}')
        logger.debug(f'best: {best}')

        # 返回选择的标签列表
        choose = []
        for i in range(len(tags)):
            if best.choose & (1 << i):
                choose.append(tags[i])
        return choose, best
