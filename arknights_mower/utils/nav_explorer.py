"""
导航探索工具：
- 从 stage_data_full.json 建立关卡元数据映射（MAIN/ACTIVITY），忽略 DAILY。
- 示例导出基础 Trie JSON（总览为起点，可后续补充子节点）。
- NavExplorer：结合 SceneGraphSolver 与 NavTrie，按目标节点执行导航。

使用：
    python -m arknights_mower.utils.nav_explorer
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Callable, Dict, List

from arknights_mower.utils.graph import SceneGraphSolver
from arknights_mower.utils.nav_trie import Navigator, NavNode, NavTrie

STAGE_DATA_PATH = Path("arknights_mower/data/stage_data_full.json")
TRIE_OUTPUT_DIR = Path("arknights_mower/data/trie")
TRIE_OUTPUT_PATH = TRIE_OUTPUT_DIR / "nav_trie.json"

Action = Callable[[], bool]
Checker = Callable[[], bool]


# ----------------- 关卡元数据 -----------------
def build_stage_meta_map(path: Path = STAGE_DATA_PATH) -> Dict[str, dict]:
    """
    建立关卡 code -> meta 的映射，便于快速查询。
    忽略 stageType == DAILY。
    MAIN: zoneNameSecond 使用已有值，缺失则退回 name。
    ACTIVITY: zoneNameSecond 使用关卡名，保留 subTitle。
    """
    data: List[dict] = json.loads(path.read_text(encoding="utf-8"))
    meta_map: Dict[str, dict] = {}

    for rec in data:
        stage_type = rec.get("stageType")
        if stage_type == "DAILY":
            continue

        code = rec.get("id") or rec.get("code")
        if not code:
            continue

        meta = dict(rec)  # copy

        if stage_type == "MAIN":
            meta["zoneNameSecond"] = meta.get("zoneNameSecond") or meta.get("name")
        elif stage_type == "ACTIVITY":
            meta["zoneNameSecond"] = meta.get("name")
            meta["subTitle"] = meta.get("subTitle") or ""

        meta_map[code] = meta

    return meta_map


# ----------------- Trie 导出示例 -----------------
def export_nav_trie_json(output_path: Path = TRIE_OUTPUT_PATH) -> None:
    """
    导出一个基础的 Trie JSON（仅根节点，总览为起点），供后续扩展。
    动作/判定名称使用占位符，需在使用时通过注册表映射到实际实现。
    """
    root = NavNode("home", checker=lambda: False)
    trie = NavTrie(root)

    overview_node = NavNode("overview", checker=lambda: False)
    trie.add_child(root, overview_node, action=lambda: False)

    def node_to_dict(node: NavNode) -> dict:
        return {
            "name": node.name,
            "checker": "checker_placeholder",
            "meta": getattr(node, "meta", {}),
            "children": {
                child_name: {
                    "action": "action_placeholder",
                    "target": node_to_dict(edge.target),
                }
                for child_name, edge in node.children.items()
            },
        }

    TRIE_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps({"root": node_to_dict(root)}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"nav trie json exported to {output_path}")


# ----------------- Nav Explorer -----------------
class NavExplorer(SceneGraphSolver):
    """
    结合 SceneGraphSolver 与 NavTrie 的导航执行器。
    通过 action/checker 注册表将 JSON 中的名称映射到具体实现。
    """

    def __init__(
        self,
        device,
        recog,
        trie: NavTrie,
        action_registry: Dict[str, Action],
        checker_registry: Dict[str, Checker],
        max_retry: int = 2,
    ):
        super().__init__(device, recog)
        self.trie = trie
        self.action_registry = action_registry
        self.checker_registry = checker_registry
        self.max_retry = max_retry
        self.navigator = Navigator(trie, max_retry=max_retry)

    def bind_actions_checkers(self, node: NavNode) -> None:
        """递归将节点/边上的名称占位符替换为注册表中的实际 callable。"""
        # NavNode.checker 目前是占位 lambda; 在 JSON 里存的是名字，需要外部加载时替换
        # 此处假设已经构建好的 NavTrie 节点的 checker/action 是可调用对象
        for edge in node.children.values():
            self.bind_actions_checkers(edge.target)

    def navigate_to(self, target_name: str) -> bool:
        """
        入口：按目标节点名称导航。
        依赖 Navigator.match 已经持有可调用的 action/checker。
        """
        return self.navigator.navigate_to(target_name)


if __name__ == "__main__":
    meta = build_stage_meta_map()
    print(f"关卡元数据条目: {len(meta)}")
    export_nav_trie_json()
