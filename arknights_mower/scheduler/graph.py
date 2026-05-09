from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import networkx as nx

from arknights_mower.scheduler.scene import Scene


def build_default_graph() -> SceneGraph:
    g = SceneGraph()

    g.add_transition(Scene.INFRA_MAIN, Scene.INDEX, "back_to_index", 1)
    g.add_transition(Scene.MISSION_DAILY, Scene.INDEX, "back_to_index", 1)
    g.add_transition(Scene.MISSION_WEEKLY, Scene.INDEX, "back_to_index", 1)
    g.add_transition(Scene.MISSION_TRAINEE, Scene.INDEX, "back_to_index", 1)
    g.add_transition(Scene.BUSINESS_CARD, Scene.INDEX, "back_to_index", 1)
    g.add_transition(Scene.FRIEND_LIST, Scene.INDEX, "back_to_index", 1)
    g.add_transition(Scene.RECRUIT_MAIN, Scene.INDEX, "back_to_index", 1)
    g.add_transition(Scene.SHOP_OTHERS, Scene.INDEX, "back_to_index", 1)
    g.add_transition(Scene.SHOP_CREDIT, Scene.INDEX, "back_to_index", 1)
    g.add_transition(Scene.TERMINAL_MAIN, Scene.INDEX, "back_to_index", 1)
    g.add_transition(Scene.TERMINAL_MAIN_THEME, Scene.INDEX, "back_to_index", 1)
    g.add_transition(Scene.TERMINAL_EPISODE, Scene.INDEX, "back_to_index", 1)
    g.add_transition(Scene.TERMINAL_COLLECTION, Scene.INDEX, "back_to_index", 1)
    g.add_transition(Scene.TERMINAL_REGULAR, Scene.INDEX, "back_to_index", 1)
    g.add_transition(Scene.TERMINAL_LONGTERM, Scene.INDEX, "back_to_index", 1)
    g.add_transition(Scene.DEPOT, Scene.INDEX, "back_to_index", 1)
    g.add_transition(Scene.HEADHUNTING, Scene.INDEX, "back_to_index", 1)
    g.add_transition(Scene.MAIL, Scene.INDEX, "back_to_index", 1)

    g.add_transition(Scene.LEAVE_INFRASTRUCTURE, Scene.INDEX, "leave_infrastructure", 1)
    g.add_transition(Scene.DOWNLOAD_VOICE_RESOURCES, Scene.INDEX, "dont_download_voice", 1)
    g.add_transition(Scene.LOGIN_QUICKLY, Scene.INDEX, "login_quickly", 1)
    g.add_transition(Scene.LOGIN_CAPTCHA, Scene.INDEX, "login_captcha", 1)
    g.add_transition(Scene.LOGIN_BILIBILI, Scene.INDEX, "login_bilibili", 1)
    g.add_transition(Scene.LOGIN_BILIBILI_PRIVACY, Scene.INDEX, "login_bilibili", 1)
    g.add_transition(Scene.EXIT_GAME, Scene.INDEX, "exit_cancel", 1)
    g.add_transition(Scene.MATERIEL, Scene.INDEX, "materiel", 1)
    g.add_transition(Scene.ANNOUNCEMENT, Scene.INDEX, "announcement", 1)
    g.add_transition(Scene.AGREEMENT_UPDATE, Scene.INDEX, "agreement", 1)

    g.add_transition(Scene.INDEX, Scene.INFRA_MAIN, "index_to_infra", 5)
    g.add_transition(Scene.INDEX, Scene.BUSINESS_CARD, "index_to_friend", 5)
    g.add_transition(Scene.INDEX, Scene.MISSION_DAILY, "index_to_mission", 5)
    g.add_transition(Scene.INDEX, Scene.RECRUIT_MAIN, "index_to_recruit", 5)
    g.add_transition(Scene.INDEX, Scene.SHOP_OTHERS, "index_to_shop", 5)
    g.add_transition(Scene.INDEX, Scene.TERMINAL_MAIN, "index_to_terminal", 5)
    g.add_transition(Scene.INDEX, Scene.DEPOT, "index_to_depot", 5)
    g.add_transition(Scene.INDEX, Scene.MAIL, "index_to_mail", 5)
    g.add_transition(Scene.INDEX, Scene.HEADHUNTING, "index_to_headhunting", 5)

    g.add_transition(Scene.INFRA_MAIN, Scene.NAVIGATION_BAR, "index_nav", 1)
    g.add_transition(Scene.RECRUIT_MAIN, Scene.NAVIGATION_BAR, "index_nav", 1)
    g.add_transition(Scene.RECRUIT_TAGS, Scene.NAVIGATION_BAR, "index_nav", 1)
    g.add_transition(Scene.MISSION_DAILY, Scene.NAVIGATION_BAR, "index_nav", 1)
    g.add_transition(Scene.MISSION_WEEKLY, Scene.NAVIGATION_BAR, "index_nav", 1)
    g.add_transition(Scene.MISSION_TRAINEE, Scene.NAVIGATION_BAR, "index_nav", 1)
    g.add_transition(Scene.BUSINESS_CARD, Scene.NAVIGATION_BAR, "index_nav", 1)
    g.add_transition(Scene.FRIEND_LIST, Scene.NAVIGATION_BAR, "index_nav", 1)
    g.add_transition(Scene.SHOP_OTHERS, Scene.NAVIGATION_BAR, "index_nav", 1)
    g.add_transition(Scene.SHOP_CREDIT, Scene.NAVIGATION_BAR, "index_nav", 1)
    g.add_transition(Scene.TERMINAL_MAIN, Scene.NAVIGATION_BAR, "index_nav", 1)
    g.add_transition(Scene.TERMINAL_MAIN_THEME, Scene.NAVIGATION_BAR, "index_nav", 1)
    g.add_transition(Scene.TERMINAL_EPISODE, Scene.NAVIGATION_BAR, "index_nav", 1)
    g.add_transition(Scene.TERMINAL_COLLECTION, Scene.NAVIGATION_BAR, "index_nav", 1)
    g.add_transition(Scene.TERMINAL_REGULAR, Scene.NAVIGATION_BAR, "index_nav", 1)
    g.add_transition(Scene.TERMINAL_LONGTERM, Scene.NAVIGATION_BAR, "index_nav", 1)
    g.add_transition(Scene.TERMINAL_PERIODIC, Scene.NAVIGATION_BAR, "index_nav", 1)
    g.add_transition(Scene.OPERATOR_CHOOSE_LEVEL, Scene.NAVIGATION_BAR, "index_nav", 1)
    g.add_transition(Scene.OPERATOR_BEFORE, Scene.NAVIGATION_BAR, "index_nav", 1)
    g.add_transition(Scene.OPERATOR_SELECT, Scene.NAVIGATION_BAR, "index_nav", 1)
    g.add_transition(Scene.OPERATOR_SUPPORT, Scene.NAVIGATION_BAR, "index_nav", 1)
    g.add_transition(Scene.INFRA_TODOLIST, Scene.NAVIGATION_BAR, "index_nav", 1)
    g.add_transition(Scene.INFRA_CONFIDENTIAL, Scene.NAVIGATION_BAR, "index_nav", 1)
    g.add_transition(Scene.INFRA_ARRANGE, Scene.NAVIGATION_BAR, "index_nav", 1)
    g.add_transition(Scene.INFRA_DETAILS, Scene.NAVIGATION_BAR, "index_nav", 1)
    g.add_transition(Scene.CTRLCENTER_ASSISTANT, Scene.NAVIGATION_BAR, "index_nav", 1)
    g.add_transition(Scene.CLUE_DAILY, Scene.NAVIGATION_BAR, "index_nav", 1)
    g.add_transition(Scene.CLUE_RECEIVE, Scene.NAVIGATION_BAR, "index_nav", 1)
    g.add_transition(Scene.CLUE_PLACE, Scene.NAVIGATION_BAR, "index_nav", 1)
    g.add_transition(Scene.ORDER_LIST, Scene.NAVIGATION_BAR, "index_nav", 1)
    g.add_transition(Scene.FACTORY_ROOMS, Scene.NAVIGATION_BAR, "index_nav", 1)
    g.add_transition(Scene.OPERATOR_ELIMINATE, Scene.NAVIGATION_BAR, "index_nav", 1)
    g.add_transition(Scene.DEPOT, Scene.NAVIGATION_BAR, "index_nav", 1)
    g.add_transition(Scene.FRIEND_VISITING, Scene.NAVIGATION_BAR, "index_nav", 1)
    g.add_transition(Scene.HEADHUNTING, Scene.NAVIGATION_BAR, "index_nav", 1)

    g.add_transition(Scene.NAVIGATION_BAR, Scene.MISSION_DAILY, "nav_mission", 1)
    g.add_transition(Scene.NAVIGATION_BAR, Scene.INDEX, "nav_index", 1)
    g.add_transition(Scene.NAVIGATION_BAR, Scene.TERMINAL_MAIN, "nav_terminal", 1)
    g.add_transition(Scene.NAVIGATION_BAR, Scene.RECRUIT_MAIN, "nav_recruit", 1)
    g.add_transition(Scene.NAVIGATION_BAR, Scene.SHOP_OTHERS, "nav_shop", 1)
    g.add_transition(Scene.NAVIGATION_BAR, Scene.HEADHUNTING, "nav_headhunting", 1)
    g.add_transition(Scene.NAVIGATION_BAR, Scene.BUSINESS_CARD, "nav_friend", 1)

    g.add_transition(Scene.MISSION_DAILY, Scene.MISSION_WEEKLY, "mission_to_weekly", 1)
    g.add_transition(Scene.MISSION_TRAINEE, Scene.MISSION_WEEKLY, "mission_to_weekly", 1)
    g.add_transition(Scene.MISSION_TRAINEE, Scene.MISSION_DAILY, "mission_trainee_to_daily", 1)

    g.add_transition(Scene.SHOP_OTHERS, Scene.SHOP_CREDIT, "shop_to_credit", 1)
    g.add_transition(Scene.SHOP_CREDIT_CONFIRM, Scene.SHOP_CREDIT, "shop_confirm", 1)

    g.add_transition(Scene.BUSINESS_CARD, Scene.FRIEND_LIST, "friend_list", 1)
    g.add_transition(Scene.FRIEND_LIST, Scene.BUSINESS_CARD, "business_card", 1)
    g.add_transition(Scene.FRIEND_VISITING, Scene.BACK_TO_FRIEND_LIST, "friend_visiting_back", 1)
    g.add_transition(Scene.BACK_TO_FRIEND_LIST, Scene.BUSINESS_CARD, "back_to_friend_confirm", 1)

    g.add_transition(Scene.TERMINAL_MAIN, Scene.TERMINAL_MAIN_THEME, "terminal_to_main_theme", 1)
    g.add_transition(Scene.TERMINAL_COLLECTION, Scene.TERMINAL_MAIN_THEME, "terminal_to_main_theme", 1)
    g.add_transition(Scene.TERMINAL_REGULAR, Scene.TERMINAL_MAIN_THEME, "terminal_to_main_theme", 1)
    g.add_transition(Scene.TERMINAL_LONGTERM, Scene.TERMINAL_MAIN_THEME, "terminal_to_main_theme", 1)
    g.add_transition(Scene.TERMINAL_PERIODIC, Scene.TERMINAL_MAIN_THEME, "terminal_to_main_theme", 1)

    g.add_transition(Scene.OPERATOR_RECOVER_POTION, Scene.OPERATOR_BEFORE, "operation_back", 1)
    g.add_transition(Scene.OPERATOR_RECOVER_ORIGINITE, Scene.OPERATOR_BEFORE, "operation_back", 1)
    g.add_transition(Scene.OPERATOR_BEFORE, Scene.OPERATOR_CHOOSE_LEVEL, "operation_back", 1)
    g.add_transition(Scene.OPERATOR_CHOOSE_LEVEL, Scene.TERMINAL_MAIN_THEME, "operation_back", 1)
    g.add_transition(Scene.OPERATOR_CHOOSE_LEVEL, Scene.TERMINAL_COLLECTION, "operation_back", 1)
    g.add_transition(Scene.OPERATOR_SUPPORT, Scene.OPERATOR_SELECT, "operation_back", 1)
    g.add_transition(Scene.OPERATOR_STRANGER_SUPPORT, Scene.OPERATOR_SUPPORT, "operation_back", 1)
    g.add_transition(Scene.OPERATOR_ELIMINATE_AGENCY, Scene.OPERATOR_ELIMINATE, "operation_back", 1)

    g.add_transition(Scene.OPERATOR_GIVEUP, Scene.OPERATOR_FAILED, "operation_give_up", 1)
    g.add_transition(Scene.OPERATOR_FINISH, Scene.OPERATOR_BEFORE, "operation_finish", 1)
    g.add_transition(Scene.OPERATOR_FAILED, Scene.OPERATOR_BEFORE, "operation_finish", 1)
    g.add_transition(Scene.UPGRADE, Scene.OPERATOR_FINISH, "upgrade", 1)

    g.add_transition(Scene.INFRA_TODOLIST, Scene.INFRA_MAIN, "todo_complete", 1)

    g.add_transition(Scene.INFRA_CONFIDENTIAL, Scene.INFRA_MAIN, "infra_back", 1)
    g.add_transition(Scene.INFRA_ARRANGE, Scene.INFRA_MAIN, "infra_back", 1)
    g.add_transition(Scene.INFRA_DETAILS, Scene.INFRA_MAIN, "infra_back", 1)
    g.add_transition(Scene.CTRLCENTER_ASSISTANT, Scene.INFRA_MAIN, "infra_back", 1)
    g.add_transition(Scene.RIIC_OPERATOR_SELECT, Scene.INFRA_DETAILS, "infra_back", 1)
    g.add_transition(Scene.CLUE_DAILY, Scene.INFRA_CONFIDENTIAL, "infra_back", 1)
    g.add_transition(Scene.CLUE_RECEIVE, Scene.INFRA_CONFIDENTIAL, "infra_back", 1)
    g.add_transition(Scene.CLUE_GIVE_AWAY, Scene.INFRA_CONFIDENTIAL, "infra_back", 1)
    g.add_transition(Scene.CLUE_SUMMARY, Scene.INFRA_CONFIDENTIAL, "infra_back", 1)
    g.add_transition(Scene.CLUE_PLACE, Scene.INFRA_CONFIDENTIAL, "infra_back", 1)
    g.add_transition(Scene.INFRA_ARRANGE_ORDER, Scene.INFRA_DETAILS, "infra_back", 1)
    g.add_transition(Scene.ORDER_LIST, Scene.INFRA_DETAILS, "infra_back", 1)
    g.add_transition(Scene.FACTORY_ROOMS, Scene.INFRA_DETAILS, "infra_back", 1)
    g.add_transition(Scene.DRONE_ACCELERATE, Scene.ORDER_LIST, "infra_back", 1)
    g.add_transition(Scene.FACTORY_DASHBOARD, Scene.FACTORY_ROOM, "infra_back", 1)

    g.add_transition(Scene.INFRA_ARRANGE_CONFIRM, Scene.INFRA_DETAILS, "infra_arrange_confirm", 1)

    g.add_transition(Scene.RIIC_REPORT, Scene.CTRLCENTER_ASSISTANT, "riic_back", 1)
    g.add_transition(Scene.CTRLCENTER_ASSISTANT, Scene.RIIC_REPORT, "riic", 1)
    g.add_transition(Scene.INFRA_MAIN, Scene.CTRLCENTER_ASSISTANT, "control_central", 1)

    g.add_transition(Scene.RECRUIT_AGENT, Scene.RECRUIT_MAIN, "recruit_result", 1)
    g.add_transition(Scene.REFRESH_TAGS, Scene.RECRUIT_TAGS, "refresh_cancel", 1)
    g.add_transition(Scene.RECRUIT_TAGS, Scene.RECRUIT_MAIN, "recruit_back", 1)
    g.add_transition(Scene.SKIP, Scene.RECRUIT_AGENT, "skip", 1)

    g.add_transition(Scene.UNDEFINED, Scene.INDEX, "get_scene", 1)

    g.add_transition(Scene.LOGIN_START, Scene.LOGIN_QUICKLY, "login_start", 1)
    g.add_transition(Scene.CONFIRM, Scene.LOGIN_START, "confirm", 1)
    g.add_transition(Scene.NETWORK_CHECK, Scene.LOGIN_START, "network_check_cancel", 1)

    g.add_transition(Scene.LOGIN_MAIN_NOENTRY, Scene.INDEX, "login_main_noentry", 1)

    return g


