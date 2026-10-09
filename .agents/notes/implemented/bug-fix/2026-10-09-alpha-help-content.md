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

User-facing help titles, link labels and FAQ wording omit the alpha label. Project links point to the repository homepage without selecting a branch; clone commands retain the actual branch name.

## Verification

Focused offline checks cover legacy downloader queries, current task-switch and database-cleanup advice, case-insensitive FAQ lookup, local source references and help navigation. No scheduling, device-control or configuration schema changes require glossary edits.

README and cookbook maintenance verifies local links and section anchors, Bash syntax without running installation, packaging output names against the platform specs, Docker commands against the server Dockerfile and entrypoint, and Node.js requirements against the frontend lockfile. Four focused help-link and Linux dependency-hint checks pass. Cross-platform installation, packaging and container execution are not performed.

## Standards Findings

PASS. Governance checks, Python lint, Vue compilation and whitespace checks pass. The focused assistant and governance suites pass on the latest alpha baseline with 39 tests and 32 subtests; structural checks retain two existing historical archive-reference warnings. No new device operations, resource lifecycles or glossary changes are introduced.

## Spec Findings

PASS. FAQ and help follow current alpha interfaces; obsolete downloader advice is removed and the supplied feedback link appears in all requested surfaces. Browser inspection shows anonymous sheet access is read-only, so copy explicitly states that editing requires permission. Email submission remains separate and does not claim to write to the sheet.
