# 仓库工具脚本

这里包含文档检查、构建打包和资源维护工具。按当前任务选择脚本；生产行为入口见[后端地图](../arknights_mower/README.md)。

| 任务 | 入口 | 验证与边界 |
| :--- | :--- | :--- |
| 文档与决策结构、引用和禁用词检查 | [verify_governance.py](verify_governance.py)；内部调用 [Note 检查](verify_agent_note_format.py)、[链接检查](verify_doc_links.py)、[术语检查](verify_glossary_alignment.py) | [治理回归](../arknights_mower/tests/verify_governance_tests.py)；检查范围见[代理验证流程](../.agents/AGENTS.md#4-verification-and-reporting) |
| Android 运行环境与热更新包 | [build_android_runtime.py](build_android_runtime.py)、[package_android.py](package_android.py)、[check_android_package.py](check_android_package.py) | [运行包回归](tests/android_release_tests.py) |
| Android 发布链接衔接 | [sync_android_release.py](sync_android_release.py) | [发布流程回归](tests/release_workflow_tests.py)；链接独立 Android 宿主的发行页面 |
| macOS ADB 与应用包检查 | [prepare_macos_adb.py](prepare_macos_adb.py)、[check_macos_app.py](check_macos_app.py) | 按实际产物和平台验证打包结果 |
| 识别模型合并与版本注入 | [collapse_recognition_models.py](collapse_recognition_models.py)、[inject_version.py](inject_version.py) | 修改前检查实际构建调用者和输出文件 |

文档检查从仓库根目录执行：

```bash
python scripts/verify_governance.py --base <comparison-commit>
```

分支审查使用真实比较提交；输出只说明机械检查的结果。构建、生成和发布脚本会产生或更新产物，查看脚本及其工作流调用者后再用于对应任务。
