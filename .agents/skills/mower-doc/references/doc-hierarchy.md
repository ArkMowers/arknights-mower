# Arknights Mower Documentation Hierarchy (One Home per Fact)

Every technical fact in Arknights Mower belongs to exactly one documentation tier.

```
/
├── AGENTS.md                          # Tier 1: Global standing pointers (1-3 lines each)
├── CONTEXT.md                         # Tier 0: Domain Glossary SSOT (English)
├── CONTEXT.zh.md                      # Tier 0: Domain Glossary SSOT (Chinese mirror)
├── CODING_STANDARDS.md                # Tier 0: Core invariants [INV-01] to [INV-06]
│
├── arknights_mower/AGENTS.md          # Tier 2: Python backend subtree contract
├── ui/AGENTS.md                       # Tier 2: Vue 3 frontend subtree contract
├── docs/AGENTS.md                     # Tier 2: Documentation subtree contract
├── .agents/notes/AGENTS.md            # Tier 2: Decision notes subtree contract
│
├── docs/
│   ├── architecture.md                # Tier 3: Panoramic architecture & data flow
│   ├── subsystems/
│   │   ├── device-control.md          # Tier 3: Device control public interfaces & contracts
│   │   └── base-scheduler.md          # Tier 3: Base scheduler public interfaces & contracts
│   ├── cookbook/
│   │   ├── device-troubleshooting.md  # Tier 4: Developer diagnostic & operational recipes
│   │   └── adding-simulator-preset.md # Tier 4: Step-by-step developer integration recipe
│   └── postmortem/
│       └── 2026-09-25-stale-adb...md  # Tier 5: Historical incident retrospective & root cause
│
└── .agents/notes/
    ├── proposed/                      # Decision records under review
    ├── implemented/                   # Active decision records (bilingual triplets)
    ├── archived/                      # Superseded architectural notes
    └── rejected/                      # Discarded proposals with avoidance rationale
```

## Routing Rules

Apply `[INV-06]` in [Coding Standards](../../../../CODING_STANDARDS.md#1-core-invariants) before deciding whether a change needs glossary synchronization. Classify each fact by what it defines:

| Fact | Authoritative destination | Review question |
| :--- | :--- | :--- |
| Concept name, meaning, boundary or relationship | `CONTEXT.md` and `CONTEXT.zh.md` | Does this identify what the concept is, what belongs to it, or how it relates to another concept? |
| Business rule or subsystem guarantee | `CODING_STANDARDS.md` invariant and the relevant `docs/subsystems/` contract | Does this specify when an operation is allowed or what execution guarantees? |
| Implementation lifecycle or interface behavior | The relevant `docs/subsystems/` contract, with focused regression tests | Does this specify how state, inputs, outputs or resources behave? |
| Developer procedure | `docs/cookbook/` | Does this provide reproducible steps to operate or verify the system? |

Definitions include constraints that determine concept identity: Actual and Projected Occupancy differ by confirmed observation, for example. Project-specific technical concepts such as Capture Frame also belong in the glossary. A rule suppressing duplicate pending off-shift tasks, excluding planned idle time from a scene timeout, or comparing the priority of an entire recalled group belongs in a contract and its regression tests when those concepts retain their definitions.

Compare the meaning before and after the change, including existing entries with unchanged names. A new helper, threshold adjustment or defect fix alone is insufficient evidence of a changed domain concept. Existing glossary paragraphs do not determine the destination of new facts; classify each fact by the table above.

Record the affected concepts and the reason for the selected route in the existing decision note or review report. Either a justified unchanged-concept result or an identified definition delta completes the assessment. For a definition delta, prepare the exact bilingual glossary proposal and follow [root approval requirements](../../../../AGENTS.md#4-global-execution-constraints) before writing it. Review exercises are available in the [concept-impact cookbook](../../../../docs/cookbook/review-glossary-impact.md).

1. **Never duplicate facts**: If a contract is defined in `docs/subsystems/device-control.md`, `architecture.md` only references it; do not copy interface definitions.
2. **No narrative in Tier 3**: `docs/architecture.md` and `docs/subsystems/` contain present-tense facts only. Zero "we used to think..." or "we considered X vs Y".
3. **Narrative belongs exclusively in Tier 5**: Only `docs/postmortem/` records timelines, mistakes, and historical trade-offs.
