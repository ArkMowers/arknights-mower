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

<a id="formal-text-checks"></a>
## 正式文本检查

术语来源为 [Arknights Mower 项目术语表](../CONTEXT.zh.md)及其[英文版](../CONTEXT.md)，它们定义业务概念、项目文档名称和开发、文档用语。共享写作方法见 [mower-prose-standard](../.agents/skills/mower-prose-standard/SKILL.md)。

`verify_governance.py` 检查 notes、docs、后端与前端注释，以及 skills、模板和根指令。既有业务避免用语始终检查；开发与文档用语从比较提交与 HEAD 的共同祖先到当前工作区检查新增行，包含暂存、未暂存和未跟踪文件。共同祖先早于对应规范的历史兼容起点时，从该起点检查新增行；尚未合入的上游变化不计为当前分支的新增文字。未指定比较提交时使用 HEAD；非 Git 目录检查全部文本。既有开发表述单独报告，不能据此声称全文没有避免用语。

<a id="policy-comparison-history"></a>
### 规范生效前的历史兼容

[governance_baselines.json](governance_baselines.json) 保存旧格式规范和开发、文档用语规范上线前的固定提交，分别供 [Note 检查](verify_agent_note_format.py)和[术语检查](verify_glossary_alignment.py)使用。长期分支的比较提交可能早于规范上线；检查器先取比较提交与 HEAD 的共同祖先，再在共同祖先早于相应起点时使用该起点判断新增内容。较新的共同祖先继续作为比较起点。两个固定提交分别保留各自规范上线前的历史，不能随着本次 HEAD 移动。

原始比较提交继续决定[决策记录引用检查](../.agents/notes/README.md#references-and-verification)的变化范围。文档结构、链接、既有业务避免用语及完整 PR 标题正文仍执行原有检查。起点配置格式无效、提交不可用、起点不属于 HEAD 历史或两者历史无法比较时，检查失败；CI 保留完整 Git 历史。未带起点配置的隔离测试仓库沿用其指定比较提交。

PR 标题或正文每次编辑前，将完整成稿存为含 `title`、`body` 字符串的 JSON 并执行：

```bash
python scripts/verify_glossary_alignment.py --pr-json <draft.json>
```

发布后用 `gh pr view <PR> --json title,body,headRefOid` 回读，再扫描保存的 JSON。`verify_governance.py --pr-json <draft.json>` 可同时检查仓库与成稿。CI 从事件载荷读取完整标题正文，`edited` 事件也触发检查；GitHub 事件中正文为 null 时按空正文扫描，其他非字符串正文仍报错。正文直接作为数据读取，不插入 shell 命令。PR 成稿检查全部文本，包括代码块及反引号中的文字。

保留的历史原文和测试反例通过 [prose_sources.json](prose_sources.json) 标注种类、用途、文件行范围、不可变来源文件链接及规范化换行后的 SHA-256。只有摘要匹配的范围保留原词，周围正文继续检查；新增来源先核实原文，不能借标记保留当前推荐中的避免用语。程序核对标记、范围和内容摘要，来源是否相关、是否确为历史引用或反例仍需审阅。真实代码标识保持原名；程序扫描代码注释和 docstrings，代码字符串和标识本身不作为正文。

真实 Python 标识的正文引用可使用 `code-identifier` 来源记录，补充 `identifier` 与 `source_path`。程序静态核对声明，只保留该范围中完全相同的行内代码标识，周围文字继续检查；不导入业务模块。其他语言或无法静态确认的引用仍须人工判断，不能用反引号整体豁免。

PR 正文中确需保留来源原文时，用单独的 `<!-- mower-prose-source {JSON} -->` 和 `<!-- /mower-prose-source -->` 包围原文。JSON 提供相同的 `kind`、`label`、`source`、`sha256`，代码标识另提供上述两个字段；行范围由标记确定。摘要按两条标记之间的原文计算。标题没有来源范围豁免；正文周围的正式文字及标记中的说明继续检查。标记必须成对且不能嵌套。

扫描不判断主体是否明确、标题是否代表完整范围或新业务概念是否需要词条。Agent 按共享写作方法完成这些判断；实际词条改动仍须按根指令展示中英文 diff 并取得明确批准。
