## Why

The 专精路线设置 modal is completely broken: default routes are never loaded, the "添加专精工具人" button does nothing because `defaultsCache._backups` is never populated, saving does not persist data because the supports array is empty, and `loadRoute()` runs unawaited in `onMounted`, causing a Vue internals crash when the API response arrives while the user is interacting with the modal.

## What Changes

- **Backend `GET /mastery-route`**: Return default routes from `training_route.json` for any profession not yet saved by the user, plus `_backups` for fallback operators. Never return 500.
- **Frontend `loadRoute()`**: Remove from `onMounted`; call lazily when the modal opens. Extract `backups` from the API response. Add error logging instead of silent `catch {}`.
- **Frontend `saveRoute()`**: Only show "已保存" if at least one API call was made. Guard against no-data state.
- **Frontend `newSupport()` / `resetRoute()`**: Properly use `defaultsCache._backups` so buttons are functional.

## Capabilities

### New Capabilities
- `mastery-route-defaults`: API returns default route data from `training_route.json` when no user-saved route exists, including backup operator names for the "添加专精工具人" feature.

### Modified Capabilities
*(none — no existing spec files are being changed)*

## Impact

- `arknights_mower/views/mastery.py` — `MasteryRouteView.get()` and `post()`
- `ui/src/pages/MasteryRecommendation.vue` — `loadRoute()`, `saveRoute()`, `newSupport()`, `resetRoute()`, `onMounted`
- `ui/src/pages/MasteryRecommendation.vue` — template button handlers
