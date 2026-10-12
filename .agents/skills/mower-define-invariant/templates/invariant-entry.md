# Invariant Entry Registration Template

Use this snippet once in `CODING_STANDARDS.md` for a new independent guarantee. Reuse existing identifiers when they already cover the change. Put its full operational contract in the owning subsystem and link from other locations.

```markdown
- **[INV-{SUBSYSTEM}-{NUMBER}] {Invariant Name}**: {Present-tense contract statement detailing the guarantee and prohibited behavior}.
```

### Example
```markdown
- **[INV-SCHED-01] Empirical Depletion Rate**: Mood forecasting must dynamically measure consecutive inspection deltas; uncalibrated static assumptions are prohibited.
```

### Checklist Entry Format
```markdown
- [ ] **[INV-{SUBSYSTEM}-{NUMBER}] {Invariant Name}**: Does the real call path preserve {observable condition} under {relevant scenario}? See the authoritative subsystem contract.
```
