# 定向离线测试导航

从仓库根目录运行与改动行为有关的测试文件。例如：

```bash
python -m pytest arknights_mower/tests/device_session_tests.py -q
```

Windows 工作区已有 `venv` 时，可使用 `venv\Scripts\python.exe`。前端测试从 [ui/](../../ui/README.md#修改入口与定向验证) 运行。

| 行为范围 | 测试入口 |
| :--- | :--- |
| 设备会话与真实调用边界 | [会话决策](device_session_tests.py)、[生产 I/O](device_session_io_tests.py)、[调用者](device_session_caller_tests.py) |
| 截图、恢复及识别与预览的联动 | [会话截图恢复](screenshot_session_recovery_tests.py)、[截图管线](screenshot_pipeline_tests.py)、[离线联动](screenshot_integration_tests.py) |
| 基建计划、状态与宿舍释放 | [调度](base_scheduler_tests.py)、[宿舍释放](dorm_release_tests.py)、[释放失败](emergency_release_failure_tests.py) |
| 资源版本与 OTA | [资源版本](resource_version_tests.py)、[OTA](resource_ota_tests.py)、[资源生成](resource_generation_tests.py) |
| 文档治理与记录迁移 | [治理回归](verify_governance_tests.py)、[记录迁移](archive_agent_note_tests.py) |

表中入口帮助选择范围，具体测试名和夹具决定覆盖的调用路径与条件。`screenshot_integration_tests.py` 使用离线替身和临时文件验证组件联动；文件名中的 integration 不代表已观察真实设备。离线通过也不能证明游戏操作成功。

新增或修改测试时遵守本目录 [AGENTS.md](AGENTS.md)，共享测试原则见[验证要求](../../CODING_STANDARDS.md#5-verification-discipline)。
