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
1. **Never duplicate facts**: If a contract is defined in `docs/subsystems/device-control.md`, `architecture.md` only references it; do not copy interface definitions.
2. **No narrative in Tier 3**: `docs/architecture.md` and `docs/subsystems/` contain present-tense facts only. Zero "we used to think..." or "we considered X vs Y".
3. **Narrative belongs exclusively in Tier 5**: Only `docs/postmortem/` records timelines, mistakes, and historical trade-offs.
