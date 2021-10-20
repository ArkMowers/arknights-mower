import traceback

from ..ocr import ocrhandle
from ..utils import segment
from ..utils.log import logger
from ..utils.config import MAX_RETRYTIME
from ..utils.recognize import Scene, RecognizeError
from ..utils.solver import BaseSolver, StrategyError
from ..data.recruit import recruit_database, recruit_tag, recruit_agent


class RecruitSolver(BaseSolver):
    """
    自动进行公招
    """

    def __init__(self, adb=None, recog=None):
        super(RecruitSolver, self).__init__(adb, recog)

    def run(self, priority=None):
        """
        :param priority: list[str], 优先考虑的公招干员，默认为火神和因陀罗
        """
        logger.info('Start: 公招')

        retry_times = MAX_RETRYTIME
        while retry_times > 0:
            try:
                if self.scene() == Scene.INDEX:
                    self.tap_element('index_recruit')
                elif self.scene() == Scene.RECRUIT_MAIN:
                    segments = segment.recruit(self.recog.img)
                    tapped = False
                    for seg in segments:
                        if self.tap_element('recruit_finish', scope=seg, detected=True):
                            tapped = True
                            break
                        required = self.recog.find('job_requirements',
                                                   scope=seg)
                        if required is None:
                            self.tap(seg)
                            tapped = True
                            break
                    if not tapped:
                        break
                elif self.scene() == Scene.RECRUIT_TAGS:
                    needs = self.recog.find('career_needs', judge=False)
                    avail_level = self.recog.find('available_level', judge=False)
                    budget = self.recog.find('recruit_budget', judge=False)
                    up = needs[0][1] - 80
                    down = needs[1][1] + 60
                    left = needs[1][0]
                    right = avail_level[0][0]
                    while True:
                        predict = ocrhandle.predict(
                            self.recog.img[up:down, left:right])
                        tags = [x[1] for x in predict]
                        logger.info(f'公招标签：{tags}')
                        for x in tags:
                            if x not in recruit_tag:
                                logger.warn(f'公招识别异常：{x} 为不存在的标签，请报告至 https://github.com/Konano/arknights-mower/issues')
                        choose, maxlevel = self.recruit_choose(tags, priority)
                        if maxlevel[0] < 4:
                            if self.tap_element('recruit_refresh', detected=True):
                                self.tap_element('double_confirm', 0.8, judge=False)
                                continue
                            if maxlevel[0] <= 3:
                                choose = []
                        break
                    logger.info(f'选择：{choose}')
                    for x in predict:
                        color = self.recog.img[
                            up+x[2][0][1]-5, left+x[2][0][0]-5]
                        if (color[2] < 100) != (x[1] not in choose):
                            self.adb.touch_tap(
                                (left+x[2][0][0]-5, up+x[2][0][1]-5))
                    self.tap_element('one_hour', 0.2, 0.8, 0)
                    self.tap((avail_level[1][0], budget[0][1]), interval=5)
                elif self.scene() == Scene.SKIP:
                    self.tap_element('skip')
                elif self.scene() == Scene.RECRUIT_AGENT:
                    agent = None
                    predict = ocrhandle.predict(self.recog.img)
                    for x in predict:
                        if x[1][-3:] == '的信物':
                            agent = x[1][:-3]
                            break
                    if agent is None:
                        logger.warn('未能识别到干员名称')
                    elif agent not in recruit_agent.keys():
                        logger.warn(f'干员识别异常：{agent} 为不存在的干员，请报告至 https://github.com/Konano/arknights-mower/issues')
                    elif recruit_agent[agent][1] < 5:
                        logger.info(f'获得干员：{agent}')
                    else:
                        logger.critical(f'获得干员：{agent}')
                    self.tap((self.recog.w // 2, self.recog.h // 2))
                elif self.scene() == Scene.MATERIEL:
                    self.tap_element('materiel_ico')
                elif self.scene() == Scene.LOADING:
                    self.sleep(3)
                elif self.get_navigation():
                    self.tap_element('nav_recruit')
                elif self.scene() != Scene.UNKNOWN:
                    self.back_to_index()
                else:
                    raise RecognizeError
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
                    valid |= (1 << tags.index('高级资深干员'))
            if x[1] == 5:
                if '资深干员' in tags:
                    valid |= (1 << tags.index('资深干员'))
            for tag in x[2]:
                if tag in tags:
                    valid |= (1 << tags.index(tag))
            for o in range(1, 1 << 5):
                if o & valid == o:
                    if o not in possibility.keys():
                        possibility[o] = [0, 7, []]
                    weight = x[1]
                    if x[0] in priority:
                        weight += 0.9 - 0.9 * priority.index(x[0]) / len(priority)
                    possibility[o][0] = max(possibility[o][0], weight)
                    possibility[o][1] = min(possibility[o][1], weight)
                    possibility[o][-1].append(x[0])
        maxlevel = [0, 0]
        maxlevel_choose = 0
        for o in possibility.keys():
            while possibility[o][0] - 1 >= possibility[o][1]:
                possibility[o][0] -= 1
            if maxlevel < possibility[o][:2]:
                maxlevel = possibility[o][:2]
                maxlevel_choose = o
        logger.debug(possibility)
        logger.debug(maxlevel_choose)
        choose = []
        for i in range(len(tags)):
            if maxlevel_choose & (1 << i):
                choose.append(tags[i])
        return choose, maxlevel

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
                    valid |= (1 << tags.index(tag))
            for o in range(1, 1 << 5):
                if o & valid == o:
                    if o not in possibility:
                        possibility.append(o)
        for x in recruit_database:
            if x[1] > 4:
                continue
            valid = 0
            for tag in x[2]:
                if tag in tags:
                    valid |= (1 << tags.index(tag))
            for o in range(1, 1 << 5):
                if o & valid == o:
                    if o in possibility:
                        possibility.remove(o)
        logger.debug(possibility)
        if len(possibility) == 0:
            return []
        choose = []
        for i in range(len(tags)):
            if possibility[0] & (1 << i):
                choose.append(tags[i])
        return choose
