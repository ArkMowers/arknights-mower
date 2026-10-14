# 原始材料

来源提交：`09bd4e0ee2ec6b4a2b68225484ee5cca921ccbb6`。

本次范围仅为该提交与其父提交的差异。不使用旧提交标题或业务说明正文作为写作输入。

## 历史证据范围

以下源码与离线测试属于该提交的历史材料，没有提供点击后的真实页面跳转、后续通知遗漏或实机验证记录，不代表本轮实际执行。

## 完整 diff

```diff
diff --git a/arknights_mower/solvers/recruit.py b/arknights_mower/solvers/recruit.py
index 79d51c7b1..6db16e5da 100644
--- a/arknights_mower/solvers/recruit.py
+++ b/arknights_mower/solvers/recruit.py
@@ -16,7 +16,7 @@ from arknights_mower.utils.email import recruit_rarity, recruit_template, send_m
 from arknights_mower.utils.graph import SceneGraphSolver
 from arknights_mower.utils.image import cmatch, cropimg, loadres, thres2
 from arknights_mower.utils.log import logger
-from arknights_mower.utils.recognize import Recognizer, Scene
+from arknights_mower.utils.recognize import RecognizeError, Recognizer, Scene
 from arknights_mower.utils.resource_pkg import (
     register_resource_reload,
     resource_pkg_path,
@@ -325,34 +325,30 @@ class RecruitSolver(SceneGraphSolver):
             self.scene_graph_navigation(Scene.RECRUIT_MAIN)
 
     def recruit_result(self):
-        try:
-            # 存在读完一次没退完再读一次
-            if str(self.recruit_index) in self.result_agent.keys():
-                self.tap((950, 150))
-                return
-
-            job_pt = None
-            for i in job_list:
-                if job_pt := self.find(i):
-                    break
+        if self.recruit_index in self.result_agent:
+            self.tap((950, 150))
+            return
 
-            img = cropimg(self.recog.gray, ((job_pt[1][0], 730), (1800, 860)))
-            img = cv2.threshold(img, 220, 255, cv2.THRESH_BINARY)[1]
-
-            score = {}
-            for id in recruit_res_template:
-                res = recruit_res_template[id]
-                result = cv2.matchTemplate(img, res, cv2.TM_CCORR_NORMED, res)
-                _, max_val, _, _ = cv2.minMaxLoc(result)
-                score[id] = max_val
-            self.result_agent[self.recruit_index] = recruit_agent[
-                max(score, key=score.get)
-            ]["name"]
-
-        except Exception as e:
-            logger.exception(f"公招开包异常:{e}")
-        finally:
-            self.tap((500, 500))
+        job_pt = None
+        for i in job_list:
+            if job_pt := self.find(i):
+                break
+        if job_pt is None:
+            raise RecognizeError("公招干员职业图标尚未识别")
+
+        img = cropimg(self.recog.gray, ((job_pt[1][0], 730), (1800, 860)))
+        img = cv2.threshold(img, 220, 255, cv2.THRESH_BINARY)[1]
+
+        score = {}
+        for id in recruit_res_template:
+            res = recruit_res_template[id]
+            result = cv2.matchTemplate(img, res, cv2.TM_CCORR_NORMED, res)
+            _, max_val, _, _ = cv2.minMaxLoc(result)
+            score[id] = max_val
+        self.result_agent[self.recruit_index] = recruit_agent[
+            max(score, key=score.get)
+        ]["name"]
+        self.tap((500, 500))
 
     def recruit_tags(self, tags):
         tem_res = self.recruit_cal(sorted(tags))
diff --git a/arknights_mower/tests/fixtures/recruit_result_lava_animation_20261002.png b/arknights_mower/tests/fixtures/recruit_result_lava_animation_20261002.png
new file mode 100644
index 000000000..818a9233a
Binary files /dev/null and b/arknights_mower/tests/fixtures/recruit_result_lava_animation_20261002.png differ
diff --git a/arknights_mower/tests/fixtures/recruit_result_lava_ready_20261002.png b/arknights_mower/tests/fixtures/recruit_result_lava_ready_20261002.png
new file mode 100644
index 000000000..e2f2fa1e3
Binary files /dev/null and b/arknights_mower/tests/fixtures/recruit_result_lava_ready_20261002.png differ
diff --git a/arknights_mower/tests/recruit_result_tests.py b/arknights_mower/tests/recruit_result_tests.py
new file mode 100644
index 000000000..f9723b4a9
--- /dev/null
+++ b/arknights_mower/tests/recruit_result_tests.py
@@ -0,0 +1,155 @@
+from pathlib import Path
+from unittest.mock import Mock
+
+import cv2
+import numpy as np
+import pytest
+
+from arknights_mower.solvers import recruit
+from arknights_mower.utils.csleep import MowerExit
+from arknights_mower.utils.recognize import RecognizeError, Recognizer, Scene
+
+
+def result_frame(state):
+    # 日志调度-20261002-065219.zip 的错误截图，保留职业、姓名与信物区域。
+    # animation: 1790895139359432800.jpg; ready: 1790895140736340800.jpg。
+    path = Path(__file__).parent / f"fixtures/recruit_result_lava_{state}_20261002.png"
+    crop = cv2.imread(str(path), cv2.IMREAD_GRAYSCALE)
+    assert crop is not None
+    frame = np.zeros((1080, 1920), dtype=np.uint8)
+    frame[730:860, 750:1920] = crop
+    return frame
+
+
+def make_solver(state="animation"):
+    device = Mock()
+    recog = Recognizer(device)
+    recog._gray = result_frame(state)
+    solver = recruit.RecruitSolver(device, recog)
+    solver.scene = Mock(return_value=Scene.RECRUIT_AGENT)
+    solver.tap = Mock()
+    return solver
+
+
+def test_result_without_profession_keeps_display_open():
+    solver = make_solver()
+    assert solver.find("recruit/agent_token") is not None
+    assert all(solver.find(name) is None for name in recruit.job_list)
+
+    with pytest.raises(RecognizeError, match="职业"):
+        solver.transition()
+
+    assert solver.result_agent == {}
+    assert solver.recruit_index == 1
+    solver.tap.assert_not_called()
+
+
+def test_ready_result_is_recorded_before_one_dismissal():
+    solver = make_solver("ready")
+    records_at_tap = []
+    solver.tap.side_effect = lambda *_: records_at_tap.append(dict(solver.result_agent))
+
+    solver.transition()
+
+    assert solver.result_agent == {1: "炎熔"}
+    assert records_at_tap == [{1: "炎熔"}]
+    solver.tap.assert_called_once_with((500, 500))
+
+
+def test_recorded_integer_slot_is_not_recognized_again():
+    solver = make_solver()
+    solver.result_agent = {1: "炎熔"}
+    solver.find = Mock(side_effect=AssertionError("已记录的结果不应重新识别"))
+
+    solver.transition()
+
+    solver.find.assert_not_called()
+    assert solver.result_agent == {1: "炎熔"}
+    solver.tap.assert_called_once()
+
+
+@pytest.mark.parametrize("error", [MowerExit(), RuntimeError("截图失败")])
+def test_recognition_failure_propagates_without_dismissal(error):
+    solver = make_solver()
+    solver.find = Mock(side_effect=error)
+
+    with pytest.raises(type(error)) as caught:
+        solver.transition()
+
+    assert caught.value is error
+    assert solver.result_agent == {}
+    solver.tap.assert_not_called()
+
+
+def test_name_matching_failure_does_not_dismiss(monkeypatch):
+    solver = make_solver("ready")
+    monkeypatch.setattr(
+        recruit, "cropimg", Mock(side_effect=ValueError("姓名裁剪失败"))
+    )
+
+    with pytest.raises(ValueError, match="姓名裁剪失败"):
+        solver.transition()
+
+    assert solver.result_agent == {}
+    solver.tap.assert_not_called()
+
+
+def prepare_run(monkeypatch, solver, scenes):
+    solver.scene = Mock(side_effect=scenes)
+    find = solver.find
+    solver.find = Mock(
+        side_effect=lambda name, *args, **kwargs: (
+            ((400, 120), (540, 220))
+            if name == "recruit/recruit_lock"
+            else find(name, *args, **kwargs)
+        )
+    )
+    solver.check_current_focus = Mock()
+    solver.add_recruit_param = Mock()
+    solver.recog.update = Mock()
+    notify = Mock()
+    monkeypatch.setattr(recruit, "send_message", notify)
+    return notify
+
+
+def test_run_retries_animation_then_records_ready_frame(monkeypatch):
+    solver = make_solver()
+    notify = prepare_run(
+        monkeypatch,
+        solver,
+        [Scene.RECRUIT_AGENT, Scene.RECRUIT_AGENT, Scene.RECRUIT_MAIN],
+    )
+    observations = []
+
+    def next_frame(interval):
+        observations.append(
+            (interval, dict(solver.result_agent), solver.tap.call_count)
+        )
+        solver.recog._gray = result_frame("ready")
+
+    solver.sleep = Mock(side_effect=next_frame)
+
+    assert solver.run() == ({}, {1: "炎熔"})
+
+    assert observations == [(3, {}, 0)]
+    solver.tap.assert_called_once_with((500, 500))
+    notify.assert_called_once()
+
+
+def test_run_stops_after_existing_recognition_budget(monkeypatch):
+    solver = make_solver()
+    budget = recruit.config.MAX_RETRYTIME
+    notify = prepare_run(
+        monkeypatch,
+        solver,
+        [Scene.RECRUIT_AGENT] * budget + [Scene.RECRUIT_MAIN],
+    )
+    solver.sleep = Mock()
+
+    assert solver.run() == ({}, {})
+
+    assert solver.scene.call_count == budget
+    assert solver.sleep.call_count == budget
+    assert solver.recruit_index == 1
+    solver.tap.assert_not_called()
+    notify.assert_not_called()
diff --git a/docs/subsystems/recruitment.md b/docs/subsystems/recruitment.md
index 397139326..9f2440870 100644
--- a/docs/subsystems/recruitment.md
+++ b/docs/subsystems/recruitment.md
@@ -2,7 +2,7 @@
 
 ## 1. Scope
 
-`RecruitSolver` calculates recruitment tag results and applies the saved selection policy before queuing tag selection.
+`RecruitSolver` calculates recruitment tag results, applies the saved selection policy before queuing tag selection, and records operators obtained from completed slots.
 
 ## 2. Selection Policy
 
@@ -12,6 +12,16 @@
 
 - <a id="manual-selection-authority"></a>**Manual Selection Authority**: Manual five-star recruitment never queues automatic selection unless the unique-choice exception is enabled and exactly one calculated choice remains.
 
+### Result recognition before dismissal
+
+The token icon identifies `RECRUIT_AGENT`, but the profession icon can still be obscured by the entrance animation. [`RecruitSolver.recruit_result`](../../arknights_mower/solvers/recruit.py) requires a recognized profession icon before cropping and matching the operator name. A missing icon raises `RecognizeError` without recording a result or tapping the display. [`BaseSolver.run`](../../arknights_mower/utils/solver.py) applies its existing consecutive recognition-failure budget and refreshes the observation between attempts. Recruitment adds no separate wait loop or retry counter.
+
+The result handler taps only after recording the name, or when that integer slot already has a recorded result. An already recorded result is not recognized again, and each call sends at most one tap. Cancellation and other recognition or device exceptions propagate to the caller without an extra dismissal tap.
+
+Repeatedly unreadable frames exhaust the existing retry budget and return the partial results under the existing solver behavior. This does not establish that the slot was recognized: the daily scheduler can still record the recruitment run time, and subsequent scene navigation can leave the display. Name-template confidence rules and daily scheduling completion semantics are outside this repair.
+
 ## 4. Verification
 
 [Offline policy tests](../../arknights_mower/tests/recruit_policy_tests.py) cover both modes, both exception states, single and multiple choices, equivalent results and other rarities. Device initialization and notification delivery are replaced with offline substitutes. The [decision](../../.agents/notes/implemented/simplification/2026-10-11-recruit-manual-selection.md) records the condition correction.
+
+[Result tests](../../arknights_mower/tests/recruit_result_tests.py) replay the profession, name and token regions from the October 2, 2026 incident screenshots through the production matcher and result handler. They cover the unreadable animation frame, successful recognition of Lava on the following frame, integer-slot deduplication, failure propagation and the existing bounded retry path. Device input, waits and notification delivery use offline substitutes; no live game timing is verified.
```
