---
title: Automatic Resource Font Expansion
status: implemented
category: bug-fix
date: 2026-10-09
---

Resource generation expands the room and mastery font subsets from the original game fonts before loading Pillow fonts. [INV-RES-01] Template Glyph Coverage requires every generated character to map to an actual glyph; absent source characters fail before either font or charset changes. Existing glyphs and metrics remain unchanged.

The pre-flight audit finds three room-name validators with the same fixed charset guard. A shared preparation routine verifies actual coverage before each consumer loads its fonts. Mastery preparation uses the existing model builder boundary. Full source fonts reside in repository-root `font_sources/`; an explicitly configured existing original can override them. Runtime keeps compact subsets and models.

Focused tests cover automatic expansion, no-op generation, actual cmap checks, missing source glyphs and unchanged rasterized existing characters.

## Standards review

PASS: generation retains matching font fingerprints, existing glyphs and metrics, runtime model boundaries and source-failure isolation. Domain concepts remain unchanged; no glossary modification is required.

## Specification review

PASS: the room subset includes 旅、门、骨; missing room names and mastery skills expand from the original game fonts. Focused glyph, template and recruitment regressions pass, and real-font raster comparison preserves all 576 room and 1519 mastery characters. The matching complete originals and licenses are bundled as generation inputs, so automatic expansion needs no administrator upload.
