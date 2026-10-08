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

| Fact | Authoritative home | Other locations |
| :--- | :--- | :--- |
| Concept name, meaning, boundary or relationship | `CONTEXT.md` and `CONTEXT.zh.md` | Link to the definition; follow root glossary approval before edits. |
| Invariant identifier and concise guarantee | `CODING_STANDARDS.md` | Reuse the identifier and link to its contract. |
| Complete interface, business rule or resource lifecycle | `docs/subsystems/` | Architecture links to the contract; review checklists ask distinct questions. |
| Task and skill coordination | `.agents/AGENTS.md` | Root and skill entry points link to the relevant branch. |
| Record ownership, schema and lifecycle criteria | `.agents/notes/AGENTS.md` | Skills implement this policy rather than redefining it. |
| Developer procedure | `docs/cookbook/` | Numbered actions and verification examples. |
| Decision rationale | One owning bilingual triplet | Link from the relevant contract; search existing owners before creation. |
| Incident timeline and retrospective | `docs/postmortem/` | Link to the resulting guarantees. |

Definitions include constraints that identify a concept, such as the distinction between confirmed Actual Occupancy and hypothetical Projected Occupancy. Project-specific technical concepts such as Capture Frame also belong in the glossary. Execution ordering, retry limits, bed takeover rules and duplicate-task suppression belong in contracts when concept identity remains stable.

Apply [INV-06](../../../../CODING_STANDARDS.md#1-core-invariants) by comparing names, meanings, boundaries and relationships before and after the change. The same name can acquire a different meaning. A new helper, numerical threshold or bug fix alone is insufficient evidence of a changed concept.

Record the concept-impact reason in the existing review or owning decision; stable concepts complete the assessment without glossary edits. For changed definitions, prepare exact bilingual wording and follow [root approval](../../../../AGENTS.md#4-global-execution-constraints) before writing. Existing mixed-content glossary paragraphs do not determine where new operational rules belong.

Contracts state current facts in present tense. Decision notes retain concise rationale; postmortems retain incident history. Root and subtree entry points carry only necessary local constraints and conditional pointers. Keep one full definition per fact instead of maintaining synchronized copies.
