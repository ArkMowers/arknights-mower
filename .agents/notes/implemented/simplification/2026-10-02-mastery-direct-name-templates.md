---
title: Direct Training Panel Name Templates
status: implemented
category: simplification
date: 2026-10-02
---

[English](2026-10-02-mastery-direct-name-templates.md) | [中文](2026-10-02-mastery-direct-name-templates.zh.md)

# Direct Training Panel Name Templates

## Contract

**[INV-REC-05] Training Panel Identity**: Training panel identity comes from full-name templates on the current Capture Frame; unknown names or missing skills retain bounded retry and never derive actual occupancy from the requested plan.

The name reader matches the complete bracketed operator name against the bundled panel templates. It requires a sufficient name score, an aligned closing bracket and a sufficient margin over the next distinct name. Alternate forms with the same name share one identity. Missing or stale models, weak or ambiguous matches produce unknown identity; OCR names never provide a fallback. Skill OCR and its existing template and fuzzy checks remain separate.

## Incident evidence

The supplied archive contains 174 Capture Frames and a runtime log. At 2026-10-02 22:06:38, two OCR passes report `[白面]脑啡肽`; the game displays `[白面鸮]脑啡肽` and `15:14:09`. The log subsequently keeps the plan pending until the following day. It contains no application build identifier and does not establish the source revision used by the incident program.

The pinned `rapidocr-onnxruntime==1.3.24` recognizer has 6,625 output symbols and excludes `鸮`, while including `白` and `面`. OCR cannot emit the complete name; thresholding cannot supply the absent symbol. Operator-list recognition already uses full-name pixel templates, separately from panel OCR.

Replay against alpha revision `7612ed88` confirms that the earlier omitted-name template correction handles these pixels. The direct template reader now identifies the name without consulting OCR. The actual panel has name score 0.892 and skill score 0.888. Replay verifies recognition and mocked start-confirmation transitions, not live-device completion or archive delivery.

## Simplification and font contract

The reader removes the name-specific thresholded OCR retry, one-character candidate search and name correction chain. Name matching uses the full roster and the current Capture Frame, independently of plans and OCR skill strings. Closing-bracket alignment rejects partial prefix matches such as `阿` within `阿米娅` or `凯尔希` within `凯尔希·思衡托`. Collections remain bounded by the bundled roster; no persisted cache, extra retry budget or operator-specific rule is introduced.

Panel templates retain the existing 37-pixel `SourceHanSansCN-Medium-mastery.ttf` font subset. Middle-dot rendering retains `NotoSansHans-Medium-room.otf` advance widths. Operator-list templates use their own card geometry and are not substituted for panel templates. The model's existing font fingerprints, charset coverage and roster digest checks remain in place. The cropped fixture retains only the 520-by-42 panel region from `1790949998483007200.jpg`; account values and the complete runtime log remain outside the repository.

The [scheduler contract](../../../../docs/subsystems/base-scheduler.md) owns name identity. The [diagnostics contract](../../../../docs/subsystems/device-control.md) retains selective screenshot archiving for visual ERROR notifications. Current glossary definitions remain accurate.

## Verification

The [identity suite](../../../../arknights_mower/tests/mastery_panel_identity_tests.py) replays production OCR and templates on the actual panel, verifies a training status update with one skill OCR call, rejects name reliance on OCR, and preserves bounded waits for absent, stale or blank evidence. The [template suite](../../../../arknights_mower/tests/mastery_panel_template_tests.py) tests every supported roster name, real panels, low scores and close competitors. Existing [skill OCR tests](../../../../arknights_mower/tests/mastery_panel_ocr_tests.py) retain cross-form skill conflicts and middle-dot spacing. Scheduling-only fixtures supply synthetic panel or name results at the reader boundary; real recognition uses rendered templates and supplied pixels.

## Standards Findings

PASS: Name evidence comes from the current Capture Frame and is independent of plans and OCR. The change removes name recovery branches, preserves font and resource contracts, and introduces no device operations or configuration changes.

## Spec Findings

PASS: Training names use direct template recognition; all OCR name fallbacks are removed. Unknown identity consumes the existing deadline without false mismatch or training writes. Skill checks and selective visual-failure archives retain their contracts.
