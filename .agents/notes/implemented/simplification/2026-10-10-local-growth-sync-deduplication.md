---
title: Local Growth Sync Deduplication
status: implemented
category: simplification
date: 2026-10-10
---

# Local Growth Sync Deduplication

**[INV-GROWTH-04] Local Progression Sync Check**: Automatic and manual Yituliu sync validate the upload payload locally and send nothing when it matches the last confirmed upload for the configured token, while failed uploads never advance the comparison baseline.

Automatic Skland retrieval and the existing refresh controls retain their behavior. A successful refresh enters the shared local upload check before any Yituliu transmission.

Both upload entry points share `sync_cached_operators`; no additional frontend comparison or remote query is required. A SHA-256 digest covers the validated upload fields with deterministic object keys and operator ordering. Cache timestamps, warehouse stock and unrelated fields are excluded. The restricted token settings file persists only the latest confirmed digest and existing status, preserving the comparison across restarts. Replacing or clearing the token resets the baseline; saving an identical token preserves it. Changed player identity or progression uploads again. A skipped result keeps the actual upload timestamp and reports that no data was transmitted. Network and validation failures preserve the last confirmed digest.

The [growth contract](../../../../docs/subsystems/growth-planning.md) defines the interfaces. Offline tests cover unchanged manual and automatic synchronization, ordering, changed progression and identity, token changes, failed requests and automatic synchronization after a successful Skland refresh.

Verification on the alpha-based branch: the focused synchronization, Skland refresh and governance suites pass 88 tests; the token-settings and mastery-store suites pass 8 tests. Ruff, ESLint, Prettier and diff whitespace checks pass. Structural governance passes with two pre-existing archived-reference warnings. These checks verify local deduplication; live write compatibility with the next Yituliu interface remains pending its published contract.
