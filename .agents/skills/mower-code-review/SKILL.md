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
2. Read the relevant [standards](../../../CODING_STANDARDS.md), subtree instructions, subsystem contract and existing decision. Use only affected sections of the [invariants checklist](references/invariants-checklist.md). Follow production callers through return values, state, persistence, side effects and recovery; tests around an unused helper do not establish that path's correctness.
3. Compare behavior with the requirements. Check record ownership and concept impact through [Agent Workflow](../../AGENTS.md#2-authority-and-record-ownership). Distinguish evidence of a changed definition from a repaired operation.
4. Run focused offline behavior tests when needed for the finding. For document/governance changes run `python scripts/verify_governance.py`; changes to its scripts also require `pytest arknights_mower/tests/verify_governance_tests.py`. For a branch or commit review, run checks in a checkout at the reviewed head and pass `--base <actual-comparison-commit>`. Checks run elsewhere describe only that checkout. Separate structural results from functional results and the semantic review conclusion.
5. Report concrete locations, impact and supporting observations. A read-only request ends with findings. If repairs are authorized, use the selected [task workflow](../../AGENTS.md#1-task-selection) and update the owning record rather than opening a second review workflow.

## Completion

Every requested source is accounted for, material findings have evidence, necessary checks are reported and unverified claims remain explicit. A branch comparison says nothing about uncommitted or untracked content unless that content is separately inspected.

Behavioral workflow cases live in [evals/evals.json](evals/evals.json). Prepare its fixture requirements before evaluating saved and current instructions in isolated read-only sessions. Supply prompts without the expected results, then assess observed routing separately from structural lint. These fixtures are evaluation inputs, not production changes required by this skill.
