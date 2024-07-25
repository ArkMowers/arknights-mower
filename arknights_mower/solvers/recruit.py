import lzma
import pickle
import traceback
from itertools import combinations

import cv2

from arknights_mower import __rootdir__
from arknights_mower.data import (
    agent_with_tags,
    recruit_agent,
)
from arknights_mower.utils import config
from arknights_mower.utils.device.device import Device
from arknights_mower.utils.email import recruit_rarity, recruit_template, send_message
from arknights_mower.utils.graph import SceneGraphSolver
from arknights_mower.utils.image import cropimg, thres2
from arknights_mower.utils.log import logger
from arknights_mower.utils.recognize import Recognizer, Scene
from arknights_mower.utils.vector import va

conf = config.conf


with lzma.open(f"{__rootdir__}/models/riic_base_digits.pkl", "rb") as f:
    number = pickle.load(f)
with lzma.open(f"{__rootdir__}/models/recruit_result.pkl", "rb") as f:
    recruit_res_template = pickle.load(f)
with lzma.open(f"{__rootdir__}/models/recruit.pkl", "rb") as f:
    tag_template = pickle.load(f)
job_list = [
    "recruit/riic_res/CASTER",
    "recruit/riic_res/MEDIC",
    "recruit/riic_res/PIONEER",
    "recruit/riic_res/SPECIAL",
    "recruit/riic_res/SNIPER",
    "recruit/riic_res/SUPPORT",
    "recruit/riic_res/TANK",
    "recruit/riic_res/WARRIOR",
]


