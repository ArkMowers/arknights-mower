# Recruitment Subsystem

## 1. Scope

`RecruitSolver` calculates recruitment tag results, applies the saved selection policy before queuing tag selection, and records operators obtained from completed slots.

## 2. Selection Policy

`recruit_auto_5 = 1` selects five-star results automatically. `recruit_auto_5 = 2` leaves them for manual selection unless `recruit_auto_only5` is enabled and exactly one calculated choice remains. Existing equivalent-result collapsing occurs before this check. Manual handling sends the rare-tag notification, advances the recruitment slot and returns without queuing selection.

<a id="unfinished-support-robots"></a>
### Unfinished support robots

`recruit_auto_robot` (自动招募未满潜支援机械) defaults to false. When enabled, the available tags must include 支援机械, and the highest guaranteed ordinary rarity must be three stars, with no four-, five- or six-star combination. A combination containing 支援机械 qualifies only when every one-star candidate is present in the local Skland roster cache with an integer `potentialRank` from zero through four; five means full potential. The sum of that rank, cached operator-specific tokens and possible copies from one-star recruitments already started in this solver run must remain below five for every candidate. Missing operators or missing, invalid or unreadable roster or item data do not confirm a deficit. Recruitment reads the shared cache without requesting a remote refresh or writing progression. Reservations apply only within the current solver run; earlier runs and unsynchronized game changes remain a cache-freshness limitation.

The solver automatically selects a qualifying combination, preferring fewer candidate operators and then fewer tags, and uses 3 hours 50 minutes. This selection takes precedence over 保留支援机械标签 (`recruit_robot`) and the three-star permit threshold (`recruitment_permit`), but still requires at least one permit. It does not refresh these tags. When the switch is off or no combination qualifies, existing rarity selection, manual handling and permit rules apply, including the saved support robot policy when higher-rarity combinations are available.

Time adjustment uses the real increase or decrease controls according to the numeric target. For a nonzero minute target, the solver sets the target hour before changing minutes, keeping the operation away from the 1:00 and 9:00 limits where the controls couple hours and minutes. Ordinary 9:00 recruitment clears minutes before changing hours. Each observation adjusts one field and refreshes the frame before deciding the next operation.

## 3. Subsystem Invariants

- <a id="manual-selection-authority"></a>**Manual Selection Authority**: Manual five-star recruitment never queues automatic selection unless the unique-choice exception is enabled and exactly one calculated choice remains.

### Result recognition before dismissal

The token icon identifies `RECRUIT_AGENT`, but the profession icon can still be obscured by the entrance animation. [`RecruitSolver.recruit_result`](../../arknights_mower/solvers/recruit.py) requires a recognized profession icon before cropping and matching the operator name. It checks the current frame immediately and makes at most five attempts for an unrecorded slot. A missing icon leaves the result unrecorded and the display untouched; before each remaining attempt, the handler waits one second and refreshes the observation. The fifth failed attempt clears the observation and ends the recruitment run without another wait or entering the shared recognition-failure retry path. This adds at most four seconds of deliberate waiting, excluding capture and recognition time. Other recognition failures retain [`BaseSolver.run`](../../arknights_mower/utils/solver.py)'s existing retry behavior.

The result handler taps only after recording the name, or when that integer slot already has a recorded result. An already recorded result is not recognized again, and each call sends at most one tap. Cancellation and other recognition or device exceptions propagate to the caller without an extra dismissal tap.

Repeatedly unreadable profession icons exhaust the five result attempts and return partial results under the existing solver behavior. This does not establish that the slot was recognized: the daily scheduler can still record the recruitment run time, and subsequent scene navigation can leave the display. Name-template confidence rules and daily scheduling completion semantics are outside this repair.

### Recruitment progress logs

