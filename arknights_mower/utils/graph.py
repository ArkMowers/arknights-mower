import functools

import networkx as nx

from arknights_mower.utils import config
from arknights_mower.utils.csleep import MowerExit
from arknights_mower.utils.device.adb_client.session import Session
from arknights_mower.utils.device.scrcpy import Scrcpy
from arknights_mower.utils.log import logger
from arknights_mower.utils.scene import Scene, SceneComment
from arknights_mower.utils.simulator import restart_simulator
from arknights_mower.utils.solver import BaseSolver

DG = nx.DiGraph()


def edge(v_from: int, v_to: int, interval: int = 1):
    def decorator(func):
        DG.add_edge(v_from, v_to, weight=interval, transition=func)

        @functools.wraps(func)
        def wrapper(*args, **kw):
            return func(*args, **kw)

        return wrapper

    return decorator


# 首页


@edge(Scene.INFRA_MAIN, Scene.INDEX)
@edge(Scene.MISSION_DAILY, Scene.INDEX)
@edge(Scene.MISSION_WEEKLY, Scene.INDEX)
@edge(Scene.MISSION_TRAINEE, Scene.INDEX)
@edge(Scene.BUSINESS_CARD, Scene.INDEX)
@edge(Scene.FRIEND_LIST, Scene.INDEX)
@edge(Scene.RECRUIT_MAIN, Scene.INDEX)
@edge(Scene.SHOP_OTHERS, Scene.INDEX)
@edge(Scene.SHOP_CREDIT, Scene.INDEX)
@edge(Scene.TERMINAL_MAIN, Scene.INDEX)
@edge(Scene.TERMINAL_MAIN_THEME, Scene.INDEX)
@edge(Scene.TERMINAL_EPISODE, Scene.INDEX)
@edge(Scene.TERMINAL_COLLECTION, Scene.INDEX)
@edge(Scene.TERMINAL_REGULAR, Scene.INDEX)
@edge(Scene.TERMINAL_LONGTERM, Scene.INDEX)
@edge(Scene.DEPOT, Scene.INDEX)
@edge(Scene.HEADHUNTING, Scene.INDEX)
@edge(Scene.MAIL, Scene.INDEX)
def back_to_index(solver: BaseSolver):
    solver.back()


@edge(Scene.LEAVE_INFRASTRUCTURE, Scene.INDEX)
def leave_infrastructure(solver: BaseSolver):
    solver.tap_element("double_confirm/main", x_rate=1)


@edge(Scene.DOWNLOAD_VOICE_RESOURCES, Scene.INDEX)
def dont_download_voice(solver: BaseSolver):
    solver.tap_element("double_confirm/main", x_rate=0)


@edge(Scene.LOGIN_QUICKLY, Scene.INDEX)
def login_quickly(solver: BaseSolver):
    solver.tap_element("login_awake")


@edge(Scene.LOGIN_CAPTCHA, Scene.INDEX)
def login_captcha(solver: BaseSolver):
    solver.solve_captcha()
    solver.sleep(5)


@edge(Scene.LOGIN_BILIBILI, Scene.INDEX)
@edge(Scene.LOGIN_BILIBILI_PRIVACY, Scene.INDEX)
def login_bilibili(solver: BaseSolver):
    solver.bilibili()


@edge(Scene.EXIT_GAME, Scene.INDEX)
def exit_cancel(solver: BaseSolver):
    solver.tap_element("double_confirm/main", x_rate=0)


@edge(Scene.MATERIEL, Scene.INDEX)
def materiel(solver: BaseSolver):
    solver.tap((960, 960))


@edge(Scene.ANNOUNCEMENT, Scene.INDEX)
def announcement(solver: BaseSolver):
    solver.tap(solver.recog.check_announcement())


@edge(Scene.AGREEMENT_UPDATE, Scene.INDEX)
def agreement(solver: BaseSolver):
    if pos := solver.find("read_and_agree"):
        solver.tap(pos)
    else:
        solver.tap((791, 728))
        solver.tap((959, 828))


