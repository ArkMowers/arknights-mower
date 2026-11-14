# Controlled Terminology Sources

[Arknights Mower Domain Glossary](../../../../CONTEXT.md) and its [Chinese mirror](../../../../CONTEXT.zh.md) define canonical domain names, development/documentation expressions, document names and Avoid lists. Read the affected entries directly rather than copying tables into another document.

[Concept Impact Review](../../../../CODING_STANDARDS.md#concept-impact-review) governs concept-impact assessment. [Documentation routing](../../mower-doc/references/doc-hierarchy.md#routing-rules) separates definitions from execution rules. [Root directives](../../../../AGENTS.md#4-global-execution-constraints) own exact glossary approval.

For ordinary expressions, state the concrete subject, condition and result without inventing a glossary entry. When a stable domain concept is new or its name, meaning, boundary or relationships change, locate its existing owner first, then prepare the exact bilingual diff and explain the change for explicit user approval. Keep the proposal outside the glossary until approved; continue independent work. Approval applies only to the exact approved text. The Avoid-term checker establishes listed-term absence, not semantic equivalence or approval.

<a id="business-wording"></a>
## 业务用语查找与复用

查词范围包括正式术语，以及项目已经使用、维护但未收入术语表的业务称呼。按本次写作对象查找，不另建或复制通用词表。

1. 从需求、实际调用者和行为变化确定需要命名的业务对象、操作、条件与结果。用它们的含义和已知称呼检索，不能只按函数名翻译或选择通用类别。
2. 正式概念读取受影响的双语术语条目；其他业务表达通过[Mower 文档导航](../../../../docs/README.md)和[Arknights Mower 系统架构说明](../../../../docs/architecture.md)找到负责该业务的维护文档，再核对对应版本的界面名称、配置项、提示、调用者、日志及测试。读取用语所在上下文，确认它指什么、适用于哪一步及哪些条件。历史记录只用于辨认旧含义，不能覆盖当前定义；本次新增或未提交的措辞须单独标明，不能用来证明此前已有该称呼。
3. 在任务材料或交接中保留本次选用的业务用语、它指代的对象或行为及适用边界、原始来源与版本。只记录本次写作所需项目，含义引用来源，不复制整份定义。多个说法并存时，依据现行定义、维护中的具体业务和本次范围选择；来源冲突或缺失时标明待核实部分。
4. 写作者回读这些必要来源，将含义匹配的已有业务用语放进完整的操作关系，按[中文表达方法](../SKILL.md#chinese-prose)补齐对象、动作及必要条件。复核时从成稿反查：同一业务对象和操作的称呼是否一致，已有具体说法是否被更泛或新造的说法替换。需要更换时，说明原称呼为何不适用、容易误解或含义已经变化；涉及稳定概念变更时仍按根指令准备审批，不把普通用词选择变成术语表修改。
