import json
import re
from datetime import datetime
from pathlib import Path

import cv2
import numpy as np

from arknights_mower import __rootdir__
from arknights_mower.data import stage_data_full
from arknights_mower.models import navigation
from arknights_mower.solvers.base_mixin import BaseMixin
from arknights_mower.utils import config, rapidocr
from arknights_mower.utils.graph import SceneGraphSolver
from arknights_mower.utils.image import loadres, thres2
from arknights_mower.utils.log import logger
from arknights_mower.utils.scene import Scene
from arknights_mower.utils.vector import va, vs

location = {
    1: {
        "1-1": (0, 0),
        "1-2": (428, -1),
        "1-3": (700, 157),
        "1-4": (1138, 158),
        "1-5": (1600, 158),
        "1-6": (2360, -1),
        "1-7": (3073, -180),
        "1-8": (3535, -181),
        "1-9": (4288, -1),
        "1-10": (4635, 167),
        "1-11": (4965, -9),
        "1-12": (5436, -10),
    },
    8: {
        "R8-1": (0, 0),
        "R8-2": (471, 0),
        "R8-3": (864, 0),
        "R8-4": (1259, 0),
        "R8-5": (1651, -4),
        "R8-6": (2045, -4),
        "R8-7": (2228, -124),
        "R8-8": (2437, -4),
        "R8-9": (2951, -4),
        "R8-10": (3284, -4),
        "R8-11": (3617, -4),
        "M8-1": (6, 339),
        "M8-2": (865, 339),
        "M8-3": (1259, 339),
        "M8-4": (1651, 339),
        "M8-5": (2045, 339),
        "M8-6": (2439, 340),
        "M8-7": (2952, 340),
        "M8-8": (3617, 339),
        "JT8-1": (4092, 171),
        "JT8-2": (4545, 171),
        "JT8-3": (5022, 171),
        "H8-1": (5556, -24),
        "H8-2": (5759, 354),
        "H8-3": (5999, -24),
        "H8-4": (6192, 354),
    },
    12: {
        "12-1": (0, 0),
        "12-2": (342, 292),
        "12-3": (701, 292),
        "12-4": (894, 121),
        "12-5": (1122, 292),
        "12-6": (1364, 121),
        "12-7": (1515, 292),
        "12-8": (2109, 290),
        "12-9": (2468, 290),
        "12-10": (2670, 125),
        "12-11": (2980, 422),
        "12-12": (3218, 125),
        "12-13": (3456, 294),
        "12-14": (3694, 123),
        "12-15": (4020, 123),
        "12-16": (4348, -14),
        "12-17": (4673, -14),
        "12-18": (4673, 210),
        "12-19": (5175, 210),
        "12-20": (5700, 210),
        "12-21": (6377, 210),
    },
    "OF": {
        "OF-1": (0, 0),
        "OF-2": (738, 144),
        "OF-3": (1122, 299),
        "OF-4": (1475, 135),
        "OF-5": (2288, -45),
        "OF-6": (2737, -45),
        "OF-7": (3550, 135),
        "OF-8": (3899, 299),
    },
    "AP": {
        "AP-1": (0, 0),
        "AP-2": (416, -74),
        "AP-3": (716, -247),
        "AP-4": (964, -417),
        "AP-5": (1116, -589),
    },
    "LS": {
        "LS-1": (0, 0),
        "LS-2": (385, -34),
        "LS-3": (710, -130),
        "LS-4": (970, -257),
        "LS-5": (1138, -421),
        "LS-6": (1213, -600),
    },
    "CA": {
        "CA-1": (0, 0),
        "CA-2": (416, -73),
        "CA-3": (716, -246),
        "CA-4": (964, -417),
        "CA-5": (1116, -589),
    },
    "CE": {
        "CE-1": (0, 0),
        "CE-2": (382, -33),
        "CE-3": (709, -128),
        "CE-4": (970, -259),
        "CE-5": (1136, -420),
        "CE-6": (1210, -597),
    },
    "SK": {
        "SK-1": (0, 0),
        "SK-2": (416, -73),
        "SK-3": (716, -246),
        "SK-4": (965, -417),
        "SK-5": (1116, -589),
    },
    "PR-A": {"PR-A-1": (0, 0), "PR-A-2": (604, -283)},
    "PR-B": {"PR-B-1": (0, 0), "PR-B-2": (684, -296)},
    "PR-C": {"PR-C-1": (0, 0), "PR-C-2": (667, -231)},
    "PR-D": {"PR-D-1": (0, 0), "PR-D-2": (639, -260)},
}

collection_prefixs = [
    "AP",
    "LS",
    "CA",
    "CE",
    "PR",
    "SK",
]

difficulty_str = [
    "normal",
    "hard",
]