@edge(Scene.INDEX, Scene.INFRA_MAIN)
def index_to_infra(solver: BaseSolver):
    solver.tap_index_element("infrastructure")


@edge(Scene.INDEX, Scene.BUSINESS_CARD)
def index_to_friend(solver: BaseSolver):
    solver.tap_index_element("friend")


@edge(Scene.INDEX, Scene.MISSION_DAILY)
def index_to_mission(solver: BaseSolver):
    solver.tap_index_element("mission")


@edge(Scene.INDEX, Scene.RECRUIT_MAIN)
def index_to_recruit(solver: BaseSolver):
    solver.tap_index_element("recruit")


@edge(Scene.INDEX, Scene.SHOP_OTHERS)
def index_to_shop(solver: BaseSolver):
    solver.tap_index_element("shop")


@edge(Scene.INDEX, Scene.TERMINAL_MAIN)
def index_to_terminal(solver: BaseSolver):
    solver.tap_index_element("terminal")


@edge(Scene.INDEX, Scene.DEPOT)
def index_to_depot(solver: BaseSolver):
    solver.tap_index_element("warehouse")


@edge(Scene.INDEX, Scene.MAIL)
def index_to_mail(solver: BaseSolver):
    solver.tap_index_element("mail")


@edge(Scene.INDEX, Scene.HEADHUNTING)
def index_to_headhunting(solver: BaseSolver):
    solver.tap_index_element("headhunting")


# 导航栏


@edge(Scene.INFRA_MAIN, Scene.NAVIGATION_BAR)
@edge(Scene.RECRUIT_MAIN, Scene.NAVIGATION_BAR)
@edge(Scene.RECRUIT_TAGS, Scene.NAVIGATION_BAR)
@edge(Scene.MISSION_DAILY, Scene.NAVIGATION_BAR)
@edge(Scene.MISSION_WEEKLY, Scene.NAVIGATION_BAR)
@edge(Scene.MISSION_TRAINEE, Scene.NAVIGATION_BAR)
@edge(Scene.BUSINESS_CARD, Scene.NAVIGATION_BAR)
@edge(Scene.FRIEND_LIST, Scene.NAVIGATION_BAR)
@edge(Scene.SHOP_OTHERS, Scene.NAVIGATION_BAR)
@edge(Scene.SHOP_CREDIT, Scene.NAVIGATION_BAR)
@edge(Scene.TERMINAL_MAIN, Scene.NAVIGATION_BAR)
@edge(Scene.TERMINAL_MAIN_THEME, Scene.NAVIGATION_BAR)
@edge(Scene.TERMINAL_EPISODE, Scene.NAVIGATION_BAR)
@edge(Scene.TERMINAL_COLLECTION, Scene.NAVIGATION_BAR)
@edge(Scene.TERMINAL_REGULAR, Scene.NAVIGATION_BAR)
@edge(Scene.TERMINAL_LONGTERM, Scene.NAVIGATION_BAR)
@edge(Scene.TERMINAL_PERIODIC, Scene.NAVIGATION_BAR)
@edge(Scene.OPERATOR_CHOOSE_LEVEL, Scene.NAVIGATION_BAR)
@edge(Scene.OPERATOR_BEFORE, Scene.NAVIGATION_BAR)
@edge(Scene.OPERATOR_SELECT, Scene.NAVIGATION_BAR)
@edge(Scene.OPERATOR_SUPPORT, Scene.NAVIGATION_BAR)
@edge(Scene.INFRA_TODOLIST, Scene.NAVIGATION_BAR)
@edge(Scene.INFRA_CONFIDENTIAL, Scene.NAVIGATION_BAR)
@edge(Scene.INFRA_ARRANGE, Scene.NAVIGATION_BAR)
@edge(Scene.INFRA_DETAILS, Scene.NAVIGATION_BAR)
@edge(Scene.CTRLCENTER_ASSISTANT, Scene.NAVIGATION_BAR)
@edge(Scene.CLUE_DAILY, Scene.NAVIGATION_BAR)
@edge(Scene.CLUE_RECEIVE, Scene.NAVIGATION_BAR)
@edge(Scene.CLUE_PLACE, Scene.NAVIGATION_BAR)
@edge(Scene.ORDER_LIST, Scene.NAVIGATION_BAR)
@edge(Scene.FACTORY_ROOMS, Scene.NAVIGATION_BAR)
@edge(Scene.OPERATOR_ELIMINATE, Scene.NAVIGATION_BAR)
@edge(Scene.DEPOT, Scene.NAVIGATION_BAR)
@edge(Scene.FRIEND_VISITING, Scene.NAVIGATION_BAR)
@edge(Scene.HEADHUNTING, Scene.NAVIGATION_BAR)
def index_nav(solver: BaseSolver):
    solver.tap_element("nav_button")


