from __future__ import annotations
from ..data import agent_base_config

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
    ArrangeOrder.STATUS: ('arrange_status', 0.1),
    ArrangeOrder.SKILL: ('arrange_skill', 0.35),
    ArrangeOrder.FEELING: ('arrange_feeling', 0.65),
    ArrangeOrder.TRUST: ('arrange_trust', 0.9),
}


class BaseSchedulerSolver(BaseSolver):
    """
    收集基建的产物：物资、赤金、信赖
    """

    def __init__(self, device: Device = None, recog: Recognizer = None) -> None:
        super().__init__(device, recog)

    def run(self, tasks, plans,current_base) -> None:
        """
        :param clue_collect: bool, 是否收取线索
        """
        self.global_plan= plans[plans["default"]]
        self.tasks = tasks
        if len(self.tasks)>0:
            # 找到时间最近的一次单个任务
            self.task = self.tasks[0]
        else: self.task = None
        self.todo_task = False
        self.current_base = current_base
        self.planned = False
        return super().run()

    def get_group(self, rest_agent, agent, groupname, name):
        for element in agent:
            if element[ 'group' ] == groupname and name != element[ "agent" ]:
                rest_agent.append(element)
                # 从大组里删除
                agent.remove(element)
        return

    def transition(self) -> None:
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

    def infra_main(self) :
        """ 位于基建首页 """
        if self.find('control_central') is None:
            self.back()
            return
        if self.task is not None:
            self.agent_arrange(self.task["plan"])
            del self.tasks[0]
            self.task = None
        elif not self.planned :
            #self.agent_get_mood()
            self.plan_solver()
            self.planned =True
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
        else:
            if len(self.tasks) > 0:
                # 找到时间最近的一次单个任务
                (self.tasks.sort(key=lambda x: x[ "time" ], reverse=False))
            return self.tasks

    def plan_solver(self):
        currentBase = self.current_base
        plan_1 =self.global_plan
        #currentBase = {'central': [{'mood': 17, 'agent': '夕'}, {'mood': 5, 'agent': '令'}, {'mood': 21, 'agent': '森蚺'}, {'mood': 21, 'agent': '布丁'}, {'mood': -1}], 'meeting': [{'mood': 11, 'agent': '陈'}, {'mood': 11, 'agent': '红'}, {'mood': -1}, {'mood': -1}, {'mood': -1}], 'room_1_1': [{'mood': 24, 'agent': '巫恋'}, {'mood': 9, 'agent': '卡夫卡'}, {'mood': 4, 'agent': '黑键'}, {'mood': -1}, {'mood': -1}], 'room_1_2': [{'mood': 22, 'agent': '异客'}, {'mood': 22, 'agent': '温蒂'}, {'mood': 22, 'agent': '掠风'}, {'mood': -1}, {'mood': -1}], 'room_1_3': [{'mood': 21, 'agent': 'Lancet-2'}, {'mood': -1}, {'mood': -1}, {'mood': -1}, {'mood': -1}], 'dormitory_1': [{'mood': 24, 'agent': '流明'}, {'mood': 24, 'agent': '蜜莓'}, {'mood': 8, 'agent': '焰尾'}, {'mood': 16, 'agent': '远牙'}, {'mood': 24, 'agent': '星极'}], 'factory': [{'mood': -1}, {'mood': -1}, {'mood': -1}, {'mood': -1}, {'mood': -1}], 'room_2_1': [{'mood': 24, 'agent': '红豆'}, {'mood': 23, 'agent': '泡泡'}, {'mood': 23, 'agent': '火神'}, {'mood': -1}, {'mood': -1}], 'room_2_2': [{'mood': 5, 'agent': '砾'}, {'mood': 13, 'agent': '迷迭香'}, {'mood': 19, 'agent': '槐琥'}, {'mood': -1}, {'mood': -1}], 'room_2_3': [{'mood': 17, 'agent': '炎狱炎熔'}, {'mood': -1}, {'mood': -1}, {'mood': -1}, {'mood': -1}], 'dormitory_2': [{'mood': 24, 'agent': '闪灵'}, {'mood': 24, 'agent': '杜林'}, {'mood': 10, 'agent': '灰毫'}, {'mood': 16, 'agent': '雷蛇'}, {'mood': -1}], 'contact': [{'mood': 12, 'agent': '絮雨'}, {'mood': -1}, {'mood': -1}, {'mood': -1}, {'mood': -1}], 'room_3_1': [{'mood': 9, 'agent': '食铁兽'}, {'mood': 12, 'agent': '至简'}, {'mood': 16, 'agent': '断罪者'}, {'mood': -1}, {'mood': -1}], 'room_3_2': [{'mood': 17, 'agent': '稀音'}, {'mood': 20, 'agent': '帕拉斯'}, {'mood': 20, 'agent': '红云'}, {'mood': -1}, {'mood': -1}], 'room_3_3': [{'mood': 21, 'agent': '正义骑士号'}, {'mood': -1}, {'mood': -1}, {'mood': -1}, {'mood': -1}], 'dormitory_3': [{'mood': 24, 'agent': '凛冬'}, {'mood': 24, 'agent': '爱丽丝'}, {'mood': 24, 'agent': '车尔尼'}, {'mood': 14, 'agent': '野鬃'}, {'mood': 24, 'agent': '夜烟'}], 'train': [{'mood': -1}, {'mood': 24, 'agent': '推进之王'}, {'mood': -1}, {'mood': -1}, {'mood': -1}], 'dormitory_4': [{'mood': 24, 'agent': '夜莺'}, {'mood': 24, 'agent': '波登可'}, {'mood': 5, 'agent': '菲亚梅塔'}, {'mood': 18, 'agent': '凯尔希'}, {'mood': 24, 'agent': '白雪'}]}
        if len(self.check_in_and_out(plan_1))>0:
            #处理龙舌兰和但书的插拔
            for room in self.check_in_and_out(plan_1):
                #self.get_in_and_out_time(room)
                in_out_plan ={}
                in_out_plan[room] = []
                for x in plan_1[room]:
                    if '但书' in x['replacement'] or '龙舌兰' in x['replacement']:
                        in_out_plan[ room ].append(x['replacement'][0])
                    else : in_out_plan[ room ].append(x["agent"])
                self.tasks.append({"time":self.get_in_and_out_time(room),"plan":in_out_plan})
        # totalAgent = [ ]
        # for key in currentBase:
        #     if (key == 'train' or key == 'factory'): continue
        #     for idx, operator in enumerate(currentBase[ key ]):
        #         data = currentBase[ key ][ idx ]
        #         # 排除识别错误
        #         if data[ "mood" ] == -1 or "agent" not in data.keys(): continue
        #         if (data[ "agent" ] in agent_base_config.keys()):
        #             # 如果有设置下限，则减去下限值 eg: 令 not in
        #             if ("lower limit" in agent_base_config[ currentBase[ key ][ idx ][ "agent" ] ]):
        #                 data[ "mood" ] = data[ "mood" ] - agent_base_config[ currentBase[ key ][ idx ][ "agent" ] ][
        #                     "lower limit" ]
        #         # assign group 数据到干员
        #         if "group" in plan_1[ key ][ idx ].keys():
        #             data[ "group" ] = plan_1[ key ][ idx ][ "group" ]
        #         else:
        #             data[ "group" ] = "None"
        #         # 把额外数据传过去
        #         if "replacement" in plan_1[ key ][ idx ].keys():
        #             data[ "replacement" ] = plan_1[ key ][ idx ][ "replacement" ]
        #         else:
        #             data[ "replacement" ] = "None"
        #         data[ "room" ] = key
        #         if(key.startswith('dormitory')): data['resting'] = True
        #         data[ "index" ] = idx
        #         totalAgent.append(data)
        # # 根据剩余心情排序
        # totalAgent.sort(key=lambda x: x[ "mood" ], reverse=False)
        # # 根据使用宿舍数量，输出需要休息的干员列表
        # number_of_dorm = 4
        # rest_agent = [ ];
        # for agent in totalAgent:
        #     if len(rest_agent) >= number_of_dorm:
        #         break
        #     if (len([ value for value in rest_agent if value[ "agent" ] == agent[ "agent" ] ]) > 0):
        #         continue;
        #     if "group" in agent.keys():
        #         # 如果在group里则同时上下班
        #         self.get_group(rest_agent, totalAgent, agent[ "group" ], agent[ "agent" ])
        #     rest_agent.append(agent)
        #     totalAgent.remove(agent)
        # output_plan = {}
        # # 输出转换后的换班plan
        # for idx, agent in enumerate(rest_agent):
        #     # 需要增加逻辑如果 replacement 不支持则使用顺位
        #     if agent[ "room" ] not in output_plan.keys():
        #         output_plan[ agent[ "room" ] ] = [ data[ "agent" ] for data in plan_1[ agent[ "room" ] ] ]
        #     output_plan[ agent[ "room" ] ][ agent[ "index" ] ] = agent[ "replacement" ][ 0 ];
        #     # 宿舍换班
        #     output_plan[ "dormitory_" + str(idx + 1) ] = [ data[ "agent" ] for data in
        #                                                    plan_1[ "dormitory_" + str(idx + 1) ] ]
        #     # 硬编了4 应该从free里代替
        #     output_plan[ "dormitory_" + str(idx + 1) ][ 4 ] = agent[ "agent" ];
        # print(output_plan)
        # # 执行换班的同时 获得时间数据
        return

    def check_in_and_out(self ,plan):
        res = {}
        for x, y in plan.items():
            if not x.startswith('room'): continue
            if any(('但书' in obj['replacement'] or '龙舌兰' in obj['replacement'])for obj in y):
                res[x]=y
        return res
    def get_in_and_out_time(self,room):
        logger.info('基建：读取插拔时间')
        # 点击进入该房间
        self.enter_room(room)
        # 进入房间详情
        self.tap((self.recog.w * 0.05, self.recog.h * 0.95), interval=3)
        time_in_seconds = self.read_time((650,660,815,710))
        execute_time = datetime.now()+timedelta(seconds=(time_in_seconds-600))
        logger.info('下一次进行插拔的时间为：' +execute_time.strftime("%H:%M:%S"))
        logger.info('返回基建主界面')
        self.back(interval=2, rebuild=False)
        self.back(interval=2)
        return execute_time
    def read_time(self,cord,upperlimit=8800):
        # 刷新图片
        self.recog.start()
        time_str = segment.read_screen(self.recog.img,type='text',cord=cord)
        try:
            h,m,s = time_str.split(':')
            seconds = int(h)*3600+int(m)*60+int(s)
            if seconds>upperlimit:
                raise RecognizeError("数值超出最大值")
            else: return seconds
        except :
            return self.read_time(cord,upperlimit)


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

    def drone(self, room: str,one_time = False):
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
                if one_time :break;
                st = accelerate[ 1 ]  # 起点
                ed = accelerate[ 0 ]  # 终点
                # 0.95, 1.05 are offset compensations
                self.swipe_noinertia(st, (ed[ 0 ] * 0.95 - st[ 0 ] * 1.05, 0), rebuild=True)
                accelerate = self.find('bill_accelerate')

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

    def switch_arrange_order(self, order: ArrangeOrder) -> None:
        self.tap_element(arrange_order_res[ order ][ 0 ], x_rate=arrange_order_res[ order ][ 1 ], judge=False)

    def arrange_order(self, order: ArrangeOrder) -> None:
        if self.get_arrange_order() != order:
            self.switch_arrange_order(order)

    def choose_agent(self, agent: list[ str ], skip_free: int = 0, order: ArrangeOrder = None) -> None:
        """
        :param order: ArrangeOrder, 选择干员时右上角的排序功能
        """
        logger.info(f'安排干员：{agent}')
        logger.debug(f'skip_free: {skip_free}')
        h, w = self.recog.h, self.recog.w
        first_time = True

        # 在 agent 中 'Free' 表示任意空闲干员
        free_num = agent.count('Free')
        agent = set(agent) - set([ 'Free' ])

        # 安排指定干员
        if len(agent):

            if not first_time:
                # 滑动到最左边
                self.sleep(interval=0.5, rebuild=False)
                for _ in range(9):
                    self.swipe_only((w // 2, h // 2), (w // 2, 0), interval=0.5)
                self.swipe((w // 2, h // 2), (w // 2, 0), interval=3, rebuild=False)
            else:
                # 第一次进入按技能排序
                if order is not None:
                    self.arrange_order(order)
            first_time = False

            checked = set()  # 已经识别过的干员
            pre = set()  # 上次识别出的干员
            error_count = 0

            while len(agent):
                try:
                    # 识别干员
                    ret = character_recognize.agent(self.recog.img)  # 返回的顺序是从左往右从上往下
                except RecognizeError as e:
                    error_count += 1
                    if error_count < 3:
                        logger.debug(e)
                        self.sleep(3)
                    else:
                        raise e
                    continue

                # 提取识别出来的干员的名字
                agent_name = set([ x[ 0 ] for x in ret ])
                if agent_name == pre:
                    error_count += 1
                    if error_count >= 3:
                        logger.warning(f'未找到干员：{list(agent)}')
                        break
                else:
                    pre = agent_name

                # 更新已经识别过的干员
                checked |= agent_name

                # 如果出现了需要的干员则选择
                # 优先安排菲亚梅塔
                if '菲亚梅塔' in agent:
                    if '菲亚梅塔' in agent_name:
                        for y in ret:
                            if y[ 0 ] == '菲亚梅塔':
                                self.tap((y[ 1 ][ 0 ]), interval=0, rebuild=False)
                                break
                        agent.remove('菲亚梅塔')

                        # 如果菲亚梅塔是 the only one
                        if len(agent) == 0:
                            break
                        # 否则滑动到最左边
                        self.sleep(interval=0.5, rebuild=False)
                        for _ in range(9):
                            self.swipe_only((w // 2, h // 2), (w // 2, 0), interval=0.5)
                        self.swipe((w // 2, h // 2), (w // 2, 0), interval=3, rebuild=False)

                        # reset the statuses and cancel the rightward-swiping
                        checked = set()
                        pre = set()
                        error_count = 0
                        continue

                else:
                    for y in ret:
                        name = y[ 0 ]
                        if name in agent_name & agent:
                            self.tap((y[ 1 ][ 0 ]), interval=0, rebuild=False)
                            agent.remove(name)
                    # for name in agent_name & agent:
                    #     for y in ret:
                    #         if y[0] == name:
                    #             self.tap((y[1][0]), interval=0, rebuild=False)
                    #             break
                    #     agent.remove(name)

                    # 如果已经完成选择则退出
                    if len(agent) == 0:
                        break

                st = ret[ -2 ][ 1 ][ 2 ]  # 起点
                ed = ret[ 0 ][ 1 ][ 1 ]  # 终点
                self.swipe_noinertia(st, (ed[ 0 ] - st[ 0 ], 0))

        # 安排空闲干员
        if free_num:

            if not first_time:
                # 滑动到最左边
                self.sleep(interval=0.5, rebuild=False)
                for _ in range(9):
                    self.swipe_only((w // 2, h // 2), (w // 2, 0), interval=0.5)
                self.swipe((w // 2, h // 2), (w // 2, 0), interval=3, rebuild=False)
            else:
                # 第一次进入按技能排序
                if order is not None:
                    self.arrange_order(order)
            first_time = False

            error_count = 0

            while free_num:
                try:
                    # 识别空闲干员
                    ret, st, ed = segment.free_agent(self.recog.img)  # 返回的顺序是从左往右从上往下
                except RecognizeError as e:
                    error_count += 1
                    if error_count < 3:
                        logger.debug(e)
                        self.sleep(3)
                    else:
                        raise e
                    continue

                while free_num and len(ret):
                    if skip_free > 0:
                        skip_free -= 1
                    else:
                        self.tap(ret[ 0 ], interval=0, rebuild=False)
                        free_num -= 1
                    ret = ret[ 1: ]

                # 如果已经完成选择则退出
                if free_num == 0:
                    break

                self.swipe_noinertia(st, (ed[ 0 ] - st[ 0 ], 0))
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
                self.current_base[ base_room_list[ idx ] ] = segment.worker_with_mood(self.recog.img)
                idx += 1
            # 识别结束
            if idx == room_total == 0:
                break
            block = ret[ -1 ]
            top = switch[ 2 ][ 1 ]
            self.swipe_noinertia(tuple(block[ 1 ]), (0, top - block[ 1 ][ 1 ]))
        logger.info('心情记录完毕')

    def agent_arrange(self, plan: tp.BasePlan) -> None:
        """ 基建排班 """
        logger.info('基建：排班')
        in_and_out=[];
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

                        # 若不是空房间，则清空工作中的干员
                        if self.find('arrange_empty_room') is None:
                            if self.find('arrange_clean') is not None:
                                self.tap_element('arrange_clean')
                            else:
                                # 对于只有一个干员的房间，没有清空按钮，需要点击干员清空
                                self.tap((self.recog.w * 0.38, self.recog.h * 0.3), interval=0)

                        try:
                            if base_room_list[ idx ].startswith('dormitory'):
                                default_order = ArrangeOrder.FEELING
                            else:
                                default_order = ArrangeOrder.SKILL
                            self.choose_agent(
                                plan[ base_room_list[ idx ] ], skip_free, default_order)
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
                idx += 1

            # 换班结束
            if idx == room_total or len(need_empty) == 0:
                break
            block = ret[ -1 ]
            top = switch[ 2 ][ 1 ]
            self.swipe_noinertia(tuple(block[ 1 ]), (0, top - block[ 1 ][ 1 ]))

        if len(in_and_out)>0:
            self.back()
            for room in in_and_out:
                logger.info("开始插拔")
                self.drone(room,True)
                self.agent_arrange({room:[ data[ "agent" ] for data in self.global_plan[room] ]})
            return
        logger.info('返回基建主界面')
        self.back()

    def choose_agent_in_order(self, agent: list[ str ], exclude: list[ str ] = None, exclude_checked_in: bool = False,
                              dormitory: bool = False):
        """
        按照顺序选择干员，只选择未在工作、未注意力涣散、未在休息的空闲干员
        :param agent: 指定入驻干员列表
        :param exclude: 排除干员列表，不选择这些干员
        :param exclude_checked_in: 是否仅选择未进驻干员
        :param dormitory: 是否是入驻宿舍，如果不是，则不选择注意力涣散的干员
        """
        if exclude is None:
            exclude = [ ]
        if exclude_checked_in:
            self.tap_element('arrange_order_options')
            self.tap_element('arrange_non_check_in')
            self.tap_element('arrange_blue_yes')
        self.tap_element('arrange_clean')

        h, w = self.recog.h, self.recog.w
        first_time = True
        far_left = True
        _free = None
        idx = 0
        while idx < len(agent):
            logger.info('寻找干员: %s', agent[ idx ])
            found = 0
            while found == 0:
                ret = character_recognize.agent(self.recog.img)
                ret = np.array(ret, dtype=object).reshape(-1, 2, 2).reshape(-1, 2)
                # 'Free'代表占位符，选择空闲干员
                if agent[ idx ] == 'Free':
                    for x in ret:
                        x[ 1 ][ 0, 1 ] -= 155
                        x[ 1 ][ 2, 1 ] -= 155
                        # 不选择已进驻的干员，如果非宿舍则进一步不选择精神涣散的干员
                        if not (self.find('agent_on_shift', scope=(x[ 1 ][ 0 ], x[ 1 ][ 2 ]))
                                or self.find('agent_resting', scope=(x[ 1 ][ 0 ], x[ 1 ][ 2 ]))
                                or (not dormitory and self.find('distracted', scope=(x[ 1 ][ 0 ], x[ 1 ][ 2 ])))):
                            if x[ 0 ] not in agent and x[ 0 ] not in exclude:
                                self.tap(x[ 1 ], x_rate=0.5, y_rate=0.5, interval=0)
                                agent[ idx ] = x[ 0 ]
                                _free = x[ 0 ]
                                found = 1
                                break

                elif agent[ idx ] != 'Free':
                    for x in ret:
                        if x[ 0 ] == agent[ idx ]:
                            self.tap(x[ 1 ], x_rate=0.5, y_rate=0.5, interval=0)
                            found = 1
                            break

                if found == 1:
                    idx += 1
                    first_time = True
                    break

                if first_time and not far_left and agent[ idx ] != 'Free':
                    # 如果是寻找这位干员目前为止的第一次滑动, 且目前不是最左端，则滑动到最左端
                    self.sleep(interval=0.5, rebuild=False)
                    for _ in range(9):
                        self.swipe_only((w // 2, h // 2), (w // 2, 0), interval=0.5)
                    self.swipe((w // 2, h // 2), (w // 2, 0), interval=3, rebuild=True)
                    far_left = True
                    first_time = False
                else:
                    st = ret[ -2 ][ 1 ][ 2 ]  # 起点
                    ed = ret[ 0 ][ 1 ][ 1 ]  # 终点
                    self.swipe_noinertia(st, (ed[ 0 ] - st[ 0 ], 0), rebuild=True)
                    far_left = False
                    first_time = False
        self.recog.update()
        return _free

    def fia(self, room: str):
        """
        使用菲亚梅塔恢复指定房间心情最差的干员的心情，同时保持工位顺序不变
        目前仅支持制造站、贸易站、发电站 （因为其他房间在输入命令时较为繁琐，且需求不大）
        使用前需要菲亚梅塔位于任意一间宿舍
        """
        # 基建干员选择界面，导航栏四个排序选项的相对位置
        BY_STATUS = [ 0.622, 0.05 ]  # 按工作状态排序
        BY_SKILL = [ 0.680, 0.05 ]  # 按技能排序
        BY_EMO = [ 0.755, 0.05 ]  # 按心情排序
        BY_TRUST = [ 0.821, 0.05 ]  # 按信赖排序

        logger.info('基建：使用菲亚梅塔恢复心情')
        self.tap_element('infra_overview', interval=2)

        logger.info('查询菲亚梅塔状态')
        idx = 0
        room_total = len(base_room_list)
        fia_resting = fia_full = None
        while idx < room_total:
            ret, switch, _ = segment.worker(self.recog.img)
            if room_total - idx < len(ret):
                # 已经滑动到底部
                ret = ret[ -(room_total - idx): ]

            fia_resting = self.find('fia_resting') or self.find('fia_resting_elite2')
            if fia_resting:
                logger.info('菲亚梅塔还在休息')
                break

            for block in ret:
                fia_full = self.find('fia_full', scope=(block[ 0 ], block[ 2 ])) \
                           or self.find('fia_full_elite2', scope=(block[ 0 ], block[ 2 ]))
                if fia_full:
                    fia_full = base_room_list[ idx ] if 'dormitory' in base_room_list[ idx ] else None
                    break
                idx += 1

            if fia_full:
                break

            block = ret[ -1 ]
            top = switch[ 2 ][ 1 ]
            self.swipe_noinertia(tuple(block[ 1 ]), (0, top - block[ 1 ][ 1 ]), rebuild=True)

        if not fia_resting and not fia_full:
            logger.warning('未找到菲亚梅塔，使用本功能前请将菲亚梅塔置于宿舍！')
        elif fia_full:
            logger.info('菲亚梅塔心情已满，位于%s', fia_full)
            logger.info('查询指定房间状态')
            self.back(interval=2)
            self.enter_room(room)

            # 进入进驻详情
            if not self.find('arrange_check_in_on'):
                self.tap_element('arrange_check_in', interval=2, rebuild=False)
            self.tap((self.recog.w * 0.82, self.recog.h * 0.25), interval=2)
            # 确保按工作状态排序 防止出错
            self.tap((self.recog.w * BY_TRUST[ 0 ], self.recog.h * BY_TRUST[ 1 ]), interval=0)
            self.tap((self.recog.w * BY_STATUS[ 0 ], self.recog.h * BY_STATUS[ 1 ]), interval=0.1)
            # 记录房间中的干员及其工位顺序
            ret = character_recognize.agent(self.recog.img)
            ret = np.array(ret, dtype=object).reshape(-1, 2, 2).reshape(-1, 2)
            on_shift_agents = [ ]
            for x in ret:
                x[ 1 ][ 0, 1 ] -= 155
                x[ 1 ][ 2, 1 ] -= 155
                if self.find('agent_on_shift', scope=(x[ 1 ][ 0 ], x[ 1 ][ 2 ])) \
                        or self.find('distracted', scope=(x[ 1 ][ 0 ], x[ 1 ][ 2 ])):
                    self.tap(x[ 1 ], x_rate=0.5, y_rate=0.5, interval=0)
                    on_shift_agents.append(x[ 0 ])
            if len(on_shift_agents) == 0:
                logger.warning('该房间没有干员在工作')
                return
            logger.info('房间内的干员顺序为: %s', on_shift_agents)

            # 确保按心情升序排列
            self.tap((self.recog.w * BY_TRUST[ 0 ], self.recog.h * BY_TRUST[ 1 ]), interval=0)
            self.tap((self.recog.w * BY_EMO[ 0 ], self.recog.h * BY_EMO[ 1 ]), interval=0)
            self.tap((self.recog.w * BY_EMO[ 0 ], self.recog.h * BY_EMO[ 1 ]), interval=0.1)
            # 寻找这个房间里心情最低的干员,
            _temp_on_shift_agents = on_shift_agents.copy()
            while 'Free' not in _temp_on_shift_agents:
                ret = character_recognize.agent(self.recog.img)
                ret = np.array(ret, dtype=object).reshape(-1, 2, 2).reshape(-1, 2)
                for x in ret:
                    if x[ 0 ] in _temp_on_shift_agents:
                        # 用占位符替代on_shift_agents中这个agent
                        _temp_on_shift_agents[ _temp_on_shift_agents.index(x[ 0 ]) ] = 'Free'
                        logger.info('房间内心情最差的干员为: %s', x[ 0 ])
                        _recover = x[ 0 ]
                        break
                if 'Free' in _temp_on_shift_agents:
                    break

                st = ret[ -2 ][ 1 ][ 2 ]  # 起点
                ed = ret[ 0 ][ 1 ][ 1 ]  # 终点
                self.swipe_noinertia(st, (ed[ 0 ] - st[ 0 ], 0), rebuild=True)

            # 用一位空闲干员替换上述心情最差的干员
            # 重新进入干员进驻页面，目的是加快安排速度
            self.back(interval=2)
            if not self.find('arrange_check_in_on'):
                self.tap_element('arrange_check_in', interval=2, rebuild=False)
            logger.info('安排一位空闲干员替换心情最差的%s', _recover)
            self.tap((self.recog.w * 0.82, self.recog.h * 0.25), interval=2)
            # 按工作状态排序，加快安排速度
            self.tap((self.recog.w * BY_TRUST[ 0 ], self.recog.h * BY_TRUST[ 1 ]), interval=0)
            self.tap((self.recog.w * BY_STATUS[ 0 ], self.recog.h * BY_STATUS[ 1 ]), interval=0.1)
            # 安排空闲干员
            _free = self.choose_agent_in_order(_temp_on_shift_agents, exclude_checked_in=True)
            self.tap_element('confirm_blue', detected=True, judge=False, interval=3)
            while self.scene() == Scene.CONNECTING:
                self.sleep(3)
            self.back(interval=2)

            logger.info('进入菲亚梅塔所在宿舍，为%s恢复心情', _recover)
            self.enter_room(fia_full)
            # 进入进驻详情
            if not self.find('arrange_check_in_on'):
                self.tap_element('arrange_check_in', interval=2, rebuild=False)
            self.tap((self.recog.w * 0.82, self.recog.h * 0.25), interval=2)

            rest_agents = [ _recover, '菲亚梅塔' ]
            self.choose_agent_in_order(rest_agents, exclude_checked_in=True)
            self.tap_element('confirm_blue', detected=True, judge=False, interval=3)
            while self.scene() == Scene.CONNECTING:
                self.sleep(3)

            logger.info('恢复完毕，填满宿舍')
            rest_agents = '菲亚梅塔 Free Free Free Free'.split()
            self.tap((self.recog.w * 0.82, self.recog.h * 0.25), interval=2)
            self.choose_agent_in_order(rest_agents, exclude=[ _recover ], dormitory=True)
            self.tap_element('confirm_blue', detected=True, judge=False, interval=3)
            while self.scene() == Scene.CONNECTING:
                self.sleep(3)

            logger.info('恢复原职')
            self.back(interval=2)
            self.enter_room(room)
            if not self.find('arrange_check_in_on'):
                self.tap_element('arrange_check_in', interval=2, rebuild=False)
            self.tap((self.recog.w * 0.82, self.recog.h * 0.25), interval=2)
            self.choose_agent_in_order(on_shift_agents)
            self.tap_element('confirm_blue', detected=True, judge=False, interval=3)
            while self.scene() == Scene.CONNECTING:
                self.sleep(3)
            self.back(interval=2)

    # def clue_statis(self):

    #     clues = {'all': {}, 'own': {}}

    #     self.recog_bar()
    #     self.tap(((x1*7+x2)//8, y0//2), rebuild=False)
    #     self.tap(((x1*7.5+x2*0.5)//8, (y0+y1)//2), rebuild=False)
    #     self.recog_view(only_y2=False)

    #     if x3 is None:
    #         return clues

    #     for i in range(1, 8):

    #         self.tap((((i+0.5)*x2+(8-i-0.5)*x1)//8, (y0+y1)//2), rebuild=False)
    #         self.clear_clue_mask()
    #         self.recog_view()

    #         count = 0
    #         if y2 < self.recog.h - 20:
    #             count = len(self.ori_clue())
    #         else:
    #             while True:
    #                 restart = False
    #                 count = 0
    #                 ret = self.ori_clue()
    #                 while True:

    #                     y4 = 0
    #                     for poly in ret:
    #                         count += 1
    #                         y4 = poly[0, 1]

    #                     self.tap((x4, y4+10), rebuild=False)
    #                     self.device.swipe([(x4, y4), (x4, y1+10), (0, y1+10)], duration=(y4-y1-10)*3)
    #                     self.sleep(1, rebuild=False)

    #                     mask = self.get_clue_mask()
    #                     if mask is not None:
    #                         self.clear_clue_mask()
    #                     ret = self.ori_clue()

    #                     if mask is None or not (ret[0][0, 1] <= mask <= ret[-1][1, 1]):
    #                         # 漂移了的话
    #                         restart = True
    #                         break

    #                     if ret[0][0, 1] <= mask <= ret[0][1, 1]:
    #                         count -= 1
    #                         continue
    #                     else:
    #                         for poly in ret:
    #                             if mask < poly[0, 1]:
    #                                 count += 1
    #                         break

    #                 if restart:
    #                     self.swipe((x4, y1+10), (0, 1000),
    #                                duration=500, interval=3, rebuild=False)
    #                     continue
    #                 break

    #         clues['all'][i] = count

    #     self.tap(((x1+x2)//2, y0//2), rebuild=False)

    #     for i in range(1, 8):
    #         self.tap((((i+0.5)*x2+(8-i-0.5)*x1)//8, (y0+y1)//2), rebuild=False)

    #         self.clear_clue_mask()
    #         self.recog_view()

    #         count = 0
    #         if y2 < self.recog.h - 20:
    #             count = len(self.ori_clue())
    #         else:
    #             while True:
    #                 restart = False
    #                 count = 0
    #                 ret = self.ori_clue()
    #                 while True:

    #                     y4 = 0
    #                     for poly in ret:
    #                         count += 1
    #                         y4 = poly[0, 1]

    #                     self.tap((x4, y4+10), rebuild=False)
    #                     self.device.swipe([(x4, y4), (x4, y1+10), (0, y1+10)], duration=(y4-y1-10)*3)
    #                     self.sleep(1, rebuild=False)

    #                     mask = self.get_clue_mask()
    #                     if mask is not None:
    #                         self.clear_clue_mask()
    #                     ret = self.ori_clue()

    #                     if mask is None or not (ret[0][0, 1] <= mask <= ret[-1][1, 1]):
    #                         # 漂移了的话
    #                         restart = True
    #                         break

    #                     if ret[0][0, 1] <= mask <= ret[0][1, 1]:
    #                         count -= 1
    #                         continue
    #                     else:
    #                         for poly in ret:
    #                             if mask < poly[0, 1]:
    #                                 count += 1
    #                         break

    #                 if restart:
    #                     self.swipe((x4, y1+10), (0, 1000),
    #                                duration=500, interval=3, rebuild=False)
    #                     continue
    #                 break

    #         clues['own'][i] = count

    #     return clues
