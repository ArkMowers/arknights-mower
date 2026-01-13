from __future__ import annotations

import json
from pathlib import Path
from typing import Callable, Dict, List, Optional

Action = Callable[[], bool]
Checker = Callable[[], bool]


class NavNode:
    def __init__(self, name: str, checker: Checker, meta: Optional[dict] = None):
        self.name = name
        self.checker = checker
        # meta 用于附加信息，例如关卡类别/ID 等
        self.meta = meta or {}
        self.children: Dict[str, NavEdge] = {}
        self.parent: Optional[NavNode] = None


class NavEdge:
    def __init__(self, target: NavNode, action: Action):
        self.target = target
        self.action = action


class NavTrie:
    def __init__(self, root: NavNode):
        self.root = root

    def add_child(self, parent: NavNode, child: NavNode, action: Action) -> None:
        child.parent = parent
        parent.children[child.name] = NavEdge(child, action)

    def build_path_map(self) -> Dict[str, List[NavEdge]]:
        paths: Dict[str, List[NavEdge]] = {}

        def dfs(node: NavNode, path: List[NavEdge]) -> None:
            paths[node.name] = path
            for edge in node.children.values():
                dfs(edge.target, path + [edge])

        dfs(self.root, [])
        return paths


class Navigator:
    def __init__(self, trie: NavTrie, max_retry: int = 2):
        self.trie = trie
        self.max_retry = max_retry
        self.paths = trie.build_path_map()

    def navigate_to(self, target_name: str) -> bool:
        route = self.paths.get(target_name)
        if route is None:
            return False
        for edge in route:
            success = False
            for _ in range(self.max_retry):
                if edge.action() and edge.target.checker():
                    success = True
                    break
            if not success:
                return False
        return True


def sequence(*actions: Action) -> Action:
    def run() -> bool:
        for act in actions:
            if not act():
                return False
        return True

    return run


def retry(action: Action, times: int = 2) -> Action:
    def run() -> bool:
        for _ in range(times):
            if action():
                return True
        return False

    return run


def load_nav_trie(
    json_path: str | Path,
    action_registry: Dict[str, Action],
    checker_registry: Dict[str, Checker],
) -> NavTrie:
    """
    Load a navigation trie from JSON.

    JSON format:
    {
      "name": "home",
      "checker": "check_home",
      "children": {
        "terminal": {
          "action": "goto_terminal",
          "target": { ... nested node ... }
        }
      }
    }
    """

    def parse_node(data: dict) -> NavNode:
        name = data["name"]
        checker_name = data["checker"]
        if checker_name not in checker_registry:
            raise KeyError(f"checker '{checker_name}' not in registry")
        meta = data.get("meta")
        node = NavNode(name, checker_registry[checker_name], meta=meta)
        for child_key, child_data in data.get("children", {}).items():
            action_name = child_data["action"]
            if action_name not in action_registry:
                raise KeyError(f"action '{action_name}' not in registry")
            target_node = parse_node(child_data["target"])
            node.children[child_key] = NavEdge(
                target_node, action_registry[action_name]
            )
            target_node.parent = node
        return node

    raw = json.loads(Path(json_path).read_text(encoding="utf-8"))
    root = parse_node(raw["root"]) if "root" in raw else parse_node(raw)
    return NavTrie(root)
