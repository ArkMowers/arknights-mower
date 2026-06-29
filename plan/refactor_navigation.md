# navigation.py 重构计划

## 现状问题

`NavigationSolver` 一个类做了 4 件事，互相耦合：

```
NavigationSolver (1149 行)
├── A) 步骤录制/回放/持久化      散落在 10+ 个函数中
├── B) BFS 导航决策              transition() + try_activity_entry() + 3 个 builder
├── C) OCR/图片匹配工具集        10 个工具函数
└── D) 日志/异常处理             logger.debug 占 ~40% 行数
```

此外，`nav_trie.py`（129 行）和 `nav_explorer.py`（136 行）是废弃的另一个方案，与当前系统无关。

---

## 目标架构

```
navigation/
├── __init__.py              # 导出 NavigationSolver（兼容旧 import）
├── solver.py                # NavigationSolver（瘦身版，只做状态机调度）
├── recorder.py              # 步骤录制、回放、持久化
├── bfs.py                   # BFS 导航器（非 LLM）
├── llm_bfs.py               # LLM 导航器（UNKNOWN 类型）
├── ocr.py                   # OCR 候选收集 + 图片匹配 + 排序
└── tools.py                 # 小工具函数（is_stage_code, normalize 等）
```

---

## 详细拆解

### 文件 1: `navigation/tools.py` — 纯工具函数

从原 `NavigationSolver` 中剥离**无状态**的静态方法/类方法。

| 原方法 | 目标 | 说明 |
|--------|------|------|
| `is_stage_code(text)` | 独立函数 | 正则 `^[A-Z0-9]+(?:-[A-Z0-9]+)+$`，不依赖 self |
| `normalize_stage_text(text)` | 独立函数 | `text.strip().upper()` |
| `stage_pattern_stem(text)` | 独立函数 | `"1-7" → "1-"`, `"EP-EX-3" → "EP-EX-"` |
| `stage_pattern_key(name)` | 独立函数 | `"1-7" → "1-*"` |
| `ocr_signature(candidates)` | 独立函数 | 候选文本的频次签名，用于判重 |

```python
# navigation/tools.py — 约 30 行
import re

def is_stage_code(text: str) -> bool:
    return bool(re.match(r"^[A-Z0-9]+(?:-[A-Z0-9]+)+$", normalize_stage_text(text)))

def normalize_stage_text(text: str) -> str:
    return text.strip().upper() if isinstance(text, str) else ""

def stage_pattern_stem(text: str) -> str:
    norm = normalize_stage_text(text)
    head, _, _ = norm.rpartition("-")
    return f"{head}-"

def stage_pattern_key(name: str) -> str | None:
    return f"{stage_pattern_stem(name)}*" if is_stage_code(name) else None

def ocr_signature(candidates: list[dict]) -> tuple[str, ...]:
    counter = {}
    for c in candidates:
        text = normalize_stage_text(c.get("text", ""))
        if text:
            counter[text] = counter.get(text, 0) + 1
    return tuple(f"{k}:{v}" for k, v in sorted(counter.items()))
```

---

### 文件 2: `navigation/ocr.py` — OCR + 图片匹配

从原 `NavigationSolver` 中剥离所有**识别相关**方法。

| 原方法 | 新方法 | 改动 |
|--------|--------|------|
| `collect_terminal_ocr_candidates()` | `collect_ocr_candidates(recog, scene)` | 纯函数，参数化 scene |
| `find_stage_banner(zone_name)` | `StageMatcher.find_banner(recog, zone_name)` | 独立类管理自适应缩放 hint |
| `find_zone_candidate_with_swipe()` | `ZoneFinder.find(device, recog, zone_name)` | 独立类，封装 swipe 逻辑 |
| `rank_activity_candidates()` | `ActivityRanker.rank(candidates, target)` | 独立类，LLM + 规则混合排序 |
| (无) | `StageSwiper` 类 | 横向滑动找目标关卡的逻辑，从 find_target_stage_after_entry 中提取 |

