# 原始材料

来源提交：`526f2f15535b8dd8d6bc6e643ed2e9820667a0ea`。

比较基线：`5094013c11240075cd00910cc894148c47d45754`，即来源提交的父提交。

本次范围仅为该提交与上方基线的差异。不使用旧提交标题或业务说明正文作为写作输入；差异中的实现记录和检查结果属于历史材料，不代表本轮实际执行。

## 完整 diff

```diff
diff --git a/.agents/notes/implemented/bug-fix/2026-10-07-base-report-field-integrity.md b/.agents/notes/implemented/bug-fix/2026-10-07-base-report-field-integrity.md
index b1f2bdd00..5da88be01 100644
--- a/.agents/notes/implemented/bug-fix/2026-10-07-base-report-field-integrity.md
+++ b/.agents/notes/implemented/bug-fix/2026-10-07-base-report-field-integrity.md
@@ -13,7 +13,7 @@ date: 2026-10-07
 
 ## Reading and storage
 
-`ReportSolver.get_number` rescales a field by `29 / 19`, thresholds it and sorts contour bounds by their left edge. Contours with strictly overlapping horizontal ranges form one group, including transitive overlaps. Adjacent ranges remain separate even without an empty column between them. Each group receives a 10 px border before matching the ten shipped `noto_sans` templates. The color masks remain unchanged.
+`ReportSolver.get_number` rescales a field by `29 / 19`, thresholds it and sorts contour bounds by their left edge. Contours with strictly overlapping horizontal ranges form one group, including transitive overlaps. Adjacent ranges remain separate even without an empty column between them. Each group receives a 10 px border before matching the ten shipped `noto_sans` templates.
 
 Separate contours can belong to one digit. Two short cuts in a zero detach its left stroke, which the contour-based reader matches as `1`, while the rest still matches as `0`. Reading each contour independently inserts a digit and changes `80500` to `810500`. Grouping overlapping bounds presents the combined strokes to the matcher once without filling the missing pixels. Strokes with disjoint horizontal ranges remain separate; this repair does not cover every possible break.
 
@@ -21,6 +21,8 @@ Template heights range from 29 to 31 px and widths from 18 to 22 px. OpenCV acce
 
 `match_digit` requires the stamp to contain its candidate template on both axes, returning `None` for incompatible geometry or an OpenCV matching error. `get_number` keeps all usable candidate scores and returns `None` for the complete field when any digit has no score or its best normalized squared-difference score saturates at 1. This prevents an unmatched fragment from becoming zero through a ten-way score tie. An available blank crop still reads as zero; absent anchors and empty crops remain unread. Both color masks use the same cached Capture Frame, and unavailable anchors affect only their dependent fields.
 
+Grey order-count detection accepts the complete OpenCV hue range of 0–179 while retaining saturation 0–100 and value 50–170. A slight tint can give nearly grey pixels a hue above 100. The previous hue cap can remove complete digits and report zero, or preserve only a small fragment that makes the complete field unread. Domain-concept names, meanings, boundaries and relationships remain unchanged.
+
 `record_report` stores every independent reading and serializes unread fields as empty cells. `parse_cell_num` treats those cells as absent. It returns failure before post-storage panel input or email when there are no readings or the CSV append fails. A successful append sets `_stored` before panel input. The initial panel supplies yesterday's readings; the normal post-storage tap expands it to show the last three days. Waiting clears the old Capture Frame cache, and the email attachment reads a fresh frame of the expanded report. Later ordinary notification or panel errors preserve the confirmed result. `read_report` ends after confirmed storage instead of repeating an append following a panel error.
 
 `read_report` permits at most three reads per run; `ReportSolver.run` permits at most three failed runs per process and date. Failed runs leave scheduler `daily_report` unset. A new date resets the outer budget, and successful storage clears accumulated attempts. Cancellation and Device Control recovery propagate through every handler without consuming either budget or replaying uncertain input.
@@ -40,3 +42,7 @@ Unused `remove_blank`, `crop_report_backup` and the `ReportSolver` instance of `
 The same broken 19 px field raises `cv2.error` with the reader before commit `a05a1b0f`, returns `810500` with that commit and returns `80500` after this repair. The October 8 dimension checks let compatible candidates survive a previously fatal shape error, exposing the existing contour-splitting defect as a wrong reading.
 
 The supplied 1280x720 JPEG, resized to 1920x1080, returns an unread gold field in the existing `crop_report` path. It does not reproduce `810500` exactly. The controlled template regression establishes the extra-digit failure mechanism; it does not establish recovery of readings lost through JPEG compression or guarantee recognition of every broken digit. The concept-impact review leaves Capture Frame and base report field names and meanings unchanged.
