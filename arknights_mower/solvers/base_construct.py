import traceback
import numpy as np

from ..utils import detector, segment
from ..utils.log import logger
from ..utils.config import MAX_RETRYTIME
from ..utils.recognize import Scene, RecognizeError
from ..utils.solver import BaseSolver, StrategyError


class BaseConstructSolver(BaseSolver):
    """
    收集基建的产物：物资、赤金、信赖
    """

    def __init__(self, adb=None, recog=None):
        super(BaseConstructSolver, self).__init__(adb, recog)

    def clue_bar(self):
        global x1, x2, y0, y1

        # x1, x2, y0, y1: 阵营选择栏
        (x1, y0), (x2, y1) = self.find('clue_nav')
        while int(self.recog.img[y0, x1-1].max()) - int(self.recog.img[y0, x1].max()) <= 1:
            x1 -= 1
        while int(self.recog.img[y0, x2].max()) - int(self.recog.img[y0, x2-1].max()) <= 1:
            x2 += 1
        while abs(int(self.recog.img[y1+1, x1].max()) - int(self.recog.img[y1, x1].max())) <= 1:
            y1 += 1
        y1 += 1

    def clue_view(self, only_y2=True):
        global y2, x3, x4

        # y2: 线索底部
        y2 = self.recog.h
        while self.recog.img[y2-1, x1:x2].ptp() <= 24:
            y2 -= 1

        if not only_y2:

            # x3: 右边黑色 mask 边缘
            x3 = x2
            while True:
                max_abs = 0
                for y in range(y1, y2):
                    max_abs = max(max_abs, abs(
                        int(self.recog.img[y, x3-1, 0]) - int(self.recog.img[y, x3-2, 0])))
                if max_abs <= 5:
                    x3 -= 1
                else:
                    break
            _bool = False
            for y in range(y1, y2):
                if int(self.recog.img[y, x3-1, 0]) - int(self.recog.img[y, x3-2, 0]) == max_abs:
                    _bool = True
            if not _bool:
                self.tap(((x1+x2)//2, y1+10), matcher=False)
                x3 = x2
                while True:
                    max_abs = 0
                    for y in range(y1, y2):
                        max_abs = max(max_abs, abs(
                            int(self.recog.img[y, x3-1, 0]) - int(self.recog.img[y, x3-2, 0])))
                    if max_abs <= 5:
                        x3 -= 1
                    else:
                        break
                _bool = False
                for y in range(y1, y2):
                    if int(self.recog.img[y, x3-1, 0]) - int(self.recog.img[y, x3-2, 0]) == max_abs:
                        _bool = True
                if not _bool:
                    x3 = None

            # x4: 四分之三的位置，用来定位单个线索
            x4 = (x1 + 3 * x2) // 4

    def get_clue_mask(self):

        mask = []
        for y in range(y1, y2):
            if int(self.recog.img[y, x3-1, 0]) - int(self.recog.img[y, x3-2, 0]) > 20 and np.ptp(self.recog.img[y, x3-2]) == 0:
                mask.append(y)

        if len(mask) > 0:
            logger.debug(np.average(mask))
            return np.average(mask)
        else:
            return None

    def clear_clue_mask(self):

        while True:
            mask = False
            for y in range(y1, y2):
                if int(self.recog.img[y, x3-1, 0]) - int(self.recog.img[y, x3-2, 0]) > 20 and np.ptp(self.recog.img[y, x3-2]) == 0:
                    self.tap((x3-2, y+1), matcher=True)
                    mask = True
                    break
            if mask:
                continue
            break

    def ori_clue(self):

        ret = []
        y3 = y1
        status = -2
        for y in range(y1, y2):
            if self.recog.img[y, x4-5:x4+5].max() < 192:
                if status == -1:
                    status = 20
                if status > 0:
                    status -= 1
                if status == 0:
                    status = -2
                    ret.append(segment.get_poly(x1, x2, y3, y-20))
                    y3 = y-20+5
            else:
                status = -1
        if status != -2:
            ret.append(segment.get_poly(x1, x2, y3, y2))
        ret = [x for x in ret if x[1][1] - x[0][1] >= self.recog.h / 5]
        logger.debug(ret)
        return ret

    def clue_statis(self):

        clues = {'all': {}, 'own': {}}

        self.clue_bar()
        self.tap(((x1*7+x2)//8, y0//2), matcher=False)
        self.tap(((x1*7.5+x2*0.5)//8, (y0+y1)//2), matcher=False)
        self.clue_view(only_y2=False)

        if x3 is None:
            return clues

        for i in range(1, 8):

            self.tap((((i+0.5)*x2+(8-i-0.5)*x1)//8, (y0+y1)//2), matcher=False)
            self.clear_clue_mask()
            self.clue_view()

            count = 0
            if y2 < self.recog.h - 20:
                count = len(self.ori_clue())
            else:
                while True:
                    restart = False
                    count = 0
                    ret = self.ori_clue()
                    while True:

                        y4 = 0
                        for poly in ret:
                            count += 1
                            y4 = poly[0, 1]

                        self.tap((x4, y4+10), matcher=False)
                        self.adb.touch_swipe(
                            (x4, y4), (-x4, y1+10-y4), duration=(y4-y1-10)*3)
                        self.adb.touch_swipe((x4, y4), (-x4, 0), duration=500)
                        self.sleep(1, matcher=False)

                        mask = self.get_clue_mask()
                        if mask is not None:
                            self.clear_clue_mask()
                        ret = self.ori_clue()

                        if mask is None or not (ret[0][0, 1] <= mask <= ret[-1][1, 1]):
                            # 漂移了的话
                            restart = True
                            break

                        if ret[0][0, 1] <= mask <= ret[0][1, 1]:
                            count -= 1
                            continue
                        else:
                            for poly in ret:
                                if mask < poly[0, 1]:
                                    count += 1
                            break

                    if restart:
                        self.swipe((x4, y1+10), (0, 1000),
                                   duration=500, interval=3, matcher=False)
                        continue
                    break

            clues['all'][i] = count

        self.tap(((x1+x2)//2, y0//2), matcher=False)

        for i in range(1, 8):
            self.tap((((i+0.5)*x2+(8-i-0.5)*x1)//8, (y0+y1)//2), matcher=False)

            self.clear_clue_mask()
            self.clue_view()

            count = 0
            if y2 < self.recog.h - 20:
                count = len(self.ori_clue())
            else:
                while True:
                    restart = False
                    count = 0
                    ret = self.ori_clue()
                    while True:

                        y4 = 0
                        for poly in ret:
                            count += 1
                            y4 = poly[0, 1]

                        self.tap((x4, y4+10), matcher=False)
                        self.adb.touch_swipe(
                            (x4, y4), (-x4, y1+10-y4), duration=(y4-y1-10)*3)
                        self.adb.touch_swipe((x4, y4), (-x4, 0), duration=500)
                        self.sleep(1, matcher=False)

                        mask = self.get_clue_mask()
                        if mask is not None:
                            self.clear_clue_mask()
                        ret = self.ori_clue()

                        if mask is None or not (ret[0][0, 1] <= mask <= ret[-1][1, 1]):
                            # 漂移了的话
                            restart = True
                            break

                        if ret[0][0, 1] <= mask <= ret[0][1, 1]:
                            count -= 1
                            continue
                        else:
                            for poly in ret:
                                if mask < poly[0, 1]:
                                    count += 1
                            break

                    if restart:
                        self.swipe((x4, y1+10), (0, 1000),
                                   duration=500, interval=3, matcher=False)
                        continue
                    break

            clues['own'][i] = count

        return clues

    def clue(self):

        global x1, x2, x3, x4, y0, y1, y2

        x1, x2, x3, x4 = 0, 0, 0, 0
        y0, y1, y2 = 0, 0, 0

        base_room = segment.base(self.recog.img, self.find('control_central'))

        room = base_room['meeting']
        for i in range(4):
            room[i, 0] = max(room[i, 0], 0)
            room[i, 0] = min(room[i, 0], self.recog.w)
            room[i, 1] = max(room[i, 1], 0)
            room[i, 1] = min(room[i, 1], self.recog.h)

        self.tap(room[0], interval=3, matcher=False)
        self.tap((10, self.recog.h-10), interval=3)

        (x0, y0), (x1, y1) = self.find('clue_func')

        self.tap(((x0+x1)//2, (y0*3+y1)//4), interval=3, matcher=False)
        self.tap((self.recog.w-10, self.recog.h-10), interval=3, matcher=False)
        self.tap((10, self.recog.h-10), interval=3, matcher=False)

        self.tap(((x0+x1)//2, (y0*5-y1)//4), interval=3)
        self.tap_element('clue_obtain', interval=3)
        self.tap_element('nav_button', x_rate=0.2, interval=3)

        clue_unlock = self.find('clue_unlock')
        if clue_unlock is not None:
            self.tap_element('clue', interval=3)

            self.clue_bar()
            self.tap(((x1*7+x2)//8, y0//2), matcher=False)
            self.clue_view(only_y2=False)

            get_all_clue = True
            for i in range(1, 8):
                self.tap((((i+0.5)*x2+(8-i-0.5)*x1) //
                         8, (y0+y1)//2), matcher=False)
                self.clear_clue_mask()
                self.clue_view()
                if len(self.ori_clue()) == 0:
                    get_all_clue = False
                    break
                self.tap(((x1+x2)//2, y1+3), matcher=False)

            self.tap((10, self.recog.h-10), interval=3, matcher=False)

            if get_all_clue and clue_unlock is not None:
                self.tap(clue_unlock)

        self.tap_element('nav_button', x_rate=0.2, interval=3)
        self.tap_element('nav_button', x_rate=0.2, interval=3)

    def drone(self, room):
        base_room = segment.base(self.recog.img, self.find('control_central'))

        room = base_room[room]
        for i in range(4):
            room[i,0] = max(room[i,0], 0)
            room[i,0] = min(room[i,0], self.recog.w)
            room[i,1] = max(room[i,1], 0)
            room[i,1] = min(room[i,1], self.recog.h)

        self.tap(room[0], interval=3, matcher=False)
        self.tap((10, self.recog.h-10), interval=3)

        accelerate = self.find('factory_accelerate')
        self.tap(accelerate)
        self.tap_element('all_in')
        self.tap(accelerate, y_rate=1)

        nav_button = self.recog.nav_button()
        self.tap(nav_button, x_rate=0.2, interval=3)
        self.tap(nav_button, x_rate=0.2, interval=3)


    def run(self, clue_collect=False, drone_room=None):
        """
        :param clue_collect: bool, 是否收取线索
        :param drone_room: str, 是否使用无人机加速（仅支持制造站）
        """
        logger.info('Start: 基建')

        retry_times = MAX_RETRYTIME
        todo_task = True
        while retry_times > 0:
            try:
                if self.scene() == Scene.INDEX:
                    self.tap_element('index_infrastructure')
                elif self.scene() == Scene.INFRA_MAIN:
                    if clue_collect:
                        self.clue()
                        clue_collect = False
                    elif todo_task:
                        notification = detector.infra_notification(self.recog.img)
                        if notification is None:
                            self.sleep(1)
                            notification = detector.infra_notification(self.recog.img)
                        if notification is not None:
                            self.tap(notification)
                        else:
                            todo_task = False
                    elif drone_room is not None:
                        self.drone(drone_room)
                        drone_room = None
                    else:
                        break
                elif self.scene() == Scene.INFRA_TODOLIST:
                    tapped = False
                    trust = self.recog.find('infra_collect_trust')
                    if trust is not None:
                        logger.info('基建：干员信赖')
                        self.tap(trust)
                        tapped = True
                    bill = self.recog.find('infra_collect_bill')
                    if bill is not None:
                        logger.info('基建：订单交付')
                        self.tap(bill)
                        tapped = True
                    factory = self.recog.find('infra_collect_factory')
                    if factory is not None:
                        logger.info('基建：可收获')
                        self.tap(factory)
                        tapped = True
                    if not tapped:
                        self.tap((10, self.recog.h-10))
                        todo_task = False
                elif self.scene() == Scene.LOADING:
                    self.sleep(3)
                elif self.get_navigation():
                    self.tap_element('nav_infrastructure')
                elif self.scene() != Scene.UNKNOWN:
                    self.back_to_index()
                else:
                    raise RecognizeError
            except RecognizeError as e:
                logger.warning(f'识别出了点小差错 qwq: {e}')
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
