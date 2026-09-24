# 会客室实机截图

`clue_live_*.png` 于 2026-09-24 从本机 MuMu 模拟器通过 ADB `exec-out screencap -p` 获取，分辨率为 1920×1080。它们保留完整画面，以便 `Recognizer` 按运行时相同的区域和模板识别。

- `clue_live_room_details.png`：进入会客室后的放大视角，无产物提示。
- `clue_live_receive_before.png`：打开接收线索列表，领取前无提示。
- `clue_live_credit_prompt.png`：领取一条好友线索后，右上角出现信用提示。
- `clue_live_receive_after.png`：同一界面上提示消失后的画面。

实机测试读取这些帧，确认提示出现时识别成功、消失后不再误报，并验证等待流程能继续执行。