class RecruitSolver(SceneGraphSolver):
    def __init__(self, device: Device = None, recog: Recognizer = None) -> None:
        super().__init__(device, recog)
        self.find_scope = {
            "recruit/begin_recruit": [(340, 200), (590, 300)],
            "recruit/job_requirements": [(100, 20), (300, 100)],
            "recruit/recruit_done": [(300, 250), (600, 340)],
            "recruit/recruit_lock": [(400, 120), (540, 220)],
        }

        # 四个招募栏位的位置 固定1920*1080所以直接写死了
        up = 270
        down = 1060
        left = 25
        right = 1890

        self.segments = {
            1: [(left, up), (950, 650)],
            2: [(970, up), (right, 650)],
            3: [(left, 690), (950, 650)],
            4: [(970, 690), (right, down)],
        }
        self.agent_choose = {}
        self.recruit_index = 1
        # 默认要支援机械
        self.recruit_order_index = 2
        self.recruit_order = [6, 5, 1, 4, 3, 2]

        self.result_agent = {}
        self.ticket_number = None

    def run(self):
        self.add_recruit_param()
        super().run()
        logger.info(self.result_agent)

        if self.agent_choose:
            logger.info("开包汇总如下")
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
            logger.info("招募汇总如下")
            if conf.recruit_email_enable:
                send_message(
                    recruit_template.render(
                        recruit_results=self.agent_choose,
                        recruit_get_agent=self.result_agent,
                        permit_count=conf.recruitment_permit,
                        title_text="公招汇总",
                    ),
                    "公招汇总通知",
                )
        return self.agent_choose, self.result_agent

    def transition(self) -> bool:
        if (scene := self.scene()) == Scene.RECRUIT_MAIN:
            if self.recruit_index > 4:
                logger.info("结束公招")
                return True
            job_requirements_scope = [
                va(
                    self.segments[self.recruit_index][0],
                    self.find_scope["recruit/job_requirements"][0],
                ),
                va(
                    self.segments[self.recruit_index][0],
                    self.find_scope["recruit/job_requirements"][1],
                ),
            ]
            begin_recruit_scope = [
                va(
                    self.segments[self.recruit_index][0],
                    self.find_scope["recruit/begin_recruit"][0],
                ),
                va(
                    self.segments[self.recruit_index][0],
                    self.find_scope["recruit/begin_recruit"][1],
                ),
            ]
            recruit_done_scope = [
                va(
                    self.segments[self.recruit_index][0],
                    self.find_scope["recruit/recruit_done"][0],
                ),
                va(
                    self.segments[self.recruit_index][0],
                    self.find_scope["recruit/recruit_done"][1],
                ),
            ]
            recruit_lock_scope = [
                va(
                    self.segments[self.recruit_index][0],
                    self.find_scope["recruit/recruit_lock"][0],
                ),
                va(
                    self.segments[self.recruit_index][0],
                    self.find_scope["recruit/recruit_lock"][1],
                ),
            ]

            if self.find("recruit/job_requirements", scope=job_requirements_scope):
                self.recruit_index = self.recruit_index + 1
                logger.debug(f"{self.recruit_index}正在招募")
                return
            elif pos := self.find("recruit/recruit_lock", scope=recruit_lock_scope):
                logger.debug(f"{self.recruit_index}锁定")
                return True
            elif pos := self.find("recruit/recruit_done", scope=recruit_done_scope):
                logger.debug(f"{self.recruit_index}结束招募 开包")
                self.tap(pos)
                return
            elif pos := self.find("recruit/begin_recruit", scope=begin_recruit_scope):
                self.ticket_number = self.get_ticket_number()
                if self.ticket_number == 0:
                    self.recruit_index = self.recruit_index + 1
                    logger.debug(f"{self.recruit_index} 张招募券")
                    return
                self.tap(pos)
                return

        elif scene == Scene.RECRUIT_TAGS:
            self.ticket_number = self.get_ticket_number()
            return self.recruit_tags()
        elif scene == Scene.REFRESH_TAGS:
            self.tap_element("recruit/refresh_comfirm")
        elif scene == Scene.RECRUIT_AGENT:
            return self.recruit_result()
        elif scene == Scene.SKIP:
            self.tap_element("skip")
        elif scene in self.waiting_scene:
            self.waiting_solver()
        else:
            self.scene_graph_navigation(Scene.RECRUIT_MAIN)

    def recruit_result(self):
        try:
            # 存在读完一次没退完再读一次
            if str(self.recruit_index) in self.result_agent.keys():
                self.tap((950, 150))
                return

            job_pt = None
            for i in job_list:
                if job_pt := self.find(i):
                    break

            img = cropimg(self.recog.gray, ((job_pt[1][0], 730), (1800, 860)))
            img = cv2.threshold(img, 220, 255, cv2.THRESH_BINARY)[1]

            score = {}
            for id in recruit_res_template:
                res = recruit_res_template[id]
                result = cv2.matchTemplate(img, res, cv2.TM_CCORR_NORMED, res)
                _, max_val, _, _ = cv2.minMaxLoc(result)
                score[id] = max_val
            self.result_agent[self.recruit_index] = recruit_agent[
                max(score, key=score.get)
            ]["name"]

        except Exception as e:
            logger.error(f"公招开包异常:{e}")
            logger.debug(traceback.format_exc())
        finally:
            self.tap((500, 500))

    def recruit_tags(self):
        tags = self.get_recruit_tag()
        logger.debug("tag识别结果{}".format(tags))

        tem_res = self.recruit_cal(sorted(tags))
        recruit_cal_result = None
        recruit_result_level = -1

        for index in self.recruit_order:
            if tem_res[index]:
                recruit_result_level = index
                break
        if recruit_result_level == -1:
            logger.error("筛选结果为 {}".format(tem_res))
            raise ValueError("筛选tag失败")
        elif recruit_result_level != 3 and self.all_same_res(
            tem_res, recruit_result_level
        ):
            recruit_cal_result = [tem_res[recruit_result_level][-1]]
        else:
            recruit_cal_result = tem_res[recruit_result_level]
        logger.debug(recruit_cal_result)
        if recruit_result_level == 3:
            if pos := self.find("recruit/refresh"):
                self.tap(pos)
                return

        if self.recruit_order.index(recruit_result_level) <= self.recruit_order_index:
            if conf.recruit_email_enable:
                send_message(
                    recruit_rarity.render(
                        recruit_results=recruit_cal_result[recruit_result_level],
                        title_text="稀有tag通知",
                    ),
                    "出稀有标签辣",
                )
                logger.info("稀有tag,发送邮件")
            if recruit_result_level == 6 or recruit_result_level == 1:
                logger.debug(f"{recruit_result_level}星稀有tag  ,不选")
                self.recruit_index = self.recruit_index + 1
                self.back()
                return
            elif recruit_result_level == 5:
                if conf.recruit_auto_5 == 2:
                    if conf.recruit_auto_only5 and len(recruit_cal_result) > 1:
                        logger.debug(
                            f"{recruit_result_level}星稀有tag,但不止一个或纯手动选择"
                        )
                        self.recruit_index = self.recruit_index + 1
                        self.back()
                        return

        if self.ticket_number == 0:
            self.recruit_index = self.recruit_index + 1
            self.back()
            return

        if self.ticket_number < conf.recruitment_permit and recruit_result_level == 3:
            self.recruit_index = self.recruit_index + 1
            logger.info("没券 返回")
            self.back()
            return

        choose = []
        if recruit_result_level > 3:
            choose = recruit_cal_result[0]["tag"]

        # tap selected tags
        logger.info(f"选择标签：{list(choose)} ")
        for x in choose:
            # 存在choose为空但是进行标签选择的情况
            logger.debug(f"tap{x}:{tags[x]}")
            self.tap(tags[x])

        # 9h为True 3h50min为False
        logger.debug("开始选择时长")
        # 默认三星招募时长是9：00
        recruit_time_choose = 540
        # 默认一星招募时长是3：50
        if recruit_result_level == 1:
            recruit_time_choose = 230

        if recruit_time_choose == 540:
            # 09:00
            logger.debug("时间9h")
            self.tap_element("one_hour", 0.2, 0.8, 0)
        elif recruit_time_choose == 230:
            # 03:50
            logger.debug("时间3h50min")
            [self.tap_element("one_hour", 0.2, 0.2, 0) for _ in range(2)]
            [self.tap_element("one_hour", 0.5, 0.2, 0) for _ in range(5)]
        # elif recruit_time_choose == 460:
        #     # 07:40
        #     logger.debug("时间7h40min")
        #     [self.tap_element("one_hour", 0.2, 0.8, 0) for _ in range(2)]
        #     [self.tap_element("one_hour", 0.5, 0.8, 0) for _ in range(2)]

        # start recruit
        self.tap_element("recruit/start_recruit")
        self.ticket_number = self.ticket_number - 1

        if recruit_result_level > 3:
            self.agent_choose[str(self.recruit_index)] = {
                "tags": list(choose),
                "result": list(recruit_cal_result[0]["result"]),
            }
            tmp_res_list = []
            for i in list(recruit_cal_result[0]["result"]):
                tmp_res_list.append(i["name"])
            logger.info(
                "第{}个位置上的公招预测结果：{}".format(
                    self.recruit_index,
                    tmp_res_list,
                )
            )
        else:
            self.agent_choose[str(self.recruit_index)] = {
                "tags": list(choose),
                "result": [{"id": "", "name": "随机三星干员", "star": 3}],
            }
            logger.info(
                f'第{self.recruit_index}个位置上的公招预测结果：{"随机三星干员"}'
            )
        self.recruit_index = self.recruit_index + 1
        return

    def all_same_res(self, recruit_cal_res, index):
        tmp_list = recruit_cal_res[index]
        last_res = tmp_list[-1]
        for i in range(len(tmp_list) - 2, -1, -1):
            if tmp_list[i]["result"] != last_res["result"]:
                return False
        return True

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
                logger.debug("{}:{}".format(item, result[item]))
        return result

    def get_recruit_tag(self):
        up = 520
        down = 740
        left = 530
        right = 1300

        img = self.recog.img[up:down, left:right]
        tags_img = self.split_tags(img)
        tags = {}
        h, w, _ = img.shape

        for index, value in enumerate(tags_img):
            max_v = -1
            tag_res = None
            for key in tag_template:
                res = cv2.matchTemplate(
                    value,
                    tag_template[key],
                    cv2.TM_CCORR_NORMED,
                )

                _, max_val, _, _ = cv2.minMaxLoc(res)
                if max_val > max_v:
                    tag_res = {"tag": key, "val": max_val}
                    max_v = max_val
            tag_pos = (
                int(left + (index % 3) * int(w / 3) + 30),
                int(up + int(index / 3) * int(h / 2) + 30),
            )
            tags[tag_res["tag"]] = tag_pos
        return tags

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

    def get_ticket_number(self, height: int | None = 0, thres: int | None = 180):
        p1, p2 = self.find("recruit/ticket")
        p3, _ = self.find("recruit/stone")
        p1 = (p2[0], p1[1] + 10)
        p3 = (p3[0] - 30, p2[1] - 5)
        img = cropimg(self.recog.gray, (p1, p3))
        default_height = 29
        if height and height != default_height:
            scale = default_height / height
            img = cv2.resize(img, None, None, scale, scale)
        img = thres2(img, thres)
        contours, _ = cv2.findContours(img, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        rect = [cv2.boundingRect(c) for c in contours]
        rect.sort(key=lambda c: c[0])
        value = 0
        for x, y, w, h in rect:
            digit = cropimg(img, ((x, y), (x + w, y + h)))
            digit = cv2.copyMakeBorder(
                digit, 10, 10, 10, 10, cv2.BORDER_CONSTANT, None, (0,)
            )
            if digit.size < 800:
                continue
            score = []
            for i in range(10):
                im = number[i]
                if digit.shape[0] < im.shape[0] or digit.shape[1] < im.shape[1]:
                    continue
                result = cv2.matchTemplate(digit, im, cv2.TM_SQDIFF_NORMED)
                min_val, _, _, _ = cv2.minMaxLoc(result)
                score.append(min_val)
            value = value * 10 + score.index(min(score))
        return value

    def add_recruit_param(self):
        if not conf.recruit_robot:
            self.recruit_order = [6, 5, 4, 3, 2, 1]
            self.recruit_order_index = 1
