# Event sign-in reference images

The five original `celebration_*.png` images come from the 2026-11-01 Thank-You Celebration
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

The `celebration_eight_claimed_*_20261108.png` images use the same rectangle
from archived MuMu frames at 23:31:21 and 23:31:24 China time. The right page
shows days seven through ten, with the first eight days already claimed. The
middle page shows complete cards for days five through seven and cropped cards
for days four and eight. The receipt mark on the cropped day-four card could
be read as day one. The replay checks that the solver confirms the overlap on
day seven and retains day five as the first complete card on the middle page.

`overlap_claimed_ambiguous_middle_20261108.png` retains the rectangle from
`(661, 348)` to `(1806, 898)` of a 22:37:41 China time archive from the same
event. It shows complete cards for days four through seven. The overlap test
pairs it with the right page above to verify that the solver distinguishes the
day-seven card from a similar claimed reward. A second case duplicates the
day-seven crop at the other candidate position and checks that the solver
rejects the ambiguous overlap.

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