# 不加从导航栏到基建首页的边，防止在基建内循环


@edge(Scene.NAVIGATION_BAR, Scene.MISSION_DAILY)
def nav_mission(solver: BaseSolver):
    solver.tap_nav_element("mission")


@edge(Scene.NAVIGATION_BAR, Scene.INDEX)
def nav_index(solver: BaseSolver):
    solver.tap_nav_element("index")


@edge(Scene.NAVIGATION_BAR, Scene.TERMINAL_MAIN)
def nav_terminal(solver: BaseSolver):
    solver.tap_nav_element("terminal")


@edge(Scene.NAVIGATION_BAR, Scene.RECRUIT_MAIN)
def nav_recruit(solver: BaseSolver):
    solver.tap_nav_element("recruit")


@edge(Scene.NAVIGATION_BAR, Scene.SHOP_OTHERS)
def nav_shop(solver: BaseSolver):
    solver.tap_nav_element("shop")


@edge(Scene.NAVIGATION_BAR, Scene.HEADHUNTING)
def nav_headhunting(solver: BaseSolver):
    solver.tap_nav_element("headhunting")


@edge(Scene.NAVIGATION_BAR, Scene.BUSINESS_CARD)
def nav_friend(solver: BaseSolver):
    solver.tap_nav_element("friend")


# 任务


@edge(Scene.MISSION_DAILY, Scene.MISSION_WEEKLY)
@edge(Scene.MISSION_TRAINEE, Scene.MISSION_WEEKLY)
def mission_to_weekly(solver: BaseSolver):
    solver.tap_element("mission_weekly")


@edge(Scene.MISSION_TRAINEE, Scene.MISSION_DAILY)
def mission_trainee_to_daily(solver: BaseSolver):
    solver.tap_element("mission_daily")


# 商店


@edge(Scene.SHOP_OTHERS, Scene.SHOP_CREDIT)
def shop_to_credit(solver: BaseSolver):
    solver.tap_element("shop_credit_2")


@edge(Scene.SHOP_CREDIT_CONFIRM, Scene.SHOP_CREDIT)
def shop_confirm(solver: BaseSolver):
    solver.back()


# 好友


@edge(Scene.BUSINESS_CARD, Scene.FRIEND_LIST)
def friend_list(solver: BaseSolver):
    solver.tap((194, 333))


@edge(Scene.FRIEND_LIST, Scene.BUSINESS_CARD)
def business_card(solver: BaseSolver):
    solver.tap((188, 198))


@edge(Scene.FRIEND_VISITING, Scene.BACK_TO_FRIEND_LIST)
def friend_visiting_back(solver: BaseSolver):
    solver.back()


@edge(Scene.BACK_TO_FRIEND_LIST, Scene.BUSINESS_CARD)
def back_to_friend_confirm(solver: BaseSolver):
    solver.tap_element("double_confirm/main", x_rate=1)


# 作战


