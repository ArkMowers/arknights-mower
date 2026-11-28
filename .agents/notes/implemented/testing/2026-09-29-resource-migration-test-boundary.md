---
title: Resource migration test boundary
status: implemented
category: testing
date: 2026-09-29
---

# Resource migration test boundary

Migration publishes a resource package without replacing the process cache. The migration tests preload the builtin selection, publish the legacy package, and explicitly refresh at a safe boundary before asserting the selected version. This covers an existing cached selection regardless of server watcher timing.

The fix reuses the existing refresh API and preserves production behavior. The tests retain the original-directory preservation and repeated-migration checks. No new abstraction or subsystem invariant is introduced.