```python
# navigation/ocr.py — 约 200 行

@dataclass
class OCRCandidate:
    text: str
    center: tuple[int, int]
    score: float

class StageMatcher:
    """模板匹配 zone banner（如 黑暗时代·上.png），带自适应缩放"""
    _scale_hint: dict[str, float] = {}

    def find_banner(self, recog, zone_name: str) -> tuple[tuple[int,int],float] | None

class ZoneFinder:
    """OCR 搜索 zone，带左右滑动"""

    def find(self, device, recog, zone_name: str, max_swipes: int = 2) -> OCRCandidate | None

class ActivityRanker:
    """LLM + 规则混合排序 OCR 候选"""

    def __init__(self, name: str, stage_meta: dict, ai_key: str)
    def rank(self, candidates: list[OCRCandidate], top_k: int = 3) -> list[OCRCandidate]

class StageSwiper:
    """在进入 zone 后的关卡列表中，横向滑动找到目标关卡"""

    def find(
        self, device, recog, target: str, max_swipes: int = 6, pattern_only: bool = False
    ) -> bool
```

---

### 文件 3: `navigation/recorder.py` — 步骤录制 / 回放 / 持久化

把原 `NavigationSolver` 中所有步骤记录相关的逻辑**收拢到一个类**。

```python
# navigation/recorder.py — 约 100 行

@dataclass
class NavStep:
    action: str          # "tap" | "swipe"
    payload: dict

class NavigationRecorder:
    """
    职责：记录 → 持久化 → 回放
    不关心导航决策，只关心步骤的存取。
    """

    def __init__(self, device, recog, stage_id: str, stage_type: str):
        self.device = device
        self.recog = recog
        self.stage_id = stage_id
        self.stage_type = stage_type
        self.steps: list[NavStep] = []
        self._suppressed = False      # 快速入口等场景不记录

    # --- 录制 ---
    def record(self, action: str, **payload):
        if not self._suppressed:
            self.steps.append(NavStep(action, payload))

    def suppress(self):  ...          # 上下文管理器，临时关闭录制
    def mark_route_success(self): ...
    def clear(self):     ...

    # --- 持久化 ---
    def save(self) -> bool            # 写入 nav_trie_steps.json
    def load(self) -> list[NavStep]   # 读取，支持精确匹配 + pattern 回退

    # --- 回放 ---
    def replay(self) -> bool          # 依次执行 tap/swipe，成功后返回 True
    def replay_and_verify(self, verifier) -> bool
```

#### 原方法迁移对照

| 原方法 | 目标 | 说明 |
|--------|------|------|
| `record_nav_step(action, **payload)` | `recorder.record(action, **payload)` | 1:1 迁移 |
| `_suppress_nav_recording` | `recorder.suppress()` | 用上下文管理器 |
| `nav_route_success` | `recorder.mark_route_success()` | |
| `persist_nav_steps()` | `recorder.save()` | 只写 JSON，不含 nav_route_success 判断 |
| `load_nav_steps_data()` | `recorder._load_raw()` | 私有方法 |
| `get_replay_steps()` | `recorder.load()` | 返回 list[NavStep] |
| `try_replay_nav_steps()` | `recorder.replay()` | 纯回放 + verify |
| `nav_steps` (list) | `recorder.steps` | |

---

### 文件 4: `navigation/bfs.py` — BFS 导航器（非 LLM）

处理 `stageType in {"MAIN", "ACTIVITY", "DAILY"}` 的导航。

```python
# navigation/bfs.py — 约 120 行

class BFSNavigator:
    """
    职责：探索从 TERMINAL_MAIN 到目标 zone → 关卡 的步骤。
    返回 list[NavStep]，不负责保存。
    """

    def __init__(self, device, recog, recorder: NavigationRecorder):
        ...

    def navigate(self, name: str, stage_meta: dict) -> bool:
        """
        主入口：
        1. OCR 尝试快速入口
        2. 回放历史步骤（recorder.replay()）
        3. 在线构建
        """
        ...

    def _build_daily(self, zone: str) -> bool     # 从 DAILY 原 build_daily_nav_steps
    def _build_main(self, zone: str) -> bool       # 从 build_activity_or_main_nav_steps
    def _build_activity(self, zone: str, subtitle: str | None) -> bool

    def _open_overview(self) -> bool               # 从 open_activity_overview_until_ready
    def _enter_zone(self, zone: str) -> bool        # 从 find_stage_image_and_enter
    def _click_subtitle(self, subtitle: str | None) # 从 click_subtitle_if_needed
    def _locate_stage(self, target: str) -> bool     # 从 find_target_stage_after_entry 的精简版
```

#### 原方法迁移对照