class NavigationSolver(SceneGraphSolver, BaseMixin):
    def run(self, name: str):
        logger.info("Start: 关卡导航")
        self.success = False
        self.act = None
        self.name = name
        # Initialize legacy navigation fields to avoid attribute errors in fallback paths.
        name_tokens = self.normalize_stage_text(name).split("-")
        prefix_raw = name_tokens[0] if name_tokens else ""
        self.prefix = int(prefix_raw) if prefix_raw.isdigit() else prefix_raw
        self.pr_prefix = (
            name_tokens[1] if prefix_raw == "PR" and len(name_tokens) > 1 else ""
        )
        self.now_difficulty = None
        self.change_to = None
        self.stage_meta = next(
            (
                item
                for item in stage_data_full
                if item.get("id") == name or item.get("name") == name
            ),
            None,
        )
        self.stageType = (
            "UNKNOWN" if not self.stage_meta else self.stage_meta.get("stageType")
        )
        logger.info(
            "Navigation target=%s stageType=%s zone=%s subTitle=%s",
            self.name,
            self.stageType,
            None if not self.stage_meta else self.stage_meta.get("zoneNameSecond"),
            None if not self.stage_meta else self.stage_meta.get("subTitle"),
        )
        self.nav_steps = []
        self.nav_route_success = False
        self._suppress_nav_recording = False
        self._activity_entry_done = False
        self._activity_entry_failed = False
        self._builder_attempted = False
        self.scene_graph_navigation(Scene.TERMINAL_MAIN)
        # rapid OCR: 如果右下角显示“上次作战”的关卡名与目标相同，直接点击进入
        logger.info("尝试使用rapid OCR识别上次作战")
        if rapidocr.engine:
            x0, y0, x1, y1 = 1680, 840, 1895, 945
            region = self.recog.img[y0:y1, x0:x1]
            ocr_raw = rapidocr.engine(region, use_det=True, use_cls=False, use_rec=True)
            ocr_result = ocr_raw[0] if isinstance(ocr_raw, tuple) else ocr_raw

            texts = []
            for item in ocr_result or []:
                try:
                    txt = None
                    if (
                        isinstance(item, (list, tuple))
                        and len(item) >= 2
                        and isinstance(item[1], str)
                    ):
                        txt = item[1]
                        logger.info(f"ocr识别结果: {txt}")
                    if txt:
                        texts.append(txt.strip())
                except Exception:
                    continue
            logger.info(f"上次作战OCR: {texts}")
            if self.name in texts:
                logger.info("识别到上次作战与目标相同，尝试点击进入")
                self.tap((self.recog.w * 0.88, self.recog.h * 0.81), interval=0.5)
                self.success = True

        super().run()
        if self.success and self.nav_steps:
            self.persist_nav_steps()
        return self.success

    def transition(self):
        if (scene := self.scene()) == Scene.TERMINAL_MAIN:
            logger.info(
                f"TERMINAL_MAIN flags: done={self._activity_entry_done}, failed={self._activity_entry_failed}, "
                f"stageType={self.stageType}, has_meta={self.stage_meta is not None}"
            )
            # DAILY/ACTIVITY/MAIN 或未知关卡：优先快速入口，再回放，再在线构建
            if not self._activity_entry_done and (
                self.stage_meta is None
                or self.stageType in {"ACTIVITY", "MAIN", "DAILY"}
            ):
                logger.info("进入 try_activity_entry")
                if self.try_activity_entry():
                    # Entry-building success means same-pattern page is reached.
                    # Exact stage positioning (left/right swipe) is the final step.
                    if self.is_stage_code(self.name):
                        self.find_target_stage_after_entry(self.name, max_swipes=6)
                    return
            if self._activity_entry_failed:
                logger.info("活动入口构建失败，终止本次导航，避免终端主界面循环")
                return True
            if self.name == "Annihilation":
                pos_list = [(943, 130), (1491, 130), (1665, 815), (1875, 815)]
                for pos in pos_list:
                    loaded = self.recog.gray[pos[1]][pos[0]] < 55
                    if loaded:
                        break
                if not loaded:
                    self.sleep()
                    return
                if pos := self.find("terminal_eliminate"):
                    self.tap(pos)
                else:
                    logger.info("本周剿灭已完成")
                    return True
            elif self.stageType == "MAIN":
                self.tap_terminal_button("main_theme")
            elif self.stageType == "ACTIVITY" and self.stage_meta.get("endTS") is None:
                self.tap_terminal_button("main_theme")
            elif self.stageType == "DAILY":
                self.tap_terminal_button("collection")
        elif scene == Scene.OPERATOR_ELIMINATE:
            if self.name != "Annihilation":
                self.back()
                return
            self.success = True
            return True
        elif scene == Scene.TERMINAL_MAIN_THEME:
            if not isinstance(self.prefix, int):
                self.back()
                return
            act_scope = ((300, 315), (400, 370))

            if self.find(f"navigation/act/{self.act}", scope=act_scope):
                if pos := self.find(f"navigation/main/{self.prefix}"):
                    self.tap(pos)
                else:
                    self.device.swipe_ext(
                        ((932, 554), (1425, 554), (1425, 554)), durations=[300, 100]
                    )
                    self.recog.update()
            else:
                self.tap((230, 175))
        elif scene == Scene.TERMINAL_BIOGRAPHY:
            if self.prefix not in ["OF"]:
                self.back()
                return
            if self.find(f"navigation/biography/{self.prefix}_banner"):
                self.tap_element("navigation/entry")
                return
            self.tap_element(f"navigation/biography/{self.prefix}_entry")
        elif scene == Scene.TERMINAL_COLLECTION:
            prefix = self.prefix
            val = 0.9
            if self.prefix not in collection_prefixs:
                self.back()
                return
            if self.prefix == "PR":
                prefix = self.prefix + "-" + self.pr_prefix
            if self.prefix not in ["LS"]:
                if self.find(f"navigation/collection/{prefix}_not_available"):
                    logger.info(f"{self.name}未开放")
                    return True
            if pos := self.find(f"navigation/collection/{prefix}_entry"):
                self.tap(pos)
            else:
                if self.prefix in ["AP", "CA", "CE", "SK"]:
                    self.swipe_noinertia((900, 500), (600, 0))
                if self.prefix in ["PR"]:
                    self.swipe_noinertia((900, 500), (-600, 0))
        elif scene == Scene.OPERATOR_CHOOSE_LEVEL:
            non_black_count = cv2.countNonZero(thres2(self.recog.gray, 10))
            non_black_ratio = non_black_count / (1920 * 1080)
            logger.info(f"{non_black_ratio=}")
            if non_black_ratio < 0.1:
                self.sleep()
                return

            name, val, loc = "", 1, None
            prefix = self.prefix
            # 资源收集关直接按坐标点击
            if prefix in collection_prefixs:
                if self.prefix == "PR":
                    prefix = "{}-{}".format(self.prefix, self.pr_prefix)
                if pos := self.find(f"navigation/collection/{prefix}-1"):
                    self.success = True
                    self.tap(va(pos[0], location[prefix][self.name]))
                return True
            # 其余关
            if self.act == 2:
                if self.now_difficulty is None:
                    if self.find("navigation/ope_normal"):
                        self.now_difficulty = 0
                    elif self.find("navigation/ope_hard"):
                        self.now_difficulty = 1
                    logger.info(f"当前难度{difficulty_str[self.now_difficulty]}")

                if self.change_to is not None and self.now_difficulty != self.change_to:
                    self.recog.update()
                    if self.find("navigation/ope_difficulty"):
                        self.tap_element(
                            f"navigation/ope_{difficulty_str[self.change_to]}_small"
                        )
                        self.now_difficulty = None
                    else:
                        self.tap_element(
                            f"navigation/ope_{difficulty_str[self.now_difficulty]}"
                        )
                        return
            if prefix not in location:
                logger.info(
                    f"prefix={prefix} 不在静态location映射中，使用OCR fallback避免崩溃"
                )
                if self.is_stage_code(self.name) and self.find_target_stage_after_entry(
                    self.name, max_swipes=6
                ):
                    self.success = True
                    return True
                self.back()
                return
            for i in location[prefix]:
                result = cv2.matchTemplate(
                    self.recog.gray, navigation[i], cv2.TM_SQDIFF_NORMED
                )
                min_val, max_val, min_loc, max_loc = cv2.minMaxLoc(result)
                if min_val < val:
                    val = min_val
                    loc = min_loc
                    name = i

            target = va(vs(loc, location[prefix][name]), location[prefix][self.name])
            if target[0] + 200 > 1920:
                self.swipe_noinertia((1400, 540), (-800, 0))
            elif target[0] < 0:
                self.swipe_noinertia((400, 540), (800, 0))
            else:
                self.success = True
                self.tap(va(target, (60, 20)))
        elif scene == Scene.OPERATOR_BEFORE:
            if self.act == 2:
                if self.change_to is not None:
                    logger.info(f"{self.name} 无法代理")
                    self.success = False
                    self.back_to_index()
                    return True
                if self.find("ope_agency_lock"):
                    self.change_to = self.now_difficulty ^ 1
                    logger.info(
                        f"{self.name} {difficulty_str[self.now_difficulty]} 无法代理，切难度尝试"
                    )
                    self.back()
                    return
            if self.success:
                return True
            else:
                self.back()
        elif scene in self.waiting_scene:
            self.waiting_solver()
        else:
            self.scene_graph_navigation(Scene.TERMINAL_MAIN)

    def try_activity_entry(self) -> bool:
        """
        运行时策略：
        1) 先尝试快速入口（490,1014 或 DAILY 800,1014）
        2) 再尝试历史步骤回放
        3) 回放失败后在线构建一次并更新 json
        """
        if not rapidocr.engine:
            logger.info("rapidocr 未初始化，跳过活动入口 OCR")
            return False
        self._activity_entry_done = True
        logger.info(
            "try_activity_entry: target=%s stageType=%s builder_attempted=%s",
            self.name,
            self.stageType,
            self._builder_attempted,
        )

        if self.try_quick_entry_from_main():
            logger.info("快速入口命中，导航成功")
            self.success = True
            return True

        if self.try_replay_nav_steps():
            logger.info("命中历史导航步骤，导航成功")
            self.success = True
            return True

        if not self._builder_attempted:
            self._builder_attempted = True
            logger.info("历史回放失败，开始在线构建一次导航步骤")
            ok = self.try_build_nav_steps_once()
            if ok:
                self.success = True
                self.persist_nav_steps()
                return True

        self._activity_entry_failed = True
        logger.info("在线构建失败，终止本次导航")
        return False

    def try_quick_entry_from_main(self) -> bool:
        if self.scene() != Scene.TERMINAL_MAIN:
            return False
        if str(self.stageType).upper() == "UNKNOWN":
            return False
        prev_suppress = self._suppress_nav_recording
        self._suppress_nav_recording = True
        try:
            # Quick entry is runtime-only and should not be persisted into trie steps.
            logger.info(
                "尝试快速入口: stageType=%s zone=%s",
                self.stageType,
                None if not self.stage_meta else self.stage_meta.get("zoneNameSecond"),
            )
            if self.stageType == "DAILY":
                self.tap((800, 1014), interval=0.2)
            else:
                self.tap((490, 1014), interval=0.2)
            self.wait_for_scene_stable(timeout_seconds=5, interval_seconds=0.2)
            zone = (self.stage_meta or {}).get("zoneNameSecond")
            if not zone:
                return False
            if self.stageType == "DAILY":
                zone_candidate = self.find_zone_candidate_with_swipe(zone, max_swipes=2)
                if not zone_candidate:
                    logger.info("快速入口未找到 DAILY zone OCR，进入后续策略")
                    return False
                logger.info(
                    "快速入口 DAILY OCR命中: text=%s center=%s",
                    zone_candidate.get("text"),
                    zone_candidate.get("center"),
                )
                moved = self.tap_and_detect_page_move(
                    zone_candidate["center"], zone_candidate["text"], record_step=False
                )
                if not moved:
                    raise RuntimeError(
                        "DAILY zone matched by OCR but click did not change page: "
                        f"target={zone} matched={zone_candidate.get('text')}"
                    )
                if self.is_stage_code(self.name):
                    return self.find_target_stage_after_entry(self.name, max_swipes=3)
                return True
            key = f"navigation/stage/{zone}"
            logger.info(f"快速入口图片匹配: key={key}")
            pos = self.find_stage_banner(zone)
            if not pos:
                logger.info("快速入口未找到 zone 图片，进入后续策略")
                return False
            moved = self.tap_and_detect_page_move(pos[0], zone, record_step=False)
            if not moved:
                logger.info("快速入口图片命中但不可点击（页面未跳转）")
                return False
            # Quick entry may land on overview first; try subtitle/chapter entry once.
            self.click_subtitle_if_needed()
            if self.is_stage_code(self.name):
                return self.find_target_stage_after_entry(self.name, max_swipes=3)
            return True
        finally:
            self._suppress_nav_recording = prev_suppress

    def try_build_nav_steps_once(self) -> bool:
        # Build navigation route (to pattern page) once.
        if self.stageType == "UNKNOWN" or self.stage_meta is None:
            return self.build_unknown_nav_steps_via_llm(max_attempts=9)
        if self.stageType == "DAILY":
            return self.build_daily_nav_steps()
        return self.build_activity_or_main_nav_steps()

    def back_to_terminal_main(self, max_back: int = 12) -> bool:
        for _ in range(max_back):
            if self.scene() != Scene.UNKNOWN:
                break
            self.back(0.4)
            self.wait_for_scene_stable(timeout_seconds=2, interval_seconds=0.2)
        self.scene_graph_navigation(Scene.TERMINAL_MAIN)
        return self.scene() == Scene.TERMINAL_MAIN

    def build_unknown_nav_steps_via_llm(self, max_attempts: int = 9) -> bool:
        # Stage A: from TERMINAL_MAIN enter event/main summary page.
        # Stage B: from summary select subtitle/entry page.
        # Stage C: verify pattern page reached (pattern_only=True).
        logger.info("构建 UNKNOWN 导航步骤：MAIN OCR + LLM 排序入口")
        if not self.back_to_terminal_main():
            logger.info("UNKNOWN 导航失败：无法回到终端主界面")
            return False

        candidates = self.collect_terminal_ocr_candidates(save_shot=True)
        if not candidates:
            logger.info("UNKNOWN 导航失败：MAIN OCR 为空")
            return False

        ranked = self.rank_activity_candidates(
            candidates, top_k=min(max_attempts, len(candidates))
        )
        logger.info(
            f"UNKNOWN 导航候选数={len(candidates)} 尝试上限={max_attempts} top={[c.get('text', '') for c in ranked]}"
        )
        main_sig = self.ocr_signature(candidates)
        failed_main_attempts = set()
        failed_sub_attempts = set()

        for idx, cand in enumerate(ranked[:max_attempts], start=1):
            main_checkpoint = len(self.nav_steps)
            text = cand.get("text", "")
            center = cand.get("center")
            main_key = (main_sig, self.normalize_stage_text(text))
            if main_key in failed_main_attempts:
                logger.info(f"UNKNOWN MAIN入口尝试[{idx}] 跳过（同页同候选已失败） text={text}")
                continue
            logger.info(f"UNKNOWN MAIN入口尝试[{idx}/{max_attempts}] text={text}")
            moved = self.tap_and_detect_page_move(center, text, record_step=True)
            if not moved:
                self.nav_steps = self.nav_steps[:main_checkpoint]
                failed_main_attempts.add(main_key)
                logger.info(f"UNKNOWN MAIN入口尝试[{idx}] 无跳转，换下一个候选")
                continue
            logger.info(f"UNKNOWN 已进入活动summary: by='{text}'")

            if self.is_stage_code(self.name) and self.find_target_stage_after_entry(
                self.name, max_swipes=4, pattern_only=True
            ):
                logger.info(f"UNKNOWN 导航成功：summary直检命中 {self.name}")
                return True

            sub_candidates = self.collect_terminal_ocr_candidates(save_shot=False)
            if not sub_candidates:
                logger.info("UNKNOWN summary OCR 为空，切换下一个MAIN候选")
                self.nav_steps = self.nav_steps[:main_checkpoint]
                failed_main_attempts.add(main_key)
                if not self.back_to_terminal_main(max_back=4):
                    logger.info("UNKNOWN 导航失败：无法回到终端主界面")
                    return False
                continue

            sub_ranked = self.rank_activity_candidates(
                sub_candidates, top_k=min(max_attempts, len(sub_candidates))
            )
            sub_sig = self.ocr_signature(sub_candidates)
            logger.info(
                f"UNKNOWN summary候选数={len(sub_candidates)} top={[c.get('text', '') for c in sub_ranked]}"
            )
            back_to_main_during_sub = False
            for sub_idx, sub_cand in enumerate(sub_ranked[:max_attempts], start=1):
                checkpoint = len(self.nav_steps)
                sub_text = sub_cand.get("text", "")
                sub_center = sub_cand.get("center")
                sub_key = (main_sig, sub_sig, self.normalize_stage_text(sub_text))
                if sub_key in failed_sub_attempts:
                    logger.info(
                        f"UNKNOWN subtitle尝试[{sub_idx}] 跳过（同页同候选已失败） text={sub_text}"
                    )
                    continue
                logger.info(f"UNKNOWN subtitle尝试[{sub_idx}/{max_attempts}] text={sub_text}")
                moved = self.tap_and_detect_page_move(sub_center, sub_text, record_step=True)
                if not moved:
                    self.nav_steps = self.nav_steps[:checkpoint]
                    failed_sub_attempts.add(sub_key)
                    logger.info(f"UNKNOWN subtitle尝试[{sub_idx}] 无跳转，换下一个候选")
                    continue
                if self.is_stage_code(self.name) and self.find_target_stage_after_entry(
                    self.name, max_swipes=4, pattern_only=True
                ):
                    logger.info(f"UNKNOWN 导航成功：subtitle候选[{sub_idx}] 命中 {self.name}")
                    return True
                self.nav_steps = self.nav_steps[:checkpoint]
                failed_sub_attempts.add(sub_key)
                self.back(0.4)
                self.wait_for_scene_stable(timeout_seconds=2, interval_seconds=0.2)
                if self.scene() == Scene.TERMINAL_MAIN:
                    logger.info("UNKNOWN subtitle尝试后回到MAIN，切换下一个MAIN候选")
                    back_to_main_during_sub = True
                    failed_main_attempts.add(main_key)
                    break

            if back_to_main_during_sub:
                self.nav_steps = self.nav_steps[:main_checkpoint]
                continue

            self.nav_steps = self.nav_steps[:main_checkpoint]
            failed_main_attempts.add(main_key)
            if not self.back_to_terminal_main(max_back=4):
                logger.info("UNKNOWN 导航失败：无法回到终端主界面")
                return False

        logger.info("UNKNOWN 导航失败：MAIN候选与summary候选均未命中目标")
        return False

    def find_stage_banner(self, zone_name: str, scope=None):
        key = f"navigation/stage/{zone_name}"
        template_path = (
            Path(__rootdir__) / "resources" / "navigation" / "stage" / f"{zone_name}.png"
        )
        if not template_path.exists():
            logger.info(f"stage banner 模板不存在，跳过图片匹配: {template_path}")
            return None
        # Baseline attempt first.
        try:
            pos = self.find(key, scope=scope)
        except Exception:
            pos = None
        if pos:
            return pos

        # Adaptive scale fallback with per-zone learned hint.
        if not hasattr(self, "_stage_scale_hint"):
            self._stage_scale_hint = {}
        hint = float(self._stage_scale_hint.get(zone_name, 1.15))
        raw_scales = [hint, hint * 0.95, hint * 1.05, 1.0, 1.1, 1.15, 1.2, 1.3]
        scales = []
        for s in raw_scales:
            s = max(0.80, min(1.60, s))
            if all(abs(s - x) > 1e-3 for x in scales):
                scales.append(s)

        template = loadres(key, True)
        for scale in scales:
            interp = cv2.INTER_LINEAR if scale >= 1.0 else cv2.INTER_AREA
            scaled = cv2.resize(
                template, None, fx=scale, fy=scale, interpolation=interp
            )
            rect = self.recog.matcher.match(
                scaled,
                scope=scope,
                prescore=0.60,
                dpi_aware=True,
                judge=True,
            )
            if rect:
                self._stage_scale_hint[zone_name] = scale
                logger.info(
                    f"stage匹配成功 zone={zone_name} scale={scale:.2f} (hint updated)"
                )
                return rect
        return None

    def find_zone_candidate_with_swipe(self, zone_name: str, max_swipes: int = 2):
        # OCR search with one right-swipe and one left-swipe fallback.
        for i in range(max_swipes + 1):
            candidates = self.collect_terminal_ocr_candidates(save_shot=(i == 0))
            matched = []
            zone_norm = re.sub(r"\s+", "", zone_name)
            for c in candidates:
                text = str(c.get("text", "")).strip()
                text_norm = re.sub(r"\s+", "", text)
                if not text_norm or not zone_norm:
                    continue
                if zone_norm in text_norm or text_norm in zone_norm:
                    match_score = 2 if zone_norm == text_norm else 1
                    matched.append({**c, "_zone_match_score": match_score})
            if matched:
                return max(
                    matched,
                    key=lambda x: (x.get("_zone_match_score", 0), x.get("score", 0)),
                )
            if i == 0:
                self.swipe_noinertia((900, 540), (700, 0))
                self.record_nav_step("swipe", start=(900, 540), vector=(700, 0))
                self.wait_for_scene_stable(timeout_seconds=3, interval_seconds=0.2)
            elif i == 1:
                self.swipe_noinertia((900, 540), (-700, 0))
                self.record_nav_step("swipe", start=(900, 540), vector=(-700, 0))
                self.wait_for_scene_stable(timeout_seconds=3, interval_seconds=0.2)
        return None

    def build_daily_nav_steps(self) -> bool:
        logger.info("构建 DAILY 导航步骤")
        if self.scene() != Scene.TERMINAL_MAIN:
            self.scene_graph_navigation(Scene.TERMINAL_MAIN)
        self.tap((800, 1014), interval=0.2)
        self.record_nav_step("tap", pos=(800, 1014), text="daily_entry")
        self.wait_for_scene_stable(timeout_seconds=5, interval_seconds=0.2)
        zone = (self.stage_meta or {}).get("zoneNameSecond")
        logger.info("DAILY 导航目标: stage=%s zone=%s", self.name, zone)
        if not zone:
            return False
        zone_candidate = self.find_zone_candidate_with_swipe(zone, max_swipes=2)
        if not zone_candidate:
            logger.info("DAILY 未找到 zoneNameSecond")
            return False
        logger.info(
            "DAILY 命中 zone 候选: text=%s center=%s",
            zone_candidate.get("text"),
            zone_candidate.get("center"),
        )
        moved = self.tap_and_detect_page_move(
            zone_candidate["center"], zone_candidate["text"]
        )
        if not moved:
            raise RuntimeError(
                "DAILY zone matched by OCR but click did not change page: "
                f"target={zone} matched={zone_candidate.get('text')}"
            )
        if self.is_stage_code(self.name):
            return self.find_target_stage_after_entry(
                self.name, max_swipes=6, pattern_only=True
            )
        return True

    def open_activity_overview_until_ready(self, max_taps: int = 8) -> bool:
        # Keep tapping top-right switch until open-time page is detected.
        for _ in range(max_taps):
            if self.find("navigation/orderby_time"):
                return True
            self.tap((1690, 65), interval=0.2)
            self.record_nav_step("tap", pos=(1690, 65), text="open_overview")
            self.wait_for_scene_stable(timeout_seconds=3, interval_seconds=0.2)
        return self.find("navigation/orderby_time")

    def find_stage_image_and_enter(self, zone_name: str, max_swipes: int = 10) -> bool:
        key = f"navigation/stage/{zone_name}"
        logger.info(
            f"find_stage_image_and_enter start: zone={zone_name}, key={key}, max_swipes={max_swipes}"
        )
        last_view = None
        stagnant_rounds = 0
        for i in range(max_swipes + 1):
            pos = self.find_stage_banner(zone_name)
            logger.info(f"find_stage_image_and_enter round={i}, pos_found={bool(pos)}")
            if pos:
                moved = self.tap_and_detect_page_move(pos[0], zone_name)
                logger.info(
                    f"find_stage_image_and_enter tap result: moved={moved}, zone={zone_name}"
                )
                if moved:
                    logger.info(f"find_stage_image_and_enter success: zone={zone_name}")
                    return True
            if i < max_swipes:
                # Overlap scan: primary + micro swipe to cover half-visible banners.
                logger.info(
                    f"find_stage_image_and_enter swipe down(primary): round={i}, zone={zone_name}"
                )
                self.swipe_noinertia((960, 700), (0, -910))
                self.record_nav_step("swipe", start=(960, 700), vector=(0, -910))
                self.wait_for_scene_stable(timeout_seconds=2, interval_seconds=0.2)
                logger.info(
                    f"find_stage_image_and_enter swipe down(micro): round={i}, zone={zone_name}"
                )
                self.swipe_noinertia((960, 700), (0, -280))
                self.record_nav_step("swipe", start=(960, 700), vector=(0, -280))
                self.wait_for_scene_stable(timeout_seconds=2, interval_seconds=0.2)

                # Stop early when view is stagnant (likely reached bottom).
                current_view = cv2.resize(self.recog.gray, (96, 54))
                if last_view is not None and np.array_equal(current_view, last_view):
                    stagnant_rounds += 1
                else:
                    stagnant_rounds = 0
                last_view = current_view
                if stagnant_rounds >= 2:
                    logger.info(
                        "find_stage_image_and_enter stop: viewport stagnant, likely at bottom"
                    )
                    break
        logger.info(f"find_stage_image_and_enter failed: zone={zone_name}")
        return False

    def click_subtitle_if_needed(self) -> None:
        # Some events require one more subtitle click before stage list appears.
        # Prefer metadata subtitle match; fallback to LLM-ranked entry candidates.
        subtitle = (self.stage_meta or {}).get("subTitle")
        candidates = self.collect_terminal_ocr_candidates(save_shot=False)
        logger.info(
            "click_subtitle_if_needed: subtitle=%s candidate_count=%s",
            subtitle,
            len(candidates),
        )
        if not candidates:
            logger.info("summary OCR 为空，无法选择第二入口")
            return

        if not subtitle:
            # No metadata subtitle -> use LLM ranking directly.
            top_k = min(5, len(candidates))
            ranked = self.rank_activity_candidates(candidates, top_k=top_k)
            logger.info(
                f"无 subtitle，使用LLM选择第二入口 top={[c.get('text', '') for c in ranked]}"
            )
            for idx, cand in enumerate(ranked, start=1):
                moved = self.tap_and_detect_page_move(cand["center"], cand["text"])
                logger.info(
                    f"无 subtitle，LLM候选[{idx}/{top_k}] moved={moved} text={cand.get('text', '')}"
                )
                if moved:
                    return
            return

        matched = [c for c in candidates if subtitle in c["text"]]
        if matched:
            chosen = max(matched, key=lambda x: x["score"])
            logger.info(
                "subtitle 直接命中: subtitle=%s text=%s center=%s",
                subtitle,
                chosen.get("text"),
                chosen.get("center"),
            )
            self.tap(chosen["center"], interval=0.2)
            self.record_nav_step("tap", pos=chosen["center"], text=chosen["text"])
            self.wait_for_scene_stable(timeout_seconds=3, interval_seconds=0.2)
            return
        logger.info(f"有 subtitle={subtitle}，但OCR未命中，回退LLM尝试第二入口")
        top_k = min(5, len(candidates))
        ranked = self.rank_activity_candidates(candidates, top_k=top_k)
        for idx, cand in enumerate(ranked, start=1):
            moved = self.tap_and_detect_page_move(cand["center"], cand["text"])
            logger.info(
                f"subtitle fallback LLM候选[{idx}/{top_k}] moved={moved} text={cand.get('text', '')}"
            )
            if moved:
                return

    def build_activity_or_main_nav_steps(self) -> bool:
        logger.info("构建 ACTIVITY/MAIN 导航步骤")
        if self.scene() != Scene.TERMINAL_MAIN:
            self.tap((120, 1014), interval=0.2)
        self.tap((490, 1014), interval=0.2)
        self.record_nav_step("tap", pos=(490, 1014), text="main_entry")

        zone = (self.stage_meta or {}).get("zoneNameSecond")
        logger.info(
            "ACTIVITY/MAIN 导航目标: stage=%s zone=%s subTitle=%s",
            self.name,
            zone,
            None if not self.stage_meta else self.stage_meta.get("subTitle"),
        )
        # if zone:
        #     # 快速路径：最近作战可直达
        #     candidates = self.collect_terminal_ocr_candidates(save_shot=False)
        #     matched = [c for c in candidates if zone in c["text"]]
        #     if matched:
        #         chosen = max(matched, key=lambda x: x["score"])
        #         moved = self.tap_and_detect_page_move(chosen["center"], chosen["text"])
        #         if moved and (
        #             not self.is_stage_code(self.name)
        #             or self.find_target_stage_after_entry(self.name, max_swipes=3)
        #         ):
        #             return True

        if not self.open_activity_overview_until_ready(max_taps=8):
            logger.info("未进入 open_time 页面")
            return False
        if zone and not self.find_stage_image_and_enter(zone, max_swipes=10):
            logger.info("stage 图片匹配失败")
            return False
        self.click_subtitle_if_needed()
        if self.is_stage_code(self.name):
            return self.find_target_stage_after_entry(
                self.name, max_swipes=6, pattern_only=True
            )
        return True

    def is_stage_code(self, text: str) -> bool:
        return (
            re.match(r"^[A-Z0-9]+(?:-[A-Z0-9]+)+$", self.normalize_stage_text(text))
            is not None
        )

    def normalize_stage_text(self, text: str) -> str:
        if not isinstance(text, str):
            return ""
        # Ignore case only; keep all non-case characters for exact matching.
        return text.strip().upper()

    def stage_pattern_stem(self, stage_text: str) -> str:
        """
        Use everything before the last '-' as pattern stem.
        Examples: 0-1 -> 0-, EP-EX-3 -> EP-EX-.
        """
        norm = self.normalize_stage_text(stage_text)
        if "-" not in norm:
            return f"{norm}-"
        head, _, _ = norm.rpartition("-")
        return f"{head}-"

    def collect_terminal_ocr_candidates(self, save_shot: bool = False) -> list[dict]:
        if save_shot:
            try:
                self.recog.save_screencap("terminal_main")
            except Exception:
                pass
        candidates = []

        if self.scene() == Scene.TERMINAL_MAIN:
            ocr_blocks = [
                ((0, 750), (1400, 950)),
                ((810, 100), (1400, 750)),
            ]
        else:
            ocr_blocks = [
                ((0, 0), (self.recog.w, self.recog.h)),
            ]

        for block in ocr_blocks:
            (x0, y0), (x1, y1) = block
            roi = self.recog.img[y0:y1, x0:x1]
            ocr_raw = rapidocr.engine(roi, use_det=True, use_cls=False, use_rec=True)
            ocr_result = ocr_raw[0] if isinstance(ocr_raw, tuple) else ocr_raw
            for item in ocr_result or []:
                if not isinstance(item, (list, tuple)) or len(item) < 2:
                    continue
                box, text = item[0], item[1]
                if not text:
                    continue
                try:
                    xs = [p[0] + x0 for p in box]
                    ys = [p[1] + y0 for p in box]
                    center = (int(sum(xs) / len(xs)), int(sum(ys) / len(ys)))
                except Exception:
                    continue
                score = float(item[2]) if len(item) > 2 else 0.0
                candidates.append(
                    {"text": str(text).strip(), "center": center, "score": score}
                )

        logger.info(f"OCR候选 count={len(candidates)}")
        return candidates

    def ocr_signature(self, candidates: list[dict]) -> tuple[str, ...]:
        counter = {}
        for c in candidates:
            text = self.normalize_stage_text(c.get("text", ""))
            if not text:
                continue
            counter[text] = counter.get(text, 0) + 1
        return tuple(f"{k}:{v}" for k, v in sorted(counter.items()))

    def rank_activity_candidates(
        self, candidates: list[dict], top_k: int = 3
    ) -> list[dict]:
        llm_ranked_indices = []
        try:
            from arknights_mower.agent.rank_activity_entries import (
                rank_activity_entries_with_agent,
            )

            llm_ranked_indices = rank_activity_entries_with_agent(
                target_stage=self.name,
                stage_meta=self.stage_meta or {},
                ocr_items=candidates,
                api_key=config.conf.ai_key,
            )
        except Exception as e:
            logger.info(f"LLM 入口排序不可用，回退规则打分: {e}")
        if llm_ranked_indices:
            llm_texts = [
                candidates[i]["text"]
                for i in llm_ranked_indices
                if isinstance(i, int) and 0 <= i < len(candidates)
            ]
            logger.info(
                f"LLM ranking indices={llm_ranked_indices} texts={llm_texts[:5]}"
            )
        else:
            logger.info("LLM ranking 为空，使用规则分")

        targets = {self.name}
        if self.stage_meta:
            for key in ("zoneNameSecond", "zoneNameFirst", "name", "subTitle"):
                val = self.stage_meta.get(key)
                if val:
                    targets.add(str(val))

        ranked = []
        for idx, c in enumerate(candidates):
            score = float(c.get("score", 0))
            text = c.get("text", "")
            if any(t and t in text for t in targets):
                score += 3.0
            if idx in llm_ranked_indices:
                # LLM排序越靠前，额外分越高
                rank_pos = llm_ranked_indices.index(idx)
                score += max(0, 120.0 - rank_pos * 20.0)
            ranked.append({**c, "_rank_score": score, "_idx": idx})
        ranked.sort(key=lambda x: x["_rank_score"], reverse=True)
        return ranked[:top_k]

    def find_target_stage_after_entry(
        self, target_stage: str, max_swipes: int = 6, pattern_only: bool = False
    ) -> bool:
        """
        进入活动后继续 OCR，若在同一 pattern 页面（如 AP-1）则横向滑动直到找到目标。
        """
        target_norm = self.normalize_stage_text(target_stage)
        pattern_stem = self.stage_pattern_stem(target_norm)
        target_tail_match = re.search(r"-(\d+)$", target_norm)
        target_tail_num = int(target_tail_match.group(1)) if target_tail_match else None
        for swipe_idx in range(max_swipes + 1):
            self.wait_for_scene_stable(timeout_seconds=3, interval_seconds=0.2)
            candidates = self.collect_terminal_ocr_candidates(save_shot=False)
            texts = [c["text"] for c in candidates]
            logger.info(
                "关卡定位: target=%s swipe_round=%s/%s pattern_only=%s ocr_count=%s sample=%s",
                target_stage,
                swipe_idx,
                max_swipes,
                pattern_only,
                len(texts),
                texts[:20],
            )
            exact = next(
                (
                    c
                    for c in candidates
                    if self.normalize_stage_text(c["text"]) == target_norm
                ),
                None,
            )
            if exact:
                self.tap(exact["center"], interval=0.2)
                self.record_nav_step(
                    "tap", pos=exact["center"], text=exact["text"], success=True
                )
                # Mark route as successful only when final pattern-level target is reached.
                self.nav_route_success = True
                logger.info(f"OCR 直接命中目标关卡 {target_stage}，导航成功")
                # Persist immediately so successful path survives unexpected early exits.
                if not self._suppress_nav_recording:
                    self.persist_nav_steps()
                return True

            has_same_pattern = any(
                self.is_stage_code(t) and self.stage_pattern_stem(t) == pattern_stem
                for t in texts
            )
            if not has_same_pattern:
                logger.info("当前页面未识别到同 pattern 关卡，停止继续滑动")
                return False

            if pattern_only:
                self.nav_route_success = True
                if self.nav_steps:
                    payload = self.nav_steps[-1].setdefault("payload", {})
                    payload["success"] = True
                if not self._suppress_nav_recording:
                    self.persist_nav_steps()
                logger.info(
                    f"命中同 pattern 页面，导航成功（pattern_only）：{target_stage}"
                )
                return True

            same_pattern_nums = []
            for t in texts:
                norm_t = self.normalize_stage_text(t)
                if (
                    not self.is_stage_code(norm_t)
                    or self.stage_pattern_stem(norm_t) != pattern_stem
                ):
                    continue
                m = re.search(r"-(\d+)$", norm_t)
                if m:
                    same_pattern_nums.append(int(m.group(1)))

            # Default swipe direction is rightward (toward larger stage numbers).
            swipe_start = (1400, 540)
            swipe_vector = (-800, 0)
            if target_tail_num is not None and same_pattern_nums:
                cur_min = min(same_pattern_nums)
                cur_max = max(same_pattern_nums)
                if target_tail_num < cur_min:
                    # Target is smaller than current visible range -> move left.
                    swipe_start = (500, 540)
                    swipe_vector = (800, 0)
                elif cur_min <= target_tail_num <= cur_max:
                    # Target should be in-view range; OCR may miss it. Move toward nearer side.
                    if (target_tail_num - cur_min) <= (cur_max - target_tail_num):
                        swipe_start = (500, 540)
                        swipe_vector = (800, 0)
                logger.info(
                    f"同pattern尾号范围=[{cur_min},{cur_max}] target={target_tail_num} "
                    f"swipe={swipe_vector}"
                )
            self.swipe_noinertia(swipe_start, swipe_vector)
            self.record_nav_step("swipe", start=swipe_start, vector=swipe_vector)
        logger.info(
            "关卡定位失败: target=%s max_swipes=%s pattern_only=%s",
            target_stage,
            max_swipes,
            pattern_only,
        )
        return False

    def record_nav_step(self, action: str, **payload):
        if self._suppress_nav_recording:
            return
        self.nav_steps.append({"action": action, "payload": payload})

    def stage_pattern_key(self, stage_name: str) -> str | None:
        if not self.is_stage_code(stage_name):
            return None
        return f"{self.stage_pattern_stem(stage_name)}*"

    def load_nav_steps_data(self) -> dict:
        path = Path(__rootdir__) / "data" / "nav_trie_steps.json"
        if not path.exists():
            return {"version": 1, "stages": {}, "patterns": {}}
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            if "stages" not in data or not isinstance(data["stages"], dict):
                data["stages"] = {}
            if "patterns" not in data or not isinstance(data["patterns"], dict):
                data["patterns"] = {}
            return data
        except Exception:
            return {"version": 1, "stages": {}, "patterns": {}}

    def get_replay_steps(self) -> list[dict]:
        data = self.load_nav_steps_data()
        stage_entry = data["stages"].get(self.name, {})
        stage_steps = stage_entry.get("steps", [])
        if stage_steps and stage_entry.get("success") is True:
            logger.info(
                f"找到精确关卡历史步骤: {self.name} steps={len(stage_steps)} success=true"
            )
            return stage_steps
        if stage_steps:
            logger.info(f"忽略精确关卡历史步骤: {self.name}（缺少success=true）")
        pattern_key = self.stage_pattern_key(self.name)
        if pattern_key:
            # Fallback to shared prefix path when exact stage path is absent.
            pattern_entry = data["patterns"].get(pattern_key, {})
            pattern_steps = pattern_entry.get("steps", [])
            if pattern_steps and pattern_entry.get("success") is True:
                logger.info(
                    f"找到同pattern历史步骤: {pattern_key} steps={len(pattern_steps)} success=true"
                )
                return pattern_steps
            if pattern_steps:
                logger.info(f"忽略同pattern历史步骤: {pattern_key}（缺少success=true）")
        return []

    def try_replay_nav_steps(self) -> bool:
        if not self.back_to_terminal_main():
            logger.info("历史回放失败：无法回到终端主界面")
            return False
        steps = self.get_replay_steps()
        if not steps:
            return False
        logger.info(f"开始回放历史步骤 count={len(steps)}")
        for idx, step in enumerate(steps, start=1):
            action = step.get("action")
            payload = step.get("payload", {}) or {}
            logger.info(
                "回放历史步骤[%s/%s]: action=%s payload=%s",
                idx,
                len(steps),
                action,
                payload,
            )
            if action == "tap":
                pos = payload.get("pos")
                if not isinstance(pos, (list, tuple)) or len(pos) != 2:
                    continue
                self.tap((int(pos[0]), int(pos[1])), interval=0.2)
                self.wait_for_scene_stable(timeout_seconds=5, interval_seconds=0.2)
            elif action == "swipe":
                start = payload.get("start")
                vector = payload.get("vector")
                if (
                    not isinstance(start, (list, tuple))
                    or len(start) != 2
                    or not isinstance(vector, (list, tuple))
                    or len(vector) != 2
                ):
                    continue
                self.swipe_noinertia(
                    (int(start[0]), int(start[1])),
                    (int(vector[0]), int(vector[1])),
                )
                self.wait_for_scene_stable(timeout_seconds=5, interval_seconds=0.2)
            # Verify target after each step; return immediately on success.
            if self.is_stage_code(self.name) and self.find_target_stage_after_entry(
                self.name, max_swipes=3, pattern_only=True
            ):
                return True
        if self.is_stage_code(self.name):
            return self.find_target_stage_after_entry(
                self.name, max_swipes=6, pattern_only=True
            )
        return False

    def persist_nav_steps(self):
        if not self.nav_route_success:
            logger.info(
                "导航步骤未到达最终目标（success=false），不写入 nav_trie_steps.json"
            )
            return
        path = Path(__rootdir__) / "data" / "nav_trie_steps.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        raw = self.load_nav_steps_data()
        raw["stages"][self.name] = {
            "updated_at": datetime.now().isoformat(timespec="seconds"),
            "stage_type": self.stageType,
            "success": True,
            "steps": self.nav_steps,
        }
        pattern_key = self.stage_pattern_key(self.name)
        if pattern_key and self.nav_steps:
            raw["patterns"][pattern_key] = {
                "updated_at": datetime.now().isoformat(timespec="seconds"),
                "stage_type": self.stageType,
                "source_stage": self.name,
                "success": True,
                "steps": self.nav_steps,
            }
        path.write_text(json.dumps(raw, ensure_ascii=False, indent=2), encoding="utf-8")
        logger.info(f"导航步骤已写入: {path}")

    def auto_generate_nav_trie_steps(
        self,
        stage_types: set[str] | None = None,
        limit: int | None = None,
    ) -> dict:
        """
        批量尝试为关卡生成导航步骤并写入 nav_trie_steps.json。
        """
        if stage_types is None:
            stage_types = {"DAILY", "ACTIVITY", "MAIN"}
        summary = {"ok": [], "failed": []}
        count = 0
        for rec in stage_data_full:
            stage_id = rec.get("id")
            stage_type = rec.get("stageType")
            if not stage_id or stage_type not in stage_types:
                continue
            if limit is not None and count >= limit:
                break
            count += 1
            try:
                logger.info(
                    f"[AUTO] build nav steps stage={stage_id} type={stage_type}"
                )
                ok = self.run(stage_id)
                if ok:
                    summary["ok"].append(stage_id)
                else:
                    summary["failed"].append(
                        {"stage": stage_id, "reason": "navigation failed"}
                    )
            except Exception as e:
                summary["failed"].append({"stage": stage_id, "reason": str(e)})
        logger.info(
            f"[AUTO] done ok={len(summary['ok'])} failed={len(summary['failed'])}"
        )
        return summary


