# 测试目录局部约束

继承[后端测试约束](../AGENTS.md#3-testing-discipline)，从 [README](README.md) 选择行为范围。

- 调度测试的导入链可能经 `cultivate_depot`、`skland` 发起网络请求。新增测试先检查导入副作用，参考 `base_scheduler_tests.py` 的隔离边界；测试目标中的调度决策保持真实。
- 需要关闭维护窗口查询时，复用 [conftest.py](conftest.py) 的 `offline_maintenance`。测试旧布尔适配或延迟画面时，按实际场景复用 `legacy_selection_conf`、`low_frame_rate`，避免依赖本机已保存的显式模式或平台默认值。
- 改动 `config.conf`、模块全局状态或 `sys.modules` 时限定替换范围，使用 fixture、`monkeypatch` 或 `patch` 的恢复机制；新增隔离不应把状态遗留给后续测试。
- 治理检查回归使用临时仓库和实际 CLI 验证比较范围。源码或测试路径的校验保持静态，不导入目标来确认引用。
