## Context

The 专精路线设置 modal has three interacting bugs:

1. **No default data flow**: `training_route.json` contains 8 professions with 3 support operators each plus `_backups` for fallback operators, but this data is never exposed to the UI via `GET /mastery-route`. The API returns whatever is in the DB — which on first use is empty.
2. **Async race condition**: `loadRoute()` runs unawaited in `onMounted`. When the API response arrives after the user has already opened the modal, `applyRoute()` replaces reactive arrays mid-interaction, causing Vue/NaiveUI internal errors (`Cannot read properties of null (reading 'type')`).
3. **Silent failures**: All `catch {}` blocks swallow errors. `saveRoute()` shows "已保存" even when no API calls were made.

## Goals / Non-Goals

**Goals:**
- Default routes from `training_route.json` are visible in the modal on first load
- "添加专精工具人" creates new support entries using `_backups` from defaults
- "恢复默认" restores default routes
- "保存" actually persists to DB and only shows "已保存" on success
- No Vue internal crashes when interacting with the modal
- All errors are logged (not silent)

**Non-Goals:**
- Not changing the route data schema in the DB (`mastery_route` table stays as `profession, supports, is_default, created_at`)
- Not changing existing backend route consumers (`_build_route_supports`, `mastery_sync.py`, `base_schedule.py`)
- Not adding new backend endpoints

## Decisions

**1. Lazy-load route data when modal opens, not in `onMounted`**
- **Why**: Eliminates the race condition entirely. The data is guaranteed to be loaded before the user sees the modal.
- **How**: The "专精路线" button click handler calls `await loadRoute()` then sets `showSettings = true`.
- **Alternative considered**: Watcher on `showSettings` — adds unnecessary complexity and still has timing issues.

**2. Backend `GET /mastery-route` always merges defaults + user-saved routes**
- **Why**: The UI always needs all 8 professions visible, regardless of how many the user has saved.
- **How**: The response includes `routes` (DB rows + default rows for missing professions) and a separate `backups` top-level field.
- **Alternative considered**: Load defaults into the DB as `is_default=1` rows — more complex, needs initialization logic, risks stale data.

**3. Backend `POST /mastery-route` stores only the supports array**
- **Why**: `half_off` and `control_center` are UI-only runtime state, not route data. The `_build_route_supports()` function already handles both array and dict formats for backward compatibility.
- **How**: `save_route(profession, supports_array_json, is_default=0)` — stores the array directly.

**4. Frontend `saveRoute()` tracks actual saves before showing success**
- **Why**: Avoid misleading "已保存" when no API calls were made (empty supports array, or all requests failed).
- **How**: Use a counter; only show message and close modal if at least one request succeeded.

**5. All API error handlers log to console**
- **Why**: Silent `catch {}` makes debugging impossible. The user saw a Vue internals crash but had no way to know it came from `loadRoute`.
- **How**: `catch (e) { console.error(...) }` instead of `catch {}`.

## Risks / Trade-offs

- **[Race condition with slow API] → Lazy-load before opening modal ensures data is ready. But if the API is very slow, the button will appear unresponsive. Mitigation: add a loading spinner** — acceptable for now since the API is local.
- **[Breaking old saved data]** → Old saves stored as dict `{"supports": [...], "half_off": ...}`. Both the frontend parser and backend `_build_route_supports` handle both array and dict formats, so backward compatibility is maintained.
- **[No loading state]** → User won't know data is being fetched when clicking the button. Acceptable for initial fix; loading indicator can be added later.
