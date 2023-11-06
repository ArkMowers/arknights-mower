from __future__ import annotations

from enum import Enum
from arknights_mower.utils import character_recognize, segment
from arknights_mower.utils.log import logger
from arknights_mower.utils import typealias as tp
from arknights_mower.utils.recognize import Scene


class ArrangeOrder(Enum):
    STATUS = 1
    SKILL = 2
    FEELING = 3
    TRUST = 4


arrange_order_res = {
    ArrangeOrder.STATUS: (1560 / 2496, 96 / 1404),
    ArrangeOrder.SKILL: (1720 / 2496, 96 / 1404),
    ArrangeOrder.FEELING: (1880 / 2496, 96 / 1404),
    ArrangeOrder.TRUST: (2050 / 2496, 96 / 1404),
}


class BaseMixin:
    def switch_arrange_order(self, index: int, asc="false") -> None:
        self.tap(
            (
                self.recog.w * arrange_order_res[ArrangeOrder(index)][0],
                self.recog.h * arrange_order_res[ArrangeOrder(index)][1],
            ),
            interval=0,
            rebuild=False,
        )
        # 点个不需要的
        if index < 4:
            self.tap(
                (
                    self.recog.w * arrange_order_res[ArrangeOrder(index + 1)][0],
                    self.recog.h * arrange_order_res[ArrangeOrder(index)][1],
                ),
                interval=0,
                rebuild=False,
            )
        else:
            self.tap(
                (
                    self.recog.w * arrange_order_res[ArrangeOrder(index - 1)][0],
                    self.recog.h * arrange_order_res[ArrangeOrder(index)][1],
                ),
                interval=0,
                rebuild=False,
            )
        # 切回来
        self.tap(
            (
                self.recog.w * arrange_order_res[ArrangeOrder(index)][0],
                self.recog.h * arrange_order_res[ArrangeOrder(index)][1],
            ),
            interval=0.2,
            rebuild=True,
        )
        # 倒序
        if asc != "false":
            self.tap(
                (
                    self.recog.w * arrange_order_res[ArrangeOrder(index)][0],
                    self.recog.h * arrange_order_res[ArrangeOrder(index)][1],
                ),
                interval=0.2,
                rebuild=True,
            )

    def scan_agent(self, agent: list[str], error_count=0, max_agent_count=-1):
        try:
            # 识别干员
            self.recog.update()
            ret = character_recognize.agent(self.recog.img)  # 返回的顺序是从左往右从上往下
            # 提取识别出来的干员的名字
            select_name = []
            for y in ret:
                name = y[0]
                if name in agent:
                    select_name.append(name)
                    # self.get_agent_detail((y[1][0]))
                    self.tap((y[1][0]), interval=0)
                    agent.remove(name)
                    # 如果是按照个数选择 Free
                    if max_agent_count != -1:
                        if len(select_name) >= max_agent_count:
                            return select_name, ret
            return select_name, ret
        except Exception as e:
            error_count += 1
            if error_count < 3:
                logger.exception(e)
                self.sleep(3)
                return self.scan_agent(agent, error_count, max_agent_count)
            else:
                raise e

    def swipe_left(self, right_swipe, w, h):
        for _ in range(right_swipe):
            self.swipe_only((w // 2, h // 2), (w // 2, 0), interval=0.5)
        return 0

    def detail_filter(self, turn_on, type="not_in_dorm"):
        logger.info(f'开始 {("打开" if turn_on else "关闭")} {type} 筛选')
        self.tap((self.recog.w * 0.95, self.recog.h * 0.05), interval=1)
        if type == "not_in_dorm":
            not_in_dorm = self.find("arrange_non_check_in", score=0.9)
            if turn_on ^ (not_in_dorm is None):
                self.tap((self.recog.w * 0.3, self.recog.h * 0.5), interval=0.5)
        # 确认
        self.tap((self.recog.w * 0.8, self.recog.h * 0.8), interval=0.5)

    def enter_room(self, room: str) -> tp.Rectangle:
        """ 获取房间的位置并进入 """
        success = False
        retry = 3
        while not success:
            try:
                # 获取基建各个房间的位置
                base_room = segment.base(self.recog.img, self.find('control_central', strict=True))
                # 将画面外的部分删去
                _room = base_room[room]

                for i in range(4):
                    _room[i, 0] = max(_room[i, 0], 0)
                    _room[i, 0] = min(_room[i, 0], self.recog.w)
                    _room[i, 1] = max(_room[i, 1], 0)
                    _room[i, 1] = min(_room[i, 1], self.recog.h)

                # 点击进入
                self.tap(_room[0], interval=3)
                while self.find('control_central') is not None:
                    self.tap(_room[0], interval=3)
                success = True
            except Exception as e:
                retry -= 1
                self.back_to_infrastructure()
                self.wait_for_scene(Scene.INFRA_MAIN, "get_infra_scene")
                if retry <= 0:
                    raise e
