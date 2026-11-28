# Official recycling preview fixtures

Source: [official base expansion preview](https://www.bilibili.com/opus/1256772817402200067), supplied by the user on 2026-10-08.

- `room.png` and `map.png`: 1920×1080 stills.
- `dashboard.png`: 1280×720 still; `room_small.png` and `dashboard_small.png` retain the earlier lower-resolution stills for cross-resolution recognition checks.
- `selection_empty.png`, `selection_two.png` and `dashboard_two.png`: original 1280×720 frames 28, 42 and 60 of the supplied `70a532089b464456b5017e154236eeed161775300.gif` (zero-based frame numbers).

Tests normalize to the standard 1920×1080 Capture Frame with OpenCV INTER_AREA. Runtime templates retain only fixed facility labels; floor numbers, operator faces, efficiency values and central animation are excluded.

These are official preview images, not live-device captures. The GIF confirms two-person multi-selection and dashboard return, but does not show the standard residence-information panel.
