---
name: mower-prose-standard
description: Use when writing or reviewing Arknights Mower formal prose, including documentation, skills, templates, PR or commit text, reports, comments, docstrings and UI copy. Preserve precise current facts; ordinary wording changes do not create records or glossary entries.
compatibility: Requires an Arknights Mower checkout and its repository contracts; this is a repository-local skill, not a standalone distribution.
---

# Mower Prose Standard

## Inputs and Output

Inputs: requested text and its authoritative role. Output: precise prose or read-only findings. Keep meaning and domain terms unless a semantic change is explicitly part of the request.

## Prose Review

1. Read the [terminology guide](references/mower-terminology-guide.md) and the affected bilingual entries before drafting. Reuse these sources within the task; reload them when the source version or writing scope changes.
2. Apply the [placement rules](../mower-doc/references/doc-hierarchy.md#routing-rules). Definitions identify concepts; behavior rules state observable guarantees; procedures describe actions. Refer to business rules by behavior names and direct links to their owning subsystem description.
3. State the actual subject, action and object, then retain conditions and results needed to understand the fact. Use present tense for current rules. Name whose responsibility or which boundary a modifier describes. Keep conditions, exceptions and failure consequences; connect adjacent sentences by their actual causal, conditional or parallel relationship. For Chinese writing or translation, apply [中文表达](#chinese-prose) when choosing words and reviewing the draft.
4. At the first reference to a project document in standalone prose, use its approved name, explain its purpose for the current matter and link to the relevant file or section. The [Arknights Mower Coding Standards](../../../CODING_STANDARDS.md) define shared behavior rules, concurrency and resource requirements, and verification requirements; identify the relevant requirements when referencing them. Repository prose uses relative links; published PRs use the reviewed commit's accessible links. Later references may use a clear short name.
5. Separate final facts from work records. Decision rationale and postmortem history keep their authoritative role. Preserved quotations and test counterexamples need an explicit label and source, separate from current recommendations. Keep real code identifiers unchanged; backticks or code fences alone do not establish an exception.
6. Verify affected links and run the applicable [text checks](../../../scripts/README.md#formal-text-checks). Program results establish listed-term absence and source-marker validity; a reviewer still checks meaning, title scope and source relevance. Prose editing alone creates no record or lifecycle transition.

<a id="chinese-prose"></a>
## 中文表达

1. 用词前核对它在当前语境中的含义和搭配，确认读者能辨认它指的事物或操作。生硬的逐词翻译、含义不明的抽象说法和内部标签先还原为实际含义，再按文本用途组织中文；描述操作时说明谁在什么条件下做什么、结果怎样。保留来源已明确的具体名称；次数和数量说明对应的动作或事物，增减写明变化的量。
2. 逐句检查语序、主谓宾、所属关系、修饰语和指代是否符合中文习惯。套用英语语序、介词或连词而造成关系不清时，按实际的条件、因果、先后或并列关系重组；拆开过长的定语，把关系不清的名词堆叠展开为对象关系或具体动作，补齐必要的动词、宾语中心词和连接词。精简时删除不影响理解的整项细节，保留事实成立所需的条件和例外。
3. 项目正式术语、通行技术词和真实标识按准确含义保留；没有自然中文对应的技术名称可以保留英文。核对疑似直译时，判断含义、搭配和整句是否自然，不能只凭词源或陌生感判错。成稿脱离原文通读，确认读者无需按英文结构反推意思；程序扫描只检查指定格式和术语，中文是否自然仍需语义复核。

## Completion

The text states its intended facts clearly, preserves approved meaning and uses valid links. Report actual semantic changes rather than treating wording improvements as new guarantees.
