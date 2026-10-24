---
title: Manufacturing Switch Boundary After Drone Acceleration
status: implemented
category: bug-fix
date: 2026-09-29
---

# Manufacturing Switch Boundary After Drone Acceleration

[English](2026-09-29-manufacturing-switch-boundary.md) | [中文](2026-09-29-manufacturing-switch-boundary.zh.md)

## Contract

- **[INV-SCHED-06] Manufacturing Switch Boundary**: After Drone Acceleration, a manufacturing product switch tracks completion of the accelerated current unit; the next unit's countdown never postpones that switch.
- The confirmation waits for the accelerated unit's estimated remaining time using the lower of the inspected and current production rates, plus the configured buffer. A switch without an acceleration result retains its fresh countdown check.

## Evidence and implementation

On 2026-09-27 at 21:29, `yunxi` logs 55 drones for B301 with zero planned wait, then defers the product change for 5,426 seconds. The delay approximates a full next unit of Intermediate Battle Records at the current production rate. Five other deferrals show the same pattern. The previous check subtracts a queue boundary captured before acceleration from a countdown that can advance to the next unit.

`BaseSchedulerSolver._execute_manufacture_acceleration` records the accelerated unit's remaining base time after confirmation. `_change_manufacture_product` uses that value and elapsed production time instead of the stale queue boundary. The [base scheduling contract](../../../../docs/subsystems/base-scheduler.md) owns the permanent rule.

## Verification

Hermetic tests cover immediate unit rollover, rollover during page navigation, and a remaining unit that still requires deferral. The focused manufacturing product switch suite exercises the surrounding behavior.
