---
name: mower-prose-standard
description: Use when writing or reviewing Arknights Mower formal prose, including documentation, skills, templates, PR or commit text, reports, comments, docstrings and UI copy. Preserve precise current facts; ordinary wording changes do not create records or glossary entries.
compatibility: Requires an Arknights Mower checkout and its repository contracts; this is a repository-local skill, not a standalone distribution.
---

# Mower Prose Standard

## Inputs and Output

Inputs: requested text and its authoritative role. Output: precise prose or read-only findings. Keep meaning and domain terms unless a semantic change is explicitly part of the request.

## Prose Review

1. Before drafting, use the [business-wording lookup](references/mower-terminology-guide.md#business-wording) to identify the existing names for the affected objects, operations, conditions and results. Read the relevant bilingual entries and owning business sources; carry the selected wording, meanings and sources into any handoff. Reuse these sources within the task; reload them when the source version or writing scope changes.
2. Apply the [placement rules](../mower-doc/references/doc-hierarchy.md#routing-rules). Definitions identify concepts; behavior rules state observable guarantees; procedures describe actions. Refer to business rules by behavior names and direct links to their owning subsystem description.
3. State the actual subject, action and object, then retain conditions and results needed to understand the fact. Use present tense for current rules. Name whose responsibility or which boundary a modifier describes. Keep conditions, exceptions and failure consequences; connect adjacent sentences by their actual causal, conditional or parallel relationship. For Chinese writing or translation, apply [中文表达](#chinese-prose) when choosing words and reviewing the draft.
4. At the first reference to a project document in standalone prose, use its approved name, explain its purpose for the current matter and link to the relevant file or section. The [Arknights Mower Coding Standards](../../../CODING_STANDARDS.md) define shared behavior rules, concurrency and resource requirements, and verification requirements; identify the relevant requirements when referencing them. Repository prose uses relative links; published PRs use the reviewed commit's accessible links. Later references may use a clear short name.
5. Separate final facts from work records. Decision rationale and postmortem history keep their authoritative role. Preserved quotations and test counterexamples need an explicit label and source, separate from current recommendations. Keep real code identifiers unchanged; backticks or code fences alone do not establish an exception.
6. Verify affected links and run the applicable [text checks](../../../scripts/README.md#formal-text-checks). Program results establish listed-term absence and source-marker validity; a reviewer still checks meaning, title scope and source relevance. Prose editing alone creates no record or lifecycle transition.

<a id="public-security-metadata"></a>
## Public Security Metadata

When the user or repository context marks a security issue as sensitive, embargoed or unsuitable for public disclosure, treat PR titles and bodies, Changelog entries, commit messages, branch names, review replies, CI annotations and public links as public metadata. Apply the disclosure boundary before selecting facts or drafting text.

1. Do not disclose the vulnerability class, severity, affected endpoint or sink when it identifies the weakness, attacker prerequisites, exploit chain, payload or proof of concept, secret values, or language confirming that a missing control existed. A user request to omit one sensitive issue from PR text also applies to the other public metadata for the same change unless the user explicitly sets a narrower boundary.
2. Use neutral but truthful wording about the maintained behavior, compatibility boundary or validation result. Do not claim that the change has no security impact or otherwise replace omitted facts with a false statement. Keep exact technical details in the implementation, focused tests and an authorized private disclosure channel; omission from public prose never authorizes weaker implementation or verification.
3. Before publishing, review the complete public metadata set for indirect disclosure through titles, examples, filenames, links or combined statements. Neutral metadata does not conceal the public Git diff. If publishing the requested branch, commit or PR would itself expose details outside the accepted disclosure boundary, stop and recommend a private security advisory or embargoed coordination instead.

<a id="chinese-prose"></a>
## 中文表达

1. 用词前核对它在当前语境中的含义和搭配，确认读者能辨认它指的事物或操作。生硬的逐词翻译、含义不明的抽象说法和内部标签先还原为实际含义，再按文本用途组织中文；描述操作时说明谁在什么条件下做什么、结果怎样。保留来源已明确的具体名称，并结合上下文写明它指代的对象及操作。界面名称放进实际操作中，交代程序或用户点击、设置或看到什么；名称本身不能代替动作。次数和数量说明对应的动作或事物，增减写明变化的量；重复执行或等待设有上限时，再说明每次实际做什么、什么情况下计数，以及达到上限后怎样处理。
2. 说明故障时，用已核实的业务操作和结果交代触发条件、程序的错误判断或动作及后果，再说明本次修复改变了什么。界面文案和内部状态名用于定位，按当前业务含义解释；涉及等待时，写出谁执行了什么操作、正在等待什么结果，以及程序何时继续或报错；界面表现与问题有关时，交代期间显示什么。只展开理解问题所需的交互过程。区分现场观察、实现推导与尚未定位的根因，更深原因未知时保留已知过程与影响。
3. 逐句检查语序、主谓宾、所属关系、修饰语和指代是否符合中文习惯。套用英语语序、介词或连词而造成关系不清时，按实际的条件、因果、先后或并列关系重组；拆开过长的定语，把关系不清的名词堆叠展开为对象关系或具体动作，补齐必要的动词、宾语中心词和连接词。精简时删除不影响理解的整项细节，保留事实成立所需的条件和例外。
4. 项目正式术语按术语来源使用，真实标识保留原名。其余对象沿用用户和项目已有的称呼，不能仅为写中文而另译已有英文名称。需要选择新称呼时，技术词和工具、功能、栏目名称在英文更准确、通行或便于辨认时优先英文，中文已有自然且同样准确的常用表达时按语境选择。英文名称进入中文句子后，语序、连接和修饰关系仍按中文习惯组织。核对疑似直译时，判断含义、搭配和整句是否自然，不能只凭词源或陌生感判错。成稿脱离原文通读，从句子本身辨认名称所指的对象、实际动作及必要的先后或因果关系；出现重复执行次数时，能指出每次计数的内容。需要借助来源才能补全这些内容时，先补查事实，再重写相关句子；程序扫描只检查指定格式和术语，中文是否自然仍需语义复核。

## Completion

The text states its intended facts clearly, uses existing business wording with its sourced meaning and boundaries, preserves approved meaning and uses valid links. Review wording reuse through the [same lookup](references/mower-terminology-guide.md#business-wording); program checks do not establish it. Report actual semantic changes rather than treating wording improvements as new guarantees.
