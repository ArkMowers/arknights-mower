# Arknights Mower Documentation Hierarchy (One Home per Fact)

Every technical fact in Arknights Mower belongs to exactly one documentation tier.

```
/
├── AGENTS.md                          # Tier 1: Global standing pointers (1-3 lines each)
├── CONTEXT.md                         # Tier 0: Domain Glossary SSOT (English)
├── CONTEXT.zh.md                      # Tier 0: Domain Glossary SSOT (Chinese mirror)
├── CODING_STANDARDS.md                # Tier 0: Core behavior contracts
│
├── arknights_mower/AGENTS.md          # Tier 2: Python backend subtree contract
├── ui/AGENTS.md                       # Tier 2: Vue 3 frontend subtree contract
├── docs/AGENTS.md                     # Tier 2: Documentation subtree contract
├── .agents/notes/AGENTS.md            # Tier 2: Conditional decision-record entry point
├── .agents/notes/README.md            # Decision ownership, formats and lifecycle bodies
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
    ├── implemented/                   # Active bilingual decision records
    ├── archived/                      # Superseded architectural notes
    └── rejected/                      # Discarded proposals with avoidance rationale
```

## Routing Rules

| Fact | Authoritative home | Other locations |
| :--- | :--- | :--- |
| Concept name, meaning, boundary or relationship | `CONTEXT.md` and `CONTEXT.zh.md` | Link to the definition; follow root glossary approval before edits. |
| Global guarantee | `CODING_STANDARDS.md` | Subsystem rules use behavior names and direct links to their own contracts. |
| Complete interface, business rule or resource lifecycle | `docs/subsystems/` | Architecture links to the contract; review checklists ask distinct questions. |
| Task and skill coordination | `.agents/AGENTS.md` | Root and skill entry points link to the relevant branch. |
| Record ownership, schema and lifecycle criteria | `.agents/notes/README.md` | The notes subtree entry and skills route to the relevant rule or body. |
| Developer procedure | `docs/cookbook/` | Numbered actions and verification examples. |
| Decision rationale | One owning bilingual record | Link from the relevant contract; search existing owners before creation. |
| Incident timeline and retrospective | `docs/postmortem/` | Link to the resulting guarantees. |

Definitions include constraints that identify a concept, such as the distinction between confirmed Actual Occupancy and hypothetical Projected Occupancy. Project-specific technical concepts such as Capture Frame also belong in the glossary. Execution ordering, retry limits, bed takeover rules and duplicate-task suppression belong in contracts when concept identity remains stable.

Complete [Concept Impact Review](../../../../CODING_STANDARDS.md#concept-impact-review) by comparing names, meanings, boundaries and relationships before and after the change. The same name can acquire a different meaning. A new helper, numerical threshold or bug fix alone is insufficient evidence of a changed concept.

Record the concept-impact reason in the existing review or owning decision; stable concepts complete the assessment without glossary edits. For changed definitions, prepare exact bilingual wording and follow [root approval](../../../../AGENTS.md#4-global-execution-constraints) before writing. Existing mixed-content glossary paragraphs do not determine where new operational rules belong.

Contracts state current facts in present tense. Decision notes retain concise rationale; postmortems retain incident history. Root and subtree entry points carry only necessary local constraints and conditional pointers. Keep one full definition per fact instead of maintaining synchronized copies.

## Mower Contract Content

Start with the affected user operation or subsystem entry point and link to the relevant configuration, implementation and focused tests. Describe inputs, observable outcomes, failure handling and known limitations where they affect a caller or user choice. Address rules by behavior names and stable anchors; use headings when related explanations form independent sections.

Select details from the changed Mower boundary: Device Control describes target identity, input delivery and cleanup; Base Infrastructure & Scheduling distinguishes Actual Occupancy, Projected Occupancy and pending tasks; configuration describes persisted selections and compatibility; packaging and updates describe shipped files and reconstruction. These are prompts for relevant facts, not mandatory sections for every document.

Keep current behavior in the subsystem contract, operational steps in the cookbook, and durable reasons and accepted costs in the owning decision. Verification evidence identifies actual offline checks and any device behavior still awaiting observation. A local repair can keep reproduction and verification in its PR or change report under the record-ownership rules.

## Choosing Reference Content

Use these prompts when maintaining an existing subsystem reference. They require neither another document nor an empty section.

| Reader need | Useful content in Mower | When needed |
| :--- | :--- | :--- |
| Choose the subsystem | User operation, responsibility and important cost | Short opening |
| Find the change location | Task, actual source entry and focused offline tests | Long or multi-entry contracts |
| Use a boundary | Preconditions, input, observable result, error and recovery | Public API, device or state boundary |
| Configure it | Relevant settings and their authoritative definition | A real configuration choice exists |
| Maintain it | Responsibility, call path and state commit or cleanup points | They explain a difficult change |
| Assess evidence | Executable command with working directory, covered behavior and unobserved device outcomes | Verification guidance |
| Understand limits | Current unsupported case, consequence and available handling | It changes a caller's decision |

A contents list helps a long reference; short pages need no fixed list. Further reading links have a stated purpose. Runtime model-input, token and KV cache fields apply only to an actual model-facing subsystem, rather than every Mower document. Temporary hypotheses remain work material until there is durable rationale to record. Metadata earns its place through an actual checker or publishing consumer.
