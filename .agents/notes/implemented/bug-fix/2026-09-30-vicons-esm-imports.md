---
format: decision
title: ES Module Icon Imports
status: implemented
category: bug-fix
date: 2026-09-30
---

# ES Module Icon Imports

## Problem

CommonJS per-icon imports render blank in the Vite 8 development server, although production builds render them correctly.

## Decision

The affected manager entry is [MowerManager.vue](../../../../ui/manager/MowerManager.vue).

The frontend imports every `@vicons` icon from the package's `es/` directory: `@vicons/<pkg>/es/<Icon>`, the `@vicons/<pkg>/es` barrel, or named imports from the bare `@vicons/<pkg>` entry, whose `module` field points at `es/index.js`. The per-icon files at the package root and under `lib/` are CommonJS. The Vite 8 dev server resolves a default import of one of them to the module object, not the icon component, so the icon renders blank with a "missing template or render function" warning. A production build renders the same import correctly, so the defect appears in development only.

## Boundary

The `no-restricted-imports` rule in `ui/.eslintrc.cjs` rejects any `@vicons/<pkg>/<path>` outside `es/`, for both the `ui/src` application and the `ui/manager` entry. The import path carries the fix; the Vite configuration keeps its defaults and adds no `legacy.inconsistentCjsInterop` or alias. The CI workflow runs prettier and vitest but not ESLint, so the rule takes effect through `npm run lint` and the editor.

## Alternatives considered

The fix keeps default Vite resolution instead of adding an alias or enabling `legacy.inconsistentCjsInterop`; the ES import path addresses the observed module interop failure directly.

## Consequences

Import restrictions cover both UI entries, but Vitest render tests cannot detect this development-server failure. The rule and its development-only limit are described above.

## Verification

The original record reports the following verification results.

ESLint reports each of the 30 root per-icon imports this fix replaces and accepts `es/` per-icon imports and both barrel forms. vitest unwraps CommonJS default imports, so render tests pass with either path and cannot guard this defect. In the dev server without a backend, `/`, `/plan-editor`, `/maasettings` and `/mowersettings` render an svg in every `.n-icon` at mobile and desktop widths with no missing-template warnings, and the dev transform of `ui/manager/MowerManager.vue` imports each icon as a plain ES module. The [navigation sidebar note](../feature/2026-09-30-navigation-sidebar.md) covers the navigation shell, where the blank icons first appeared.
