# Recycling collection evidence

`device.png` is the reward crop supplied on 2026-10-10.

`reward_quantity_20261012.jpg` is the unchanged archived 1920×1080 reward frame from the user-authorized remote inspection on 2026-10-12 at 14:41:55 (Asia/Shanghai). It shows 装置 × 1. Replay in the remote environment reads the quantity as `1` with confidence approximately 0.94976, which the previous 0.95 threshold rejected. The regression exercises the real reader through collection persistence with two matching observations, without connecting to a device.

`reward_orirock_20261013.jpg` is the unchanged 1920×1080 archived reward frame supplied with the Windows failure logs for 2026-10-13 at 15:06:47 (Asia/Shanghai). It shows 固源岩组 × 1. The regression simulates `cv2.imread` returning no image while loading the real Chinese-named material icon, and exercises the real reader through collection persistence. It verifies Unicode-safe loading without requiring a Windows runtime or connecting to a device.

`occupants_20261012.jpg` is the unchanged 1920×1080 frame captured on 2026-10-12 at 14:41:59 (Asia/Shanghai), retrieved during the user-authorized remote inspection on 2026-10-14. SHA-256: `e44c294a8bee7ece7a7aa48bacd24e827d9f01fc326bd1cdb98a41600eec0695`. The recycling residence panel shows 旅骨 and 岳羽由加莉. Its left-edge pixel at `(1233, 1)` is dark even though the panel title matches. The regression exercises actual panel and occupant recognition through collection persistence without connecting to a device.

`default_valuation_20261012.xlsx` is the unchanged `mower默认旅骨效率计算器.xlsx` from the supplied `准备发给果果.zip`. SHA-256: `5f481da7a5378c4821a3abb80f8250d16bd43d57373f08f01229839866c08578`. The `在此导入!A3:D149` values supply the default catalog. `计算表!C49/F53/C53` and `计算表 (2)!C49/F53/C53` provide independent cached results for daily sanity and 20%/30% operator efficiency under the two mechanism assumptions. The probability weights match the existing recycling model.

The companion `九色鹿_蚀清_年材料价值计算结果.xlsx` explains Nine-Colored Deer causality, Corroserum fixed byproducts and Nian/Arene random byproducts. Its 晶体元件 value differs by 0.1 from the final calculator input. The default preserves the calculator's complete saved price snapshot, including its cached crafting values; the metadata records this discrepancy and both source hashes. No workbook macros or attached Python scripts are executed.

`reward_sugar_20261027.jpg` is the unchanged 1920×1080 frame from the supplied error archive for 2026-10-27 at 12:06:50 (Asia/Shanghai). It shows 糖 × 1 and passes offline replay with the existing reader and with the alpha.13 PP-OCRv6 tiny implementation. The fixture preserves the archived JPEG bytes; it cannot establish which original uncompressed observation or validation stage failed. New archives retain lossless PNG pixels and per-stage recognition logs for that diagnosis.
