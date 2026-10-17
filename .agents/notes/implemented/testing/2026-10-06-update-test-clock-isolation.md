---
title: Update Test Clock Isolation
status: implemented
category: testing
date: 2026-10-06
---

# Update Test Clock Isolation

Update compatibility tests replace the worker module’s clock reference. Standard-library time functions remain available to other threads; cleanup retry and expiry assertions count only worker calls. The permanent-lock case includes an unrelated standard-library sleep inside the patch scope.
