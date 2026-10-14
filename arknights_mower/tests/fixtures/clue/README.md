# 会客室实机截图

`clue_live_*.png` 于 2026-09-24 从本机 MuMu 模拟器通过 ADB `exec-out screencap -p` 获取，分辨率为 1920×1080。它们保留完整画面，以便 `Recognizer` 按运行时相同的区域和模板识别。

- `clue_live_room_details.png`：进入会客室后的放大视角，无产物提示。
- `clue_live_receive_before.png`：打开接收线索列表，领取前无提示。
- `clue_live_credit_prompt.png`：领取一条好友线索后，右上角出现信用提示。
- `clue_live_receive_after.png`：同一界面上提示消失后的画面。
- `clue_live_party_before.png`：会客室右上角线索交流详情收起，显示“查看”入口。
- `clue_live_party_time.png`：点击“查看”后显示“剩余时间 18:46:14”；这是实际 `read_party_time()` 读取的区域。

实机测试读取这些帧，确认提示出现时识别成功、消失后不再误报，验证等待流程与线索交流倒计时读取。

`clue_access_record_video.png` 是用户提供的视频截图，显示打开信息板后的上周“访问记录”结算页。图中有水印和字幕，画面比例也不同于标准设备截图。[信用领取测试](../../clue_credit_tests.py) 使用真实 OCR 验证原图、缩放至 1920×1080 的图像及普通会客室负例。该素材只能验证文字识别，不能证明弹窗自行消失或实际点击后的状态转换；点击流程另以离线画面序列验证。
