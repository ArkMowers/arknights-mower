# Event sign-in reference images

The `celebration_*.png` images come from the 2026-11-01 Thank-You Celebration
ten-day sign-in activity, captured on a MuMu device at 1920 × 1080. Each image is
the unscaled rectangle from `(650, 205)` to `(1850, 920)` of the original frame.
The recognition test restores that rectangle at its original position on a
1920 × 1080 canvas. The crop excludes account information.

- `celebration_before.png`: day one is unlocked and unclaimed.
- `celebration_claimed.png`: day one's receipt mark appears after collection.
- `celebration_middle.png`: the list is scrolled to the middle.
- `celebration_right.png`: the list is at its right edge, including day ten.
- `celebration_right_settled.png`: a later right-edge frame with slightly
  different numeral edges after the list settles.

All five images show one unlocked day. Future rewards, operator presentations
and costume presentations have no device verification in these references.

The `overlap_claimed_*_20261106.png` images retain the rectangle from
`(661, 714)` to `(1806, 898)` of two archived 1920 × 1080 frames recorded at
05:05:36 and 05:05:38 China time on 2026-11-06. They preserve the reward regions
before and after scrolling from days one through four to days four through
seven. The crops are saved as PNG without scaling after decoding the archived
JPEGs; account information and the rest of the page are excluded.

The overlap workflow test restores these regions at their original positions
and supplies the observed card coordinates: receipt-only spacing gives
279-pixel intervals before scrolling, while the visible day-seven numeral
establishes a 280-pixel grid afterward. It exercises both scroll directions
and rejects a page whose overlapping reward has been replaced by a different
card or whose candidate crops cannot contain the comparison region. This verifies
paging confirmation offline, without device input or reward collection.

## Costume presentation

`costume_without_wear_20261106.jpg` is a 1920 × 1080 frame from the 2026-11-06
day-six sign-in archive. It shows the Alanna costume presentation after `SKIP`,
with the `BRAND` label and `FLOT` logo visible and no 穿戴 button. The two
recognition templates use crops from an earlier frame in the same archive.