+
+The order-count JPEG fixture from 2026-10-13 contains a 50x77 px strip showing 37 and 0, extracted after resizing the supplied JPEG to 1920x1080. The hue regression places this strip in a report frame with real anchors and compares the original tint with a brightness-preserving neutral patch inside the first digit. With the previous hue cap, the cases read 0 and `None`, respectively; the complete hue range reads 37 in both cases and preserves the Orundum order count of zero.
+
+The native PNG fixture preserves a 600x510 px report panel at its original position without resizing or changing pixels. Real report cropping reads all six fields: 18000 experience, 61500 gold value, 62500 LMD, 37 LMD orders and both Orundum fields zero. With the earlier contour-based reader at `f1b8d62e4`, the previous hue cap removes ten pixels in the LMD count crop and separates the lower stroke of 3. After scaling and padding, that detached contour is only 27 px high and cannot contain any digit template, so the complete count is unread. Alpha's overlapping-stroke grouping already reads this native PNG as 37 with the previous hue cap; the hue repair preserves the complete strokes and also repairs the two JPEG cases that grouping alone cannot recover. The focused suite passes all 67 cases, including the existing 64 cases.
diff --git a/.agents/notes/implemented/bug-fix/2026-10-07-base-report-field-integrity.zh.md b/.agents/notes/implemented/bug-fix/2026-10-07-base-report-field-integrity.zh.md
index 2968f211d..128244001 100644
--- a/.agents/notes/implemented/bug-fix/2026-10-07-base-report-field-integrity.zh.md
+++ b/.agents/notes/implemented/bug-fix/2026-10-07-base-report-field-integrity.zh.md
@@ -13,7 +13,7 @@ date: 2026-10-07
 
 ## 读取与存储
 
-`ReportSolver.get_number` 按 `29 / 19` 缩放字段，二值化后按轮廓边界的左端排序。横向范围严格相交的轮廓组成一组，包括通过其他轮廓相交的情况。相邻但不相交的范围保持分离，即使两者之间没有空列。每组补 10 px 边框后与随包的十个 `noto_sans` 数字模板匹配。颜色掩码保持不变。
+`ReportSolver.get_number` 按 `29 / 19` 缩放字段，二值化后按轮廓边界的左端排序。横向范围严格相交的轮廓组成一组，包括通过其他轮廓相交的情况。相邻但不相交的范围保持分离，即使两者之间没有空列。每组补 10 px 边框后与随包的十个 `noto_sans` 数字模板匹配。
 
 同一数字可以包含多个独立轮廓。在零上做两处短切口会分离左侧笔画，逐轮廓读取时该笔画被匹配为 `1`，剩余部分仍被匹配为 `0`。分别读取两个轮廓会多插入一位，将 `80500` 变为 `810500`。合并横向相交的边界后，组合笔画只匹配一次，不填补缺失像素。横向范围不相交的笔画仍保持分离；本次修复不覆盖所有断裂情况。
 
