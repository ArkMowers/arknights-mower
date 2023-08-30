from __future__ import annotations

import smtplib
import time
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from itertools import combinations

from ..data import recruit_agent, recruit_tag, recruit_agent_list
from ..ocr import ocr_rectify, ocrhandle
from ..utils import segment
from ..utils.device import Device
from ..utils.email import recruit_template, recruit_rarity
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

        self.result_agent = []
        self.agent_choose = []

    def run(self, priority: list[str] = None, email_config={}) -> None:
        """
        :param priority: list[str], 优先考虑的公招干员，默认为高稀有度优先
        """
        self.priority = priority
        self.recruiting = 0
        self.has_ticket = True  # 默认含有招募票
        self.can_refresh = True  # 默认可以刷新
        self.email_config = email_config

        logger.info('Start: 公招')
        # logger.info(f'目标干员：{priority if priority else "无，高稀有度优先"}')
        super().run()

        if self.result_agent:
            logger.info(f"上次公招结果汇总{self.result_agent}")

        if self.agent_choose:
            logger.info(f'公招标签：{self.agent_choose}')

        if self.agent_choose or self.result_agent:
            self.send_email(recruit_template.render(recruit_results=self.agent_choose,
                                                    recruit_get_agent=self.result_agent,
                                                    title_text="公招汇总"), "公共选择通知", "html")

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

            # 计算招募标签组合结果
            best, need_choose = self.recruit_cal(tags, self.priority)

            # 刷新标签
            if need_choose is False:
                '''稀有tag或支援，不需要选'''
                self.send_email(recruit_rarity.render(recruit_results=best, title_text="稀有tag通知"), "出稀有标签辣", "html")
                continue
            # best为空说明是三星，刷新标签
            if not best:
                # refresh
                if self.tap_element('recruit_refresh', detected=True):
                    self.tap_element('double_confirm', 0.8,
                                     interval=3, judge=False)
                    logger.info("刷新标签")
                    continue
            break

        # 如果没有招募券则只刷新标签不选人
        if not self.has_ticket:
            logger.info('无招募券 结束公招')
            self.back()
            return

        choose = []
        if len(best) > 0:
            choose = (next(iter(best)))
            # tap selected tags

        logger.info(f'选择标签：{choose}')

        for x in ocr:
            color = self.recog.img[up + x[2][0][1] - 5, left + x[2][0][0] - 5]
            if (color[2] < 100) != (x[1] not in choose):
                # 存在choose为空但是进行标签选择的情况
                logger.info(f"tap{x}")
                self.device.tap((left + x[2][0][0] - 5, up + x[2][0][1] - 5))

        # 9h为True 3h50min为False
        recruit_time_choose = True
        if len(best) > 0:
            if best[choose]['level'] == 1:
                recruit_time_choose = False

        if recruit_time_choose:
            # 09:00
            self.tap_element('one_hour', 0.2, 0.8, 0)
        else:
            # 03:50
            [self.tap_element('one_hour', 0.2, 0.2, 0) for _ in range(2)]
            [self.tap_element('one_hour', 0.5, 0.2, 0) for _ in range(5)]
        # start recruit
        self.tap((avail_level[1][0], budget[0][1]), interval=3)
        if len(best) > 0:
            logger_result = best[choose]['agent']
            self.agent_choose.append(best)
            logger.info(f'公招预测结果：{logger_result}')
        else:
            logger.info('公招预测结果：{随机三星干员}')

    def recruit_result(self) -> bool:
        """ 识别公招招募到的干员 """
        """ 卡在首次获得 挖个坑"""
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
                agent_with_suf = [x + '的信物' for x in recruit_agent.keys()]
                agent = ocr_rectify(
                    self.recog.img, agent_ocr, agent_with_suf, '干员名称')[:-3]
            if agent in recruit_agent.keys():
                if 2 <= recruit_agent[agent]['stars'] <= 4:
                    logger.info(f'获得干员：{agent}')
                else:
                    logger.critical(f'获得干员：{agent}')

        if agent is not None:
            # 汇总开包结果
            self.result_agent.append(agent)

        self.tap((self.recog.w // 2, self.recog.h // 2))

    '''
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
    '''

    def merge_agent_list(self, tags: [str], list_1: list[dict], list_2={}, list_3={}):
        """
        交叉筛选干员

        tags:组合出的标签
        list_x:每个单独标签对应的干员池

        return : 筛选出来的干员池，平均等级，是否稀有标签，是否支援机械
        """
        List1_name_dict = {}
        merge_list = []
        isRarity = False
        isRobot = False
        level = 7

        for operator in list_1:
            if operator['level'] == 6 and "高级资深干员" not in tags:
                continue
            elif operator['level'] == 1 and "支援机械" not in tags:
                continue
            elif operator['level'] == 2:
                continue
            List1_name_dict[operator['name']] = operator

        for key in List1_name_dict:
            if List1_name_dict[key]['level'] == 2:
                print(List1_name_dict[key])

        if len(tags) == 1 and not list_2 and not list_3:
            for key in List1_name_dict:
                if List1_name_dict[key]['level'] < level:
                    level = List1_name_dict[key]['level']
                merge_list.append(List1_name_dict[key])

        elif len(tags) == 2 and not list_3:
            for operator in list_2:
                if operator['name'] in List1_name_dict:
                    if operator['level'] < level:
                        level = operator['level']
                    merge_list.append(operator)


        elif len(tags) == 3 and list_3:
            List1and2_name_dict = {}
            for operator in list_2:
                if operator['name'] in List1_name_dict:
                    List1and2_name_dict[operator['name']] = operator

            for operator in list_3:
                if operator['name'] in List1and2_name_dict:
                    if operator['level'] < level:
                        level = operator['level']
                    merge_list.append(operator)

        if level >= 5:
            isRarity = True
        elif level == 1:
            isRobot = True
        logger.debug(f"merge_list{merge_list}")

        return merge_list, level, isRarity, isRobot

    def recruit_cal(self, tags: list[str], auto_robot=False, need_Robot=True) -> (dict, bool):
        possible_list = {}
        has_rarity = False
        has_robot = False

        for item in combinations(tags, 1):
            # 防止出现类似情况 ['重', '装', '干', '员']

            merge_temp, level, isRarity, isRobot = self.merge_agent_list(item, recruit_agent_list[item[0]]['agent'])
            if len(merge_temp) > 0:
                if has_rarity is False and isRarity:
                    has_rarity = isRarity
                if has_robot is False and isRobot:
                    has_robot = isRobot
                possible_list[item[0],] = {
                    "isRarity": isRarity,
                    "isRobot": isRobot,
                    "level": level,
                    "agent": merge_temp
                }

        for item in combinations(tags, 2):
            merge_temp, level, isRarity, isRobot = self.merge_agent_list(item, recruit_agent_list[item[0]]['agent'],
                                                                         recruit_agent_list[item[1]]['agent'])
            if len(merge_temp) > 0:
                if has_rarity is False and isRarity:
                    has_rarity = isRarity
                if has_robot is False and isRobot:
                    has_robot = isRobot
                possible_list[item[0], item[1]] = {
                    "isRarity": isRarity,
                    "isRobot": isRobot,
                    "level": level,
                    "agent": merge_temp
                }
        for item in combinations(tags, 3):
            merge_temp, level, isRarity, isRobot = self.merge_agent_list(item, recruit_agent_list[item[0]]['agent'],
                                                                         recruit_agent_list[item[1]]['agent'],
                                                                         recruit_agent_list[item[2]]['agent'])
            if len(merge_temp) > 0:
                if has_rarity is False and isRarity:
                    has_rarity = isRarity
                if has_robot is False and isRobot:
                    has_robot = isRobot

                possible_list[item[0], item[1], item[2]] = {
                    "isRarity": isRarity,
                    "isRobot": isRobot,
                    "level": level,
                    "agent": merge_temp
                }

        logger.debug(f"公招可能性:{self.recruit_str(possible_list)}")

        for key in list(possible_list.keys()):
            # 五星六星选择优先级大于支援机械
            if has_rarity:
                if possible_list[key]['isRarity'] is False:
                    del possible_list[key]
                    continue
                elif possible_list[key]['level'] < 6 and "高级资深干员" in tags:
                    del possible_list[key]
                    continue
            # 不要支援机械
            elif need_Robot is False and possible_list[key]['isRobot'] is True:
                del possible_list[key]
                continue
            # 支援机械手动选择
            elif has_robot and need_Robot is True and possible_list[key]['isRobot'] is False:
                del possible_list[key]
                continue

            '''只保留大概率能出的tag'''
            for i in range(len(possible_list[key]["agent"]) - 1, -1, -1):
                if possible_list[key]["agent"][i]['level'] != possible_list[key]["level"]:
                    possible_list[key]["agent"].remove(possible_list[key]["agent"][i])

        # 六星 五星 支援机械手动选择返回全部结果

        # 有支援机械 不需要自动点支援机械 并且需要支援机械的情况下，邮件提醒
        notice_robot = (has_robot and auto_robot == False and need_Robot)
        need_choose = True
        if notice_robot or has_rarity:
            need_choose = False
            logger.info(f"稀有tag:{self.recruit_str(possible_list)}")
            return possible_list, need_choose

        best = {}
        # 4星=需要选择tag返回选择的tag，3星不选
        for key in possible_list:
            if possible_list[key]['level'] >= 4:
                best[key] = possible_list[key]
                break

        return best, need_choose

    def recruit_str(self, recruit_result: dict):
        if not recruit_result:
            return "随机三星干员"
        result_str = "{"
        for key in recruit_result:
            temp_str = "{[" + ",".join(list(key))
            temp_str = temp_str + "],level:"
            temp_str = temp_str + str(recruit_result[key]["level"]) + ",agent:"
            temp_str = temp_str + str(recruit_result[key]["agent"]) + "},"
            result_str = result_str + temp_str

        return result_str
