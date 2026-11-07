# 换人按钮与等待处理的给定材料

本材料供离线写作演练使用。所有运行结果均为给定记录，不是写作时重新执行。

## 原始操作与实现

- 在房间选好干员后，程序通过游戏中的“确认”按钮提交房间安排。普通选人、训练室和二次确认使用三个不同识别资源，原图中的按钮文字均为“确认”。
- 游戏处理安排时可能显示“正在提交反馈至神经……”，期间进驻信息可能仍是旧驻员。提示消失只表示当前识别场景改变，仍需读取实际驻员判断换人是否完成。
- 修改前后都按按钮资源逐个处理；每个资源有一个最多执行 12 轮的循环。每进入一次循环计一轮，该轮可能查找按钮、执行点击、等待按钮淡出或检查后续画面。实际点击另行计数，不与 12 轮混用。
- 修改前循环遇到提交提示后等待 1 秒并进入下一轮，因此同一提示持续出现也会消耗这个循环上限。用尽 12 轮时报告“干员确认画面仍未稳定，返回房间重试”。这段行为来自旧版源码推导，未运行旧版对照。
- 修改后保留此循环，遇到提示时在当前轮调用已有场景等待方法。该方法读取“等待时间”中的“截图间隔”和“等待次数”，每次先等待相应秒数，再检查场景是否改变；改变则返回按钮处理，次数用尽仍相同则失败。该方法内部的重复等待不再逐次消耗外层循环轮数。
- 原有默认值未变：“正在提交反馈至神经……”为 1 秒／10 次，“加载中”为 2 秒／30 次。等待超时会退出游戏、等待 3 秒并检查游戏前台状态，再向调用者返回失败。没有保证修复后在所有配置下都等待更久。
- 房间异常返回原来直接按返回，修改后先处理仍在提交或加载的场景，普通画面才按返回。后续仍读取实际驻员：目标已在岗则完成对应房间，否则按原调用者边界处理；普通排队任务保留对象、时间和未完成安排，不增加延迟任务。

## 给定证据和恢复条件

- 新增离线测试把场景等待设置为 1 秒／20 次，连续输入 13 帧提交画面。覆盖提示出现在按钮点击前后及有无二次确认，修改后可以继续处理按钮且不重复提交；旧版按源码推导会在这些提交帧处理完之前耗尽 12 轮。
- 将场景等待次数设为 3，持续相同画面，离线用例验证超时、退出游戏和恢复，不报告成功。房间异常用例另覆盖完成、超时、取消及提交和加载反复切换，失败时仍保留任务。
- 现场训练室两张原图分别显示提示存在且仍为旧驻员、提示消失且驻员已更换。未提供修复后的实机记录、抓包、网络监控或服务器日志，不能定位提交变慢发生在哪一网络环节。
- 回退代码不会还原游戏已经接受的安排，恢复需重读实际驻员并核对原任务；没有独立数据修复或迁移。

## 原始来源

- 审阅版本为 `62fb2c0b7cd0881a82b2a0872118baddffb8ad9f`，对照为 `3ec11ca6d652202eb94c6f64e9675f800a33181f`。对应仓库资源与实现均在这两个提交可核对。
- [修改前按钮处理](https://github.com/NiceAfternoon/arknights-mower/blob/3ec11ca6d652202eb94c6f64e9675f800a33181f/arknights_mower/solvers/base_schedule.py#L8945-L8999)与[修改后按钮处理](https://github.com/NiceAfternoon/arknights-mower/blob/62fb2c0b7cd0881a82b2a0872118baddffb8ad9f/arknights_mower/solvers/base_schedule.py#L8945-L8999)：`tap_confirm`；[等待实现](https://github.com/NiceAfternoon/arknights-mower/blob/62fb2c0b7cd0881a82b2a0872118baddffb8ad9f/arknights_mower/utils/solver.py#L876-L890)：`waiting_solver`。
- [等待设置](https://github.com/NiceAfternoon/arknights-mower/blob/62fb2c0b7cd0881a82b2a0872118baddffb8ad9f/ui/src/pages/Settings.vue#L357-L387)；[默认值](https://github.com/NiceAfternoon/arknights-mower/blob/62fb2c0b7cd0881a82b2a0872118baddffb8ad9f/arknights_mower/utils/config/conf.py#L147-L153)：`WaitingSceneConf`。
- 按钮资源：[confirm_blue.png](https://github.com/NiceAfternoon/arknights-mower/blob/62fb2c0b7cd0881a82b2a0872118baddffb8ad9f/arknights_mower/resources/confirm_blue.png)、[confirm_train.png](https://github.com/NiceAfternoon/arknights-mower/blob/62fb2c0b7cd0881a82b2a0872118baddffb8ad9f/arknights_mower/resources/confirm_train.png)、[arrange_confirm.png](https://github.com/NiceAfternoon/arknights-mower/blob/62fb2c0b7cd0881a82b2a0872118baddffb8ad9f/arknights_mower/resources/arrange_confirm.png)；提示资源：[connecting.png](https://github.com/NiceAfternoon/arknights-mower/blob/62fb2c0b7cd0881a82b2a0872118baddffb8ad9f/arknights_mower/resources/connecting.png)。
- [专项测试](https://github.com/NiceAfternoon/arknights-mower/blob/62fb2c0b7cd0881a82b2a0872118baddffb8ad9f/arknights_mower/tests/navigation_feedback_tests.py)、[异常恢复测试](https://github.com/NiceAfternoon/arknights-mower/blob/62fb2c0b7cd0881a82b2a0872118baddffb8ad9f/arknights_mower/tests/room_retry_dispatch_tests.py)及[原图回放](https://github.com/NiceAfternoon/arknights-mower/blob/62fb2c0b7cd0881a82b2a0872118baddffb8ad9f/arknights_mower/tests/training_submission_tests.py)。
