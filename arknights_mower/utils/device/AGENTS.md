# 设备子目录修改入口

继承[后端约束](../../AGENTS.md)。从本目录 [README](README.md) 找到实际调用者和定向测试，再读取与改动对应的[设备控制规范](../../../docs/subsystems/device-control.md)。

- 修改 `DeviceControl` 的结果或取消、关闭行为时，检查 `server.py` 与 `arknights_mower/__main__.py` 中的调用者，并核对相应的调用者、路由或关闭回归。
- 修改会话决策时，沿 `session.py` 的 `SessionADB`、`Simulator` 协议检查 `session_io.py` 的生产实现；改变外部命令或预算时，复核对应 I/O 回归，而不只测试决策替身。
- 添加或改变模拟器预设时，按[预设操作步骤](../../../docs/cookbook/adding-simulator-preset.md)核对发现、绑定、生产 I/O 和 UI 入口。
- 截图或输入后端变动跨出本目录时，继续检查识别、HTTP 预览或 solver 的真实使用路径；从[测试导航](../../tests/README.md)选择对应回归。