| 原方法 | 目标 | 说明 |
|--------|------|------|
| `build_daily_nav_steps()` | `_build_daily()` | 1:1 迁移 |
| `build_activity_or_main_nav_steps()` | `_build_main()` / `_build_activity()` | 拆成两个 |
| `open_activity_overview_until_ready()` | `_open_overview()` | 简化，去掉 python 化命名 |
| `find_stage_image_and_enter()` | `_enter_zone()` | 1:1 |
| `click_subtitle_if_needed()` | `_click_subtitle()` | |

---

### 文件 5: `navigation/llm_bfs.py` — LLM 导航器

处理 `stageType == "UNKNOWN"` 或 `endTs` 进行中的活动。

```python
# navigation/llm_bfs.py — 约 80 行

class LLMBFSNavigator:
    """
    职责：对于未知类型的关卡，用 OCR + LLM 排序做 BFS 探索。
    BFS 两层：MAIN 入口 → subtitle 入口
    """

    def __init__(self, device, recog, recorder: NavigationRecorder, ranker: ActivityRanker):
        ...

    def navigate(self, name: str, stage_meta: dict, max_attempts: int = 9) -> bool:
        """
        BFS 主循环：
        for each MAIN candidate (LLM ranked):
            tap → detect page change
            if stage found: return True
            for each subtitle candidate (LLM ranked):
                tap → detect page change
                if stage found: return True
                back
            back to TERMINAL_MAIN
        """
        ...
```

当前 `build_unknown_nav_steps_via_llm` 的 118 行可以简化为约 80 行，把**去重**（`failed_main_attempts`、`failed_sub_attempts`）、**OCR签名**、**回退逻辑** 用独立的小方法提取：

```python
def navigate(self, name, stage_meta, max_attempts=9) -> bool:
    if not self._back_to_terminal():
        return False

    candidates = collect_ocr_candidates(self.recog, Scene.TERMINAL_MAIN)
    main_ranked = self.ranker.rank(candidates, top_k=max_attempts)
    main_sig = ocr_signature(candidates)
    failed_main: set = set()
    failed_sub: set = set()

    for cand in main_ranked:
        key = (main_sig, normalize_stage_text(cand.text))
        if key in failed_main:
            continue
        checkpoint = len(self.recorder.steps)

        if not self._try_enter(cand):    # tap + detect page move
            failed_main.add(key)
            continue

        if self._try_locate_stage(name):  # 直接命中
            return True

        ok = self._explore_sub(cand, name, max_attempts, main_sig, failed_main, failed_sub)
        if ok:
            return True

        # 还原 + 回 MAIN
        self._rollback(checkpoint, failed_main, key)
    return False

def _explore_sub(self, parent_cand, name, max_attempts, main_sig, failed_main, failed_sub) -> bool:
    sub_candidates = collect_ocr_candidates(self.recog)
    sub_ranked = self.ranker.rank(sub_candidates, top_k=max_attempts)
    sub_sig = ocr_signature(sub_candidates)

    for sub in sub_ranked:
        sub_key = (main_sig, sub_sig, normalize_stage_text(sub.text))
        if sub_key in failed_sub:
            continue
        checkpoint = len(self.recorder.steps)

        if not self._try_enter(sub):
            failed_sub.add(sub_key)
            continue

        if self._try_locate_stage(name):
            return True

        # 回退
        self.recorder.steps = self.recorder.steps[:checkpoint]
        failed_sub.add(sub_key)
        self.back()
        if self.scene() == Scene.TERMINAL_MAIN:
            failed_main.add((main_sig, normalize_stage_text(parent_cand.text)))
            return False
    return False
```

---

### 文件 6: `navigation/solver.py` — 瘦身版 NavigationSolver

只做**调度**和**状态机**，不直接操作 OCR/录制/BFS。

