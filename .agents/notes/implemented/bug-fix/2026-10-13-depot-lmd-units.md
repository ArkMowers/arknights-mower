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

## Decision

LMD uses the existing OCR engine on the complete quantity band and converts 万 and 亿 with decimal arithmetic. Complete plain integers remain valid. Malformed or low-confidence readings return `None` and use the scan's existing skip behavior. The [depot recognition description](../../../../docs/subsystems/depot-recognition.md) defines accepted values and failure behavior.

## Alternatives considered

Adding an 亿 template requires a representative game screenshot and new template mapping. The existing OCR engine already supports Chinese characters and avoids a new asset. Falling back to digit templates after failed OCR repeats the original unit-loss defect, so uncertain LMD readings remain unconfirmed. Other item readers retain their existing templates.

## Consequences

The selected reader recognizes unit-bearing amounts without a new model or configuration. LMD recognition now depends on OCR confidence. Cloud inventory counts are parsed as complete integers; missing cloud currency entries leave scanned currency relevant. Existing incorrect inventory requires a successful new scan; changing code alone does not correct historical snapshots.

## Verification

Offline tests cover unit conversion, plain integers, malformed readings, OCR initialization and failure, reader selection and full cloud integer counts. Real game screenshot OCR accuracy requires a recorded quantity band and remains outside mocked OCR tests.