@edge(Scene.TERMINAL_MAIN, Scene.TERMINAL_MAIN_THEME)
@edge(Scene.TERMINAL_COLLECTION, Scene.TERMINAL_MAIN_THEME)
@edge(Scene.TERMINAL_REGULAR, Scene.TERMINAL_MAIN_THEME)
@edge(Scene.TERMINAL_LONGTERM, Scene.TERMINAL_MAIN_THEME)
@edge(Scene.TERMINAL_PERIODIC, Scene.TERMINAL_MAIN_THEME)
def terminal_to_main_theme(solver: BaseSolver):
    solver.tap_terminal_button("main_theme")


@edge(Scene.OPERATOR_RECOVER_POTION, Scene.OPERATOR_BEFORE)
@edge(Scene.OPERATOR_RECOVER_ORIGINITE, Scene.OPERATOR_BEFORE)
@edge(Scene.OPERATOR_BEFORE, Scene.OPERATOR_CHOOSE_LEVEL)
@edge(Scene.OPERATOR_CHOOSE_LEVEL, Scene.TERMINAL_MAIN_THEME)
@edge(Scene.OPERATOR_CHOOSE_LEVEL, Scene.TERMINAL_COLLECTION)
@edge(Scene.OPERATOR_SUPPORT, Scene.OPERATOR_SELECT)
@edge(Scene.OPERATOR_STRANGER_SUPPORT, Scene.OPERATOR_SUPPORT)
@edge(Scene.OPERATOR_ELIMINATE_AGENCY, Scene.OPERATOR_ELIMINATE)
def operation_back(solver: BaseSolver):
    solver.back()


@edge(Scene.OPERATOR_GIVEUP, Scene.OPERATOR_FAILED)
def operation_give_up(solver: BaseSolver):
    solver.tap_element("double_confirm/main", x_rate=1)


@edge(Scene.OPERATOR_FINISH, Scene.OPERATOR_BEFORE)
@edge(Scene.OPERATOR_FAILED, Scene.OPERATOR_BEFORE)
def operation_finish(solver: BaseSolver):
    solver.tap((310, 330))


@edge(Scene.UPGRADE, Scene.OPERATOR_FINISH)
def upgrade(solver: BaseSolver):
    solver.tap((960, 540))


# 基建


@edge(Scene.INFRA_TODOLIST, Scene.INFRA_MAIN)
def todo_complete(solver: BaseSolver):
    solver.tap((1840, 140))


@edge(Scene.INFRA_CONFIDENTIAL, Scene.INFRA_MAIN)
@edge(Scene.INFRA_ARRANGE, Scene.INFRA_MAIN)
@edge(Scene.INFRA_DETAILS, Scene.INFRA_MAIN)
@edge(Scene.CTRLCENTER_ASSISTANT, Scene.INFRA_MAIN)
@edge(Scene.RIIC_OPERATOR_SELECT, Scene.INFRA_DETAILS)
@edge(Scene.CLUE_DAILY, Scene.INFRA_CONFIDENTIAL)
@edge(Scene.CLUE_RECEIVE, Scene.INFRA_CONFIDENTIAL)
@edge(Scene.CLUE_GIVE_AWAY, Scene.INFRA_CONFIDENTIAL)
@edge(Scene.CLUE_SUMMARY, Scene.INFRA_CONFIDENTIAL)
@edge(Scene.CLUE_PLACE, Scene.INFRA_CONFIDENTIAL)
@edge(Scene.ORDER_LIST, Scene.INFRA_DETAILS)
@edge(Scene.FACTORY_ROOMS, Scene.INFRA_DETAILS)
@edge(Scene.DRONE_ACCELERATE, Scene.ORDER_LIST)
@edge(Scene.FACTORY_FORMULA, Scene.FACTORY_DASHBOARD)
@edge(Scene.FACTORY_DASHBOARD, Scene.FACTORY_ROOM)
@edge(Scene.FACTORY_ROOM, Scene.INFRA_MAIN)
def infra_back(solver: BaseSolver):
    solver.back()


@edge(Scene.INFRA_ARRANGE_CONFIRM, Scene.INFRA_DETAILS)
def infra_arrange_confirm(solver: BaseSolver):
    solver.tap((1452, 1029))


