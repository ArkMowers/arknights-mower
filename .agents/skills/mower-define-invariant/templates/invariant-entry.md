# Invariant Entry Registration Template

Use this markdown snippet when registering a new invariant in `docs/subsystems/*.md`, `CODING_STANDARDS.md`, and `.agents/skills/mower-code-review/references/invariants-checklist.md`:

```markdown
- **[INV-{SUBSYSTEM}-{NUMBER}] {Invariant Name}**: {Present-tense contract statement detailing the guarantee and prohibited behavior}.
```

### Example
```markdown
- **[INV-SCHED-01] Empirical Depletion Rate**: Mood forecasting must dynamically measure consecutive inspection deltas; uncalibrated static assumptions are prohibited.
```

### Checklist Entry Format
```markdown
- [ ] **[INV-{SUBSYSTEM}-{NUMBER}] {Invariant Name}**: Does the change strictly enforce {condition}? Is {prohibited action} prohibited?
```
