import os
from itertools import combinations

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont

from arknights_mower import __rootdir__
from arknights_mower.data import (
    agent_with_tags,
    recruit_agent,
    recruit_tag,
    result_template_list,
)
from arknights_mower.utils import config, rapidocr, segment
from arknights_mower.utils.device.device import Device
from arknights_mower.utils.digit_reader import DigitReader
from arknights_mower.utils.email import recruit_rarity, recruit_template, send_message
from arknights_mower.utils.graph import SceneGraphSolver
from arknights_mower.utils.image import cropimg, loadres
from arknights_mower.utils.log import logger
from arknights_mower.utils.recognize import Recognizer, Scene

conf = config.conf


class RecruitSolver(SceneGraphSolver):
    def __init__(self, device: Device = None, recog: Recognizer = None) -> None:
        super().__init__(device, recog)

        self.result_agent = {}
        self.agent_choose = {}

        self.recruit_pos = -1

        self.recruiting = 0
        self.has_ticket = True  # 默认含有招募票
        self.can_refresh = True  # 默认可以刷新
        self.permit_count = None
        self.can_refresh = None
        self.enough_lmb = True
        self.digitReader = DigitReader()
        self.recruit_order = [6, 5, 1, 4, 3, 2]
        self.recruit_index = 2

    def run(self):
        self.recruiting = 0
        self.has_ticket = True  # 默认含有招募票
        self.permit_count = None

        # 调整公招参数
        self.add_recruit_param()

        logger.info("Start: 公招")
        # 清空
        self.result_agent.clear()

        self.result_agent = {}
        self.agent_choose = {}
        self.tag_template = {}
        self.font = ImageFont.truetype(
            "{}/fonts/SourceHanSansCN-Medium.otf".format(__rootdir__), 30
        )
        for tag in recruit_tag:
            im = Image.new(mode="RGBA", color=(49, 49, 49), size=(215, 70))
            # im=Image.open("D:\\Git_Repositories\\Pycharm_Project\\Mower\\screenshot_tags\\{}.png".format(tag))
            W, H = im.size
            draw = ImageDraw.Draw(im)
            _, _, w, h = draw.textbbox((0, 0), tag, font=self.font)
            # text_color=(255,255,255)
            # if tag =="高级资深干员" or tag =="资深干员":
            #     text_color=(255,235,4)

            draw.text(((W - w) / 2, (H - h) / 2 - 5), tag, font=self.font)

            self.tag_template[tag] = cv2.cvtColor(
                np.array(im.crop(im.getbbox())), cv2.COLOR_RGB2BGR
            )
        try:
            if len(self.tag_template) < len(recruit_tag):
                raise "tag生成失败{}".format(self.tag_template)
            super().run()
        except Exception as e:
            logger.error(e)

        logger.debug(self.agent_choose)
        logger.debug(self.result_agent)

        if self.result_agent:
            logger.info(f"上次公招结果汇总{self.result_agent}")

        if self.agent_choose:
            for pos in self.agent_choose:
                agent = []
                for item in self.agent_choose[pos]["result"]:
                    agent.append(item["name"])
                logger.info(
                    "{}:[".format(pos)
                    + ",".join(self.agent_choose[pos]["tags"])
                    + "]:{}".format(",".join(agent))
                )
        if self.agent_choose or self.result_agent:
            if conf.recruit_email_enable:
                send_message(
                    recruit_template.render(
                        recruit_results=self.agent_choose,
                        recruit_get_agent=self.result_agent,
                        permit_count=self.permit_count,
                        title_text="公招汇总",
                    ),
                    "公招汇总通知",
                )

        return self.agent_choose, self.result_agent

    def add_recruit_param(self):
        if not conf.recruit_robot:
            self.recruit_order = [6, 5, 4, 3, 2, 1]
            self.recruit_index = 1

    def transition(self) -> bool:
        if (scene := self.scene()) == Scene.RECRUIT_MAIN:
            segments = segment.recruit(self.recog.img)

            if self.can_refresh is None:
                refresh_img = self.recog.img[100:150, 1390:1440]

                refresh_gray = cv2.cvtColor(refresh_img, cv2.COLOR_BGR2GRAY)
                refresh_binary = cv2.threshold(
                    refresh_gray, 220, 255, cv2.THRESH_BINARY
                )[1]
                refresh_res = rapidocr.engine(
                    refresh_binary, use_det=False, use_cls=False, use_rec=True
                )[0][0][0]
                if refresh_res == "0" or refresh_res == "o" or refresh_res == "O":
                    refresh_res = 0
                    self.can_refresh = False
                else:
                    self.can_refresh = True

                logger.info(f"刷新次数:{refresh_res}")

            try:
                # 招募前读取数量
                template_ticket = loadres("recruit_ticket")
                img = self.recog.img
                res = cv2.matchTemplate(img, template_ticket, cv2.TM_CCOEFF_NORMED)
                min_val, max_val, min_loc, max_loc = cv2.minMaxLoc(res)
                h, w = template_ticket.shape[:-1]
                p0 = max_loc
                p1 = (p0[0] + w, p0[1] + h)

                template_stone = loadres("stone")
                res = cv2.matchTemplate(img, template_stone, cv2.TM_CCOEFF_NORMED)
                min_val, max_val, min_loc, max_loc = cv2.minMaxLoc(res)
                p2 = max_loc

                res = self.digitReader.get_recruit_ticket(
                    img[p2[1] : p1[1], p1[0] : p2[0]]
                )
                if str(res).isdigit():
                    self.permit_count = int(res)
                    logger.info(f"招募券数量:{res}")
            except Exception:
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
                if self.tap_element("recruit_finish", scope=seg, detected=True):
                    # 完成公招点击聘用候选人
                    self.recruit_pos = idx
                    tapped = True
                    break
                if not (self.has_ticket or self.enough_lmb) and not self.can_refresh:
                    continue
                # 存在职业需求，说明正在进行招募
                required = self.find("job_requirements", scope=seg)
                if required is None:
                    # 不在进行招募的位置 （1、空位 2、人力办公室等级不够没升的位置）
                    # 下一次循环进入对应位置，先存入值
                    self.recruit_pos = idx
                    self.tap(seg)
                    tapped = True
                    self.recruiting |= 1 << idx
                    break
            if not tapped:
                return True
        elif scene == Scene.RECRUIT_TAGS:
            return self.recruit_tags()
        elif scene == Scene.RECRUIT_AGENT:
            return self.recruit_result()
        elif scene == Scene.SKIP:
            self.tap_element("skip")
        elif scene in self.waiting_scene:
            self.waiting_solver()
        else:
            self.scene_graph_navigation(Scene.RECRUIT_MAIN)

    def recruit_tags(self):
        """识别公招标签的逻辑"""
        if self.find("recruit_no_ticket") is not None:
            self.has_ticket = False
        if self.find("recruit_no_refresh") is not None:
            self.can_refresh = False
        if self.find("recruit_no_lmb") is not None:
            self.enough_lmb = False

        needs = self.find("career_needs")
        avail_level = self.find("available_level")
        budget = self.find("recruit_budget")
        up = needs[0][1] - 80
        down = needs[1][1] + 60
        left = needs[1][0] + 50
        right = avail_level[0][0]

        while True:
            # ocr the recruitment tags and rectify
            img = self.recog.img[up:down, left:right]
            tags_img = self.split_tags(img)
            tags = {}
            h, w, _ = img.shape
            for index, value in enumerate(tags_img):
                res = self.get_recruit_tag(value)
                tag_pos = (
                    int(left + (index % 3) * int(w / 3) + 30),
                    int(up + int(index / 3) * int(h / 2) + 30),
                )
                tags[res["tag"]] = tag_pos

                logger.info("tag识别结果{} {}".format(res, tag_pos))

            if len(tags) != 5:
                raise "标签识别失败 tag={}".format(tags)

            logger.info(f"第{self.recruit_pos + 1}个位置上的公招标签：{tags}")

            # 计算招募标签组合结果
            recruit_cal_result = self.recruit_cal(list(tags.keys()))
            logger.debug("筛选结果:{}".format(recruit_cal_result))
            recruit_result_level = -1

            for index in self.recruit_order:
                if recruit_cal_result[index]:
                    recruit_result_level = index
                    break
            if recruit_result_level == -1:
                logger.error("筛选结果为 {}".format(recruit_cal_result))
                raise "筛选tag失败"
            logger.info("recruit_result_level={}".format(recruit_result_level))

            if self.recruit_order.index(recruit_result_level) <= self.recruit_index:
                if conf.recruit_email_enable:
                    logger.info("稀有tag,发送邮件")
                    send_message(
                        recruit_rarity.render(
                            recruit_results=recruit_cal_result[recruit_result_level],
                            title_text="稀有tag通知",
                        ),
                        "出稀有标签辣",
                    )

                if recruit_result_level == 6:
                    logger.debug("六星tag")
                    self.back()
                    return
                if recruit_result_level == 1 and conf.recruit_robot:
                    logger.debug("支援机械 发送邮件")
                    self.back()
                    return
                if conf.recruit_auto_5 == 2:
                    if conf.recruit_auto_only5:
                        if len(recruit_cal_result[recruit_result_level]) > 1:
                            logger.debug("手动选择且单五星词条自动,但词条不止一种")
                            self.back()
                            return
                    else:
                        logger.debug("手动选择且单五星词条不自动")
                        self.back()
                        return

            if recruit_result_level == 3:
                # refresh
                recruit_refresh_pos = (1455, 610)
                if self.get_color(recruit_refresh_pos)[2] > 200:
                    self.tap(recruit_refresh_pos)
                    self.tap_element("double_confirm/main", x_rate=1, interval=3)
                    logger.info("刷新标签")
                    continue
            break

        if not self.enough_lmb:
            logger.info("龙门币不足 结束公招")
            self.back()
            return
        # 如果没有招募券则只刷新标签不选人
        if not self.has_ticket:
            logger.info("无招募券")
            self.back()
            return

        # best为空说明这次大概率三星
        # 券数量少于预期值，仅招募四星或者停止招募，只刷新标签
        if self.permit_count <= conf.recruitment_permit and recruit_result_level == 3:
            logger.info("不招三星")
            self.back()
            return

        choose = []
        if recruit_result_level > 3:
            choose = recruit_cal_result[recruit_result_level][0]["tag"]

        # tap selected tags
        logger.info(f"选择标签：{list(choose)} ")
        for x in choose:
            # 存在choose为空但是进行标签选择的情况
            logger.debug(f"tap{x}:{tags[x]}")
            self.device.tap(tags[x])
        # 9h为True 3h50min为False
        logger.debug("开始选择时长")
        recruit_time_choose = 540
        if recruit_result_level >= 3:
            if recruit_result_level == 1:
                recruit_time_choose = 230

        if recruit_time_choose == 540:
            # 09:00
            logger.debug("时间9h")
            self.tap_element("one_hour", 0.2, 0.8, 0)
        elif recruit_time_choose == 230:
            # 03:50
            logger.debug("时间3h50min")
            pos = self.find("one_hour")
            [self.tap(pos, 0.2, 0.2, 0.1) for _ in range(2)]
            [self.tap(pos, 0.5, 0.2, 0.1) for _ in range(5)]

        # start recruit
        self.tap((avail_level[1][0], budget[0][1]), interval=3)

        # 有券才能点下去
        if self.permit_count > 1:
            self.permit_count -= 1

        if recruit_result_level > 3:
            self.agent_choose[str(self.recruit_pos + 1)] = {
                "tags": choose,
                "result": recruit_cal_result[recruit_result_level][0]["result"],
            }
            logger.info(
                "第{}个位置上的公招预测结果：{}".format(
                    self.recruit_pos + 1,
                    recruit_cal_result[recruit_result_level][0]["result"],
                )
            )
        else:
            self.agent_choose[str(self.recruit_pos + 1)] = {
                "tags": choose,
                "result": [{"id": "", "name": "随机三星干员", "star": 3}],
            }
            logger.info(
                f'第{self.recruit_pos + 1}个位置上的公招预测结果：{"随机三星干员"}'
            )

    def recruit_result(self):
        try:
            agent = None
            gray_img = cropimg(self.recog.gray, ((800, 600), (1500, 1000)))

            img_binary = cv2.threshold(gray_img, 220, 255, cv2.THRESH_BINARY)[1]
            max = 0
            get_path = ""

            for template_name in result_template_list:
                tem_path = f"{__rootdir__}/resources/agent_name/{template_name}.png"
                template_ = cv2.imdecode(
                    np.fromfile(tem_path.__str__(), dtype=np.uint8),
                    cv2.IMREAD_GRAYSCALE,
                )
                res = cv2.matchTemplate(img_binary, template_, cv2.TM_CCORR_NORMED)
                min_val, max_val, min_loc, max_loc = cv2.minMaxLoc(res)
                if max < max_val:
                    get_path = tem_path
                    max = max_val
                if max > 0.7:
                    break

            if max > 0.7:
                agent_id = os.path.basename(get_path)
                agent_id = agent_id.replace(".png", "")
                agent = recruit_agent[agent_id]["name"]

            if agent is not None:
                # 汇总开包结果
                self.result_agent[str(self.recruit_pos + 1)] = agent
        except Exception as e:
            logger.error(f"公招开包异常{e}")
            send_message(f"公招开包异常{e}")

        self.tap((self.recog.w // 2, self.recog.h // 2))

    def recruit_cal(self, tags: list[str]):
        logger.debug(f"选择标签{tags}")
        index_dict = {k: i for i, k in enumerate(self.recruit_order)}

        combined_agent = {}
        if "新手" in tags:
            tags.remove("新手")
        for item in combinations(tags, 1):
            tmp = agent_with_tags[item[0]]

            if len(tmp) == 0:
                continue
            tmp.sort(key=lambda k: k["star"], reverse=True)
            combined_agent[item] = tmp
        for item in combinations(tags, 2):
            tmp = [j for j in agent_with_tags[item[0]] if j in agent_with_tags[item[1]]]

            if len(tmp) == 0:
                continue
            tmp.sort(key=lambda k: k["star"])
            combined_agent[item] = tmp
        for item in combinations(tags, 3):
            tmp1 = [
                j for j in agent_with_tags[item[0]] if j in agent_with_tags[item[1]]
            ]
            tmp = [j for j in tmp1 if j in agent_with_tags[item[2]]]

            if len(tmp) == 0:
                continue
            tmp.sort(key=lambda k: k["star"], reverse=True)
            combined_agent[item] = tmp

        sorted_list = sorted(
            combined_agent.items(), key=lambda x: index_dict[x[1][0]["star"]]
        )

        result_dict = {}
        for item in sorted_list:
            result_dict[item[0]] = []
            max_star = -1
            min_star = 7
            for agent in item[1]:
                if "高级资深干员" not in item[0] and agent["star"] == 6:
                    continue
                if agent["star"] > max_star:
                    max_star = agent["star"]
                if agent["star"] < min_star:
                    min_star = agent["star"]
            for agent in item[1]:
                if max_star > 1 and agent["star"] == 2:
                    continue
                if max_star > 1 and agent["star"] == 1:
                    continue
                if max_star < 6 and agent["star"] == 6:
                    continue
                result_dict[item[0]].append(agent)
                logger.debug(item[0], agent)
            try:
                for key in list(result_dict.keys()):
                    if len(result_dict[key]) == 0:
                        result_dict.pop(key)

                result_dict[item[0]] = sorted(
                    result_dict[item[0]], key=lambda x: x["star"], reverse=True
                )
                min_star = result_dict[item[0]][-1]["star"]
                for res in result_dict[item[0]][:]:
                    if res["star"] > min_star:
                        result_dict[item[0]].remove(res)
            except KeyError:
                logger.debug("Recruit Cal Key Error :{}".format(result_dict))
                continue
        result = {
            6: [],
            5: [],
            4: [],
            3: [],
            2: [],
            1: [],
        }
        for tag in result_dict:
            result[result_dict[tag][0]["star"]].append(
                {"tag": tag, "result": result_dict[tag]}
            )
        for item in result:
            if result[item]:
                logger.info("{}:{}".format(item, result[item]))
        return result

    def get_recruit_tag(self, img):
        max_v = -1
        tag_res = None
        for key in self.tag_template:
            res = cv2.matchTemplate(
                img,
                self.tag_template[key],
                cv2.TM_CCORR_NORMED,
            )

            min_val, max_val, min_loc, max_loc = cv2.minMaxLoc(res)
            if max_val > max_v:
                tag_res = {"tag": key, "val": max_val}
                max_v = max_val
        return tag_res

    def split_tags(self, img):
        tag_img = []
        h, w, _ = img.shape
        ori_img = img
        tag_h, tag_w = int(h / 2), int(w / 3)
        for i in range(0, 2):
            for j in range(0, 3):
                if i * j == 2:
                    continue
                tag_img.append(img[0:tag_h, 0:tag_w])
                img = img[0:h, tag_w:w]
            img = ori_img[tag_h:h, 0:w]

        return tag_img