@edge(Scene.INFRA_ARRANGE_ORDER, Scene.INFRA_DETAILS)
def infra_arrange_order(solver: BaseSolver):
    solver.tap_element("arrange_blue_yes", x_rate=0.66)


@edge(Scene.RIIC_REPORT, Scene.CTRLCENTER_ASSISTANT)
def riic_back(solver: BaseSolver):
    solver.tap((30, 55))


@edge(Scene.CTRLCENTER_ASSISTANT, Scene.RIIC_REPORT)
def riic(solver: BaseSolver):
    solver.tap_element("control_central_assistants")


@edge(Scene.INFRA_MAIN, Scene.CTRLCENTER_ASSISTANT)
def control_central(solver: BaseSolver):
    solver.tap_element("control_central")


# 公招


@edge(Scene.RECRUIT_AGENT, Scene.RECRUIT_MAIN)
def recruit_result(solver: BaseSolver):
    solver.tap((960, 540))


@edge(Scene.REFRESH_TAGS, Scene.RECRUIT_TAGS)
def refresh_cancel(solver: BaseSolver):
    solver.tap_element("double_confirm/main", x_rate=0)


@edge(Scene.RECRUIT_TAGS, Scene.RECRUIT_MAIN)
def recruit_back(solver: BaseSolver):
    solver.back()


@edge(Scene.SKIP, Scene.RECRUIT_AGENT)
def skip(solver: BaseSolver):
    solver.tap_element("skip")


# 其它场景


@edge(Scene.UNDEFINED, Scene.INDEX)
def get_scene(solver: BaseSolver):
    solver.scene()


@edge(Scene.LOGIN_START, Scene.LOGIN_QUICKLY)
def login_start(solver: BaseSolver):
    solver.tap((665, 741))


@edge(Scene.CONFIRM, Scene.LOGIN_START)
def confirm(solver: BaseSolver):
    solver.tap_element("confirm")


@edge(Scene.NETWORK_CHECK, Scene.LOGIN_START)
def network_check_cancel(solver: BaseSolver):
    solver.tap_element("confirm")


class SceneGraphSolver(BaseSolver):
    def scene_graph_navigation(self, scene: int):
        if scene not in DG.nodes:
            logger.error(f"{SceneComment[scene]}不在场景图中")
            return

        error_count = 0

        while (current := self.scene()) != scene:
            if current in self.waiting_scene:
                self.waiting_solver()
                continue

            if current not in DG.nodes:
                logger.debug(f"{SceneComment[current]}不在场景图中")
                self.sleep()

            try:
                sp = nx.shortest_path(DG, current, scene, weight="weight")
            except Exception as e:
                logger.exception(f"场景图路径计算异常：{e}")
                restart_simulator()
                self.device.client.check_server_alive()
                Session().connect(config.conf.adb)
                if config.conf.droidcast.enable:
                    self.device.start_droidcast()
                if config.conf.touch_method == "scrcpy":
                    self.device.control.scrcpy = Scrcpy(self.device.client)
                return

            logger.debug(sp)

            next_scene = sp[1]
            transition = DG.edges[current, next_scene]["transition"]

            try:
                transition(self)
                error_count = 0
            except MowerExit:
                raise
            except Exception as e:
                logger.exception(f"场景转移异常：{e}")
                if error_count <= 5:
                    self.sleep()
                    error_count += 1
                    continue
                if restart_simulator():
                    self.device.client.check_server_alive()
                    Session().connect(config.conf.adb)
                    if config.conf.droidcast.enable:
                        self.device.start_droidcast()
                    if config.conf.touch_method == "scrcpy":
                        self.device.control.scrcpy = Scrcpy(self.device.client)
                    self.check_current_focus()
                else:
                    self.restart_game()
                error_count = 0

    def back_to_index(self):
        logger.info("场景图导航：back_to_index")
        self.scene_graph_navigation(Scene.INDEX)

    def back_to_infrastructure(self):
        logger.info("场景图导航：back_to_infrastructure")
        self.scene_graph_navigation(Scene.INFRA_MAIN)
