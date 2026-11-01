---
name: mower-code-review
description: Use when reviewing Arknights Mower worktree changes, a branch, a commit or a specified range against standards and requirements. Do not use for prose-only editing or treat review as authorization to implement or create records.
compatibility: Requires an Arknights Mower checkout and its repository contracts; this is a repository-local skill, not a standalone distribution.
---

# Mower Code Review

## Inputs and Output

Inputs: requested scope, actual comparison base where applicable, requirements and affected contracts. Output: one report with standards findings, requirement findings, checks run and unresolved evidence. Use the [report template](references/review-template.md) when a written report is useful.

## Review

1. Resolve scope from the request. For a working-tree review, inspect all three sources:

   ```bash
   git status --short
   git diff --cached
   git diff
   git ls-files --others --exclude-standard
   ```

   Read untracked files in scope; they are absent from `git diff`. For a branch use the requested merge-base comparison, `git diff <base>...<head>`; for two commits use `git diff <before> <after>`, and for one commit use `git show <commit>`. If the necessary base is missing, obtain it rather than substituting a default remote branch.
2. Read the relevant [standards](../../../CODING_STANDARDS.md), subtree instructions, subsystem contract and existing decision. Use only affected sections of the [invariants checklist](references/invariants-checklist.md). Check application log calls against the [shared logger rule](#shared-logger). Follow production callers through return values, state, persistence, side effects and recovery; tests around an unused helper do not establish that path's correctness.
3. Compare behavior with the requirements. Check record ownership and concept impact through [Agent Workflow](../../AGENTS.md#2-authority-and-record-ownership). Distinguish evidence of a changed definition from a repaired operation.
4. Run focused offline behavior tests when needed for the finding. For document/governance changes run `python scripts/verify_governance.py`; changes to its scripts also require `pytest arknights_mower/tests/verify_governance_tests.py`. For a branch or commit review, run checks in a checkout at the reviewed head and pass `--base <actual-comparison-commit>`. Checks run elsewhere describe only that checkout. Separate structural results from functional results and the semantic review conclusion.
5. Report concrete locations, impact and supporting observations using the shared [prose rules](../mower-prose-standard/SKILL.md) and their bilingual terminology sources. A read-only request ends with findings. For authorized repairs, use the selected [task workflow](../../AGENTS.md#1-task-selection) and its [review feedback loop](../../AGENTS.md#4-verification-and-reporting); apply record ownership when the recorded rationale or evidence changes.

## Interface Authentication

When the reviewed scope adds or changes an HTTP route, WebSocket or other remotely callable backend interface, apply the [API authentication skill](../mower-api-auth/SKILL.md) to every affected method and representation. Treat a missing authentication decision or missing focused rejection evidence as a review finding; do not infer a public exception from `GET`, a frontend-only caller, loopback-oriented use, Origin or CORS handling, or an unprotected neighbouring route.

## Scheduling Guards and Progress

For native scheduling or income-simulation guards, follow the [Runtime Task Failure contract](../../../docs/subsystems/base-scheduler.md#211-runtime-task-failure). Reject excessive defensive behavior: identify the concrete invalid action being prevented, the smallest dependent work that must wait, and the observation or arrangement change that releases it. Missing evidence is not evidence of an illegal configuration. Check whether a valid estimate or existing observation already satisfies the requirement before adding another mandatory read.

Before accepting any deferral, require these checks:

1. Reevaluate current valid observations, estimates, task state and feasible arrangements first. Use the existing bounded observation recovery only when information needed for the decision is missing, stale or contradictory. If the operation is feasible after this recheck, continue it immediately. A failed recheck alone does not justify waiting.
2. Reject fixed one-minute postponements, including a default retry interval or a one-minute minimum added to an otherwise calculated delay. Substituting another arbitrary interval is also prohibited. Every timed deferral must derive an absolute next eligible time from an observed production or training countdown, a valid mood or resource recovery estimate, or a known prerequisite completion time. Require the calculation's inputs, reason and applicable bounds; unchanged evidence must not move that deadline forward on each dispatch.
3. If no supported time can be calculated, preserve the original unfinished task, remaining work and timestamp, release dispatch, and resume only after a relevant new observation or dependency change. Do not invent a wakeup time, create periodic retry tasks or stop automation. A calculated duration that happens to equal one minute is valid only when its evidence supports that result.
4. Waiting must release dispatch. Reject sleeps, polling or reservations that block unrelated ready work or the observations and prerequisite tasks needed to make progress. Preserve actual dependencies, including shared operators, occupied slots and started handoffs; a failed or non-dispatchable task must not become a global prerequisite for other work.

Trace the dispatch callers, task reservations and persistence together. A guard that blocks unrelated work, repeatedly recreates the same task, or requires progress that its own reservation prevents is a defect. A delay, polling loop, blanket automation stop or log-severity change alone does not repair that defect. Preserve genuine shared-operator and started-handoff dependencies; do not treat unknown mood as recovered. Require the [progress tests](../mower-define-invariant/SKILL.md#scheduling-progress-evidence) to establish both restraint and continued execution.

## Shared Logger

Python modules that emit application logs use the shared logger from `arknights_mower.utils.log`:

```python
from arknights_mower.utils.log import logger
```

Application log calls use this object, including diagnostics otherwise written with `print()` or framework loggers such as `current_app.logger`. Do not create a module logger with `logging.getLogger(__name__)` or use root logging calls such as `logging.info()`. Runtime file logging, frontend delivery, and child-process forwarding attach to the shared logger; an independent module logger does not reach those handlers.

When an eager import creates a circular dependency, import the shared logger inside the calling function after logging initialization, or use an existing logger injection point supplied with the shared logger. Do not bypass the rule by creating another logger. Handler configuration remains owned by `utils/log.py`.

Preserve the existing `_get_logger()` fallback in `agent/missed_order.py` and `agent/tools/analyze_missed_order.py`: these offline analysis paths prefer the shared logger and fall back to a module logger if importing it fails, so diagnostics cannot prevent an analysis result. Do not copy this exception into new application modules.

Keep machine-readable stdout, build-tool output and the detached standard-library updater's `update.log` stream as their existing output contracts require. These channels must remain usable without importing the application runtime or changing protocol payloads.

## Completion

Every requested source is accounted for, material findings have evidence, necessary checks are reported and unverified claims remain explicit. A branch comparison says nothing about uncommitted or untracked content unless that content is separately inspected.

Behavioral workflow cases live in [evals/evals.json](evals/evals.json). Prepare its fixture requirements before evaluating saved and current instructions in isolated read-only sessions. Supply prompts without the expected results, then assess observed routing separately from structural lint. These fixtures are evaluation inputs, not production changes required by this skill.
