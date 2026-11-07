# 原始材料

来源提交：`e23513ed541cce042e6c180e5aa38170253abd11`。

本次范围仅为该提交与其父提交的差异。不使用旧提交标题或业务说明正文作为写作输入。

相邻历史材料：[前一条提交的材料](recruit-premature-dismissal.md)。它用于理解基线，不属于本次提交范围。

## 历史检查记录

以下记录来自来源提交当时的正文，仅保留检查结果与证据限制，不代表本轮实际执行。

公招相关五个离线测试文件通过37项测试，Ruff、格式及文档结构检查通过。
没有实机时序验证。

## 完整 diff

```diff
diff --git a/arknights_mower/solvers/recruit.py b/arknights_mower/solvers/recruit.py
index 6db16e5da..9de461613 100644
--- a/arknights_mower/solvers/recruit.py
+++ b/arknights_mower/solvers/recruit.py
@@ -16,7 +16,7 @@ from arknights_mower.utils.email import recruit_rarity, recruit_template, send_m
 from arknights_mower.utils.graph import SceneGraphSolver
 from arknights_mower.utils.image import cmatch, cropimg, loadres, thres2
 from arknights_mower.utils.log import logger
-from arknights_mower.utils.recognize import RecognizeError, Recognizer, Scene
+from arknights_mower.utils.recognize import Recognizer, Scene
 from arknights_mower.utils.resource_pkg import (
     register_resource_reload,
     resource_pkg_path,
@@ -329,12 +329,19 @@ class RecruitSolver(SceneGraphSolver):
             self.tap((950, 150))
             return
 
-        job_pt = None
-        for i in job_list:
-            if job_pt := self.find(i):
+        for attempt in range(5):
+            job_pt = None
+            for i in job_list:
+                if job_pt := self.find(i):
+                    break
+            if job_pt is not None:
                 break
-        if job_pt is None:
-            raise RecognizeError("公招干员职业图标尚未识别")
+            if attempt < 4:
+                self.sleep(1)
+        else:
+            logger.warning("公招干员职业图标连续5次未识别，结束本次公招")
+            self.recog.update()
+            return True
 
         img = cropimg(self.recog.gray, ((job_pt[1][0], 730), (1800, 860)))
         img = cv2.threshold(img, 220, 255, cv2.THRESH_BINARY)[1]
diff --git a/arknights_mower/tests/recruit_result_tests.py b/arknights_mower/tests/recruit_result_tests.py
index f9723b4a9..8aaf8c00a 100644
--- a/arknights_mower/tests/recruit_result_tests.py
+++ b/arknights_mower/tests/recruit_result_tests.py
@@ -1,11 +1,12 @@
 from pathlib import Path
-from unittest.mock import Mock
+from unittest.mock import Mock, call
 
 import cv2
 import numpy as np
 import pytest
 
 from arknights_mower.solvers import recruit
+from arknights_mower.utils import solver as base_solver
 from arknights_mower.utils.csleep import MowerExit
 from arknights_mower.utils.recognize import RecognizeError, Recognizer, Scene
 
@@ -33,12 +34,13 @@ def make_solver(state="animation"):
 
 def test_result_without_profession_keeps_display_open():
     solver = make_solver()
+    solver.sleep = Mock()
     assert solver.find("recruit/agent_token") is not None
     assert all(solver.find(name) is None for name in recruit.job_list)
 
-    with pytest.raises(RecognizeError, match="职业"):
-        solver.transition()
+    assert solver.transition() is True
 
+    assert solver.sleep.call_args_list == [call(1)] * 4
     assert solver.result_agent == {}
     assert solver.recruit_index == 1
     solver.tap.assert_not_called()
@@ -46,6 +48,7 @@ def test_result_without_profession_keeps_display_open():
 
 def test_ready_result_is_recorded_before_one_dismissal():
     solver = make_solver("ready")
+    solver.sleep = Mock()
     records_at_tap = []
     solver.tap.side_effect = lambda *_: records_at_tap.append(dict(solver.result_agent))
 
@@ -54,6 +57,7 @@ def test_ready_result_is_recorded_before_one_dismissal():
     assert solver.result_agent == {1: "炎熔"}
     assert records_at_tap == [{1: "炎熔"}]
     solver.tap.assert_called_once_with((500, 500))
+    solver.sleep.assert_not_called()
 
 
 def test_recorded_integer_slot_is_not_recognized_again():
@@ -112,12 +116,13 @@ def prepare_run(monkeypatch, solver, scenes):
     return notify
 
 
-def test_run_retries_animation_then_records_ready_frame(monkeypatch):
+@pytest.mark.parametrize("ready_attempt", [2, 4, 5])
+def test_run_retries_animation_then_records_ready_frame(monkeypatch, ready_attempt):
     solver = make_solver()
     notify = prepare_run(
         monkeypatch,
         solver,
-        [Scene.RECRUIT_AGENT, Scene.RECRUIT_AGENT, Scene.RECRUIT_MAIN],
+        [Scene.RECRUIT_AGENT, Scene.RECRUIT_MAIN],
     )
     observations = []
 
@@ -125,31 +130,89 @@ def test_run_retries_animation_then_records_ready_frame(monkeypatch):
         observations.append(
             (interval, dict(solver.result_agent), solver.tap.call_count)
         )
-        solver.recog._gray = result_frame("ready")
 
-    solver.sleep = Mock(side_effect=next_frame)
+    wait = Mock(side_effect=next_frame)
+    monkeypatch.setattr(base_solver, "csleep", wait)
+
+    def refresh_frame():
+        if wait.call_count == ready_attempt - 1:
+            solver.recog._gray = result_frame("ready")
+
+    solver.recog.update.side_effect = refresh_frame
 
     assert solver.run() == ({}, {1: "炎熔"})
 
-    assert observations == [(3, {}, 0)]
+    assert observations == [(1, {}, 0)] * (ready_attempt - 1)
     solver.tap.assert_called_once_with((500, 500))
     notify.assert_called_once()
 
 
-def test_run_stops_after_existing_recognition_budget(monkeypatch):
+def test_run_stops_after_five_result_attempts_without_final_wait(monkeypatch):
     solver = make_solver()
-    budget = recruit.config.MAX_RETRYTIME
     notify = prepare_run(
         monkeypatch,
         solver,
-        [Scene.RECRUIT_AGENT] * budget + [Scene.RECRUIT_MAIN],
+        [Scene.RECRUIT_AGENT, Scene.RECRUIT_MAIN],
     )
-    solver.sleep = Mock()
+    wait = Mock()
+    monkeypatch.setattr(base_solver, "csleep", wait)
 
     assert solver.run() == ({}, {})
 
-    assert solver.scene.call_count == budget
-    assert solver.sleep.call_count == budget
+    solver.scene.assert_called_once()
+    assert (
+        sum(args[0] == recruit.job_list[0] for args, _ in solver.find.call_args_list)
+        == 5
+    )
+    assert wait.call_args_list == [call(1)] * 4
+    assert solver.recog.update.call_count == 5
     assert solver.recruit_index == 1
     solver.tap.assert_not_called()
     notify.assert_not_called()
+
+
+@pytest.mark.parametrize("error", [MowerExit(), RuntimeError("截图失败")])
+def test_failure_during_result_wait_propagates_without_dismissal(monkeypatch, error):
+    solver = make_solver()
+    notify = prepare_run(monkeypatch, solver, [Scene.RECRUIT_AGENT])
+    wait = Mock(side_effect=error)
+    monkeypatch.setattr(base_solver, "csleep", wait)
+
+    with pytest.raises(type(error)) as caught:
+        solver.run()
+
+    assert caught.value is error
+    wait.assert_called_once_with(1)
+    solver.recog.update.assert_not_called()
+    assert solver.result_agent == {}
+    solver.tap.assert_not_called()
+    notify.assert_not_called()
+
+
+def test_exhausted_result_attempts_preserve_previous_records(monkeypatch):
+    solver = make_solver()
+    solver.result_agent = {2: "炎熔"}
+    notify = prepare_run(monkeypatch, solver, [Scene.RECRUIT_AGENT])
+    monkeypatch.setattr(base_solver, "csleep", Mock())
+
+    assert solver.run() == ({}, {2: "炎熔"})
+
+    assert solver.recruit_index == 1
+    solver.tap.assert_not_called()
+    notify.assert_called_once()
+
+
+def test_other_recognition_failures_keep_shared_retry_behavior(monkeypatch):
+    solver = make_solver()
+    notify = prepare_run(monkeypatch, solver, [Scene.RECRUIT_AGENT] * 5)
+    solver.find = Mock(side_effect=RecognizeError("截图识别失败"))
+    wait = Mock()
+    monkeypatch.setattr(base_solver, "csleep", wait)
+
+    assert solver.run() == ({}, {})
+
+    assert solver.scene.call_count == 5
+    assert wait.call_args_list == [call(3)] * 5
+    assert solver.result_agent == {}
+    solver.tap.assert_not_called()
+    notify.assert_not_called()
diff --git a/docs/subsystems/recruitment.md b/docs/subsystems/recruitment.md
index 9f2440870..6b1a6dda5 100644
--- a/docs/subsystems/recruitment.md
+++ b/docs/subsystems/recruitment.md
@@ -14,14 +14,14 @@
 
 ### Result recognition before dismissal
 
-The token icon identifies `RECRUIT_AGENT`, but the profession icon can still be obscured by the entrance animation. [`RecruitSolver.recruit_result`](../../arknights_mower/solvers/recruit.py) requires a recognized profession icon before cropping and matching the operator name. A missing icon raises `RecognizeError` without recording a result or tapping the display. [`BaseSolver.run`](../../arknights_mower/utils/solver.py) applies its existing consecutive recognition-failure budget and refreshes the observation between attempts. Recruitment adds no separate wait loop or retry counter.
+The token icon identifies `RECRUIT_AGENT`, but the profession icon can still be obscured by the entrance animation. [`RecruitSolver.recruit_result`](../../arknights_mower/solvers/recruit.py) requires a recognized profession icon before cropping and matching the operator name. It checks the current frame immediately and makes at most five attempts for an unrecorded slot. A missing icon leaves the result unrecorded and the display untouched; before each remaining attempt, the handler waits one second and refreshes the observation. The fifth failed attempt clears the observation and ends the recruitment run without another wait or entering the shared recognition-failure retry path. This adds at most four seconds of deliberate waiting, excluding capture and recognition time. Other recognition failures retain [`BaseSolver.run`](../../arknights_mower/utils/solver.py)'s existing retry behavior.
 
 The result handler taps only after recording the name, or when that integer slot already has a recorded result. An already recorded result is not recognized again, and each call sends at most one tap. Cancellation and other recognition or device exceptions propagate to the caller without an extra dismissal tap.
 
-Repeatedly unreadable frames exhaust the existing retry budget and return the partial results under the existing solver behavior. This does not establish that the slot was recognized: the daily scheduler can still record the recruitment run time, and subsequent scene navigation can leave the display. Name-template confidence rules and daily scheduling completion semantics are outside this repair.
+Repeatedly unreadable profession icons exhaust the five result attempts and return partial results under the existing solver behavior. This does not establish that the slot was recognized: the daily scheduler can still record the recruitment run time, and subsequent scene navigation can leave the display. Name-template confidence rules and daily scheduling completion semantics are outside this repair.
 
 ## 4. Verification
 
 [Offline policy tests](../../arknights_mower/tests/recruit_policy_tests.py) cover both modes, both exception states, single and multiple choices, equivalent results and other rarities. Device initialization and notification delivery are replaced with offline substitutes. The [decision](../../.agents/notes/implemented/simplification/2026-10-11-recruit-manual-selection.md) records the condition correction.
 
-[Result tests](../../arknights_mower/tests/recruit_result_tests.py) replay the profession, name and token regions from the October 2, 2026 incident screenshots through the production matcher and result handler. They cover the unreadable animation frame, successful recognition of Lava on the following frame, integer-slot deduplication, failure propagation and the existing bounded retry path. Device input, waits and notification delivery use offline substitutes; no live game timing is verified.
+[Result tests](../../arknights_mower/tests/recruit_result_tests.py) replay the profession, name and token regions from the October 2, 2026 incident screenshots through the production matcher and result handler. They cover the unreadable animation frame, successful recognition of Lava on the second, fourth or fifth attempt, integer-slot deduplication, failure propagation, cancellation during a wait, exactly five failed result attempts with four one-second waits, and unchanged shared retry behavior for other recognition failures. Device input, waits and notification delivery use offline substitutes; no live game timing is verified.
```
