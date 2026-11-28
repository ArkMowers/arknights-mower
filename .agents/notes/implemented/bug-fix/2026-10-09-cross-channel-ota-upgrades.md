---
title: Cross-channel OTA upgrades
status: implemented
category: bug-fix
date: 2026-10-09
---

# Cross-channel OTA upgrades

[INV-UPD-06] makes installed update channels admission boundaries: development admits Nightly, beta and stable; beta admits beta and stable; stable admits stable. Newer installable public releases replace the primary target without changing saved preferences. Development and beta primary-index failures remain errors; stable retains its GitHub Latest fallback. Optional channel failures preserve the primary result. Existing channel-specific index schemas remain compatible with older clients.

`latest_release_index` reuses semantic ordering and full-package validation. The selected target supplies both its full asset and exact-source OTA asset. Publisher source selection reserves bounded recent Nightly sources for beta releases and beta/Nightly sources for stable releases. This removes the publisher's blanket Nightly exclusion without adding another package format, client installer or channel preference.

Focused tests exercise the real update-check callers, retained preferences, exact-source OTA selection, stable-channel isolation, version equality, optional-index failures and incompatible packages. Existing Nightly direction, rollback confirmation and reconstruction tests retain their guarantees. MowerRelease and Android companion suites cover producer source quotas and Android selection. Verification passes: 110 focused desktop/source/OTA tests with 165 subtests, 27 publisher tests with 13 subtests, and 23 Android tests with 30 subtests. Real Nightly `g85e916f7` to alpha.11 produces a 2,430,022-byte Windows OTA and a 23,479,114-byte Android OTA. Windows reconstruction matches the target files; Android reconstruction matches 3,130 Mower files and 10,396 runtime entries, permissions and hashes, and passes package inspection. Runtime recompression changes the container digest and updates only its corresponding manifest digest; runtime contents remain identical. No live device installation is performed.

Standards Findings: bounded existing requests, canonical path checks, checksums and full-package fallback remain enforced; no glossary concepts change. Spec Findings: newer public releases become eligible without changing preferences, exact-source cross-channel OTA is generated, same-version checks remain idle, and unsupported optional assets preserve the primary result.

[Software update contract](../../../../docs/subsystems/software-update.md#11-cross-channel-upgrades) owns the interface rules.
