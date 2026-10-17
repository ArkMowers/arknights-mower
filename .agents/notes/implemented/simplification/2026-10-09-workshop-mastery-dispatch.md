---
title: Confirmed crafting mastery dispatch
status: implemented
category: simplification
date: 2026-10-09
---

# Confirmed crafting mastery dispatch

Confirmed workshop output updates the local inventory database. Automatic mastery start admission accepts that confirmed stock after each batch and reuses the existing start dispatcher, plan priority, material-wait boundary and per-plan task deduplication. The queued task uses the current time; training-room observation and protection still govern execution after workshop staffing restoration.

[INV-SCHED-40] prohibits admission from unconfirmed output, missing local counts or disabled automation. The supplied stock is authoritative even when the cloud snapshot contains a higher count. Candidate or queue failures retain confirmed inventory and log the dispatch failure separately from crafting confirmation.

The simplification audit identifies existing scan and web callers of the same dispatcher. An optional material-name inventory input reuses candidate selection without a second scheduler, polling loop or cloud refresh. Warehouse and web callers retain their existing snapshot input. Offline tests exercise real batch confirmation, inventory persistence and start-task deduplication, including partial preparation, consumption, invalidated counts, disabled automation and dispatch failure.
