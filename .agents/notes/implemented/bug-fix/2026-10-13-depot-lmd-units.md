---
format: decision
title: Depot LMD units
status: implemented
category: bug-fix
date: 2026-10-13
---

# Depot LMD units

## Problem

The depot digit matcher has templates for ten digits, a decimal point and 万, but none for 亿. Its conversion code also applies only the 万 multiplier, so `1亿` loses its unit and becomes `1`.

Recorded game evidence from 2026-10-31 exposes a separate error in the OCR input: the quantity is `721.4万`, but OCR reads the adjacent LMD icon as a leading `1`, producing `1721.4万` with confidence 0.93051. The scan consequently records 17,214,000 instead of 7,214,000. Earlier tests supplied mocked OCR results and could not detect this pixel recognition error.

## Decision

LMD uses the existing OCR engine on the complete quantity text and converts 万 and 亿 with decimal arithmetic. Complete plain integers remain valid. Malformed or low-confidence readings return `None` and use the scan's existing skip behavior. The [Depot Recognition Subsystem](../../../../docs/subsystems/depot-recognition.md) defines accepted values and failure behavior.

Before OCR, `读取龙门币数字` selects rows 12 through 45 of the existing 50-by-180-pixel grayscale quantity band and applies a brightness threshold of 180. It removes foreground components connected to the top or bottom edge, where the adjacent icon and background extend beyond the text height. The full horizontal width remains available for digits and units, including components touching the left or right edge. This preprocessing changes neither the Capture Frame definition nor the meaning of an inventory quantity; both existing domain concepts remain unchanged.

## Alternatives considered

Adding an 亿 template requires a representative game screenshot and new template mapping. The existing OCR engine already supports Chinese characters and avoids a new asset. Falling back to digit templates after failed OCR repeats the original unit-loss defect, so uncertain LMD readings remain unconfirmed. Other item readers retain their existing templates.

Cropping a fixed horizontal margin or deleting a recognized leading `1` can remove a real digit from a long amount. Raising the confidence threshold also cannot reliably distinguish an icon from text: brightness thresholding without component removal still reads the recorded amount incorrectly with confidence 0.98699. Removing components that cross the text's vertical limits addresses the visible interference while retaining the complete amount.

## Consequences

The selected reader recognizes unit-bearing amounts without a new model or configuration. LMD recognition now depends on OCR confidence. Cloud inventory counts are parsed as complete integers; missing cloud currency entries leave scanned currency relevant. Existing incorrect inventory requires a successful new scan; changing code alone does not correct historical snapshots.

## Verification

Offline tests cover unit conversion, plain integers, malformed readings, OCR initialization and failure, reader selection and full cloud integer counts. The [recorded-pixel regression](../../../../arknights_mower/tests/depot_lmd_pixel_tests.py) runs the real item model, category scan and local OCR engine on the complete 2026-10-31 basic-items frame, producing 7,214,000. It also crops and matches the actual LMD item from the existing 2026-10-18 frame, producing 7,512,000. That older frame's other items are outside this regression. Constructed quantity bands reuse recorded glyphs to verify a real leading `1` in `1721.4万` and the longer `9999.9万`; they are not recorded game amounts. The new fixture preserves the original JPEG bytes; its SHA256 is `3b43800bc54174930c620168a9a439b0ee0944a3a8b6e930c842180031cb686a`. These examples cover the observed icon interference and width preservation, rather than establishing accuracy for every game quantity or screenshot.
