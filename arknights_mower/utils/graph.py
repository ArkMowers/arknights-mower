import functools

import networkx as nx

from arknights_mower.utils.scene import Scene
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


@edge(Scene.INFRA_MAIN, Scene.INDEX, interval=3)
@edge(Scene.MISSION_DAILY, Scene.INDEX, interval=3)
@edge(Scene.MISSION_WEEKLY, Scene.INDEX, interval=3)
@edge(Scene.MISSION_TRAINEE, Scene.INDEX, interval=3)
@edge(Scene.FRIEND_LIST_OFF, Scene.INDEX, interval=3)
@edge(Scene.FRIEND_LIST_ON, Scene.INDEX, interval=3)
@edge(Scene.RECRUIT_MAIN, Scene.INDEX, interval=3)
@edge(Scene.SHOP_OTHERS, Scene.INDEX, interval=3)
@edge(Scene.SHOP_CREDIT, Scene.INDEX, interval=3)
def back_to_index(solver: BaseSolver):
    solver.back()


@edge(Scene.INDEX, Scene.INFRA_MAIN, interval=3)
def index_to_infra(solver: BaseSolver):
    solver.tap_index_element("infrastructure")


@edge(Scene.INDEX, Scene.FRIEND_LIST_OFF, interval=3)
def index_to_friend(solver: BaseSolver):
    solver.tap_index_element("friend")


@edge(Scene.INDEX, Scene.MISSION_DAILY, interval=3)
@edge(Scene.INDEX, Scene.MISSION_TRAINEE, interval=3)
def index_to_mission(solver: BaseSolver):
    solver.tap_index_element("mission")


@edge(Scene.INDEX, Scene.RECRUIT_MAIN, interval=3)
def index_to_recruit(solver: BaseSolver):
    solver.tap_index_element("recruit")


@edge(Scene.INDEX, Scene.SHOP_OTHERS, interval=3)
def index_to_shop(solver: BaseSolver):
    solver.tap_index_element("shop")


@edge(Scene.INDEX, Scene.TERMINAL_MAIN, interval=3)
def index_to_terminal(solver: BaseSolver):
    solver.tap_index_element("terminal")


# 导航栏


@edge(Scene.INFRA_MAIN, Scene.NAVIGATION_BAR)
@edge(Scene.RECRUIT_MAIN, Scene.NAVIGATION_BAR)
@edge(Scene.MISSION_DAILY, Scene.NAVIGATION_BAR)
@edge(Scene.MISSION_WEEKLY, Scene.NAVIGATION_BAR)
@edge(Scene.MISSION_TRAINEE, Scene.NAVIGATION_BAR)
@edge(Scene.FRIEND_LIST_OFF, Scene.NAVIGATION_BAR)
@edge(Scene.FRIEND_LIST_ON, Scene.NAVIGATION_BAR)
@edge(Scene.SHOP_OTHERS, Scene.NAVIGATION_BAR)
@edge(Scene.SHOP_CREDIT, Scene.NAVIGATION_BAR)
def index_nav(solver: BaseSolver):
    solver.tap_element("nav_button")


@edge(Scene.NAVIGATION_BAR, Scene.MISSION_DAILY)
@edge(Scene.NAVIGATION_BAR, Scene.MISSION_TRAINEE)
def nav_mission(solver: BaseSolver):
    solver.tap_element("nav_mission")


@edge(Scene.NAVIGATION_BAR, Scene.INDEX)
def nav_index(solver: BaseSolver):
    solver.tap_element("nav_index")


@edge(Scene.NAVIGATION_BAR, Scene.TERMINAL_MAIN)
def nav_terminal(solver: BaseSolver):
    solver.tap_element("nav_terminal")


@edge(Scene.NAVIGATION_BAR, Scene.RECRUIT_MAIN)
def nav_recruit(solver: BaseSolver):
    solver.tap_element("nav_recruit")


@edge(Scene.NAVIGATION_BAR, Scene.SHOP_OTHERS)
def nav_shop(solver: BaseSolver):
    solver.tap_element("nav_shop")


@edge(Scene.NAVIGATION_BAR, Scene.INFRA_MAIN)
def nav_infrastructure(solver: BaseSolver):
    solver.tap_element("nav_infrastructure")


# 任务


@edge(Scene.MISSION_DAILY, Scene.MISSION_WEEKLY)
@edge(Scene.MISSION_TRAINEE, Scene.MISSION_WEEKLY)
def mission_to_weekly(solver: BaseSolver):
    solver.tap_element("mission_weekly")


# 商店


@edge(Scene.SHOP_OTHERS, Scene.SHOP_CREDIT)
def shop_to_credit(solver: BaseSolver):
    solver.tap_element("shop_credit_2")


# 好友


@edge(Scene.FRIEND_LIST_OFF, Scene.FRIEND_LIST_ON)
def friend_list_on(solver: BaseSolver):
    solver.tap_element("friend_list")