```python
# navigation/solver.py — 约 100 行

class NavigationSolver(SceneGraphSolver, BaseMixin):
    """
    精简后的导航调度器：
    - run()  → 查元数据 → 去 TERMINAL_MAIN → 尝试 上次作战 OCR
             → 委托给 BFSNavigator / LLMBFSNavigator
    - transition() → 状态机，只保留场景路由
    """

    def run(self, name: str) -> bool:
        self.name = name
        self.stage_meta = lookup_stage(name)        # 查 stage_data_full.json
        self.stageType = self.stage_meta.get("stageType") if self.stage_meta else "UNKNOWN"
        self.recorder = NavigationRecorder(self.device, self.recog, name, self.stageType)
        self.bfs = BFSNavigator(self.device, self.recog, self.recorder)
        self.llm_bfs = LLMBFSNavigator(...)

        self.scene_graph_navigation(Scene.TERMINAL_MAIN)
        self._try_last_battle_ocr()                  # 快速入口

        if not self._try_activity_entry():            # BFS/LLM 导航
            return False

        if self.success and self.recorder.steps:
            self.recorder.save()
        return self.success

    def transition(self):
        """只保留场景路由，去掉所有 OCR/录制逻辑"""
        scene = self.scene()
        if scene == Scene.TERMINAL_MAIN:
            if self.name == "Annihilation":
                return self.enter_annihilation_from_terminal_main()
            # 状态机只负责切 tab，不负责找关卡
            if self.stageType == "MAIN" or (self.stageType == "ACTIVITY" and ...):
                self.tap_terminal_button("main_theme")
            elif self.stageType == "DAILY":
                self.tap_terminal_button("collection")
            else:
                return self.success
        elif scene == Scene.OPERATOR_ELIMINATE:
            ...   # 与 annihilation 相关
        elif scene in self.waiting_scene:
            self.waiting_solver()
        elif scene in (Scene.OPERATOR_CHOOSE_LEVEL, Scene.OPERATOR_BEFORE):
            return self.success    # BFS 已经处理完了
        else:
            self.scene_graph_navigation(Scene.TERMINAL_MAIN)

    def _try_last_battle_ocr(self) -> bool:
        """快速入口：检查右下角"上次作战"是否匹配"""
```

> `_try_activity_entry()` → `BFSNavigator.navigate()` 或 `LLMBFSNavigator.navigate()`
>
> `transition()` 在导航成功后会被持续调用，此时 BFS 已经完成了所有操作，`transition()` 只需返回 `self.success` 防止重复操作。

---

### 原 navigation.py 中无迁移的方法

以下方法太耦合于具体业务，不适合分层，保留在 `NavigationSolver` 中：

| 方法 | 保留理由 |
|------|---------|
| `enter_annihilation_from_terminal_main()` | 特殊逻辑，仅 annihilation 用 |
| `_activity_end_ts()` | 元数据查询 |
| `should_use_llm_navigation()` | 决策用 |
| `back_to_terminal_main()` | 通用工具 |
| `tap_and_detect_page_move()` | 在 `BaseMixin` 中已有？确认是否需要 |
| `wait_for_scene_stable()` | 继承自 BaseSolver |
| `auto_generate_nav_trie_steps()` | 批量生成工具 |

---

## 删除废弃文件

```
arknights_mower/utils/nav_trie.py         → 删除
arknights_mower/utils/nav_explorer.py     → 删除
arknights_mower/utils/nav_trie_steps.json → 保留（已有数据）
```

---

## 迁移步骤

```
Step 1: 创建 navigation/ 包，建空文件
Step 2: 写 navigation/tools.py（无状态函数，+测试）
Step 3: 写 navigation/ocr.py（StageMatcher, ZoneFinder, ActivityRanker, StageSwiper）
Step 4: 写 navigation/recorder.py（NavigationRecorder）
Step 5: 写 navigation/bfs.py（BFSNavigator）+ navigation/llm_bfs.py（LLMBFSNavigator）
Step 6: 重写 navigation/solver.py（瘦身版 NavigationSolver）
Step 7: navigation/__init__.py 导出 NavigationSolver
Step 8: 删除 nav_trie.py、nav_explorer.py
Step 9: 更新所有 import（base_schedule.py、credit_fight.py 等引用处）
Step 10: 删除原 navigation.py
Step 11: 运行测试 + lint
```

---

## 最终结果

```
Before:  arknights_mower/solvers/navigation.py         1149 行
         arknights_mower/utils/nav_trie.py              129 行  ← 废弃
         arknights_mower/utils/nav_explorer.py          136 行  ← 废弃
         ─────────────────────────────────────────
         合计 1414 行，其中 265 行废弃

After:   arknights_mower/solvers/navigation/__init__.py   5 行
         arknights_mower/solvers/navigation/tools.py     30 行
         arknights_mower/solvers/navigation/ocr.py      200 行
         arknights_mower/solvers/navigation/recorder.py  100 行
         arknights_mower/solvers/navigation/bfs.py      120 行
         arknights_mower/solvers/navigation/llm_bfs.py   80 行
         arknights_mower/solvers/navigation/solver.py   100 行
         ─────────────────────────────────────────
         合计 ~635 行，减少 55%，每个文件职责单一
```
