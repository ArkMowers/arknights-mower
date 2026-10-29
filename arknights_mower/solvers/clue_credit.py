"""双 Mower 模式的信息板领取；原有线索、访友和购物入口负责调度。"""

from datetime import datetime, timedelta

from arknights_mower.solvers.shop import CreditShop
from arknights_mower.utils import config
from arknights_mower.utils.csleep import MowerExit
from arknights_mower.utils.datetime import get_server_time
from arknights_mower.utils.log import logger
from arknights_mower.utils.scene import Scene


class ClueCreditMixin:
    @staticmethod
    def _clue_credit_enabled():
        return bool(getattr(config.conf, "should_defer_clue_credit", False))

    def _clue_flow_resume_time(self, at=None):
        """03:45 至 04:00 暂缓开始线索流程，返回本机时间的恢复时刻。"""
        if not self._clue_credit_enabled():
            return None
        server_time = get_server_time()
        if at is not None:
            # 交流结束时间和调度任务使用本机时间，避让按国服游戏日计算。
            server_time = at.astimezone(server_time.tzinfo)
        reset_time = (server_time + timedelta(days=1)).replace(
            hour=0, minute=0, second=0, microsecond=0
        )
        if server_time >= reset_time - timedelta(minutes=15):
            return reset_time.astimezone().replace(tzinfo=None)
        return None

    def _run_on_demand_clue_shop(self, *, settlement_checked=None):
        """线索流程结束后购物；不发起访友，也不安排额外购物任务。"""
        if config.stop_mower.is_set():
            raise MowerExit
        if getattr(self, "_clue_access_record_exhausted", False):
            if not self._clue_access_record_cleared():
                return False
            self._clue_access_record_exhausted = False
        visit_day = get_server_time().date()
        if visit_day not in (
            getattr(self, "daily_visit_friend", None),
            getattr(self, "daily_visit_friend_attempt", None),
        ):
            logger.info("本游戏日尚未尝试访友，等待后续线索流程购物")
            return
        shop = CreditShop(self.device, self.recog)
        shop.run(on_demand=True)
        if self._needs_clue_credit(shop):
            if settlement_checked is None:
                logger.info(
                    "购物还差 %s 信用，准备打开信息板尝试领取上周结算，本次不领取本周信用",
                    shop.credit_deficit,
                )
                settlement_checked = self._visit_clue_message_board(
                    collect_current=False
                )
                # 打开板子可能已自动到账；访问记录未能关闭时保留本轮任务。
                if (
                    getattr(self, "_clue_access_record_exhausted", False)
                    and not self._clue_access_record_cleared()
                ):
                    return False
                shop.run(on_demand=True)
            if settlement_checked and self._needs_clue_credit(shop):
                logger.info(
                    "购物仍差 %s 信用，准备打开信息板领取本周信用",
                    shop.credit_deficit,
                )
                self._visit_clue_message_board(collect_current=True)
                if (
                    getattr(self, "_clue_access_record_exhausted", False)
                    and not self._clue_access_record_cleared()
                ):
                    return False
                shop.run(on_demand=True)
        self.scene_graph_navigation(Scene.INFRA_MAIN)

    def _needs_clue_credit(self, shop):
        if config.stop_mower.is_set():
            raise MowerExit
        return (
            self._clue_credit_enabled()
            and shop.credit_deficit is not None
            and shop.credit_deficit > 0
            and not self._can_wait_for_clue_party(shop)
        )

    def _visit_clue_message_board(self, *, collect_current):
        self.scene_graph_navigation(Scene.INFRA_MAIN)
        if (
            getattr(self, "_clue_access_record_exhausted", False)
            and not self._clue_access_record_cleared()
        ):
            return False
        self.enter_room("meeting")
        completed = self._collect_clue_message_board(collect_current=collect_current)
        if (
            getattr(self, "_clue_access_record_exhausted", False)
            and not self._clue_access_record_cleared()
        ):
            return False
        # 打开信息板就可能有信用到账；其他未确认页面仍先退出，再由商店读取余额。
        self.scene_graph_navigation(Scene.INFRA_MAIN)
        return completed

    def _prepare_clue_room(self):
        self.wait_product_complete()
        # 线索交流提示占住右上角一小块，会挡住会客室界面，先点掉
        if self.find("clue/title_party"):
            self.tap_element("clue/title_party")
        # 关闭提示后重新取帧，避免后续匹配仍使用关闭前的画面。
        self.recog.update()

    def _open_clue_message_board(self):
        """唤出家具交互入口后打开信息板，仅在确认仍在房间时补救一次。"""
        self.recog.update()
        if (
            self.scene() == Scene.CLUE_MESSAGE_BOARD
            or self._clue_access_record_visible()
        ):
            return self._wait_clue_message_board()
        if self.scene() != Scene.INFRA_DETAILS:
            return False
        self._prepare_clue_room()
        for attempt in range(2):
            self.recog.update()
            scene = self.scene()
            # 结算弹窗可能透出房间特征，不能在弹窗上点击家具交互。
            if self.find("materiel_ico") or self._clue_access_record_visible():
                return False
            if scene == Scene.CLUE_MESSAGE_BOARD:
                return True
            if scene != Scene.INFRA_DETAILS:
                return False
            if self.find("room_detail"):
                # 侧栏打开时，点击家具交互按钮只会关闭侧栏，不会唤出入口。
                logger.info("关闭会客室入住信息侧栏，再唤出信息板入口")
                self.tap((680, 1000))
                self.recog.update()
                if (
                    self.scene() != Scene.INFRA_DETAILS
                    or self.find("room_detail")
                    or self.find("materiel_ico")
                    or self._clue_access_record_visible()
                ):
                    logger.warning(
                        "会客室入住信息侧栏关闭后未确认房间画面，结束本次打开尝试",
                        extra={"archive_screenshots": True},
                    )
                    return False
            was_visible = self.find("clue/message_board") is not None
            if attempt:
                logger.info("仍在会客室，重新唤出信息板入口后补救一次")
            # 入口可能处于进房动画或即将消失，不能仅凭可见就直接点击。
            self.tap((680, 1000))
            if self.scene() != Scene.INFRA_DETAILS or self.find("materiel_ico"):
                return False
            if board_pos := self.find("clue/message_board"):
                # 家具交互提示只短暂显示，使用当前帧的位置及时点击。
                logger.info("点击会客室信息板入口")
                self.tap(board_pos)
                if self._wait_clue_message_board():
                    logger.info("已确认打开会客室信息板")
                    return True
            elif not was_visible:
                # 唤出前后均无入口，没有状态变化时不重复点击。
                break
            # 原来可见的提示可能已过期；下一轮先核实房间，再重新唤出。
        logger.warning(
            "信息板未打开，结束本次打开尝试", extra={"archive_screenshots": True}
        )
        return False

    def _clue_access_record_visible(self):
        """核对访问记录固定前景，排除背景和结算数值。"""
        return bool(self.find("clue/access_record"))

    def _clue_access_record_cleared(self):
        return not self._clue_access_record_visible() and self.scene() not in (
            *self.waiting_scene,
            Scene.CLUE_ACCESS_RECORD,
        )

    def _wait_clue_message_board(self, *, confirm_collection=False):
        """处理已识别的结算和奖励页，等待信息板并核实领取按钮状态。"""
        if getattr(self, "_clue_access_record_exhausted", False):
            self.recog.update()
            if not self._clue_access_record_cleared():
                return False
            self._clue_access_record_exhausted = False
        reward_dismissed = False
        record_dismissed = False
        record_frames = 0
        cleared_frames = 0
        for _ in range(8):
            self.recog.update()
            scene = self.scene()
            # 奖励页可能透出底层信息板特征，必须先检查弹窗。
            if self.find("materiel_ico") or scene == Scene.MATERIEL:
                cleared_frames = 0
                record_frames = 0
                if not reward_dismissed:
                    logger.info("关闭信息板领取物资提示")
                    self.tap((960, 960))
                    reward_dismissed = True
            # 固定前景独立核实，避免背景场景的误判阻止关闭弹窗。
            elif self._clue_access_record_visible():
                cleared_frames = 0
                record_frames += 1
                # 先等结算页自行消失；下一帧仍确认存在时才点击一次中央空白处。
                if record_frames >= 2 and not record_dismissed:
                    logger.info("关闭信息板上周访问记录")
                    self.tap((960, 540))
                    record_dismissed = True
            elif scene == Scene.CLUE_MESSAGE_BOARD:
                record_frames = 0
                if not confirm_collection:
                    return True
                if self.find("clue/message_board_collect"):
                    cleared_frames = 0
                else:
                    cleared_frames += 1
                    # 单帧漏识别不能确认领取；必须在信息板上连续确认按钮消失。
                    if cleared_frames >= 2:
                        return True
            else:
                cleared_frames = 0
                record_frames = 0
            self.sleep(0.5)
        if record_dismissed:
            self._clue_access_record_exhausted = True
        logger.warning(
            "信息板%s，保留现场截图",
            "领取未确认" if confirm_collection else "页面未确认",
            extra={"archive_screenshots": True},
        )
        return False

    def _collect_clue_message_board(self, *, collect_current=True):
        """打开信息板并按需领取本周信用，确认页面处理和返回结果。"""
        if self._open_clue_message_board():
            completed = True
            if collect_current and (collect := self.find("clue/message_board_collect")):
                logger.info("领取信息板信用")
                self.tap(collect)
                completed = self._wait_clue_message_board(confirm_collection=True)
            # 未知页面交给外层导航退出，不能把返回成功当作领取成功。
            if self.find("materiel_ico") or self.scene() != Scene.CLUE_MESSAGE_BOARD:
                return False
            self.back()
            for _ in range(4):
                self.recog.update()
                if self.scene() == Scene.INFRA_DETAILS:
                    return completed
                self.sleep(0.5)
            logger.warning(
                "信息板未返回会客室，结束本次信用领取",
                extra={"archive_screenshots": True},
            )
        return False

    def _can_wait_for_clue_party(self, shop_solver):
        """本日交流收益足够补齐购物缺口，且在 03:45 前结束时暂缓领取。"""
        deficit = shop_solver.credit_deficit
        party_time = getattr(self, "party_time", None)
        if (
            deficit is None
            or not 0 < deficit <= 210
            or not isinstance(party_time, datetime)
        ):
            return False
        server_now = get_server_time()
        # read_party_time 产生本机时间；统一转换到游戏日使用的时区后比较。
        party_time = party_time.astimezone(server_now.tzinfo)
        # get_server_time 的午夜对应国服凌晨 04:00。
        reset_time = (server_now + timedelta(days=1)).replace(
            hour=0, minute=0, second=0, microsecond=0
        )
        if server_now < party_time < reset_time - timedelta(minutes=15):
            logger.info(
                "购物缺口 %s 信用，等待 %s 结束的线索交流提供 210 信用，暂缓领取信息板",
                deficit,
                self.party_time,
            )
            return True
        return False