INFO records describe recognized tag names, confirmed recruitment starts and operators recognized from completed slots. Tag coordinates, candidate pools, internal operator identifiers and repeated selection steps remain at DEBUG under the [application logging rules](../../CODING_STANDARDS.md#6-application-logging).

A recruitment start is reported once when a pending choice is first confirmed, either by a successful return after starting recruitment or by observing that slot recruiting on the main screen. The message states the chosen tags, or that no tags were selected, and the configured recruitment duration. A candidate pool is never reported as an acquired operator. The result handler reports an operator after recording the recognized name, includes `log_agents` for in-place avatars and does not report an already recorded slot again. End-of-run summaries retain the existing return values and notification payloads without repeating these INFO events.

Rare-tag notifications retain their selection policy. Slots left for manual selection say so explicitly. When ordinary recruitment is skipped because permits are below the configured three-star threshold, the message reports the observed permit count and threshold. A tag-calculation failure reports a readable ERROR while its calculation data remains at DEBUG. Existing unreadable-result warnings remain visible.

Recognized tag lists carry neutral display metadata. Confirmed starts carry the selected tag combination and its existing calculated rarity through the optional [recruitment log fields](web-access.md#live-log-records). Rare-tag notices include every distinct combination at the selected rarity, in calculation order before equivalent-result collapsing. Tags within a combination are joined by `＋`; combinations are separated by `；`. The frontend colors each combination as one unit and gives the notice text the selected rarity's color. It does not infer that each member independently has that rarity. Reporting all combinations does not change candidate calculation, equivalent-result collapsing, automatic or manual selection, notification eligibility or acquired-operator recognition.

DEBUG records distinguish acquired results, confirmed arrangements, tag coordinates and candidate calculations. The end-of-run arrangement record retains complete candidate details without repeating a separate per-slot candidate-name summary. An empty slot skipped with zero permits reports the original slot and the actual zero count; advancing the slot never substitutes its number for the permit count.

When the solver starts collecting a finished recruitment or opens the tags for an eligible empty slot, it records that slot and binds subsequent observations to the same operation. Advancing ends the slot check. A failure or stop closes any open check with the corresponding state. Ending the slot check is distinct from starting a new recruitment. The [running log presentation](web-access.md#running-log-presentation) uses that association to present a summary and retain the complete source lines for copying. Confirmed starts say 开始招募，选择标签 followed by the chosen combination; empty choices retain the explicit 不选标签 wording. Historical start messages using 标签 remain readable.

## 4. Verification

[Support robot tests](../../arknights_mower/tests/recruit_robot_tests.py) cover the default-off switch, saved configuration, both support robot preservation modes, valid and invalid cached potential, unavailable caches, mixed candidate pools, higher rarities and missing robot tags. Offline scene transitions verify tag selection, adjustment to 3 hours 50 minutes, starting below the permit threshold and refusing to start without a permit. Cache files use temporary directories; device input and notifications use substitutes.

[Offline policy tests](../../arknights_mower/tests/recruit_policy_tests.py) cover both modes, both exception states, single and multiple choices, equivalent results and other rarities. Device initialization and notification delivery are replaced with offline substitutes. The [decision](../../.agents/notes/implemented/simplification/2026-10-11-recruit-manual-selection.md) records the condition correction.

[Progress log tests](../../arknights_mower/tests/recruit_log_tests.py) exercise the solver entry points offline to separate INFO outcomes from DEBUG data, verify both start-confirmation paths and repeated observations, retain manual selection and permit-threshold behavior, and preserve return values and notification inputs.

[Result tests](../../arknights_mower/tests/recruit_result_tests.py) replay the profession, name and token regions from the October 2, 2026 incident screenshots through the production matcher and result handler. They cover the unreadable animation frame, successful recognition of Lava on the second, fourth or fifth attempt, integer-slot deduplication, failure propagation, cancellation during a wait, exactly five failed result attempts with four one-second waits, and unchanged shared retry behavior for other recognition failures. Device input, waits and notification delivery use offline substitutes; no live game timing is verified.
