## 1. Create Constitution Spec

- [x] 1.1 Extract 8 hard requirements from AGENTS.md into `specs/project-constitution/spec.md` with scenarios
- [x] 1.2 Extract 3 core principles and 5 prohibitions with scenarios
- [x] 1.3 Extract Data Class Boundaries rules with scenarios
- [x] 1.4 Extract File Organization and Naming conventions with scenarios
- [x] 1.5 Add screencap recovery + tap/swipe fail-fast requirement with scenario
- [x] 1.6 Add DevicePort reconnect at dispatch layer requirement with scenario
- [x] 1.7 Verify all 14 requirements have at least one scenario each

## 2. Create Migration Architecture Spec

- [x] 2.1 Document system architecture overview (scheduler/ layers, InfraKit, data flow) in `specs/migration-architecture/spec.md`
- [x] 2.2 Expand recognition layer architecture: 3-tier strategy dispatch (ColorMatcher → TemplateMatcher → FeatureMatcher ORB+FLANN+SVM) with scenario
- [x] 2.3 Document three-layer scheduling model (Planner → Dispatch → Executor) with scenario
- [x] 2.4 Document LifecycleHook chain (7 planned hooks: maintenance, daily, warehouse, sanity, secret sanctum, dormancy, update)
- [x] 2.5 Document migration roadmap split into Phase 1 (Steps 1-5+7) and Phase 2 (Step 6 Copilot)
- [x] 2.6 Document current migration status and unfinished work items
- [x] 2.7 Verify all 8 requirements have at least one scenario each

## 3. Verify and Finalize

- [ ] 3.1 Run `openspec status --change "project-constitution-and-migration-architecture"` to confirm all artifacts complete
- [ ] 3.2 Cross-check constitution spec requirements against AGENTS.md to ensure no missing constraints
- [ ] 3.3 Cross-check architecture spec status against PROJECT_MEMORY.md to ensure accuracy
- [ ] 3.4 Archive the change with `/opsx:archive` to merge specs into baseline `openspec/specs/`
