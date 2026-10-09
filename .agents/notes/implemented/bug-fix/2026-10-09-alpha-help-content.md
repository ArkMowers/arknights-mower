---
title: Alpha Help and FAQ Content
status: implemented
category: bug-fix
date: 2026-10-09
---

# Alpha Help and FAQ Content

## Contract

[INV-AI-01] applies to built-in FAQ advice as well as tool instructions. The FAQ and one-stop help describe current alpha interfaces and expose the user-supplied feedback sheet. Email feedback remains a separate explicit operation.

## Pre-flight Simplification

The existing FAQ list, standalone help HTML and feedback component retain their responsibilities. FAQ entries carry local source references for maintenance. The help removes obsolete installation commands, duplicate navigation IDs, duplicate clipboard listeners and a development live-reload script; it adds no documentation framework or submission service.

## Implementation

Current software/resource updates, device binding, task switches, scheduling recovery, growth planning and configuration backup replace obsolete downloader and manual migration advice. The system instruction includes the installed version. FAQ matching ignores Latin letter case. Help, FAQ and the feedback modal link to the supplied sheet without submitting data to it. The [assistant contract](../../../../docs/subsystems/ai-assistant.md) defines the boundary. The [earlier prompt decision](../../implemented/bug-fix/2026-10-09-ai-assistant-prompts.md) covers tool argument alignment.

Email submission returns the success message checked by the feedback component, so successful delivery also triggers its success notice and description-copy behavior. The explicit recipient list preserves the original mailbox and adds the user-requested feedback mailbox for both the UI and assistant. No sheet submission service is added.

The user requests current instructions in the application repository while the documentation-site PR remains separate. README again owns source deployment for Windows, Linux and macOS and links to [local packaging](../../../../docs/cookbook/packaging.md) and [Docker deployment](../../../../docs/cookbook/docker-deploy.md). The one-stop guide is rewritten against current code; help and FAQ use the repository homepage for deployment instead of depending on an unpublished website page. macOS setup prepares the default ADB path. Manual package downloads still use the main project's Releases; backend update sources remain unchanged.

User-facing help titles, link labels and FAQ wording omit the alpha label. Project links point to the repository homepage without selecting a branch; clone commands retain the actual branch name. Manual package downloads in help and FAQ point to the main project's Releases page; backend update sources remain unchanged.

DeepSeek uses one provider option with preset or custom model selection. A separate model field preserves local/online custom-provider settings when switching providers. The [assistant contract](../../../../docs/subsystems/ai-assistant.md) owns model IDs and legacy selection migration. The former per-model dispatch map is removed; the existing model factory and key resolution remain in use. This reuses [INV-01] explicit-field persistence without a new invariant, abstraction or glossary concept.

The one-stop guide has light/dark semantic colors for content, navigation, links, tables, code and callouts. The embedded page follows Mower theme changes without reload; standalone use follows system preference, with explicit query selection available. Theme synchronization accepts only validated same-origin parent messages. A dedicated scheduling theory section restores field responsibilities, a complete three-position replacement example, mood-limit and threshold interpretation, bounded work/rest estimates, backup composition and an authoring checklist; examples are checked against the current editor and scheduling contract.

Scheduling authoring examples distinguish ordinary replacements, same-group working/dormitory primary exchanges and explicit temporary Free bindings. Recovery capacity counts fixed recovery positions without duplicating dynamic beds, excludes dormitory followers and zero-mood workers from ordinary recovery demand, and retains baseline Free continuity and per-room minimums without a fixed manager count. Multiple-binding examples describe per-group candidates, single-binding working anchors and common candidates for concurrent rest. The guide and FAQ also describe whole-slot Current inheritance, backup list additions/removals, resting priorities, personal/ling-xi/global mood-limit precedence and the editor's local three-facility layout. This corrects incomplete tutorial coverage without changing scheduler behavior or glossary definitions. The refreshed instructions follow the current protected-bed and grouped-capacity rules in the [scheduler contract](../../../../docs/subsystems/base-scheduler.md), ordinary fixed working anchors and the [training-slot precheck](../../../../doc/plan-roster-validation.md). FAQ advice includes these changes without modifying scheduling logic or glossary definitions.

