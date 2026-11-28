# 原始材料

来源提交：`55f8233eb85ca39af66e967c003330056b52db2c`。

比较基线：`ba3621f84c3d3c87fb9594ccba208ae7e928dfa6`，即来源提交的父提交。

本用例在项目仓库内执行。读取两版原文与完整差异：

```text
git diff ba3621f84c3d3c87fb9594ccba208ae7e928dfa6 55f8233eb85ca39af66e967c003330056b52db2c
git show 55f8233eb85ca39af66e967c003330056b52db2c:arknights_mower/utils/character_recognize.py
git show ba3621f84c3d3c87fb9594ccba208ae7e928dfa6:arknights_mower/utils/character_recognize.py
```

对象和操作通过该版本的调用者定位：从 `operator_list_train` 的调用入口追到 `arknights_mower/solvers/base_schedule.py` 及其房间选择逻辑。`arknights_mower/data/__init__.py` 和配置中的设施映射用于核实所在设施。

相关行为说明与原始画面证据位于同版本的 `docs/subsystems/base-scheduler.md`、`arknights_mower/tests/training_tail_name_tests.py` 和差异中新增的识别记录。它们用于核实坐标范围、干员身份匹配和原有选人流程各自的角色。

不使用旧提交标题或业务说明正文作为写作输入。来源记录中的检查结果属于历史材料，不代表本轮实际执行。
