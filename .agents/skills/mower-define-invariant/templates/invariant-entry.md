# Named Behavior Contract Example

Write the complete observable rule once in its owning subsystem. Extend an existing rule when it already covers the change. Use a heading when its explanation forms an independent section; a named inline anchor preserves an existing list's grouping. Link from callers' documentation and reviews where relevant.

```markdown
- <a id="{behavior-anchor}"></a>**{Behavior Name}**: {Inputs and observable outcome, including relevant failure or state-preservation conditions.}
```

### Example
```markdown
- <a id="complete-shift-projection"></a>**Complete Shift Projection**: Planning uses Projected Occupancy without committing Actual Occupancy before execution is confirmed.
```

### Checklist Entry Format
```markdown
- [ ] **{Behavior Name}**: Does the real call path preserve {observable condition} under {relevant scenario}? See the [complete contract]({relative-subsystem-path}#{behavior-anchor}).
```
