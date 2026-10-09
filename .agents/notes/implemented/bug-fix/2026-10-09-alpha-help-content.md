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

Current software/resource updates, device binding, task switches, scheduling recovery, growth planning and configuration backup replace obsolete downloader and manual migration advice. The system instruction includes the installed version. FAQ matching ignores Latin letter case. Help, FAQ, the feedback modal and README link to the supplied sheet without submitting data to it. The [assistant contract](../../../../docs/subsystems/ai-assistant.md) defines the boundary. The [earlier prompt decision](../../implemented/bug-fix/2026-10-09-ai-assistant-prompts.md) covers tool argument alignment.

Email submission returns the success message checked by the feedback component, so successful delivery also triggers its success notice and description-copy behavior. The explicit recipient list preserves the original mailbox and adds the user-requested feedback mailbox for both the UI and assistant. No sheet submission service is added.

README retains the overview, screenshots, source deployment for Windows, Linux and macOS, feedback entry and project notice. Packaging and developer checks move to the linked [packaging cookbook](../../../../docs/cookbook/packaging.md); Docker instructions move to the linked [deployment cookbook](../../../../docs/cookbook/docker-deploy.md). Release details remain in the existing platform document. Source instructions use the frontend's current Node.js requirement and include direct startup commands; the Linux dependency error points to the existing platform document instead of the removed packaging section.

README, the packaging cookbook, one-stop help and FAQ recommend source deployment for macOS and Linux while retaining independent package support.

User-facing help titles, link labels and FAQ wording omit the alpha label. Project links point to the repository homepage without selecting a branch; clone commands retain the actual branch name. Manual package downloads in help and FAQ point to the main project's Releases page; backend update sources remain unchanged.

DeepSeek uses one provider option with preset or custom model selection. A separate model field preserves local/online custom-provider settings when switching providers. The [assistant contract](../../../../docs/subsystems/ai-assistant.md) owns model IDs and legacy selection migration. The former per-model dispatch map is removed; the existing model factory and key resolution remain in use. This reuses [INV-01] explicit-field persistence without a new invariant, abstraction or glossary concept.

The one-stop guide has light/dark semantic colors for content, navigation, links, tables, code and callouts. The embedded page follows Mower theme changes without reload; standalone use follows system preference, with explicit query selection available. Theme synchronization accepts only validated same-origin parent messages. A dedicated scheduling theory section restores field responsibilities, a complete three-position replacement example, mood-limit and threshold interpretation, bounded work/rest estimates, backup composition and an authoring checklist; examples are checked against the current editor and scheduling contract.

Scheduling authoring examples distinguish ordinary replacements, same-group working/dormitory primary exchanges and explicit temporary Free bindings. Recovery capacity counts fixed recovery positions without duplicating dynamic beds, excludes dormitory followers and zero-mood workers from ordinary recovery demand, and retains baseline Free continuity and per-room minimums without a fixed manager count. Multiple-binding examples describe per-group candidates, single-binding working anchors and common candidates for concurrent rest. The guide and FAQ also describe whole-slot Current inheritance, backup list additions/removals, resting priorities, personal/ling-xi/global mood-limit precedence and the editor's local three-facility layout. This corrects incomplete tutorial coverage without changing scheduler behavior or glossary definitions.

## Verification

Focused offline checks cover legacy downloader queries, current task-switch and database-cleanup advice, case-insensitive FAQ lookup, local source references and help navigation. Scheduling and device-control semantics remain unchanged. The additional DeepSeek model setting introduces no glossary concept.

README and cookbook maintenance verifies local links and section anchors, Bash syntax without running installation, packaging output names against the platform specs, Docker commands against the server Dockerfile and entrypoint, and Node.js requirements against the frontend lockfile. Four focused help-link and Linux dependency-hint checks pass. Cross-platform installation, packaging and container execution are not performed.

DeepSeek maintenance passes 18 focused AI feature/prompt tests with 16 subtests and three frontend store checks. Legacy Flash/Pro selections retain their model and key, custom IDs reach the official endpoint, Pro thinking parameters remain present, blank IDs fail before model construction, and serialization omits unselected defaults. Frontend checks cover loading preset/custom IDs and saving only the changed provider or model field while preserving unrelated settings. The settings component script/template compile and formatting checks pass; no live model request is sent.

Theme verification passes nine focused frontend tests covering system defaults/changes, explicit theme selection, parent-message validation and embedded updates without iframe reload. CSS parsing and 34 text/background checks pass WCAG AA contrast (minimum 4.56:1 light and 7.04:1 dark). Help navigation/source checks pass. The browser tool blocks local file URLs, so the updated theme has no browser visual-verification evidence.

Scheduling documentation verification passes 59 focused tests and nine subtests across prompt/navigation checks and selected existing scheduling regressions. Coverage includes same-group primary identity and matching, fixed versus dynamic recovery capacity, dormitory followers, multiple-binding candidate intersection and validation, shared temporary Free lifetime, variable manager counts, backup Free layouts, ordered list additions/removals and mood-limit precedence. Governance and FAQ lint/format checks pass; these are offline checks without device operations.

## Standards Findings

PASS. Governance checks, Python lint, Vue compilation and whitespace checks pass. The focused assistant and governance suites pass on the latest alpha baseline with 39 tests and 32 subtests; structural checks retain two existing historical archive-reference warnings. No new device operations, resource lifecycles or glossary changes are introduced.

## Spec Findings

PASS. FAQ and help follow current alpha interfaces; obsolete downloader advice is removed and the supplied feedback link appears in all requested surfaces. Browser inspection shows anonymous sheet access is read-only, so copy explicitly states that editing requires permission. Email submission remains separate and does not claim to write to the sheet.
