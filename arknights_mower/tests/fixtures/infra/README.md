# Base recycling screenshots

These user-supplied screenshots from 2026-10-10 preserve the standard 1920×1080 RGB canvas:

- `base_main.png`: Base overview with the recycling facility visible.
- `recycle_todo.png`: Base to-do footer with one material output available for collection.
- `recycle_reward.png`: Material reward after collecting that output.

`resources/infra_collect_recycle.png` is the unscaled crop `(245, 986, 323, 1064)` from `recycle_todo.png`. The crop includes the recycling icon and blue collection badge; tests vary the quantity and remove the badge to verify eligibility. Tests replay scene transitions with mocked capture and input.

`order_todo.png` preserves the footer at `y >= 970` from a 1920×1080 runtime screenshot captured on 2026-11-04 at 19:51:26. The rest of the frame is blacked out. It shows manufacturing output and one order available for collection. `resources/infra_collect_bill.png` is the unscaled crop `(494, 990, 544, 1058)` from this frame, excluding the changing quantity. Tests exercise actual order recognition and the to-do collection caller, quantity changes, horizontal movement and screens without an order prompt.
