---
title: Room Title Confirmation
status: implemented
category: simplification
date: 2026-10-12
---

# Room Title Confirmation

## Contract

[INV-REC-11] Facility Title Priority: A positively matched facility title on the current Capture Frame takes precedence over icon color, including during entry animation; unknown titles retain icon recognition and bounded room-entry recovery.

## Boundary and simplification

`BaseMixin.detect_room` owns room identity for entry confirmation, roster readback and training navigation. Its existing title matching runs before color classification and includes the recycling title. `detect_room_type` remains the shared icon classifier for production-facility observations. The change reorders existing recognition rather than adding an animation timer, another classifier or another recovery loop. Scheduling mechanics, device lifecycles and configuration schemas retain their existing contracts; no glossary change is required.

## Verification

Offline tests replay three title crops from the supplied archive, retain the original decoded pixels, and confirm recycling identity during animation and after settling. Synthetic competing training color cannot override a positive title. Blank titles remain unknown, numbered manufacturing facilities and training icons retain recognition, and actual entry confirmation avoids unnecessary home recovery. Existing map relocation tests retain bounded failure and cancellation checks.

## Review

### Standards Findings

Pass: recognition uses the same Capture Frame, adds no external operation or retry loop, retains existing unknown verdicts and configuration, and passes governance and Python lint checks. The simplification audit retains the shared production-facility classifier and removes no public interface.

### Spec Findings

Pass: all 590 archived frames replay offline. Against alpha baseline `798630d5`, five former training identities become recycling; every other identity remains unchanged. The strongest interfering crop also reproduces training color under the current icon classifier, while title recognition and entry confirmation identify recycling.

Validation on the alpha-based branch: `python -m pytest arknights_mower/tests/room_map_relocation_tests.py arknights_mower/tests/verify_governance_tests.py -q` passes 84 tests. `python scripts/verify_governance.py --base origin/alpha`, repository-wide Ruff lint and format checks, and `git diff --check` pass. Device execution remains unverified.

## Workshop title extension

The 2026-10-13 archive contains three entry frames whose visible workshop title accompanies icon pixels classified as manufacturing. On baseline `4f3f331e`, these frames return `room_1_3` and cause repeated room-entry recovery. The existing title-first decision also covers the workshop. Its text-only template excludes the colored icon and facility number, retaining the 0.78 threshold and existing icon fallback without delaying captures. The template comes from the settled title at 02:07:16.675; four lossless title crops preserve decoded pixels from the entry, repeated entry and settled JPEG frames.

Offline replay of the same 1,152 archived title crops changes exactly three identities from `room_1_3` to `factory`; all remaining identities are unchanged. Before the extension, seven focused assertions fail across archive recognition, competing icon color and actual entry confirmation. After the extension, 166 focused room-navigation, recycling and governance tests pass, including rejection of a manufacturing-room target while the workshop title is visible. Standards review retains the same Capture Frame, unknown verdict, recovery budget and shared icon classifier. Requirement review confirms the three incident frames without introducing capture waits. The decision remains implemented, with unchanged domain concepts and no glossary edit; live device execution is unverified.
