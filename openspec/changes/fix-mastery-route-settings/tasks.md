## 1. Backend - Fix GET /mastery-route

- [x] 1.1 Return default routes from `training_route.json` for professions not in DB, plus `backups` field
- [x] 1.2 Wrap in try/except so it never returns 500
- [x] 1.3 Simplify POST to store supports array directly (no dict wrapping)

## 2. Frontend - Fix loadRoute race condition

- [x] 2.1 Move `loadRoute()` out of `onMounted`
- [x] 2.2 Add lazy-load on modal open: `openSettings()` calls `await loadRoute()` before setting `showSettings = true`
- [x] 2.3 Extract `backups` from API response into `defaultsCache._backups`
- [x] 2.4 Add console.error logging to all catch blocks

## 3. Frontend - Fix saveRoute

- [x] 3.1 Track whether any POST request succeeded
- [x] 3.2 Only show "已保存" and close modal if at least one request succeeded
- [x] 3.3 Keep modal open with warning if no professions have data

## 4. Verify all interactions work

- [x] 4.1 "添加专精工具人" adds entries using defaultsCache._backups
- [x] 4.2 "恢复默认" restores from defaultsCache
- [x] 4.3 "保存" persists to DB and shows success
- [x] 4.4 Tab switching and modal close do not cause Vue internal errors