@@ -21,6 +21,8 @@ date: 2026-10-07
 
 `match_digit` 要求数字块在两个维度都容纳候选模板，尺寸不兼容或 OpenCV 匹配出错时返回 `None`。`get_number` 保留全部可用候选分数，任一数字没有分数或最佳归一化平方差分数饱和为 1 时，完整字段返回 `None`，防止无法匹配的碎片因十个候选分数相同而被当成零。有效裁剪中的空白仍读作零；缺失锚点和空裁剪保持未读取。两种颜色掩码使用同一份缓存的 Capture Frame，缺失锚点仅影响依赖它的字段。
 
+灰色订单数检测接受 OpenCV 的完整色相范围 0–179，同时保留饱和度 0–100 和明度 50–170 的限制。轻微色偏可以使接近灰色的像素具有超过 100 的色相。原色相上限可能过滤完整数字并读作零，也可能只留下一个小碎片，使完整字段保持未读取。领域概念的名称、含义、边界和关系均未改变。
+
 `record_report` 存储独立读出的每个字段，将未读字段序列化为空单元格。`parse_cell_num` 将这些单元格视为缺失值。没有读数或 CSV 追加失败时，在存储之后的报告界面输入和邮件发送前返回失败。追加成功后，在面板输入之前设置 `_stored`。初始界面用于读取昨日数据；正常存储后的点击展开近三天报告。等待时清除旧 Capture Frame 缓存，邮件附件随后取得展开报告的新截图。后续普通通知或面板错误保留已确认的结果。确认存储后，`read_report` 结束本次读取，不因面板错误重复追加数据。
 
 `read_report` 每次运行最多读取三次；`ReportSolver.run` 在同一进程的同一天最多允许三次失败运行。运行失败时，调度器的 `daily_report` 保持未设置。新日期重置外层预算，存储成功清空累计尝试次数。取消和设备控制恢复通过所有异常处理分支向上传递，不消耗两层预算，也不重放结果未确认的输入。
@@ -40,3 +42,7 @@ date: 2026-10-07
 同一个断裂的 19 px 字段在提交 `a05a1b0f` 之前的读取方法中抛出 `cv2.error`，在该提交中返回 `810500`，本次修复后返回 `80500`。10 月 8 日增加的尺寸检查让兼容候选在原先会终止读取的尺寸错误中继续参与匹配，使既有的轮廓分割缺陷表现为错误读数。
 
 提供的 1280x720 JPEG 放大到 1920x1080 后，现有 `crop_report` 路径将赤金字段读为未读取，没有精确复现 `810500`。受控模板回归确定了多读一位的故障机制，不能据此确认 JPEG 压缩造成的读数丢失已经修复，也不保证所有断裂数字都能识别。概念影响检查确认 Capture Frame 与基建报告字段的名称和含义没有变化。
+
+2026-10-13 的订单数 JPEG 样本在用户提供的 JPEG 放大到 1920x1080 后提取，尺寸为 50x77 px，显示 37 和 0。色相回归将该区域放入带有真实锚点的报告画面，分别读取原色偏样本，以及在首位数字内保留明度、改为中性灰的局部样本。使用原色相上限时，两种情况分别读出 0 和 `None`；完整色相范围在两种情况下均读出 37，并保留合成玉订单数量为零。
+
+原生 PNG 样本按原位置保留 600x510 px 的报告面板，没有缩放或改动像素。真实报告裁剪读出全部六个字段：作战录像 18000、赤金价值 61500、龙门币 62500、龙门币订单数 37，两项合成玉字段均为零。此前提交 `f1b8d62e4` 中的逐轮廓读取方法使用原色相上限时，会过滤订单数裁剪中的十个像素，分离数字 3 的下部笔画。缩放补边后，该独立轮廓只有 27 px 高，不能容纳任何数字模板，因此完整订单数保持未读取。alpha 的横向相交笔画合并在原色相上限下已能将这份原生 PNG 读为 37；色相修复保留完整笔画，并修复仅靠合并仍无法恢复的两个 JPEG 样本。定向测试中的 67 个用例全部通过，其中包含既有的 64 个用例。
diff --git a/arknights_mower/solvers/report.py b/arknights_mower/solvers/report.py
index 6ae78bf72..60ec59b9b 100644
--- a/arknights_mower/solvers/report.py
+++ b/arknights_mower/solvers/report.py
@@ -245,7 +245,8 @@ class ReportSolver(SceneGraphSolver):
         logger.info("蓝字读取完成")
 
         img = cv2.cvtColor(self.recog.img, cv2.COLOR_RGB2HSV)
