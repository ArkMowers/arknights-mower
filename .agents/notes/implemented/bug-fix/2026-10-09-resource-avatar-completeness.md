---
title: Complete Operator Avatars
status: implemented
category: bug-fix
date: 2026-10-09
---

Resource generation previously logged an unreadable operator avatar and still wrote the operator directory. The generator now fails with the operator name and code before publishing that directory. [INV-RES-04] requires a decoded 96×96 WEBP avatar for every obtainable operator in the generated directory.

MowerResource preserves existing images and fills missing PNGs from a pinned `ArknightsAssets/ArknightsAssets2` Chinese-server asset commit. Its source gate watches `cn`, downloads are bounded and validated, and publication checks every generated avatar. The original source lacks 德·托莱多, 旅骨 and 克莱门莎; the supplementary source contains all three.

The change reuses Pillow conversion and the existing resource pipeline. It adds no runtime image lookup or domain concept. Offline regressions exercise successful conversion, missing or corrupt source images and rejection despite a preexisting output. Publisher tests cover source-branch detection, finite reads, invalid images and rejection before release side effects.

Verification: generator tests pass; all 24 publisher tests pass. A replay of the published resource plus the three supplementary PNGs validates all 432 operator avatars with zero omissions. Standards review confirms finite 30-second downloads, a 2 MiB read cap and decoded image validation; specification review confirms no runtime dependency on the supplementary source. Repository structural checks pass independently.