The chat panel reuses the existing assistant component and theme variables. It adds a header, draft-only suggestions, multiline composition, completed-reply actions and scroll-aware navigation; hiding preserves the current conversation. Responsive CSS replaces the resize listener, and socket/timer cleanup belongs to component disposal. The compact desktop panel supports header dragging with pointer capture and viewport bounds; its position remains transient. Header controls retain click behavior and narrow screens retain the full-height layout. The additive WebSocket completion frame keeps the request busy across progress chunks and permits a new turn only after completion or failure. Model settings group the existing fields without changing persistence. This reuses [INV-01] and [INV-AI-01], with no new glossary concept or independent record.

## Verification

Focused offline checks cover legacy downloader queries, current task-switch and database-cleanup advice, case-insensitive FAQ lookup, local source references and help navigation. Scheduling and device-control semantics remain unchanged. The additional DeepSeek model setting introduces no glossary concept.

The earlier website split passed seven prompt/help tests and nine subtests. The current restoration checks the repository documentation and embedded guide together. Cross-platform installation, packaging and container execution remain outside this verification; deployment commands are checked against current entry points and build files.

DeepSeek maintenance passes 18 focused AI feature/prompt tests with 16 subtests and three frontend store checks. Legacy Flash/Pro selections retain their model and key, custom IDs reach the official endpoint, Pro thinking parameters remain present, blank IDs fail before model construction, and serialization omits unselected defaults. Frontend checks cover loading preset/custom IDs and saving only the changed provider or model field while preserving unrelated settings. The settings component script/template compile and formatting checks pass; no live model request is sent.

Theme verification passes nine focused frontend tests covering system defaults/changes, explicit theme selection, parent-message validation and embedded updates without iframe reload. CSS parsing and 34 text/background checks pass WCAG AA contrast (minimum 4.56:1 light and 7.04:1 dark). Help navigation/source checks pass. The browser tool blocks local file URLs, so the updated theme has no browser visual-verification evidence.

Scheduling documentation verification passes 59 focused tests and nine subtests across prompt/navigation checks and selected existing scheduling regressions. Coverage includes same-group primary identity and matching, fixed versus dynamic recovery capacity, dormitory followers, multiple-binding candidate intersection and validation, shared temporary Free lifetime, variable manager counts, backup Free layouts, ordered list additions/removals and mood-limit precedence. Governance and FAQ lint/format checks pass; these are offline checks without device operations.

Chat UI verification passes 15 focused interaction tests and three existing DeepSeek partial-save tests. Six backend tests and eleven subtests cover authenticated streaming, additive completion after all chunks, empty streams and model failures. Browser checks cover light/dark desktop rendering, suggestion drafting, streaming state and feedback entry. At 390×844 and 320×568 the panel fits the viewport without horizontal overflow and the composer remains visible; chat actions have 40-pixel height. A fresh preview has no console errors. The local frontend production build passes, and the applied application files match the reviewed worktree. Preview responses are simulated; Mower background instances remain stopped and no model or device is contacted.

## Standards Findings

PASS. Governance checks, Python lint, Vue compilation and whitespace checks pass. The focused assistant and governance suites pass on the latest alpha baseline with 39 tests and 32 subtests; structural checks retain two existing historical archive-reference warnings. No new device operations, resource lifecycles or glossary changes are introduced.

## Spec Findings

PASS. FAQ and help follow current alpha interfaces; obsolete downloader advice is removed and the supplied feedback link appears in all requested surfaces. Browser inspection shows anonymous sheet access is read-only, so copy explicitly states that editing requires permission. Email submission remains separate and does not claim to write to the sheet.

Compact-panel browser checks verify the 440-by-560 desktop size, header movement, viewport bounds, position retention on reopening and bounds after resizing. Pointer tests cover cancellation, unrelated pointers, header controls and mobile drag suppression.

Repository-document refresh verification passes 24 focused backend tests and 24 frontend checks (15 chat interactions and nine help-theme checks). The frontend production build, Ruff, Prettier, ESLint, whitespace checks and structural governance pass. Three Markdown link sets, 15 Bash blocks and referenced deployment files are checked. Browser checks cover light/dark guide rendering and 390- and 320-pixel layouts without horizontal overflow. Installers, packages and containers are not executed; no model, device or feedback email is contacted.
