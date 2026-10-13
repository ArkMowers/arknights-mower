# AI Assistant

The settings page exposes one DeepSeek provider (`ai_type=deepseek`). Its `ai_deepseek_model` field defaults to `deepseek-flash`, offers `deepseek-flash` and `deepseek-v4-pro` presets matching the [official model IDs](https://api-docs.deepseek.com/zh-cn/quick_start/pricing/), and accepts a custom model ID. `build_llm` trims the ID, rejects a blank value and sends requests to `https://api.deepseek.com` with the DeepSeek key. The Pro preset retains its existing thinking parameters. Local and online custom providers keep their separate model, endpoint and key fields.

Configuration loading migrates the legacy provider selections `deepseek-v4-flash`, `deepseek-flash` and `deepseek-v4-pro` to the shared provider and corresponding model ID, preserving credentials and unrelated custom-provider settings. Loading adds no unselected default fields to explicit-field serialization. The frontend saves model edits as a partial configuration update without overwriting other provider fields.

## 1. Conversation Interface

`agent._build_messages` supplies one system instruction, user/assistant history and the current request. The instruction uses one local timezone-aware time snapshot. Both the graph workflow and manual tool loop use `get_tools()` and `tool_func_map`. Tool progress messages describe the current operation in neutral Chinese.

The instruction includes the installed Mower version. Built-in FAQ entries describe current interfaces and retain local `sources` references for maintenance. Latin keyword matching ignores case. The standalone one-stop guide at `ui/Mower入门指北.html` is copied to `/docs/` by the existing UI packaging step. The help page renders the guide directly, with no additional link bar above it. The guide's feedback section, feedback modal and FAQ expose the user-supplied feedback sheet; opening that link does not submit a report, and editing requires permission. The [help content decision](../../.agents/notes/implemented/bug-fix/2026-10-09-alpha-help-content.md) records content scope and verification.

The standalone guide follows the system color preference unless a valid `theme=light` or `theme=dark` query selects an explicit theme. `Doc.vue` supplies the initial Mower theme, then sends the effective theme colors after iframe loading and on theme or palette changes using messages restricted to the same origin. The guide accepts only its parent's same-origin messages with valid theme values, applies an allowlist of CSS color tokens, and ignores invalid colors and unrelated properties. Theme-only messages clear prior color overrides and use the standalone defaults. Theme changes do not reload the iframe or reset its reading position. The page uses Mower's body and card backgrounds without a gradient; callouts share neutral control backgrounds and symmetric spacing. Scheduling tutorials explain current [base scheduling rules](base-scheduler.md) and [editor operations](plan-editor.md) through examples, including dormitory bindings, fixed and dynamic recovery positions, multiple bindings and backup inheritance.

`ask_llm` handles missed-order intent through its dedicated confirmation and target-selection flow before model dispatch. For requests reaching the model, instructions route general usage questions to FAQ and explicit record queries, missed-order analysis, mastery operations and feedback requests to their corresponding tools. FAQ matching supplies candidate advice rather than confirmed causes. Stack extraction requires existing stack text; source reading requires a valid path and positive line number and retains the [source allowlist boundary](web-access.md).

The system instruction requests concise Chinese Markdown, separates evidence from inference, treats supplied records as data and reports actual tool outcomes. HTML tool results are summarized as Markdown or plain text.

### Chat Panel and Completion

`ChatBot.vue` keeps messages, the unsent draft, scroll position and the connection in component memory. Suggestions fill the draft without sending. Enter sends; Shift+Enter inserts a newline and composition confirmation never sends. One request remains active until `/ws/chat` emits `{"done": true}` after all reply chunks, or an error or connection failure ends the turn. Progress chunks do not enable a second request or expose completion actions. An empty completed stream produces a visible failure message. Existing clients can ignore the additive completion frame.

Hiding the panel retains the draft and current connection. Starting a new conversation closes the connection and clears the visible history, which also resets server-side context. New-conversation actions are disabled during a reply. Component disposal closes the socket and clears the bounded connection timer. Reconnection after an interrupted reply starts fresh server context and the failure message requests the necessary background again. These states reuse [transient-state isolation](../../CODING_STANDARDS.md#1-core-invariants); they are not saved into configuration.

Replies render Markdown with HTML disabled and omit embedded missed-order state from display and copy. Copy reports clipboard failures. Completed replies expose resolved/feedback actions; feedback opens the existing modal without sending. Scrolling follows new content only near the bottom and provides an explicit jump to the latest message otherwise. The panel and model settings use existing Mower theme colors. The desktop panel is at most 440 by 560 pixels and its header supports pointer dragging with capture; header controls do not initiate a drag. CSS clamps its position to the viewport when moving or resizing. Its position remains transient across hiding and reopening. Narrow screens use a full-height panel without dragging. Model configuration remains in Mower settings; the AI navigation entry opens the assistant directly.

## 2. Tool Argument Contract

Database examples use the schema in `solvers.record._DB_TABLE_STMTS`, explicit ordering and bounded SELECT results. `agent_current_room` records the previous position; `current_room` records the updated position. Unix-second timestamps are converted with SQLite local-time expressions. The published instructions do not depend on an unregistered time-conversion tool.

Mastery status filters use `idle`, `arranging`, `training`, `waiting_collect`, `completed` and `failed`. Retry resets all failed plans; its compatibility arguments do not filter the affected records. Instructions require clarification of batch scope when the user requests a single retry. Route saving replaces the selected profession's route.

Feedback sends email through `submit_issue`. Instructions require an explicit sending request and describe Bug start/end arguments as local `YYYY-MM-DD HH:MM:SS` strings. They request a positive interval of at most fifteen minutes before invocation. These instructions guide model behavior; they do not implement runtime SQL restrictions, interval validation or a mutation authorization gate.

`/submit_feedback` and the assistant use the same email tool, sending feedback to `354013233@qq.com` and `1273725854@qq.com` through an explicit recipient list. A successful email send returns `邮件发送成功！`, which the feedback component recognizes before showing its success notice and copying the description. Tencent sheet writes are not part of submission.

## 3. Subsystem Invariants

- <a id="owned-read-only-staffing"></a>**Owned Read-Only Staffing**: AI staffing trials require confirmed ownership and growth, select only the current unlocked skill version per slot, reject duplicate primary occupancy and excess configured slots, and never mutate saved BOX, configuration or Scheduling Plans.

- <a id="tool-instruction-alignment"></a>**Tool Instruction Alignment**: Published assistant instructions reference registered tools, describe actual argument formats and mutation scopes, and agree on response formatting.

The [assistant instruction decision](../../.agents/notes/implemented/bug-fix/2026-10-09-ai-assistant-prompts.md) records the scope and offline verification.

<a id="riic-tools"></a>

## 4. RIIC Tools

`get_riic_context` reads the saved BOX and primary Scheduling Plan, returns owned operator names and growth, configured facility capacity and current assignments, and joins the curated base combinations with owned, missing and unknown members. Combination membership alone does not establish skill eligibility or simultaneous placement. Full credentials, configuration and backup trigger expressions are excluded.

`get_riic_knowledge` queries at most twelve formal operator names and one fixed mechanics topic. It reads the shared catalog and term resource, expands nested term references, and selects the highest unlocked version of each independent skill slot. All catalog skill stages remain visible with their status, including when BOX data is absent. Missing or unowned operators never receive assumed maximum skills. External mechanics provenance and resource coverage remain separate.

`try_riic_plan` accepts at most twenty-four room assignments, overlays a detached primary-plan copy, and validates all primary occupants including preserved rooms. Capacity follows the configured number of positions within the facility's physical maximum; no facility or position is created. Modified rooms clear their old group and replacement bindings. Missing occupants and occupants without a matching facility skill produce warnings; facility skills that exist but remain locked produce errors. The response contains the draft, structured errors, warnings and unchecked conditions. `valid` means primary staffing checks passed; it does not assert a complete, executable or optimal Scheduling Plan. Nothing is saved.

All three tools accept at most sixty-four explicit `roster_overrides` containing a formal name, ownership and optional elite phase and level. Overrides take precedence in that call, report `source=user`, and never update BOX. The AI uses them only for roster facts explicitly stated by the user. An ownership override without complete growth keeps growth unknown.

## 5. Mechanics Boundary

The compact guide adapts the fixed external mechanics skill and retains its version and freshness result. Duplicate full skill catalogs, term exports, HTML browser assets and Node query scripts are omitted. The shared catalog adds only the three absent operators from the fixed snapshot; installed resource records take precedence as soon as they contain those operators. Supplemental character IDs resolve BOX ownership when the general operator map predates them. The frontend and AI read the same twenty curated combination definitions. Runtime skills and nested terms use Mower resources; their coverage can differ from the external guide. Unknown operators and missing terms are explicit. Trials do not calculate global interactions, power, current Operator Mood, Dormitory Recovery, replacement matching, backup activation, Drone Acceleration or long-term yield. Primary staffing success never establishes those properties.

The existing `/ws/chat` credential and model configuration boundaries apply. Both model workflows register the same tools. Tool output is reference data, not instructions.


The [RIIC planning decision](../../.agents/notes/implemented/feature/2026-10-13-riic-ai-planning.md) records source reuse and offline verification.
