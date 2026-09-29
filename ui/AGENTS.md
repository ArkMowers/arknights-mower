# UI Subtree Contract

Local contract for the Vue 3 frontend application under `ui/`.

## 1. Frontend State & Configuration Contracts

- **Persistent vs Ephemeral Isolation**: The configuration store (`conf.device`) persists only explicitly confirmed user selections. Device identity (`preset_id`, `installation_path`, `manager_path`, `config_path`, `instance_id`, `last_serial`, `game_package`) persists through a verified connection only. Non-identity settings (`screenshot_backend`, `touch_backend`, `recovery_timeout`, `recovery_attempts`, `recovery_local_wait`, `recovery_shutdown_wait`, `manager_query_timeout`, `simulator_hotkey`, `simulator_hotkey_delay`) persist on the user's edit. Candidate instance lists from `/device/candidates` remain ephemeral UI state.
- **Immediate Edit Payload**: An immediate save submits only the keys that one edit changed, so identity values edited in the same draft never reach the persisted profile.
- **Connection Group Placement**: The capture and touch backends render outside the advanced identity form; the recovery budget and the boss key stay with the identity fields under the advanced toggle. The read-only and save rules are stated in the help of the connection status tag, and the notice above the buttons carries preset-specific guidance only.
- **Label Column Width**: A device label plus its help icon needs a wider label column than the settings form's 120px default; at 120px the icon drops to a second line and every row grows taller.
- **Menu Width Follows Content**: A dropdown menu sizes to its widest option. Pinning it to the trigger width clips or shifts a longer option label.
- **Dynamic Policy Exposure**: Advanced recovery configuration (`recovery_timeout`, `recovery_attempts`, `recovery_local_wait`, `recovery_shutdown_wait`, `manager_query_timeout`) binds dynamically to backend recovery policies.
- **Target Clearance**: Modifying preset or instance selections in the UI must immediately invalidate and clear `last_serial` to prevent stale endpoint reuse.
- **IPC Backend Coupling**: Selecting MuMu IPC capture backend automatically couples the touch backend to MuMu IPC; selecting alternative touch methods disables IPC capture.
- **Bound Instance Start**: Detection starts only a selected supported instance after a stopped verdict; multiple candidates require selection. MuMu Pro may open its manager application before this check. The independent connection test performs no lifecycle actions. AVD, redroid and Genymotion requests carry the current selected instance as immediate confirmation.

## 2. Testing Discipline

- **Targeted Unit Testing**: Run focused unit tests for modified components or utilities (e.g., `npm test -- ui/src/utils/deviceSettings.test.js`).
- Do not trigger full frontend build or end-to-end browser suites in rapid iteration loops.

## 3. Controlled Language

- UI labels, tooltips, and source comments adhere strictly to authoritative definitions in [CONTEXT.md](../CONTEXT.md).
- Never introduce issue tracker numbers (`#xxx`).
