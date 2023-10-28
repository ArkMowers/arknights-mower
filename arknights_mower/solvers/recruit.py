from __future__ import annotations

import os
import pathlib
from itertools import combinations
from typing import Tuple, Dict, Any
import re
import cv2

from ..data import recruit_agent, agent_with_tags, recruit_tag
from ..ocr import ocr_rectify, ocrhandle
from ..utils import segment, rapidocr
from .. import __rootdir__
from ..utils.device import Device
from ..utils.email import recruit_template, recruit_rarity
from ..utils.image import cropimg, bytes2img
from ..utils.log import logger
from ..utils.recognize import RecognizeError, Recognizer, Scene
from ..utils.solver import BaseSolver


class RecruitSolver(BaseSolver):
    """
    自动进行公招
    """

    def __init__(self, device: Device = None, recog: Recognizer = None) -> None:
        super().__init__(device, recog)

        self.result_agent = {}
        self.agent_choose = {}
        self.recruit_config = {}

        self.recruit_pos = -1

        self.priority = None
        self.recruiting = 0
        self.has_ticket = True  # 默认含有招募票
        self.can_refresh = True  # 默认可以刷新
        self.send_message_config = None
        self.permit_count = None
        self.can_refresh = None
        self.enough_lmb = True

        self.recruit_order = [6, 5, 1, 4, 3, 2]

    def run(self, priority: list[str] = None, send_message_config={}, recruit_config={}):
        """
        :param priority: list[str], 优先考虑的公招干员，默认为高稀有度优先
        """
        self.priority = priority
        self.recruiting = 0
        self.has_ticket = True  # 默认含有招募票
        self.send_message_config = send_message_config
        self.permit_count = None

        # 调整公招参数
        self.add_recruit_param(recruit_config)

        logger.info('Start: 公招')
        # 清空
        self.result_agent.clear()

        self.result_agent = {}
        self.agent_choose = {}

        # logger.info(f'目标干员：{priority if priority else "无，高稀有度优先"}')\
        try:
            super().run()
        except Exception as e:
            logger.error(e)

        logger.debug(self.agent_choose)
        logger.debug(self.result_agent)

        if self.result_agent:
            logger.info(f"上次公招结果汇总{self.result_agent}")

        if self.agent_choose:
            logger.info(f'公招标签：{self.agent_choose}')
        if self.agent_choose or self.result_agent:
            self.send_message(recruit_template.render(recruit_results=self.agent_choose,
                                                      recruit_get_agent=self.result_agent,
                                                      permit_count=self.permit_count.__str__(),
                                                      title_text="公招汇总"), "公招汇总通知", "html")

        return self.agent_choose, self.result_agent

    def add_recruit_param(self, recruit_config):
        if not recruit_config:
            raise Exception("招募设置为空")

        if recruit_config['recruitment_time']:
            recruitment_time = 460
        else:
            recruitment_time = 540

        self.recruit_config = {
            "recruitment_time": {
                "3": recruitment_time,
                "4": 540
            },
            "recruit_robot": recruit_config['recruit_robot'],
            "permit_target": recruit_config['permit_target']
        }

    def transition(self) -> bool:
        if self.scene() == Scene.INDEX:
            self.tap_themed_element('index_recruit')
        elif self.scene() == Scene.RECRUIT_MAIN:
            segments = segment.recruit(self.recog.img)

            if self.can_refresh is None:
                refresh_img = self.recog.img[100:150, 1390:1440]

                refresh_gray = cv2.cvtColor(refresh_img, cv2.COLOR_BGR2GRAY)
                refresh_binary = cv2.threshold(refresh_gray, 220, 255, cv2.THRESH_BINARY)[1]
                refresh_res = rapidocr.engine(refresh_binary, use_det=False, use_cls=False, use_rec=True)[0][0][0]
                if refresh_res == '0' or refresh_res == 'o' or refresh_res == 'O':
                    refresh_res = 0
                    self.can_refresh = False
                else:
                    self.can_refresh = True

                logger.info(f"刷新次数:{refresh_res}")

            if self.permit_count is None:
                recruit_ticket_img = self.recog.img[20:80, 1230:1380]
                recruit_ticket_gray = cv2.cvtColor(recruit_ticket_img, cv2.COLOR_BGR2GRAY)
                try:
                    res = rapidocr.engine(recruit_ticket_gray, use_det=False, use_cls=False, use_rec=True)[0][0][0]
                    res = re.sub("\D", "", res)
                    if res == '0' or res == 'o' or res == 'O':
                        res = 0
                    if str(res).isdigit():
                        self.permit_count = int(res)
                        logger.info(f"招募券数量:{res}")
                except:
                    # 设置为1 先保证后续流程能正常进行
                    self.permit_count = 1
                    logger.error("招募券数量读取失败")

            if self.can_refresh is False and self.permit_count <= 0:
                logger.info("无招募券和刷新次数，结束公招")
                return True

            if self.permit_count <= 0:
                self.has_ticket = False

            tapped = False
            for idx, seg in enumerate(segments):
                # 在主界面重置为-1
                self.recruit_pos = -1
                if self.recruiting & (1 << idx) != 0:
                    continue
                if self.tap_element('recruit_finish', scope=seg, detected=True):
                    # 完成公招点击聘用候选人
                    self.recruit_pos = idx
                    tapped = True
                    break
                if not (self.has_ticket or self.enough_lmb) and not self.can_refresh:
                    continue
                # 存在职业需求，说明正在进行招募
                required = self.find('job_requirements', scope=seg)
                if required is None:
                    # 不在进行招募的位置 （1、空位 2、人力办公室等级不够没升的位置）
                    # 下一次循环进入对应位置，先存入值
                    self.recruit_pos = idx
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
        if self.find('recruit_no_lmb') is not None:
            self.enough_lmb = False

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
            logger.info(f'第{self.recruit_pos + 1}个位置上的公招标签：{tags}')

            # 计算招募标签组合结果
            recruit_cal_result = self.recruit_cal(tags)
            recruit_result_level = recruit_cal_result[0][1][0]['star']
            if len(recruit_cal_result) >= 1 and self.recruit_order.index(recruit_result_level) <= 2:
                self.send_message(recruit_rarity.render(recruit_results=recruit_cal_result, title_text="稀有tag通知"),
                                  "出稀有标签辣",
                                  "html")
                logger.info('稀有tag,发送邮件')
                self.back()
                return True

            if recruit_cal_result[0][1][0]['star'] == 3:
                # refresh
                if self.tap_element('recruit_refresh', detected=True):
                    self.tap_element('double_confirm', 0.8,
                                     interval=3, judge=False)
                    logger.info("刷新标签")
                    continue
            break

        if not self.enough_lmb:
            logger.info('龙门币不足 结束公招')
            self.back()
            return False
        # 如果没有招募券则只刷新标签不选人
        if not self.has_ticket:
            logger.info('无招募券')
            self.back()
            return False

        # best为空说明这次大概率三星
        # 券数量少于预期值，仅招募四星或者停止招募，只刷新标签
        if self.permit_count <= self.recruit_config["permit_target"] and recruit_result_level == 3:
            logger.info('不招三星')
            self.back()
            return False

        choose = []
        if recruit_result_level > 3:
            choose = list(recruit_cal_result[0][0])

        # tap selected tags
        logger.info(f'选择标签：{list(choose)}')
        for x in ocr:
            color = self.recog.img[up + x[2][0][1] - 5, left + x[2][0][0] - 5]
            if (color[2] < 100) != (x[1] not in choose):
                # 存在choose为空但是进行标签选择的情况
                logger.debug(f"tap{x}")
                self.device.tap((left + x[2][0][0] - 5, up + x[2][0][1] - 5))

        # 9h为True 3h50min为False
        recruit_time_choose = self.recruit_config["recruitment_time"]["3"]
        if recruit_result_level >= 3:
            if recruit_result_level == 1:
                recruit_time_choose = 230
            else:
                recruit_time_choose = self.recruit_config["recruitment_time"][str(recruit_result_level)]

        if recruit_time_choose == 540:
            # 09:00
            logger.debug("时间9h")
            self.tap_element('one_hour', 0.2, 0.8, 0)
        elif recruit_time_choose == 230:
            # 03:50
            logger.debug("时间3h50min")
            [self.tap_element('one_hour', 0.2, 0.2, 0) for _ in range(2)]
            [self.tap_element('one_hour', 0.5, 0.2, 0) for _ in range(5)]
        elif recruit_time_choose == 460:
            # 07:40
            logger.debug("时间7h40min")
            [self.tap_element('one_hour', 0.2, 0.8, 0) for _ in range(2)]
            [self.tap_element('one_hour', 0.5, 0.8, 0) for _ in range(2)]

        # start recruit
        self.tap((avail_level[1][0], budget[0][1]), interval=3)

        # 有券才能点下去
        if self.permit_count > 1:
            self.permit_count -= 1

        if recruit_result_level > 3:
            self.agent_choose[str(self.recruit_pos + 1)] = {
                "tags": choose,
                "result": recruit_cal_result[0][1]
            }
            logger.info(f'第{self.recruit_pos + 1}个位置上的公招预测结果：{recruit_cal_result[0][1]}')
        else:
            self.agent_choose[str(self.recruit_pos + 1)] = {
                "tags": choose,
                "result": [{'id': '', 'name': '随机三星干员', 'star': 3}]
            }
            logger.info(f'第{self.recruit_pos + 1}个位置上的公招预测结果：{"随机三星干员"}')

    def recruit_result(self):
        agent = None
        gray_img = cropimg(self.recog.gray, ((800, 600), (1500, 1000)))

        img_binary = cv2.threshold(gray_img, 220, 255, cv2.THRESH_BINARY)[1]
        max = 0
        get_path = ""

        for tem_path in pathlib.Path(f"{__rootdir__}/resources/agent_name").glob("*.png"):

            template_ = cv2.imread(tem_path.__str__())
            template_ = cv2.cvtColor(template_, cv2.COLOR_BGR2GRAY)
            res = cv2.matchTemplate(img_binary, template_, cv2.TM_CCORR_NORMED)
            min_val, max_val, min_loc, max_loc = cv2.minMaxLoc(res)
            if max < max_val:
                get_path = tem_path
                max = max_val

        if max > 0.7:
            agent_id = os.path.basename(get_path)
            agent_id = agent_id.replace(".png", "")
            agent = recruit_agent[agent_id]['name']

            # 暂时不会选6星，所以不会有阿
            if agent == "阿":
                agent = "阿消"

        if agent is not None:
            # 汇总开包结果
            self.result_agent[str(self.recruit_pos + 1)] = agent

        self.tap((self.recog.w // 2, self.recog.h // 2))

    def recruit_cal(self, tags: list[str]):
        logger.debug(f"选择标签{tags}")
        self.recruit_order = [6, 5, 1, 4, 3, 2]
        index_dict = {k: i for i, k in enumerate(self.recruit_order)}

        combined_agent = {}
        if '新手' in tags:
            tags.remove('新手')
        for item in combinations(tags, 1):
            tmp = agent_with_tags[item[0]]
            if "支援机械" not in item:
                tmp = [x for x in tmp if x['star'] >= 3]
            if "高级资深干员" not in item:
                tmp = [x for x in tmp if x['star'] < 6]
            if len(tmp) == 0:
                continue
            tmp.sort(key=lambda k: k['star'])
            combined_agent[item] = tmp
        for item in combinations(tags, 2):
            tmp = [j for j in agent_with_tags[item[0]] if j in agent_with_tags[item[1]]]

            if "支援机械" not in item:
                tmp = [x for x in tmp if x['star'] >= 3]
            if "高级资深干员" not in item:
                tmp = [x for x in tmp if x['star'] < 6]
            if len(tmp) == 0:
                continue
            tmp.sort(key=lambda k: k['star'])
            combined_agent[item] = tmp
        for item in combinations(tags, 3):
            tmp1 = [j for j in agent_with_tags[item[0]] if j in agent_with_tags[item[1]]]
            tmp = [j for j in tmp1 if j in agent_with_tags[item[2]]]

            if "支援机械" not in item:
                tmp = [x for x in tmp if x['star'] >= 3]
            if "高级资深干员" not in item:
                tmp = [x for x in tmp if x['star'] < 6]
            if len(tmp) == 0:
                continue
            tmp.sort(key=lambda k: k['star'])
            combined_agent[item] = tmp

        sorted_list = sorted(combined_agent.items(), key=lambda x: index_dict[x[1][0]['star']])

        result_dict = {}
        for item in sorted_list:
            if item[1][0]['star'] == sorted_list[0][1][0]['star']:
                result_dict[item[0]] = item[1]

        sorted_list = sorted(result_dict.items(), key=lambda x: len(x[1]), reverse=True)
        logger.debug(f"before sort{sorted_list}")
        if 3 <= sorted_list[0][1][0]['star'] <= 5:
            for res in sorted_list[1:]:
                if len(res[1]) != len(sorted_list[0][1]) and sorted_list[0][1][0]['star'] > 4:
                    continue
                contain_all = True
                for value in res[1]:
                    if value not in sorted_list[0][1]:
                        contain_all = False
                if contain_all:
                    sorted_list.remove(res)

        logger.debug(f"recruit_cal result:{sorted_list}")
        return sorted_list
        # if len(sorted_list) > 1 and sorted_list[0][1][0]['star'] >= 5:
        #     print("do nothing")
        # for item in sorted_list:
        #     print(item)
