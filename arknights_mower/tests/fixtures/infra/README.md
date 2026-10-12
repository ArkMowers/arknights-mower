# Base recycling screenshots

These user-supplied screenshots from 2026-10-10 preserve the standard 1920×1080 RGB canvas:

- `base_main.png`: Base overview with the recycling facility visible.
- `recycle_todo.png`: Base to-do footer with one material output available for collection.
- `recycle_reward.png`: Material reward after collecting that output.

`resources/infra_collect_recycle.png` is the unscaled crop `(245, 986, 323, 1064)` from `recycle_todo.png`. The crop includes the recycling icon and blue collection badge; tests vary the quantity and remove the badge to verify eligibility. Tests replay scene transitions with mocked capture and input.