@dataclass
class SceneTransition:
    target: Scene
    action: str
    weight: float = 1.0


class SceneGraph:
    def __init__(self) -> None:
        self._graph: nx.DiGraph = nx.DiGraph()

    def add_transition(
        self,
        from_scene: Scene,
        to_scene: Scene,
        action: str,
        weight: float = 1.0,
    ) -> None:
        self._graph.add_edge(from_scene, to_scene, action=action, weight=weight)

    def find_path(
        self, current: Scene, target: Scene
    ) -> Optional[list[SceneTransition]]:
        try:
            sp = nx.shortest_path(self._graph, current, target, weight="weight")
        except (nx.NetworkXNoPath, nx.NodeNotFound):
            return None
        result = []
        for i in range(len(sp) - 1):
            edge = self._graph.edges[sp[i], sp[i + 1]]
            result.append(SceneTransition(sp[i + 1], edge["action"], edge["weight"]))
        return result

    def can_reach(self, current: Scene, target: Scene) -> bool:
        return self.find_path(current, target) is not None

    def transition(
        self, from_scene: Scene, to_scene: Scene, weight: float = 1.0
    ):
        def decorator(action_fn):
            name = action_fn.__name__
            if name.startswith("_action_"):
                name = name[8:]
            self.add_transition(from_scene, to_scene, name, weight)
            return action_fn

        return decorator
