# AI Assistant

The settings page exposes one DeepSeek provider (`ai_type=deepseek`). Its `ai_deepseek_model` field defaults to `deepseek-flash`, offers `deepseek-flash` and `deepseek-v4-pro` presets matching the [official model IDs](https://api-docs.deepseek.com/zh-cn/quick_start/pricing/), and accepts a custom model ID. `build_llm` trims the ID, rejects a blank value and sends requests to `https://api.deepseek.com` with the DeepSeek key. The Pro preset retains its existing thinking parameters. Local and online custom providers keep their separate model, endpoint and key fields.

Configuration loading migrates the legacy provider selections `deepseek-v4-flash`, `deepseek-flash` and `deepseek-v4-pro` to the shared provider and corresponding model ID, preserving credentials and unrelated custom-provider settings. Loading adds no unselected default fields to explicit-field serialization. The frontend saves model edits as a partial configuration update without overwriting other provider fields.

## 1. Conversation Interface

`agent._build_messages` supplies one system instruction, user/assistant history and the current request. The instruction uses one local timezone-aware time snapshot. Both the graph workflow and manual tool loop use `get_tools()` and `tool_func_map`. Tool progress messages describe the current operation in neutral Chinese.

The instruction includes the installed Mower version. Built-in FAQ entries describe current interfaces and retain local `sources` references for maintenance. Latin keyword matching ignores case. The standalone one-stop guide at `ui/Mower入门指北.html` is copied to `/docs/` by the existing UI packaging step. The help page, feedback modal and FAQ expose the user-supplied feedback sheet; opening that link does not submit a report, and editing requires permission. The [help content decision](../../.agents/notes/implemented/bug-fix/2026-10-09-alpha-help-content.md) records content scope and verification.

The standalone guide follows the system color preference unless a valid `theme=light` or `theme=dark` query selects an explicit theme. `Doc.vue` supplies the initial Mower theme, then updates it after iframe loading and on theme changes using messages restricted to the same origin. The guide accepts only its parent's same-origin messages with valid theme values. Theme changes do not reload the iframe or reset its reading position. Scheduling tutorials explain current [base scheduling rules](base-scheduler.md) and [editor operations](plan-editor.md) through examples, including dormitory bindings, fixed and dynamic recovery positions, multiple bindings and backup inheritance.

`ask_llm` handles missed-order intent through its dedicated confirmation and target-selection flow before model dispatch. For requests reaching the model, instructions route general usage questions to FAQ and explicit record queries, missed-order analysis, mastery operations and feedback requests to their corresponding tools. FAQ matching supplies candidate advice rather than confirmed causes. Stack extraction requires existing stack text; source reading requires a valid path and positive line number and retains the [source allowlist boundary](web-access.md).

The system instruction requests concise Chinese Markdown, separates evidence from inference, treats supplied records as data and reports actual tool outcomes. HTML tool results are summarized as Markdown or plain text.

### Chat Panel and Completion

`ChatBot.vue` keeps messages, the unsent draft, scroll position and the connection in component memory. Suggestions fill the draft without sending. Enter sends; Shift+Enter inserts a newline and composition confirmation never sends. One request remains active until `/ws/chat` emits `{"done": true}` after all reply chunks, or an error or connection failure ends the turn. Progress chunks do not enable a second request or expose completion actions. An empty completed stream produces a visible failure message. Existing clients can ignore the additive completion frame.

Hiding the panel retains the draft and current connection. Starting a new conversation closes the connection and clears the visible history, which also resets server-side context. New-conversation actions are disabled during a reply. Component disposal closes the socket and clears the bounded connection timer. Reconnection after an interrupted reply starts fresh server context and the failure message requests the necessary background again. These states reuse [transient-state isolation](../../CODING_STANDARDS.md#1-core-invariants); they are not saved into configuration.

Replies render Markdown with HTML disabled and omit embedded missed-order state from display and copy. Copy reports clipboard failures. Completed replies expose resolved/feedback actions; feedback opens the existing modal without sending. Scrolling follows new content only near the bottom and provides an explicit jump to the latest message otherwise. The panel and model settings use existing Mower theme colors, with a full-height panel on narrow screens.

## 2. Tool Argument Contract

Database examples use the schema in `solvers.record._DB_TABLE_STMTS`, explicit ordering and bounded SELECT results. `agent_current_room` records the previous position; `current_room` records the updated position. Unix-second timestamps are converted with SQLite local-time expressions. The published instructions do not depend on an unregistered time-conversion tool.

Mastery status filters use `idle`, `arranging`, `training`, `waiting_collect`, `completed` and `failed`. Retry resets all failed plans; its compatibility arguments do not filter the affected records. Instructions require clarification of batch scope when the user requests a single retry. Route saving replaces the selected profession's route.

Feedback sends email through `submit_issue`. Instructions require an explicit sending request and describe Bug start/end arguments as local `YYYY-MM-DD HH:MM:SS` strings. They request a positive interval of at most fifteen minutes before invocation. These instructions guide model behavior; they do not implement runtime SQL restrictions, interval validation or a mutation authorization gate.

`/submit_feedback` and the assistant use the same email tool, sending feedback to `354013233@qq.com` and `1273725854@qq.com` through an explicit recipient list. A successful email send returns `邮件发送成功！`, which the feedback component recognizes before showing its success notice and copying the description. Tencent sheet writes are not part of submission.

## 3. Subsystem Invariants

- **[INV-AI-01] Tool Instruction Alignment**: Published assistant instructions reference registered tools, describe actual argument formats and mutation scopes, and agree on response formatting.

The [assistant instruction decision](../../.agents/notes/implemented/bug-fix/2026-10-09-ai-assistant-prompts.md) records the scope and offline verification.
