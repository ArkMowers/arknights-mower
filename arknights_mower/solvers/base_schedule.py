from __future__ import annotations
import copy
from ..data import agent_base_config, agent_list

from enum import Enum
from datetime import datetime, timedelta
import numpy as np

from ..data import base_room_list
from ..utils import character_recognize, detector, segment
from ..utils import typealias as tp
from ..utils.device import Device
from ..utils.log import logger
from ..utils.recognize import RecognizeError, Recognizer, Scene
from ..utils.solver import BaseSolver


class ArrangeOrder(Enum):
    STATUS = 1
    SKILL = 2
    FEELING = 3
    TRUST = 4


arrange_order_res = {
    ArrangeOrder.STATUS: (1560/2496, 96/1404),
    ArrangeOrder.SKILL: (1720/2496, 96/1404),
    ArrangeOrder.FEELING: (1880/2496, 96/1404),
    ArrangeOrder.TRUST: (2050/2496, 96/1404),
}


class BaseSchedulerSolver(BaseSolver):
    """
    收集基建的产物：物资、赤金、信赖
    """

    def __init__(self, device: Device = None, recog: Recognizer = None) -> None:
        super().__init__(device, recog)

    def run(self) -> None:
        """
        :param clue_collect: bool, 是否收取线索
        """

        self.currentPlan = self.global_plan[ self.global_plan[ "default" ] ]
        if len(self.tasks) > 0:
            # 找到时间最近的一次单个任务
            self.task = self.tasks[ 0 ]
        else:
            self.task = None
        self.todo_task = False
        self.planned = False
        if len(self.operators.keys()) ==0:
            self.get_agent()
        return super().run()

    def get_group(self, rest_agent, agent, groupname, name):
        for element in agent:
            if element[ 'group' ] == groupname and name != element[ "agent" ]:
                rest_agent.append(element)
                # 从大组里删除
                agent.remove(element)
        return

    def transition(self) -> None:
        self.recog.update()
        if self.scene() == Scene.INDEX:
            self.tap_element('index_infrastructure')
        elif self.scene() == Scene.INFRA_MAIN:
            return self.infra_main()
        elif self.scene() == Scene.INFRA_TODOLIST:
            return self.todo_list()
        elif self.scene() == Scene.INFRA_DETAILS:
            self.back()
        elif self.scene() == Scene.LOADING:
            self.sleep(3)
        elif self.scene() == Scene.CONNECTING:
            self.sleep(3)
        elif self.get_navigation():
            self.tap_element('nav_infrastructure')
        elif self.scene() == Scene.INFRA_ARRANGE_ORDER:
            self.tap_element('arrange_blue_yes')
        elif self.scene() != Scene.UNKNOWN:
            self.back_to_index()
        else:
            raise RecognizeError('Unknown scene')

    def infra_main(self):
        """ 位于基建首页 """
        if self.find('control_central') is None:
            self.back()
            return
        if self.task is not None:
            try:
                self.agent_arrange(self.task["plan"])
                del self.tasks[0]
            except Exception as e:
                logger.exception("error")
            self.task = None
        elif not self.todo_task:
            # 处理基建 Todo
            notification = detector.infra_notification(self.recog.img)
            if notification is None:
                self.sleep(1)
                notification = detector.infra_notification(self.recog.img)
            if notification is not None:
                self.tap(notification)
            else:
                self.todo_task = True
        elif not self.planned:
            try:
                self.agent_get_mood()
                self.plan_solver()
            except Exception as e:
                logger.exception("error")
            self.planned = True
        else:
            if len(self.tasks) > 0:
                # 找到时间最近的一次单个任务
                (self.tasks.sort(key=lambda x: x[ "time" ], reverse=False))
            return True

    def get_plan(self,room,index=-1):
        # -1 就是不换人
        result = []
        for data in self.currentPlan[room]:
            result.append(data["agent"])
        return result

    def plan_solver(self):
        current_base = self.current_base
        plan = self.currentPlan
        # current_base = {'central': [{'mood': 17, 'agent': '夕'}, {'mood': 5, 'agent': '令'}, {'mood': 21, 'agent': '森蚺'}, {'mood': 21, 'agent': '布丁'}, {'mood': -1}], 'meeting': [{'mood': 11, 'agent': '陈'}, {'mood': 11, 'agent': '红'}, {'mood': -1}, {'mood': -1}, {'mood': -1}], 'room_1_1': [{'mood': 24, 'agent': '巫恋'}, {'mood': 9, 'agent': '卡夫卡'}, {'mood': 4, 'agent': '黑键'}, {'mood': -1}, {'mood': -1}], 'room_1_2': [{'mood': 22, 'agent': '异客'}, {'mood': 22, 'agent': '温蒂'}, {'mood': 22, 'agent': '掠风'}, {'mood': -1}, {'mood': -1}], 'room_1_3': [{'mood': 21, 'agent': 'Lancet-2'}, {'mood': -1}, {'mood': -1}, {'mood': -1}, {'mood': -1}], 'dormitory_1': [{'mood': 24, 'agent': '流明'}, {'mood': 24, 'agent': '蜜莓'}, {'mood': 8, 'agent': '焰尾'}, {'mood': 16, 'agent': '远牙'}, {'mood': 24, 'agent': '星极'}], 'factory': [{'mood': -1}, {'mood': -1}, {'mood': -1}, {'mood': -1}, {'mood': -1}], 'room_2_1': [{'mood': 24, 'agent': '红豆'}, {'mood': 23, 'agent': '泡泡'}, {'mood': 23, 'agent': '火神'}, {'mood': -1}, {'mood': -1}], 'room_2_2': [{'mood': 5, 'agent': '砾'}, {'mood': 13, 'agent': '迷迭香'}, {'mood': 19, 'agent': '槐琥'}, {'mood': -1}, {'mood': -1}], 'room_2_3': [{'mood': 17, 'agent': '炎狱炎熔'}, {'mood': -1}, {'mood': -1}, {'mood': -1}, {'mood': -1}], 'dormitory_2': [{'mood': 24, 'agent': '闪灵'}, {'mood': 24, 'agent': '杜林'}, {'mood': 10, 'agent': '灰毫'}, {'mood': 16, 'agent': '雷蛇'}, {'mood': -1}], 'contact': [{'mood': 12, 'agent': '絮雨'}, {'mood': -1}, {'mood': -1}, {'mood': -1}, {'mood': -1}], 'room_3_1': [{'mood': 9, 'agent': '食铁兽'}, {'mood': 12, 'agent': '至简'}, {'mood': 16, 'agent': '断罪者'}, {'mood': -1}, {'mood': -1}], 'room_3_2': [{'mood': 17, 'agent': '稀音'}, {'mood': 20, 'agent': '帕拉斯'}, {'mood': 20, 'agent': '红云'}, {'mood': -1}, {'mood': -1}], 'room_3_3': [{'mood': 21, 'agent': '正义骑士号'}, {'mood': -1}, {'mood': -1}, {'mood': -1}, {'mood': -1}], 'dormitory_3': [{'mood': 24, 'agent': '凛冬'}, {'mood': 24, 'agent': '爱丽丝'}, {'mood': 24, 'agent': '车尔尼'}, {'mood': 14, 'agent': '野鬃'}, {'mood': 24, 'agent': '夜烟'}], 'train': [{'mood': -1}, {'mood': 24, 'agent': '推进之王'}, {'mood': -1}, {'mood': -1}, {'mood': -1}], 'dormitory_4': [{'mood': 24, 'agent': '夜莺'}, {'mood': 24, 'agent': '波登可'}, {'mood': 5, 'agent': '菲亚梅塔'}, {'mood': 18, 'agent': '凯尔希'}, {'mood': 24, 'agent': '白雪'}]}
        if len(self.check_in_and_out()) > 0:
            # 处理龙舌兰和但书的插拔
            for room in self.check_in_and_out():
                if any(room in obj[ "plan" ].keys() for obj in self.tasks): continue;
                in_out_plan = {}
                in_out_plan[ room ] = [ ]
                for x in plan[ room ]:
                    if '但书' in x[ 'replacement' ] or '龙舌兰' in x[ 'replacement' ]:
                        in_out_plan[ room ].append(x[ 'replacement' ][ 0 ])
                    else:
                        in_out_plan[ room ].append(x[ "agent" ])
                self.tasks.append({"time": self.get_in_and_out_time(room), "plan": in_out_plan})
        total_agent = [ ]
        error_agent = [ ]
        # 准备数据
        logger.info(current_base)
        for key in current_base:
            if (key == 'train' or key == 'factory'): continue
            for idx, operator in enumerate(current_base[ key ]):
                data = current_base[ key ][ idx ]
                if len(data.keys())!=2 or (data["mood"] =='' and data["agent"]==''):
                    # 跳过空房间
                    continue
                # 排除识别错误
                elif data[ "mood" ] == -1 or data["agent"] not in agent_list:
                    # 把错误的名字清除
                    logger.error("干员名字或者心情 识别错误： 房间:"+key+" Index:"+str(idx)+" 识别结果:名字"+data["agent"])
                    data["agent"] = ''
                    continue
                if (data[ "agent" ] in agent_base_config.keys()):
                    # 如果有设置下限，则减去下限值 eg: 令
                    if ("LowerLimit" in agent_base_config[ current_base[ key ][ idx ][ "agent" ] ]):
                        data[ "mood" ] = data[ "mood" ] - agent_base_config[ current_base[ key ][ idx ][ "agent" ] ][
                            "LowerLimit" ]
                # assign group 数据到干员
                if "group" in plan[ key ][ idx ].keys():
                    data[ "group" ] = plan[ key ][ idx ][ "group" ]
                else:
                    data[ "group" ] = "None"
                # 把额外数据传过去
                if "replacement" in plan[ key ][ idx ].keys():
                    data[ "replacement" ] = plan[ key ][ idx ][ "replacement" ]
                else:
                    data[ "replacement" ] = "None"
                data[ "current_room" ] = key
                data[ "room_index" ] = idx
                total_agent.append(data)
        # 纠错
        # for agent in self.operators.keys():
        #     if not any(((agent == obj["agent"] and obj["type"]=='high') for obj in total_agent)):
        #         error_agent.append(self.operators[agent])
        #     else:
        #         data = next((x for x in total_agent if x["agent"]==agent),None)
        #         if data is not None:
        #             self.operators[agent]["mood"] = data["mood"]
        # if len(error_agent)>0:
        #     output_plan = {}
        #     for data in error_agent:
        #         output_plan[data["room"]] = self.get_plan(room)
        #     self.tasks.append({"plan":output_plan,"time":datetime.now()})
        #     return
        total_agent.sort(key=lambda x: x["mood"], reverse=False)
        # if len(self.resting)< self.dorm_count:
        #
        #     # 根据剩余心情排序
        #
        #     # 根据使用宿舍数量，输出需要休息的干员列表
        #     number_of_dorm = 4
        #     rest_agent = [ ]
        #     for agent in total_agent:
        #         if len(rest_agent) >= number_of_dorm:
        #             break
        #         if (len([ value for value in rest_agent if value[ "agent" ] == agent[ "agent" ] ]) > 0):
        #             continue
        #         if "group" in agent.keys():
        #             # 如果在group里则同时上下班
        #             self.get_group(rest_agent, total_agent, agent[ "group" ], agent[ "agent" ])
        #         rest_agent.append(agent)
        #         total_agent.remove(agent)
        #     output_plan = {}
        #     # 输出转换后的换班plan
        #     for idx, agent in enumerate(rest_agent):
        #         # 需要增加逻辑如果 replacement 不支持则使用顺位
        #         if agent[ "room" ] not in output_plan.keys():
        #             output_plan[ agent[ "room" ] ] = [ data[ "agent" ] for data in plan[ agent[ "room" ] ] ]
        #         output_plan[ agent[ "room" ] ][ agent[ "index" ] ] = agent[ "replacement" ][ 0 ];
        #         # 宿舍换班
        #         output_plan[ "dormitory_" + str(idx + 1) ] = [ data[ "agent" ] for data in
        #                                                        plan[ "dormitory_" + str(idx + 1) ] ]
        #         # 硬编了4 应该从free里代替
        #         output_plan[ "dormitory_" + str(idx + 1) ][ 4 ] = agent[ "agent" ];
        #     print(output_plan)
        fia_plan, fia_room = self.check_fia()
        if fia_room is not None and fia_plan is not None:
            if not any(fia_room in obj["plan"].keys() and len(obj["plan"][fia_room]) == 2 for obj in self.tasks):
                if next(obj for obj in total_agent if obj["agent"] == '菲亚梅塔')["mood"] ==24:
                    change_time = datetime.now()
                else : change_time = self.get_time(fia_room,'菲亚梅塔')
                logger.info('下一次进行菲亚梅塔充能：' + change_time.strftime("%H:%M:%S"))
                self.tasks.append({"time": change_time, "plan": {fia_room:[next(obj for obj in total_agent if obj["agent"] in fia_plan["replacement"])["agent"],"菲亚梅塔"]}})
    def get_agent(self):
        plan = self.currentPlan
        high_production = [ ]
        replacements = [ ]
        for room in plan.keys():
            for idx,data in enumerate(plan[ room ]):
                high_production.append({"name":data["agent"],"room":room,"index":idx})
                if "replacement" in data.keys() and data["agent"]!='菲亚梅塔' :
                    replacements.extend(data["replacement"])
        for agent in high_production:
            agent["type"]="high"
            self.operators[agent["name"]] = agent
        for agent in replacements:
            self.operators[ agent ] = {"type": "low","name":agent}

    def check_in_and_out(self):
        res = {}
        for x, y in self.currentPlan.items():
            if not x.startswith('room'): continue
            if any(('但书' in obj[ 'replacement' ] or '龙舌兰' in obj[ 'replacement' ]) for obj in y):
                res[ x ] = y
        return res

    def check_fia(self):
        res = {}
        for x, y in self.currentPlan.items():
            if not x.startswith('dormitory'): continue
            if any('菲亚梅塔' == obj[ 'agent' ]  for obj in y):
                return next((obj for obj in y if obj["agent"] == '菲亚梅塔'), None),x
        return None,None

    def get_time(self,room,name,adjustment=0):
        self.enter_room(room)
        self.tap((self.recog.w * 0.05, self.recog.h * 0.2), interval=0.2)
        self.tap((self.recog.w * 0.05, self.recog.h * 0.4), interval=0.2)
        self.tap((self.recog.w * 0.82, self.recog.h * 0.2), interval=0.2)
        self.choose_agent([name],room)
        if "菲亚梅塔"== name: upperLimit = 43200
        else :upperLimit = 21600
        time_in_seconds = self.read_time((int(self.recog.w*540/2496), int(self.recog.h*380/1404), int(self.recog.w*710/2496), int(self.recog.h*430/1404)),upperLimit)
        execute_time = datetime.now() + timedelta(seconds=(time_in_seconds+adjustment))
        logger.info(name+' 心情恢复时间为：' + execute_time.strftime("%H:%M:%S"))
        logger.info('返回基建主界面')
        self.back(interval=2, rebuild=False)
        self.back(interval=2)
        return execute_time

    def get_in_and_out_time(self, room):
        logger.info('基建：读取插拔时间')
        # 点击进入该房间
        self.enter_room(room)
        # 进入房间详情
        self.tap((self.recog.w * 0.05, self.recog.h * 0.95), interval=3)
        time_in_seconds = self.read_time((int(self.recog.w*650/2496), int(self.recog.h*660/1404), int(self.recog.w*815/2496), int(self.recog.h*710/1404)))
        execute_time = datetime.now() + timedelta(seconds=(time_in_seconds - 600))
        logger.info('下一次进行插拔的时间为：' + execute_time.strftime("%H:%M:%S"))
        logger.info('返回基建主界面')
        self.back(interval=2, rebuild=False)
        self.back(interval=2)
        return execute_time

    def read_time(self, cord, upperlimit=8800):
        # 刷新图片
        self.recog.update()
        time_str = segment.read_screen(self.recog.img, type='text', cord=cord)
        try:
            h, m, s = time_str.split(':')
            seconds = int(h) * 3600 + int(m) * 60 + int(s)
            if seconds > upperlimit:
                logger.error("数值超出最大值" + "--> " + str(seconds))
                raise RecognizeError("")
            else:
                return seconds
        except:
            logger.error("读取失败"+"--> "+time_str)
            return self.read_time(cord, upperlimit)

    def todo_list(self) -> None:
        """ 处理基建 Todo 列表 """
        tapped = False
        trust = self.find('infra_collect_trust')
        if trust is not None:
            logger.info('基建：干员信赖')
            self.tap(trust)
            tapped = True
        bill = self.find('infra_collect_bill')
        if bill is not None:
            logger.info('基建：订单交付')
            self.tap(bill)
            tapped = True
        factory = self.find('infra_collect_factory')
        if factory is not None:
            logger.info('基建：可收获')
            self.tap(factory)
            tapped = True
        if not tapped:
            self.tap((self.recog.w * 0.05, self.recog.h * 0.95))
            self.todo_task = True

    def clue(self) -> None:
        # 一些识别时会用到的参数
        global x1, x2, x3, x4, y0, y1, y2
        x1, x2, x3, x4 = 0, 0, 0, 0
        y0, y1, y2 = 0, 0, 0

        logger.info('基建：线索')

        # 进入会客室
        self.enter_room('meeting')

        # 点击线索详情
        self.tap((self.recog.w * 0.1, self.recog.h * 0.9), interval=3)

        # 如果是线索交流的报告则返回
        self.find('clue_summary') and self.back()

        # 识别右侧按钮
        (x0, y0), (x1, y1) = self.find('clue_func', strict=True)

        logger.info('接收赠送线索')
        self.tap(((x0 + x1) // 2, (y0 * 3 + y1) // 4), interval=3, rebuild=False)
        self.tap((self.recog.w - 10, self.recog.h - 10), interval=3, rebuild=False)
        self.tap((self.recog.w * 0.05, self.recog.h * 0.95), interval=3, rebuild=False)

        logger.info('领取会客室线索')
        self.tap(((x0 + x1) // 2, (y0 * 5 - y1) // 4), interval=3)
        obtain = self.find('clue_obtain')
        if obtain is not None and self.get_color(self.get_pos(obtain, 0.25, 0.5))[ 0 ] < 20:
            self.tap(obtain, interval=2)
            if self.find('clue_full') is not None:
                self.back()
        else:
            self.back()

        logger.info('放置线索')
        clue_unlock = self.find('clue_unlock')
        if clue_unlock is not None:
            # 当前线索交流未开启
            self.tap_element('clue', interval=3)

            # 识别阵营切换栏
            self.recog_bar()

            # 点击总览
            self.tap(((x1 * 7 + x2) // 8, y0 // 2), rebuild=False)

            # 获得和线索视图相关的数据
            self.recog_view(only_y2=False)

            # 检测是否拥有全部线索
            get_all_clue = True
            for i in range(1, 8):
                # 切换阵营
                self.tap(self.switch_camp(i), rebuild=False)

                # 清空界面内被选中的线索
                self.clear_clue_mask()

                # 获得和线索视图有关的数据
                self.recog_view()

                # 检测该阵营线索数量为 0
                if len(self.ori_clue()) == 0:
                    logger.info(f'无线索 {i}')
                    get_all_clue = False
                    break

            # 检测是否拥有全部线索
            if get_all_clue:
                for i in range(1, 8):
                    # 切换阵营
                    self.tap(self.switch_camp(i), rebuild=False)

                    # 获得和线索视图有关的数据
                    self.recog_view()

                    # 放置线索
                    logger.info(f'放置线索 {i}')
                    self.tap(((x1 + x2) // 2, y1 + 3), rebuild=False)

            # 返回线索主界面
            self.tap((self.recog.w * 0.05, self.recog.h * 0.95), interval=3, rebuild=False)

        # 线索交流开启
        if clue_unlock is not None and get_all_clue:
            self.tap(clue_unlock)
        else:
            self.back(interval=2, rebuild=False)

        logger.info('返回基建主界面')
        self.back(interval=2)

    def switch_camp(self, id: int) -> tuple[ int, int ]:
        """ 切换阵营 """
        x = ((id + 0.5) * x2 + (8 - id - 0.5) * x1) // 8
        y = (y0 + y1) // 2
        return x, y

    def recog_bar(self) -> None:
        """ 识别阵营选择栏 """
        global x1, x2, y0, y1

        (x1, y0), (x2, y1) = self.find('clue_nav', strict=True)
        while int(self.recog.img[ y0, x1 - 1 ].max()) - int(self.recog.img[ y0, x1 ].max()) <= 1:
            x1 -= 1
        while int(self.recog.img[ y0, x2 ].max()) - int(self.recog.img[ y0, x2 - 1 ].max()) <= 1:
            x2 += 1
        while abs(int(self.recog.img[ y1 + 1, x1 ].max()) - int(self.recog.img[ y1, x1 ].max())) <= 1:
            y1 += 1
        y1 += 1

        logger.debug(f'recog_bar: x1:{x1}, x2:{x2}, y0:{y0}, y1:{y1}')

    def recog_view(self, only_y2: bool = True) -> None:
        """ 识别另外一些和线索视图有关的数据 """
        global x1, x2, x3, x4, y0, y1, y2

        # y2: 线索底部
        y2 = self.recog.h
        while self.recog.img[ y2 - 1, x1:x2 ].ptp() <= 24:
            y2 -= 1
        if only_y2:
            logger.debug(f'recog_view: y2:{y2}')
            return y2
        # x3: 右边黑色 mask 边缘
        x3 = self.recog_view_mask_right()
        # x4: 用来区分单个线索
        x4 = (54 * x1 + 25 * x2) // 79

        logger.debug(f'recog_view: y2:{y2}, x3:{x3}, x4:{x4}')

    def recog_view_mask_right(self) -> int:
        """ 识别线索视图中右边黑色 mask 边缘的位置 """
        x3 = x2
        while True:
            max_abs = 0
            for y in range(y1, y2):
                max_abs = max(max_abs,
                              abs(int(self.recog.img[ y, x3 - 1, 0 ]) - int(self.recog.img[ y, x3 - 2, 0 ])))
            if max_abs <= 5:
                x3 -= 1
            else:
                break
        flag = False
        for y in range(y1, y2):
            if int(self.recog.img[ y, x3 - 1, 0 ]) - int(self.recog.img[ y, x3 - 2, 0 ]) == max_abs:
                flag = True
        if not flag:
            self.tap(((x1 + x2) // 2, y1 + 10), rebuild=False)
            x3 = x2
            while True:
                max_abs = 0
                for y in range(y1, y2):
                    max_abs = max(max_abs,
                                  abs(int(self.recog.img[ y, x3 - 1, 0 ]) - int(self.recog.img[ y, x3 - 2, 0 ])))
                if max_abs <= 5:
                    x3 -= 1
                else:
                    break
            flag = False
            for y in range(y1, y2):
                if int(self.recog.img[ y, x3 - 1, 0 ]) - int(self.recog.img[ y, x3 - 2, 0 ]) == max_abs:
                    flag = True
            if not flag:
                x3 = None
        return x3

    def get_clue_mask(self) -> None:
        """ 界面内是否有被选中的线索 """
        try:
            mask = [ ]
            for y in range(y1, y2):
                if int(self.recog.img[ y, x3 - 1, 0 ]) - int(self.recog.img[ y, x3 - 2, 0 ]) > 20 and np.ptp(
                        self.recog.img[ y, x3 - 2 ]) == 0:
                    mask.append(y)
            if len(mask) > 0:
                logger.debug(np.average(mask))
                return np.average(mask)
            else:
                return None
        except Exception as e:
            raise RecognizeError(e)

    def clear_clue_mask(self) -> None:
        """ 清空界面内被选中的线索 """
        try:
            while True:
                mask = False
                for y in range(y1, y2):
                    if int(self.recog.img[ y, x3 - 1, 0 ]) - int(self.recog.img[ y, x3 - 2, 0 ]) > 20 and np.ptp(
                            self.recog.img[ y, x3 - 2 ]) == 0:
                        self.tap((x3 - 2, y + 1), rebuild=True)
                        mask = True
                        break
                if mask:
                    continue
                break
        except Exception as e:
            raise RecognizeError(e)

    def ori_clue(self):
        """ 获取界面内有多少线索 """
        clues = [ ]
        y3 = y1
        status = -2
        for y in range(y1, y2):
            if self.recog.img[ y, x4 - 5:x4 + 5 ].max() < 192:
                if status == -1:
                    status = 20
                if status > 0:
                    status -= 1
                if status == 0:
                    status = -2
                    clues.append(segment.get_poly(x1, x2, y3, y - 20))
                    y3 = y - 20 + 5
            else:
                status = -1
        if status != -2:
            clues.append(segment.get_poly(x1, x2, y3, y2))

        # 忽视一些只有一半的线索
        clues = [ x.tolist() for x in clues if x[ 1 ][ 1 ] - x[ 0 ][ 1 ] >= self.recog.h / 5 ]
        logger.debug(clues)
        return clues

    def enter_room(self, room: str) -> tp.Rectangle:
        """ 获取房间的位置并进入 """

        # 获取基建各个房间的位置
        base_room = segment.base(self.recog.img, self.find('control_central', strict=True))

        # 将画面外的部分删去
        room = base_room[ room ]
        for i in range(4):
            room[ i, 0 ] = max(room[ i, 0 ], 0)
            room[ i, 0 ] = min(room[ i, 0 ], self.recog.w)
            room[ i, 1 ] = max(room[ i, 1 ], 0)
            room[ i, 1 ] = min(room[ i, 1 ], self.recog.h)

        # 点击进入
        self.tap(room[ 0 ], interval=3)
        while self.find('control_central') is not None:
            self.tap(room[ 0 ], interval=3)

    def drone(self, room: str, one_time=False, not_return=False):
        logger.info('基建：无人机加速')

        # 点击进入该房间
        self.enter_room(room)
        # 进入房间详情
        self.tap((self.recog.w * 0.05, self.recog.h * 0.95), interval=3)

        accelerate = self.find('factory_accelerate')
        if accelerate:
            logger.info('制造站加速')
            self.tap(accelerate)
            self.tap_element('all_in')
            self.tap(accelerate, y_rate=1)

        else:
            accelerate = self.find('bill_accelerate')
            while accelerate:
                logger.info('贸易站加速')
                self.tap(accelerate)
                self.tap_element('all_in')
                self.tap((self.recog.w * 0.75, self.recog.h * 0.8), interval=3)  # relative position 0.75, 0.8
                if one_time: break;
                st = accelerate[ 1 ]  # 起点
                ed = accelerate[ 0 ]  # 终点
                # 0.95, 1.05 are offset compensations
                self.swipe_noinertia(st, (ed[ 0 ] * 0.95 - st[ 0 ] * 1.05, 0), rebuild=True)
                accelerate = self.find('bill_accelerate')
        if not_return: return
        logger.info('返回基建主界面')
        self.back(interval=2, rebuild=False)
        self.back(interval=2)

    def get_arrange_order(self) -> ArrangeOrder:
        best_score, best_order = 0, None
        for order in ArrangeOrder:
            score = self.recog.score(arrange_order_res[ order ][ 0 ])
            if score is not None and score[ 0 ] > best_score:
                best_score, best_order = score[ 0 ], order
        # if best_score < 0.6:
        #     raise RecognizeError
        logger.debug((best_score, best_order))
        return best_order

    def switch_arrange_order(self, index: int, asc="false") -> None:
        self.tap((self.recog.w*arrange_order_res[ ArrangeOrder(index) ][0],self.recog.h*arrange_order_res[ ArrangeOrder(index) ][1]), interval=0.2, rebuild=False)
        # 点个不需要的
        if index < 4:
            self.tap((self.recog.w*arrange_order_res[ ArrangeOrder(index+1) ][0],self.recog.h*arrange_order_res[ ArrangeOrder(index) ][1]), interval=0.2, rebuild=False)
        else:
            self.tap((self.recog.w*arrange_order_res[ ArrangeOrder(index-1) ][0],self.recog.h*arrange_order_res[ ArrangeOrder(index) ][1]), interval=0.2, rebuild=False)
        # 切回来
        self.tap((self.recog.w*arrange_order_res[ ArrangeOrder(index) ][0],self.recog.h*arrange_order_res[ ArrangeOrder(index) ][1]), interval=0.2, rebuild=False)
        # 倒序
        if asc != "false":
            self.tap((self.recog.w*arrange_order_res[ ArrangeOrder(index) ][0],self.recog.h*arrange_order_res[ ArrangeOrder(index) ][1]), interval=0.2, rebuild=False)
        self.sleep(1)

    def scan_agant(self, agent: list[ str ],order_matters=False,error_count = 0):
        try:
            # 识别干员
            self.recog.update()
            ret = character_recognize.agent(self.recog.img)  # 返回的顺序是从左往右从上往下
            # 提取识别出来的干员的名字
            agent_name = set([x[0] for x in ret])
            agent_size = len(agent)
            if order_matters:
                # 按照顺序
                while len(agent) > 0:
                    if any(agent[0] == obj for obj in agent_name):
                        y = next((e for e in ret if e[0] == agent[0]), None)
                        self.tap((y[1][0]), interval=0.5, rebuild=False)
                        agent.remove(agent[0])
                        continue
                    break
            else:
                # 任意顺序
                for y in ret:
                    name = y[0]
                    if name in agent:
                        self.tap((y[1][0]), interval=0.5, rebuild=False)
                        agent.remove(name)
            return agent_size != len(agent), ret
        except Exception as e:
            error_count += 1
            if error_count < 3:
                logger.error(e)
                self.sleep(3)
                return self.scan_agant(agent,order_matters,error_count)
            else:
                raise e

    def get_order(self, name):
        if (name in agent_base_config.keys()):
            if "ArrangeOrder" in agent_base_config[ name ].keys():
                return True,agent_base_config[ name ][ "ArrangeOrder" ]
            else:
                return False,agent_base_config[ "Default" ][ "ArrangeOrder" ]
        return False, agent_base_config[ "Default" ][ "ArrangeOrder" ]

    def choose_agent(self, agent_list: list[ str ], room:str, skip_free: int = 0) -> None:
        """
        :param order: ArrangeOrder, 选择干员时右上角的排序功能
        """
        agent = copy.deepcopy(agent_list)
        logger.info(f'安排干员：{agent}')
        # 若不是空房间，则清空工作中的干员
        is_dorm = room.startswith("dorm")
        one_man = len(self.currentPlan[room])==1
        logger.debug(f'skip_free: {skip_free}')
        h, w = self.recog.h, self.recog.w
        first_time = True
        # 在 agent 中 'Free' 表示任意空闲干员
        free_num = agent.count('Free')
        for i in range(agent.count("Free")):
            agent.remove("Free")
        # TODO 后面想到好办法remove这一行 会有空字符是从currentPlan里面读取的
        for i in range(agent.count("")):
            agent.remove("")
        order_matters = ("菲亚梅塔" in agent and len(agent_list)==2) or "巫恋" in agent_list or "卡夫卡" in agent_list or "柏喙" in agent_list
        is_clear = False
        index_change = False
        pre_order = [ 2, False ]
        right_swipe = 0
        while len(agent) > 0:
            if right_swipe>20:
                # 到底了则返回再来一次
                for _ in range(right_swipe):
                    self.swipe_only((w // 2, h // 2), (w // 2, 0), interval=0.5)
                self.swipe((w // 2, h // 2), (w // 2, 0), interval=3, rebuild=False)
                right_swipe = 0
            if first_time:
                # 清空
                if is_dorm:
                    self.switch_arrange_order(3, "true")
                    pre_order = [3,'true']
                if not one_man:
                    self.tap((self.recog.w * 0.38, self.recog.h * 0.95), interval=0.5)
                else:
                    self.tap((self.recog.w * 0.38, self.recog.h * 0.3), interval=0.5)
                changed, ret = self.scan_agant(agent)
                if changed:
                    if len(agent) == 0: break;
                    index_change = True

            # 如果选中了人，则可能需要重新排序
            if index_change or first_time:
                # 第一次则调整
                is_custom, arrange_type = self.get_order(agent[0])
                if is_dorm and not is_custom :
                    arrange_type = (3,'true')
                #如果重新排序则滑到最左边
                if pre_order[ 0 ] != arrange_type[ 0 ] or pre_order[ 1 ] != arrange_type[ 1 ]:
                    self.switch_arrange_order(arrange_type[ 0 ], arrange_type[ 1 ])
                    # 滑倒最左边
                    self.sleep(interval=0.5, rebuild=True)
                    for _ in range(right_swipe):
                        self.swipe_only((w // 2, h // 2), (w // 2, 0), interval=0.5)
                    self.swipe((w // 2, h // 2), (w // 2, 0), interval=3, rebuild=False)
                    #重置右划次数
                    right_swipe = 0
                    pre_order = arrange_type
            first_time = False

            changed, ret = self.scan_agant(agent)
            if len(agent) == 0: break;
            if not changed:
                # 如果没找到
                index_change = False
                st = ret[ -2 ][ 1 ][ 2 ]  # 起点
                ed = ret[ 0 ][ 1 ][ 1 ]  # 终点
                self.swipe_noinertia(st, (ed[ 0 ] - st[ 0 ], 0))
                right_swipe+=1
            else:
                # 如果找到了
                index_change = True
        # 再次排序
        if order_matters:
            for _ in range(right_swipe):
                self.swipe_only((w // 2, h // 2), (w // 2, 0), interval=0.5)
            self.swipe((w // 2, h // 2), (w // 2, 0), interval=3, rebuild=False)
            agent_with_order = copy.deepcopy(agent_list)
            if "菲亚梅塔" in agent_with_order:
                self.switch_arrange_order(2,"true")
            else:
                self.switch_arrange_order(3)
            self.tap((self.recog.w * 0.38, self.recog.h * 0.95), interval=0.5)
            self.scan_agant(agent_with_order,True)
        # 安排空闲干员
        first_time = True

    def agent_get_mood(self) -> None:
        self.tap_element('infra_overview', interval=2)
        logger.info('基建：记录心情')
        room_total = len(base_room_list)
        idx = 0
        while idx < room_total:
            ret, switch, mode = segment.worker(self.recog.img)
            if len(ret) == 0:
                raise RecognizeError('未识别到进驻总览中的房间列表')
            # 关闭撤下干员按钮
            if mode:
                self.tap((switch[ 0 ][ 0 ] + 5, switch[ 0 ][ 1 ] + 5), rebuild=False)
                continue

            if room_total - idx < len(ret):
                # 已经滑动到底部
                ret = ret[ -(room_total - idx): ]
            for block in ret:
                y = (block[ 0 ][ 1 ] + block[ 2 ][ 1 ]) // 2
                x = (block[ 2 ][ 0 ] - block[ 0 ][ 0 ]) // 7 + block[ 0 ][ 0 ]
                self.tap((x, y), rebuild=False)
                if base_room_list[ idx ] not in [ 'train', 'factory']:
                    self.current_base[ base_room_list[ idx ] ] = character_recognize.agent_with_mood(self.recog.img,length= len(self.currentPlan[base_room_list[ idx ]]))
                idx += 1
            # 识别结束
            if idx == room_total == 0:
                break
            block = ret[ -1 ]
            top = switch[ 2 ][ 1 ]
            self.swipe_noinertia(tuple(block[ 1 ]), (0, top - block[ 1 ][ 1 ]))
        logger.info('心情记录完毕')
        self.back()

    def agent_arrange(self, plan: tp.BasePlan) -> None:
        """ 基建排班 """
        logger.info('基建：排班')
        in_and_out = [ ]
        fia_room = ""
        # 进入进驻总览
        self.tap_element('infra_overview', interval=2)

        logger.info('安排干员工作……')
        idx = 0
        room_total = len(base_room_list)
        need_empty = set(list(plan.keys()))
        while idx < room_total:
            ret, switch, mode = segment.worker(self.recog.img)
            if len(ret) == 0:
                raise RecognizeError('未识别到进驻总览中的房间列表')

            # 关闭撤下干员按钮
            if mode:
                self.tap((switch[ 0 ][ 0 ] + 5, switch[ 0 ][ 1 ] + 5), rebuild=False)
                continue

            if room_total - idx < len(ret):
                # 已经滑动到底部
                ret = ret[ -(room_total - idx): ]

            for block in ret:
                if base_room_list[ idx ] in need_empty:
                    need_empty.remove(base_room_list[ idx ])
                    # 对这个房间进行换班
                    finished = len(plan[ base_room_list[ idx ] ]) == 0
                    skip_free = 0
                    error_count = 0
                    while not finished:
                        x = (7 * block[ 0 ][ 0 ] + 3 * block[ 2 ][ 0 ]) // 10
                        y = (block[ 0 ][ 1 ] + block[ 2 ][ 1 ]) // 2
                        self.tap((x, y))
                        try:
                            self.choose_agent(
                                plan[ base_room_list[ idx ] ],base_room_list[ idx ], skip_free)
                        except RecognizeError as e:
                            error_count += 1
                            if error_count >= 3:
                                raise e
                            # 返回基建干员进驻总览
                            self.recog.update()
                            while self.scene() not in [ Scene.INFRA_ARRANGE,
                                                        Scene.INFRA_MAIN ] and self.scene() // 100 != 1:
                                pre_scene = self.scene()
                                self.back(interval=3)
                                if self.scene() == pre_scene:
                                    break
                            if self.scene() != Scene.INFRA_ARRANGE:
                                raise e
                            continue
                        self.recog.update()
                        self.tap_element(
                            'confirm_blue', detected=True, judge=False, interval=3)
                        if self.scene() == Scene.INFRA_ARRANGE_CONFIRM:
                            x = self.recog.w // 3 * 2  # double confirm
                            y = self.recog.h - 10
                            self.tap((x, y), rebuild=True)
                        finished = True
                        while self.scene() == Scene.CONNECTING:
                            self.sleep(3)
                        # 插拔逻辑
                        if '但书' in plan[ base_room_list[ idx ] ] or '龙舌兰' in plan[ base_room_list[ idx ] ]:
                            in_and_out.append(base_room_list[ idx ])
                        if '菲亚梅塔' in plan[ base_room_list[ idx ] ] and len(plan[ base_room_list[ idx ] ])==2:
                            fia_room = base_room_list[ idx ];
                idx += 1

            # 换班结束
            if idx == room_total or len(need_empty) == 0:
                break
            block = ret[-1]
            top = switch[2][1]
            self.swipe_noinertia(tuple(block[1]), (0, top - block[1][1]))

        if len(in_and_out) > 0:
            self.back()
            replace_plan={}
            for room in in_and_out:
                logger.info("开始插拔")
                self.drone(room,True,True)
                self.tap((self.recog.w * 0.22, self.recog.h * 0.95), interval=0.5)
                if len(self.current_base.keys())>0:
                    in_and_out_plan = [ data[ "agent" ] for data in self.current_base[ room ] ]
                else:
                    in_and_out_plan = [data["agent"] for data in self.currentPlan[room]]
                replace_plan[room] =in_and_out_plan
                self.back(interval=2)
            self.tasks.append( {'time': datetime.now(), 'plan': replace_plan})
            # 急速换班
            self.todo_task = True
            self.planned = True
        if fia_room!='':
            replace_agent = plan[fia_room][0]
            fia_change_room= self.operators[replace_agent]["room"]
            self.back(interval=2)
            del self.tasks[0]
            if len(self.current_base.keys()) > 0:
                fia_room_plan = [data["agent"] for data in self.current_base[fia_room]]
                fia_change_room_plan = [data["agent"] for data in self.current_base[fia_change_room]]
            else:
                fia_room_plan = [data["agent"] for data in self.currentPlan[fia_room]]
                fia_change_room_plan = [data["agent"] for data in self.currentPlan[fia_change_room]]
            self.tasks.append({'time':datetime.now(),'plan':{ fia_room:fia_room_plan,fia_change_room: fia_change_room_plan}})
            #急速换班
            self.todo_task = True
            self.planned = True
        logger.info('返回基建主界面')
        self.back()