-        img = cv2.inRange(img, (0, 0, 50), (100, 100, 170))
+        # Grey text can have any hue when capture introduces a slight color tint.
+        img = cv2.inRange(img, (0, 0, 50), (179, 100, 170))
         self.report_res["龙门币订单数"] = self.get_number(
             img, area["iron_order_number"], height=19, thres=200
         )
diff --git a/arknights_mower/tests/base_report_read_tests.py b/arknights_mower/tests/base_report_read_tests.py
index d3502c5cd..f743d0169 100644
--- a/arknights_mower/tests/base_report_read_tests.py
+++ b/arknights_mower/tests/base_report_read_tests.py
@@ -133,6 +133,52 @@ def _order_count_roi(img):
     return ((1820, trade_pt[1][1] + 10), (1870, assist_pt[0][1] - 65))
 
 
+@pytest.mark.parametrize("mixed_hue", [False, True])
+def test_tinted_grey_order_counts_keep_complete_digits(mixed_hue):
+    """A supplied screenshot shows 37 and 0 with a slight blue grey tint."""
+    counts = cv2.imread(
+        str(
+            ROOT
+            / "arknights_mower/tests/fixtures/base_report_order_counts_20261013.png"
+        )
+    )
+    counts = cv2.cvtColor(counts, cv2.COLOR_BGR2RGB)
+    if mixed_hue:
+        # Preserve brightness while making a small part of the first digit neutral.
+        # A hue-limited mask retains only that fragment and leaves the count unread.
+        patch = counts[3:8, 5:10]
+        patch[:] = patch.max(axis=2, keepdims=True)
+    img = _report_frame()
+    img[463:540, 1820:1870] = counts
+    solver = _solver_for(img)
+
+    solver.crop_report()
+
+    assert solver.report_res["龙门币订单数"] == 37
+    assert solver.report_res["合成玉订单数量"] == 0
+
+
+def test_native_report_png_reads_all_fields():
+    """Replay the unscaled PNG panel through real anchor and digit recognition."""
+    panel = cv2.imread(
+        str(ROOT / "arknights_mower/tests/fixtures/base_report_panel_20261013.png")
+    )
+    img = np.zeros((1080, 1920, 3), np.uint8)
+    img[120:630, 1300:1900] = cv2.cvtColor(panel, cv2.COLOR_BGR2RGB)
+    solver = _solver_for(img)
+
+    solver.crop_report()
+
+    assert solver.report_res == {
+        "作战录像": 18000,
+        "赤金": 61500,
+        "龙门币订单": 62500,
+        "龙门币订单数": 37,
+        "合成玉": 0,
+        "合成玉订单数量": 0,
+    }
+
+
 def test_degenerate_contour_does_not_abort_the_whole_read():
     """A 4x4 speck used to raise cv2.error out of crop_report."""
     img = _report_frame()
diff --git a/arknights_mower/tests/fixtures/base_report_order_counts_20261013.png b/arknights_mower/tests/fixtures/base_report_order_counts_20261013.png
new file mode 100644
index 000000000..4cafa70de
Binary files /dev/null and b/arknights_mower/tests/fixtures/base_report_order_counts_20261013.png differ
diff --git a/arknights_mower/tests/fixtures/base_report_panel_20261013.png b/arknights_mower/tests/fixtures/base_report_panel_20261013.png
new file mode 100644
index 000000000..d34163d55
Binary files /dev/null and b/arknights_mower/tests/fixtures/base_report_panel_20261013.png differ
```
