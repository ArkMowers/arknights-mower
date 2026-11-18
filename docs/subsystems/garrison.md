# Garrison Simulation

The long-task editor offers personal quick simulation with three wins per strategy for a gold medal or six for the plated medal. Mower opens the rightmost terminal tab and the activity's open simulation entry. A personal lobby with an unfinished match takes the reconnection path. The solver checks for quick simulation before processing the match.

## Gameplay and device ownership

On first use Mower retrieves the Python script and tile layout directly from [GarrisonFarm](https://github.com/UnknownGlyph/GarrisonFarm/tree/fd373c9b1ab1e8fbb52ad78b8da4c461ab325abb). The [adapter](../../arknights_mower/solvers/garrison/upstream.py) verifies both files against pinned SHA-256 digests and stores them under the shared instance-data root in `downloads/garrisonfarm/<revision>/`. A verified cache supports offline use. The Mower distribution contains the adapter. Each session initializes separate upstream gameplay state and uses the low-requirement preset team profile.

The script reads 1920 × 1080 frames through Mower's recognizer and OCR engine. Taps and swipes use the current device. Dragging a unit across multiple frames uses Android pointer events on that same ADB connection. The scheduler keeps control of the worker throughout the task. The [long-task dormitory rules](base-scheduler.md#long-task-dormitory-maintenance) govern admission. The solver reserves the last thirty seconds before the next deadline for handover. Each new match requires ten minutes of playing time in addition to the handover reserve. The solver checks the budget after settlement and immediately before starting a match, so navigation time and changes to the base queue count against the available window. A saved match can resume when at least nine minutes remain before the next deadline, including the handover reserve. The same budget applies when an ordinary dorm release can be deferred. An active match can continue past ten minutes while its scheduling window remains open. Handover releases a held touch, closes the game and invalidates the cached scene. The next entry uses the game's saved match when available.

## Strategy progress

Mower reads the completion banner after recognizing the open strategy panel. It accepts split text and circled digits, retries unreadable counts and permits play when the count is clear but the strategy name is unknown. Only a recognized strategy contributes to the per-account, per-device progress record. The results screen counts attempts. Medal completion requires observed counts for all strategies in the season.

An unchanged failed run remains blocked. The long-task editor displays the reason and offers `重新核对并继续`. Rechecking clears the observed victory cache and keeps the pending match. Changing the target preserves observed wins. See the [focused tests](../../arknights_mower/tests/garrison_tests.py) for progress, admission and handover cases.

## Match-count goal

For level farming the long-task editor accepts a target number of settled matches. Zero allows continued play in eligible idle windows. This mode accepts an already decorated strategy. Both wins and losses count when the simulation result offers a return to the lobby. Mower saves the count before leaving that result. Reconnecting to an unfinished match or observing the same settlement twice adds no extra match.

Changing the match limit retains the recorded count for the current device and account. Reaching a positive limit ends the task and skips future dispatch until the user increases the target or starts a fresh count with `重新计数并继续`.
