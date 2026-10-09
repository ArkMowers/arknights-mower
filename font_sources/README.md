# Generation source fonts

These complete original fonts expand the compact room and mastery subsets before model generation. They are build inputs in the repository root and are excluded from runtime application and resource packages.

| File | Source | SHA-256 | License |
| --- | --- | --- | --- |
| `NotoSansHans-Medium.otf` | Arknights CN Android 2.7.71, Unity `sharedassets1.assets`, `Font` named `NotoSansHans-Medium` | `25033438cfa41f1873d4902b8555956557b765117756bcef96406e023e49578c` | Apache License 2.0; see [license](LICENSE-APACHE-2.0.txt) |
| `SourceHanSansCN-Medium.ttf` | Arknights CN Android 2.7.71, APK `assets/font/SourceHanSansCN-Medium.ttf` | `f09e7abc149f1079ea73ab8dffd31d4f5f9dc30c1d7716d4770f87d84be3b6c9` | SIL Open Font License 1.1; see [license](LICENSE-OFL-1.1.txt) |

`build_font_subsets.source_font` uses a matching file in an explicit `MOWERFONTS_DIR` when present, then these bundled originals, then the legacy local `ArknightsGameResource/fonts` directory. The public-recruitment font inputs retain their existing source; automatic room and mastery expansion needs no new MowerFonts upload.
