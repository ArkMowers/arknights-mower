# 原始材料

来源提交：`a32ce1a3c12d0d8da178215d31e7c79ab9b5d15e`。

本次范围仅为该提交与其父提交的差异。不使用旧提交标题或业务说明正文作为写作输入；差异中的检查记录属于历史材料，不代表本轮实际执行。

## 完整 diff

```diff
diff --git a/.agents/notes/implemented/simplification/2026-10-10-local-growth-sync-deduplication.md b/.agents/notes/implemented/simplification/2026-10-10-local-growth-sync-deduplication.md
new file mode 100644
index 000000000..730520b55
--- /dev/null
+++ b/.agents/notes/implemented/simplification/2026-10-10-local-growth-sync-deduplication.md
@@ -0,0 +1,18 @@
+---
+title: Local Growth Sync Deduplication
+status: implemented
+category: simplification
+date: 2026-10-10
+---
+
+# Local Growth Sync Deduplication
+
+**[INV-GROWTH-04] Local Progression Sync Check**: Automatic and manual Yituliu sync validate the upload payload locally and send nothing when it matches the last confirmed upload for the configured token, while failed uploads never advance the comparison baseline.
+
+Automatic Skland retrieval and the existing refresh controls retain their behavior. A successful refresh enters the shared local upload check before any Yituliu transmission.
+
+Both upload entry points share `sync_cached_operators`; no additional frontend comparison or remote query is required. A SHA-256 digest covers the validated upload fields with deterministic object keys and operator ordering. Cache timestamps, warehouse stock and unrelated fields are excluded. The restricted token settings file persists only the latest confirmed digest and existing status, preserving the comparison across restarts. Replacing or clearing the token resets the baseline; saving an identical token preserves it. Changed player identity or progression uploads again. A skipped result keeps the actual upload timestamp and reports that no data was transmitted. Network and validation failures preserve the last confirmed digest.
+
+The [growth contract](../../../../docs/subsystems/growth-planning.md) defines the interfaces. Offline tests cover unchanged manual and automatic synchronization, ordering, changed progression and identity, token changes, failed requests and automatic synchronization after a successful Skland refresh.
+
+Verification on the alpha-based branch: the focused synchronization, Skland refresh and governance suites pass 88 tests; the token-settings and mastery-store suites pass 8 tests. Ruff, ESLint, Prettier and diff whitespace checks pass. Structural governance passes with two pre-existing archived-reference warnings. These checks verify local deduplication; the [OAuth adapter decision](2026-10-11-yituliu-oauth-upload.md) records the current live write validation.
diff --git a/.agents/notes/implemented/simplification/2026-10-10-local-growth-sync-deduplication.sidecar.json b/.agents/notes/implemented/simplification/2026-10-10-local-growth-sync-deduplication.sidecar.json
new file mode 100644
index 000000000..5b416e766
--- /dev/null
+++ b/.agents/notes/implemented/simplification/2026-10-10-local-growth-sync-deduplication.sidecar.json
@@ -0,0 +1,19 @@
+{
+  "title": "Local Growth Sync Deduplication",
+  "status": "implemented",
+  "category": "simplification",
+  "date": "2026-10-10",
+  "authors": [
+    "Codex"
+  ],
+  "invariants": [
+    "[INV-GROWTH-04]"
+  ],
+  "code_symbols": [
+    "arknights_mower.utils.yituliu_sync.sync_cached_operators"
+  ],
+  "test_suites": [
+    "arknights_mower/tests/yituliu_sync_tests.py",
+    "arknights_mower/tests/cultivate_depot_tests.py"
+  ]
+}
diff --git a/.agents/notes/implemented/simplification/2026-10-10-local-growth-sync-deduplication.zh.md b/.agents/notes/implemented/simplification/2026-10-10-local-growth-sync-deduplication.zh.md
new file mode 100644
index 000000000..a6f7800f9
--- /dev/null
+++ b/.agents/notes/implemented/simplification/2026-10-10-local-growth-sync-deduplication.zh.md
@@ -0,0 +1,18 @@
+---
+title: 养成同步本地去重
+status: implemented
+category: simplification
+date: 2026-10-10
+---
+
+# 养成同步本地去重
+
+**[INV-GROWTH-04] 练度同步本地校验**：自动和手动同步一图流先在本地校验上传内容，与当前 Token 上次确认成功的上传相同时不发送请求，上传失败不更新比较基线。
+
+森空岛自动获取和现有刷新控件保留原有行为。成功刷新后，在向一图流传输前进入共用的本地上传校验。
+
+两个上传入口共用 `sync_cached_operators`，无需增加前端比较或远程查询。SHA-256 摘要覆盖已校验的上传字段，固定对象键和干员排列顺序，排除缓存时间、仓库库存和无关字段。受限权限的 Token 设置文件仅持久化最新确认成功的摘要及现有状态，重启后仍可比较。替换或清除 Token 重置基线；保存相同 Token 保留基线。玩家身份或练度变化时重新上传。跳过结果保留实际上传时间，并说明未传输数据。网络和校验失败保留上次确认成功的摘要。
+
+[养成规划契约](../../../../docs/subsystems/growth-planning.md)定义接口。离线测试覆盖相同内容的手动与自动同步、顺序变化、练度和身份变化、Token 变化、请求失败及森空岛成功刷新后的自动同步。
+
+基于 alpha 的分支验证：同步、森空岛刷新及治理定向测试共 88 项通过；Token 设置和专精状态仓库测试共 8 项通过。Ruff、ESLint、Prettier 及差异空白检查通过。结构治理检查通过，保留两条既有历史归档引用警告。这些检查验证本地去重；[OAuth 适配决策](2026-10-11-yituliu-oauth-upload.md)记录当前实际写入验证。
diff --git a/.agents/notes/implemented/simplification/2026-10-11-yituliu-oauth-upload.md b/.agents/notes/implemented/simplification/2026-10-11-yituliu-oauth-upload.md
new file mode 100644
index 000000000..1dfdc4a96
--- /dev/null
+++ b/.agents/notes/implemented/simplification/2026-10-11-yituliu-oauth-upload.md
@@ -0,0 +1,18 @@
+---
+title: Yituliu OAuth Upload
+status: implemented
+category: simplification
+date: 2026-10-11
+---
+
+# Yituliu OAuth Upload
+
+**[INV-GROWTH-05] Confirmed OAuth Upload**: Yituliu synchronization sends only bound game UID and validated operator fields to the fixed OAuth save endpoint with a Bearer token, and advances its success baseline only after an integer business code of 200 and complete nonnegative save counts.
+
+The [growth contract](../../../../docs/subsystems/growth-planning.md) defines the interface. Both automatic refresh and manual synchronization call `sync_cached_operators`; `_upload` has one production caller. The existing lock, local digest and token file serve both entry points. The adapter replaces the legacy upload schema directly, removes nickname/channel validation and the legacy ownership field, and adds no parallel client or authentication store. Nickname and channel changes no longer trigger transmission because the OAuth payload excludes them.
+
+The payload contains `playerInfo.akUid` and `operators`. Skill values combine basic skill level and mastery stage; absent skills remain zero. `potentialRank` retains the cached zero-based rank. All five equipment branches remain explicit, including zero values, because omitted fields reset to zero on the provider. A confirmed result requires created, updated and unchanged counts summing to the submitted roster size. Business failures and malformed confirmations preserve the successful digest. Known business errors produce local messages without reflecting remote text or credentials. Redirects and uncertain retries remain disabled.
+
+Offline synchronization, refresh, settings and governance checks cover the contract. The glossary introduces no changed domain concepts.
+
+Validation on 2026-10-11: 113 focused backend tests and 8 frontend tests pass. Ruff and frontend lint/format checks pass. Structural governance passes with two existing historical archived-test reference warnings. One authorized live upload of the existing local Skland snapshot confirms 429 updated operators, zero created and zero unchanged; a repeat local sync skips transmission and preserves the success timestamp. The supplied token has no read scope (`80008`), so the evidence is the save confirmation rather than a readback. Temporary isolated settings are removed after validation; credentials and player data are absent from the patch.
diff --git a/.agents/notes/implemented/simplification/2026-10-11-yituliu-oauth-upload.sidecar.json b/.agents/notes/implemented/simplification/2026-10-11-yituliu-oauth-upload.sidecar.json
new file mode 100644
index 000000000..7912cfdd6
--- /dev/null
+++ b/.agents/notes/implemented/simplification/2026-10-11-yituliu-oauth-upload.sidecar.json
@@ -0,0 +1,21 @@
+{
+  "title": "Yituliu OAuth Upload",
+  "status": "implemented",
+  "category": "simplification",
+  "date": "2026-10-11",
+  "authors": [
+    "Codex"
+  ],
+  "invariants": [
+    "[INV-GROWTH-05]",
+    "[INV-GROWTH-04]"
+  ],
+  "code_symbols": [
+    "arknights_mower.utils.yituliu_sync.build_upload_payload",
+    "arknights_mower.utils.yituliu_sync.sync_cached_operators"
+  ],
+  "test_suites": [
+    "arknights_mower/tests/yituliu_sync_tests.py",
+    "arknights_mower/tests/cultivate_depot_tests.py"
+  ]
+}
diff --git a/.agents/notes/implemented/simplification/2026-10-11-yituliu-oauth-upload.zh.md b/.agents/notes/implemented/simplification/2026-10-11-yituliu-oauth-upload.zh.md
new file mode 100644
index 000000000..a70b429a2
--- /dev/null
+++ b/.agents/notes/implemented/simplification/2026-10-11-yituliu-oauth-upload.zh.md
@@ -0,0 +1,18 @@
+---
+title: 一图流 OAuth 上传
+status: implemented
+category: simplification
+date: 2026-10-11
+---
+
+# 一图流 OAuth 上传
+
+**[INV-GROWTH-05] OAuth 上传确认**：一图流同步仅使用 Bearer 令牌向固定 OAuth 保存端点发送已绑定游戏 UID 与已校验干员字段，只有整数业务码 200 且非负保存计数完整时才更新成功基线。
+
+[养成契约](../../../../docs/subsystems/growth-planning.md)定义接口。自动刷新与手动同步均调用 `sync_cached_operators`；`_upload` 只有一个生产调用方。现有锁、本地摘要和令牌文件服务两个入口。适配器直接替换旧版上传结构，删除昵称、区服校验和旧版拥有标记，无需并行客户端或额外认证存储。OAuth 上传内容不含昵称和区服，因此这些字段变化不再触发传输。
+
+请求包含 `playerInfo.akUid` 与 `operators`。技能值为基础技能等级加专精阶段；不存在的技能保持零。`potentialRank` 保留缓存中从零开始的潜能序号。五类模组均显式发送，包含零值，因为服务端将省略字段重置为零。成功确认要求新增、更新和未变更计数之和等于提交干员数。业务失败和无效确认均保留成功摘要。已知业务错误使用本地提示，不回显远程文本或凭据。重定向和不确定请求自动重试保持禁用。
+
+离线同步、刷新、设置及治理检查覆盖该契约。领域词汇不引入概念变更。
+
+2026-10-11 验证：113 项后端定向测试与 8 项前端测试通过。Ruff、前端静态与格式检查通过。结构治理检查通过，保留两条既有历史归档测试引用警告。使用现有本地森空岛快照完成一次授权实际上传，确认更新 429 名干员，新增和未变更均为零；重复本地同步跳过传输并保留成功时间。提供的令牌没有读取权限（`80008`），因此证据来自保存确认，未进行读取回验。验证后删除隔离的临时设置；补丁不含凭据及玩家数据。
diff --git a/.agents/skills/mower-code-review/references/invariants-checklist.md b/.agents/skills/mower-code-review/references/invariants-checklist.md
index 736e8f6d2..b147184e3 100644
--- a/.agents/skills/mower-code-review/references/invariants-checklist.md
+++ b/.agents/skills/mower-code-review/references/invariants-checklist.md
@@ -30,10 +30,14 @@ Checklist for evaluating pull requests and git diffs under the Standards axis of
 
 - [ ] **[INV-WORKSHOP-02] T5 Specialist Priority**: Do Homebound's elite-two recommendations and allocation stay within her T5 specialty, do copied manual settings exclude non-T5 recipes without changing saved settings, and does Nian retain priority through her higher bonus? See the [workshop contract](../../../../docs/subsystems/growth-planning.md#3-subsystem-invariants).
 
-- [ ] **[INV-GROWTH-02] Public Survey Isolation**: Does public survey retrieval omit local identity and credentials? Are missing rates unknown and plans preserved during survey display and filtering? Does a configured token produce only one fixed-endpoint upload after each actual successful Skland refresh, or an explicit manual sync, with no upload merely on token save or cache read? Are uploaded fields limited to game UID, nickname, server and progression, credentials absent from responses and logs, and upload failure isolated from local cache and Skland success?
+- [ ] **[INV-GROWTH-02] Public Survey Isolation**: Does public survey retrieval omit local identity and credentials? Are missing rates unknown and plans preserved during survey display and filtering? Does a configured token produce at most one fixed-endpoint upload after each actual successful Skland refresh, or an explicit manual sync, with no upload merely on token save or cache read? Are uploaded fields limited to bound game UID and progression, credentials absent from responses and logs, and upload failure isolated from local cache and Skland success?
 
 - [ ] **[INV-GROWTH-01] Shared Growth Budget**: Do admission and crafting tests distinguish unready projects from dispatched training, count shared costs once and avoid consuming stock twice? See the [registered guarantee](../../../../CODING_STANDARDS.md#2-subsystem-invariants).
 
+- [ ] **[INV-GROWTH-04] Local Progression Sync Check**: Do automatic and manual sync skip the network for unchanged validated content, preserve the last confirmed baseline across failures and restarts, and reset it when the token changes? See the [synchronization contract](../../../../docs/subsystems/growth-planning.md#6-authorized-progression-synchronization).
+
+- [ ] **[INV-GROWTH-05] Confirmed OAuth Upload**: Yituliu synchronization sends only bound game UID and validated operator fields to the fixed OAuth save endpoint with a Bearer token, and advances its success baseline only after an integer business code of 200 and complete nonnegative save counts.
+
 - [ ] **[INV-GROWTH-03] Ordered Crafting Prerequisites**: Do allocation tests observe prerequisite preparation before project costs and distinguish skipping an unstarted shortage from blocking behind protected training? See the [registered guarantee](../../../../CODING_STANDARDS.md#2-subsystem-invariants).
 
 - [ ] **[INV-REC-06] Selection Page Exit**: Do anomalous selection readings detect the known facility roster marker on the same Capture Frame and propagate page exit without filter reset or further selection input, while normal readings avoid additional page lookups or captures and existing room recovery reads actual occupants?
diff --git a/CODING_STANDARDS.md b/CODING_STANDARDS.md
index d53f6c1fd..d0653dc5a 100644
--- a/CODING_STANDARDS.md
+++ b/CODING_STANDARDS.md
@@ -26,10 +26,14 @@
 
 - **[INV-WORKSHOP-01] Rejected Recipe Handoff**: Game-rejected recipes do not dispatch another worker against unchanged relevant inventory and configuration; rejections remain transient, renewed inventory observations permit retries without fabricated counts, and processing failures stop consecutive handoffs.
 
-- **[INV-GROWTH-02] Public Survey Isolation**: Public survey retrieval sends no local identity or credentials, missing survey rates remain unknown, and survey display or filtering never mutates plans; a configured write-only token permits one fixed-endpoint upload of game identity and progression after each successful Skland refresh or an explicit manual sync, without exposing the credential or invalidating local refresh success on upload failure.
+- **[INV-GROWTH-02] Public Survey Isolation**: Public survey retrieval sends no local identity or credentials, missing survey rates remain unknown, and survey display or filtering never mutates plans; a configured OAuth access token with `gama-data.write` permits at most one fixed-endpoint upload of game identity and progression after each successful Skland refresh or an explicit manual sync, without exposing the credential or invalidating local refresh success on upload failure.
 
 - **[INV-GROWTH-01] Shared Growth Budget**: Growth planning admits unready operators without dispatching training, counts shared prerequisites once, reserves stock in crafting-project order, emits only outstanding permitted recipes for fully supplied projects, and keeps manual chip conversion separate from automatic crafting.
 
+- **[INV-GROWTH-04] Local Progression Sync Check**: Automatic and manual Yituliu sync validate the upload payload locally and send nothing when it matches the last confirmed upload for the configured token, while failed uploads never advance the comparison baseline.
+
+- **[INV-GROWTH-05] Confirmed OAuth Upload**: Yituliu synchronization sends only bound game UID and validated operator fields to the fixed OAuth save endpoint with a Bearer token, and advances its success baseline only after an integer business code of 200 and complete nonnegative save counts.
+
 - **[INV-GROWTH-03] Ordered Crafting Prerequisites**: The saved unified plan order determines crafting priority and relative skill training priority, active training remains fixed first, each admitted project prepares its minimum unsatisfied promotion and basic-skill prerequisites before its own costs without counting shared prerequisites twice, and an unstarted shortage skips that project while a protected training shortage blocks later preparation.
 
 - **[INV-REC-06] Selection Page Exit**: Known facility roster pages detected during anomalous selection readings abort selection inputs and page-local fallback; normal readings add no page-template lookup or capture.
diff --git a/arknights_mower/tests/yituliu_sync_tests.py b/arknights_mower/tests/yituliu_sync_tests.py
index eb414d285..f227b18c1 100644
--- a/arknights_mower/tests/yituliu_sync_tests.py
+++ b/arknights_mower/tests/yituliu_sync_tests.py
@@ -25,7 +25,10 @@ def sync_case(tmp_path, monkeypatch):
     session.__enter__.return_value = session
     response = MagicMock(status_code=200)
     response.__enter__.return_value = response
-    response.json.return_value = {"code": 200, "data": {"affectedRows": 1}}
+    response.json.return_value = {
+        "code": 200,
+        "data": {"createdCount": 1, "updatedCount": 0, "unchangedCount": 0},
+    }
     session.post.return_value = response
     monkeypatch.setattr(sync.requests, "Session", lambda: session)
     snapshot = {
@@ -98,30 +101,24 @@ def test_payload_matches_documented_fields_and_potential_index(sync_case):
     _, _, _, snapshot, definitions = sync_case
     original = copy.deepcopy(snapshot)
     body = sync.build_upload_payload(snapshot, definitions)
-    assert set(body) == {
-        "uid",
-        "nickName",
-        "channelName",
-        "channelMasterId",
-        "operatorDataList",
-    }
-    assert body["operatorDataList"] == [
+    assert set(body) == {"playerInfo", "operators"}
+    assert body["playerInfo"] == {"akUid": "12345678"}
+    assert body["operators"] == [
         {
-            "charId": "char_test",
-            "own": True,
+            "id": "char_test",
             "level": 90,
-            "elite": 2,
-            "potential": 6,
+            "evolvePhase": 2,
+            "potentialRank": 5,
             "rarity": 6,
-            "mainSkill": 7,
-            "skill1": 1,
-            "skill2": 3,
+            "mainSkillLevel": 7,
+            "skill1": 8,
+            "skill2": 10,
             "skill3": 0,
-            "modX": 2,
-            "modY": 0,
-            "modD": 0,
-            "modA": 0,
-            "modB": 0,
+            "equipX": 2,
+            "equipY": 0,
+            "equipD": 0,
+            "equipA": 0,
+            "equipB": 0,
         }
     ]
     assert "must-not-upload" not in json.dumps(body)
@@ -147,7 +144,7 @@ def test_explicit_sync_sends_only_fixed_target_header_and_whitelisted_snapshot(
     assert result["success"] and result["count"] == 1
     session.post.assert_called_once_with(
         sync.UPLOAD_URL,
-        headers={"Authorization": TOKEN},
+        headers={"Authorization": f"Bearer {TOKEN}"},
         json=sync.build_upload_payload(snapshot, definitions),
         timeout=(3, 15),
         allow_redirects=False,
@@ -175,7 +172,8 @@ def test_automatic_refresh_uses_passed_snapshot_once_without_reading_newer_cache
     assert sync.sync_after_cultivate(snapshot)["success"] is True
     session.post.assert_called_once()
     assert (
-        session.post.call_args.kwargs["json"]["uid"] == snapshot["_mower_player"]["uid"]
+        session.post.call_args.kwargs["json"]["playerInfo"]["akUid"]
+        == snapshot["_mower_player"]["uid"]
     )
 
 
@@ -232,3 +230,297 @@ def test_token_and_sync_routes_require_local_auth_and_explicit_manual_action(
     assert (
         client.delete("/growth-sync-token", headers=headers).json["configured"] is False
     )
+
+
+@pytest.mark.parametrize("automatic", [False, True])
+def test_identical_confirmed_payload_skips_manual_and_automatic_network(
+    sync_case, automatic
+):
+    paths, session, _, snapshot, _ = sync_case
+    sync.save_token(TOKEN)
+    first = sync.sync_cached_operators()
+    # Re-reading persisted settings exercises the baseline used after a restart.
+    saved = json.loads(paths["@app/config/yituliu_sync.json"].read_text())
+    assert len(saved["last_synced_fingerprint"]) == 64
+    result = (
+        sync.sync_after_cultivate(snapshot)
+        if automatic
+        else sync.sync_cached_operators()
+    )
+    assert result["success"] and result["skipped"]
+    assert result["synced_at"] == first["synced_at"]
+    assert result["count"] == 1
+    assert "未传输" in result["message"]
+    assert sync.token_status()["last_synced_at"] == first["synced_at"]
+    assert "fingerprint" not in json.dumps(sync.token_status())
+    session.post.assert_called_once()
+
+
+def test_order_inventory_and_snapshot_timestamps_do_not_trigger_upload(sync_case):
+    _, session, response, snapshot, definitions = sync_case
+    response.json.return_value["data"]["createdCount"] = 2
+    second = copy.deepcopy(snapshot["data"]["characters"][0])
+    second["id"] = "char_second"
+    definitions["char_second"] = copy.deepcopy(definitions["char_test"])
+    snapshot["data"]["characters"].append(second)
+    sync.save_token(TOKEN)
+    sync.sync_cached_operators(snapshot)
+    snapshot["data"]["characters"].reverse()
+    snapshot["data"]["items"][0]["count"] += 1
+    snapshot["_mower_inventory_observed_at"] = 12345
+    snapshot["_mower_player"]["cred"] = "different-secret"
+    assert sync.sync_cached_operators(snapshot)["skipped"]
+    session.post.assert_called_once()
+
+
+@pytest.mark.parametrize(
+    "field",
+    [
+        "level",
+        "elite",
+        "potential",
+        "basic",
+        "skill",
+        "module",
+        "uid",
+        "rarity",
+    ],
+)
+def test_changed_upload_fields_transmit_again(sync_case, field):
+    _, session, _, snapshot, definitions = sync_case
+    sync.save_token(TOKEN)
+    sync.sync_cached_operators(snapshot)
+    char = snapshot["data"]["characters"][0]
+    if field == "level":
+        char["level"] = 89
+    elif field == "elite":
+        char["evolvePhase"] = 1
+    elif field == "potential":
+        char["potentialRank"] = 4
+    elif field == "basic":
+        char["mainSkillLevel"] = 6
+    elif field == "skill":
+        char["skills"][0]["level"] = 2
+    elif field == "module":
+        char["equips"][1]["level"] = 3
+    elif field == "uid":
+        snapshot["_mower_player"]["uid"] = "87654321"
+    else:
+        definitions["char_test"]["rarity"] = 5
+    assert not sync.sync_cached_operators(snapshot).get("skipped")
+    assert session.post.call_count == 2
+    assert sync.sync_cached_operators(snapshot)["skipped"]
+    assert session.post.call_count == 2
+
+
+def test_failed_changed_upload_preserves_baseline_and_can_retry(sync_case):
+    paths, session, _, snapshot, _ = sync_case
+    sync.save_token(TOKEN)
+    sync.sync_cached_operators(snapshot)
+    first = json.loads(paths["@app/config/yituliu_sync.json"].read_text())
+    snapshot["data"]["characters"][0]["level"] = 89
+    session.post.side_effect = requests.Timeout()
+    assert not sync.sync_after_cultivate(snapshot)["success"]
+    failed = json.loads(paths["@app/config/yituliu_sync.json"].read_text())
+    assert failed["last_synced_fingerprint"] == first["last_synced_fingerprint"]
+    session.post.side_effect = None
+    assert not sync.sync_cached_operators(snapshot).get("skipped")
+    assert session.post.call_count == 3
+
+
+def test_payload_validation_happens_before_deduplication(sync_case):
+    _, session, _, snapshot, _ = sync_case
+    sync.save_token(TOKEN)
+    sync.sync_cached_operators(snapshot)
+    snapshot["data"]["characters"][0]["level"] = True
+    with pytest.raises(ValueError, match="等级无效"):
+        sync.sync_cached_operators(snapshot)
+    session.post.assert_called_once()
+
+
+def test_same_token_preserves_baseline_and_replacement_or_clear_resets_it(sync_case):
+    _, session, _, snapshot, _ = sync_case
+    sync.save_token(TOKEN)
+    sync.sync_cached_operators(snapshot)
+    sync.save_token("  " + TOKEN + "  ")
+    assert sync.sync_cached_operators(snapshot)["skipped"]
+    session.post.assert_called_once()
+    replacement = "abcdef0123456789abcdef0123456789"
+    sync.save_token(replacement)
+    assert not sync.sync_cached_operators(snapshot).get("skipped")
+    assert session.post.call_args.kwargs["headers"] == {
+        "Authorization": f"Bearer {replacement}"
+    }
+    sync.clear_token()
+    sync.save_token(replacement)
+    assert not sync.sync_cached_operators(snapshot).get("skipped")
+    assert session.post.call_count == 3
+
+
+def test_concurrent_identical_sync_requests_upload_once(sync_case):
+    from concurrent.futures import ThreadPoolExecutor
+
+    _, session, _, snapshot, _ = sync_case
+    sync.save_token(TOKEN)
+    with ThreadPoolExecutor(max_workers=2) as workers:
+        results = list(
+            workers.map(lambda _: sync.sync_cached_operators(snapshot), range(2))
+        )
+    assert all(result["success"] for result in results)
+    assert sum(bool(result.get("skipped")) for result in results) == 1
+    session.post.assert_called_once()
+
+
+def test_saving_token_repairs_unreadable_settings(sync_case):
+    paths, session, _, _, _ = sync_case
+    paths["@app/config/yituliu_sync.json"].write_text("invalid-json")
+    assert sync.save_token(TOKEN)["configured"]
+    session.post.assert_not_called()
+
+
+def test_first_failed_upload_cannot_establish_deduplication_baseline(sync_case):
+    paths, session, response, snapshot, _ = sync_case
+    sync.save_token(TOKEN)
+    response.json.return_value = {"code": 403}
+    assert not sync.sync_after_cultivate(snapshot)["success"]
+    saved = json.loads(paths["@app/config/yituliu_sync.json"].read_text())
+    assert "last_synced_fingerprint" not in saved
+    response.json.return_value = {
+        "code": 200,
+        "data": {"createdCount": 1, "updatedCount": 0, "unchangedCount": 0},
+    }
+    assert not sync.sync_cached_operators(snapshot).get("skipped")
+    assert session.post.call_count == 2
+
+
+@pytest.mark.parametrize(
+    "confirmation",
+    [
+        {"code": 200},
+        {
+            "code": 200.0,
+            "data": {"createdCount": 1, "updatedCount": 0, "unchangedCount": 0},
+        },
+        {"code": 200, "data": None},
+        {
+            "code": 200,
+            "data": {"createdCount": 0, "updatedCount": 0, "unchangedCount": 0},
+        },
+        {
+            "code": 200,
+            "data": {"createdCount": True, "updatedCount": 0, "unchangedCount": 0},
+        },
+        {
+            "code": 200,
+            "data": {"createdCount": -1, "updatedCount": 2, "unchangedCount": 0},
+        },
+        {
+            "code": 200,
+            "data": {"createdCount": "1", "updatedCount": 0, "unchangedCount": 0},
+        },
+    ],
+)
+def test_invalid_confirmation_never_advances_success_baseline(sync_case, confirmation):
+    paths, session, response, snapshot, _ = sync_case
+    sync.save_token(TOKEN)
+    sync.sync_cached_operators(snapshot)
+    first = json.loads(paths["@app/config/yituliu_sync.json"].read_text())
+    snapshot["data"]["characters"][0]["level"] -= 1
+    response.json.return_value = confirmation
+    result = sync.sync_after_cultivate(snapshot)
+    assert not result["success"]
+    saved = json.loads(paths["@app/config/yituliu_sync.json"].read_text())
+    assert saved["last_synced_fingerprint"] == first["last_synced_fingerprint"]
+    assert saved["last_synced_at"] == first["last_synced_at"]
+    assert session.post.call_count == 2
+
+
+@pytest.mark.parametrize(
+    "code, expected",
+    [
+        (80001, "失效"),
+        (80008, "gama-data.write"),
+        (10002, "字段"),
+        (30006, "2 秒"),
+        (40003, "限流服务"),
+        (40004, "冲突"),
+        (40001, "繁忙"),
+    ],
+)
+def test_oauth_business_errors_are_actionable_without_retry_or_remote_echo(
+    sync_case, code, expected, caplog
+):
+    paths, session, response, snapshot, _ = sync_case
+    sync.save_token(TOKEN)
+    response.json.return_value = {
+        "code": code,
+        "msg": TOKEN,
+        "data": {"retryAfterSeconds": 2},
+    }
+    result = sync.sync_after_cultivate(snapshot)
+    assert not result["success"] and expected in result["message"]
+    assert TOKEN not in json.dumps(result) + caplog.text
+    assert "last_synced_fingerprint" not in json.loads(
+        paths["@app/config/yituliu_sync.json"].read_text()
+    )
+    session.post.assert_called_once()
+
+
+def test_oauth_target_and_legacy_baseline_migration(sync_case):
+    paths, session, _, snapshot, _ = sync_case
+    assert (
+        sync.UPLOAD_URL == "https://auth.yituliu.cn/oauth2/ak-accounts/operators/save"
+    )
+    paths["@app/config/yituliu_sync.json"].write_text(
+        json.dumps(
+            {
+                "token": TOKEN,
+                "last_synced_fingerprint": "legacy-payload-digest",
+                "last_synced_at": 1,
+            }
+        )
+    )
+    assert not sync.sync_cached_operators(snapshot).get("skipped")
+    assert sync.sync_cached_operators(snapshot)["skipped"]
+    session.post.assert_called_once()
+
+
+def test_only_bound_uid_is_required_and_untransmitted_identity_does_not_upload(
+    sync_case,
+):
+    _, session, _, snapshot, _ = sync_case
+    sync.save_token(TOKEN)
+    sync.sync_cached_operators(snapshot)
+    snapshot["_mower_player"] = {"uid": "12345678"}
+    assert sync.sync_cached_operators(snapshot)["skipped"]
+    snapshot["_mower_player"].update(nickName="changed", channelMasterId="2")
+    assert sync.sync_cached_operators(snapshot)["skipped"]
+    session.post.assert_called_once()
+
+
+@pytest.mark.parametrize(
+    "basic, mastery, expected",
+    [(1, 0, 1), (6, 0, 6), (7, 0, 7), (7, 1, 8), (7, 2, 9), (7, 3, 10)],
+)
+def test_oauth_skill_levels_and_zero_based_potential(
+    sync_case, basic, mastery, expected
+):
+    _, _, _, snapshot, definitions = sync_case
+    char = snapshot["data"]["characters"][0]
+    char.update(
+        mainSkillLevel=basic, potentialRank=0, skills=[{"id": "s1", "level": mastery}]
+    )
+    row = sync.build_upload_payload(snapshot, definitions)["operators"][0]
+    assert row["skill1"] == expected
+    assert row["skill2"] == row["skill3"] == 0
+    assert row["potentialRank"] == 0
+
+
+@pytest.mark.parametrize("cid", ["", "a" * 65, "char test", "char_中文", "char_\n"])
+def test_invalid_operator_ids_are_rejected_before_network(sync_case, cid):
+    _, session, _, snapshot, definitions = sync_case
+    definitions[cid] = definitions.pop("char_test")
+    snapshot["data"]["characters"][0]["id"] = cid
+    sync.save_token(TOKEN)
+    assert not sync.sync_after_cultivate(snapshot)["success"]
+    session.post.assert_not_called()
diff --git a/arknights_mower/utils/yituliu_sync.py b/arknights_mower/utils/yituliu_sync.py
index 4ca05b78a..2f9a98f3d 100644
--- a/arknights_mower/utils/yituliu_sync.py
+++ b/arknights_mower/utils/yituliu_sync.py
@@ -2,6 +2,7 @@
 
 import json
 import re
+from hashlib import sha256
 from threading import RLock
 from time import time
 
@@ -10,8 +11,7 @@ import requests
 from arknights_mower.utils.config import atomic_write
 from arknights_mower.utils.path import get_path
 
-UPLOAD_URL = "https://backend.yituliu.cn/open-api/operator/upload"
-PLAYER_FIELDS = ("uid", "nickName", "channelName", "channelMasterId")
+UPLOAD_URL = "https://auth.yituliu.cn/oauth2/ak-accounts/operators/save"
 _lock = RLock()
 
 
@@ -51,8 +51,14 @@ def save_token(token):
     if not isinstance(token, str) or not re.fullmatch(
         r"[A-Za-z0-9._~-]{16,512}", token.strip()
     ):
-        raise ValueError("请输入有效的一图流只写 Token，不要填写森空岛凭据")
+        raise ValueError("请输入有效的一图流 OAuth access_token，不要填写森空岛凭据")
     with _lock:
+        try:
+            saved = _settings()
+        except ValueError:
+            saved = {}
+        if saved.get("token") == token.strip():
+            return token_status()
         path = get_path("@app/config/yituliu_sync.json")
         atomic_write(path, lambda stream: json.dump({"token": token.strip()}, stream))
         path.chmod(0o600)
@@ -72,24 +78,15 @@ def _integer(value, lower, upper, label):
 
 
 def build_upload_payload(snapshot, definitions):
-    """Map cached fields to the official PlayerInfoDTO without account secrets."""
+    """Map the bound UID and progression to the OAuth save request."""
     player = snapshot.get("_mower_player") if isinstance(snapshot, dict) else None
-    if not isinstance(player, dict) or any(key not in player for key in PLAYER_FIELDS):
+    if not isinstance(player, dict) or "uid" not in player:
         raise ValueError(
             "当前缓存缺少游戏账号信息，请先重新同步一次森空岛，再立即同步一图流"
         )
-    uid = str(player["uid"])
-    if not re.fullmatch(r"[0-9]{1,20}", uid):
+    uid = player["uid"]
+    if not isinstance(uid, str) or not re.fullmatch(r"[\x21-\x7e]{1,32}", uid):
         raise ValueError("缓存中的游戏 UID 无效，请重新同步森空岛")
-    for key in ("nickName", "channelName"):
-        if not isinstance(player[key], str) or len(player[key]) > 100:
-            raise ValueError("缓存中的游戏账号信息无效，请重新同步森空岛")
-    try:
-        channel = int(player["channelMasterId"])
-    except (TypeError, ValueError):
-        raise ValueError("缓存中的区服信息无效，请重新同步森空岛") from None
-    if channel < 0 or channel > 100 or type(player["channelMasterId"]) is bool:
-        raise ValueError("缓存中的区服信息无效，请重新同步森空岛")
     data = snapshot.get("data")
     chars = data.get("characters") if isinstance(data, dict) else None
     if not isinstance(chars, list) or not 1 <= len(chars) <= 2000:
@@ -99,19 +96,22 @@ def build_upload_payload(snapshot, definitions):
         if not isinstance(char, dict) or not isinstance(char.get("id"), str):
             raise ValueError("干员缓存格式无效，请重新同步森空岛")
         cid = char["id"]
+        if not re.fullmatch(r"[\x21-\x7e]{1,64}", cid):
+            raise ValueError("干员编码无效，请重新同步森空岛")
         definition = definitions.get(cid)
         if not definition or cid in seen:
             raise ValueError("部分干员资源缺失或缓存重复，请更新资源并重新同步森空岛")
         seen.add(cid)
         row = {
-            "charId": cid,
-            "own": True,
+            "id": cid,
             "level": _integer(char.get("level"), 1, 90, "等级"),
-            "elite": _integer(char.get("evolvePhase"), 0, 2, "精英化阶段"),
-            "potential": _integer(char.get("potentialRank"), 0, 5, "潜能等级") + 1,
+            "evolvePhase": _integer(char.get("evolvePhase"), 0, 2, "精英化阶段"),
+            "potentialRank": _integer(char.get("potentialRank"), 0, 5, "潜能等级"),
             "rarity": _integer(definition.get("rarity"), 1, 6, "星级"),
-            "mainSkill": _integer(char.get("mainSkillLevel"), 1, 7, "基础技能等级"),
-            **{f"mod{branch}": 0 for branch in "XYDAB"},
+            "mainSkillLevel": _integer(
+                char.get("mainSkillLevel"), 1, 7, "基础技能等级"
+            ),
+            **{f"equip{branch}": 0 for branch in "XYDAB"},
             **{f"skill{index}": 0 for index in range(1, 4)},
         }
         skills, equips = char.get("skills"), char.get("equips")
@@ -124,7 +124,9 @@ def build_upload_payload(snapshot, definitions):
         for index, skill in enumerate(skills, 1):
             if not isinstance(skill, dict):
                 raise ValueError("干员技能缓存无效，请重新同步森空岛")
-            row[f"skill{index}"] = _integer(skill.get("level"), 0, 3, "专精等级")
+            row[f"skill{index}"] = row["mainSkillLevel"] + _integer(
+                skill.get("level"), 0, 3, "专精等级"
+            )
         modules = {m["id"]: m for m in definition.get("modules", [])}
         for equip in equips:
             if not isinstance(equip, dict) or not isinstance(equip.get("id"), str):
@@ -135,30 +137,21 @@ def build_upload_payload(snapshot, definitions):
             branch = modules.get(equip["id"], {}).get("type", "").rsplit("-", 1)[-1]
             if branch not in ("X", "Y", "D", "A", "B"):
                 raise ValueError("部分模组资源缺失，请更新资源后再同步一图流")
-            row[f"mod{branch}"] = max(row[f"mod{branch}"], level)
+            row[f"equip{branch}"] = max(row[f"equip{branch}"], level)
         rows.append(row)
     return {
-        "uid": uid,
-        "nickName": player["nickName"],
-        "channelName": player["channelName"],
-        "channelMasterId": channel,
-        "operatorDataList": rows,
+        "playerInfo": {"akUid": uid},
+        "operators": rows,
     }
 
 
-def _upload(snapshot, token):
-    from arknights_mower.utils.growth import growth_data
-    from arknights_mower.utils.mastery_recommendation import get_skill_data
-
-    payload = build_upload_payload(
-        snapshot, growth_data(get_skill_data())["characters"]
-    )
+def _upload(payload, token):
     try:
         with requests.Session() as session:
             session.trust_env = False
             with session.post(
                 UPLOAD_URL,
-                headers={"Authorization": token},
+                headers={"Authorization": f"Bearer {token}"},
                 json=payload,
                 timeout=(3, 15),
                 allow_redirects=False,
@@ -173,14 +166,46 @@ def _upload(snapshot, token):
         ) from None
     except (TypeError, ValueError):
         raise ValueError("一图流返回无效响应，同步结果尚未确认") from None
-    if not isinstance(result, dict) or result.get("code") != 200:
-        raise ValueError("一图流未确认同步成功，请检查只写 Token 的有效性及写入权限")
-    count = len(payload["operatorDataList"])
+    if not isinstance(result, dict) or type(result.get("code")) is not int:
+        raise ValueError("一图流返回无效响应，同步结果尚未确认")
+    if result["code"] != 200:
+        messages = {
+            80001: "一图流 OAuth 令牌已失效，请重新获取并保存 access_token",
+            80008: "一图流令牌缺少 gama-data.write 权限，请重新授权后保存 access_token",
+            10002: "一图流拒绝上传字段，请更新资源并重新同步森空岛",
+            30006: "一图流上传过于频繁，请稍后手动重试",
+            40003: "一图流限流服务暂不可用，请稍后手动重试",
+            40004: "一图流数据保存冲突，请稍后重新同步",
+            40001: "一图流服务繁忙，请稍后手动重试",
+        }
+        if result["code"] == 30006:
+            data = result.get("data")
+            delay = data.get("retryAfterSeconds") if isinstance(data, dict) else None
+            if type(delay) is int and 1 <= delay <= 3600:
+                raise ValueError(f"一图流上传过于频繁，请在 {delay} 秒后手动重试")
+        raise ValueError(
+            messages.get(result["code"], "一图流未确认同步成功，请稍后重试")
+        )
+    count = len(payload["operators"])
+    data = result.get("data")
+    if not isinstance(data, dict):
+        raise ValueError("一图流返回无效保存计数，同步结果尚未确认")
+    counts = [
+        data.get(key) for key in ("createdCount", "updatedCount", "unchangedCount")
+    ]
+    if (
+        any(type(value) is not int or value < 0 for value in counts)
+        or sum(counts) != count
+    ):
+        raise ValueError("一图流返回无效保存计数，同步结果尚未确认")
     return {
         "success": True,
         "count": count,
         "synced_at": time(),
-        "message": f"已同步 {count} 名干员的练度至一图流",
+        "message": (
+            f"已同步 {count} 名干员的练度至一图流"
+            f"（新增 {counts[0]}，更新 {counts[1]}，未变更 {counts[2]}）"
+        ),
     }
 
 
@@ -188,11 +213,34 @@ def sync_cached_operators(snapshot=None):
     with _lock:
         saved = _settings()
         if not saved.get("token"):
-            raise ValueError("请先保存一图流只写 Token")
+            raise ValueError(
+                "请先保存具有 gama-data.write 权限的一图流 OAuth access_token"
+            )
         try:
-            result = _upload(
-                _snapshot() if snapshot is None else snapshot, saved["token"]
+            from arknights_mower.utils.growth import growth_data
+            from arknights_mower.utils.mastery_recommendation import get_skill_data
+
+            payload = build_upload_payload(
+                _snapshot() if snapshot is None else snapshot,
+                growth_data(get_skill_data())["characters"],
             )
+            canonical = {
+                **payload,
+                "operators": sorted(payload["operators"], key=lambda row: row["id"]),
+            }
+            fingerprint = sha256(
+                json.dumps(canonical, sort_keys=True, separators=(",", ":")).encode()
+            ).hexdigest()
+            if fingerprint == saved.get("last_synced_fingerprint"):
+                result = {
+                    "success": True,
+                    "skipped": True,
+                    "count": len(payload["operators"]),
+                    "synced_at": saved["last_synced_at"],
+                    "message": "与上次成功同步的数据相同，已跳过上传，未传输数据",
+                }
+            else:
+                result = _upload(payload, saved["token"])
         except ValueError as exc:
             result = {"success": False, "message": str(exc)}
         except Exception:
@@ -207,7 +255,9 @@ def sync_cached_operators(snapshot=None):
         )
         if result["success"]:
             saved.update(
-                last_synced_at=result["synced_at"], last_synced_count=result["count"]
+                last_synced_at=result["synced_at"],
+                last_synced_count=result["count"],
+                last_synced_fingerprint=fingerprint,
             )
         try:
             path = get_path("@app/config/yituliu_sync.json")
@@ -215,7 +265,7 @@ def sync_cached_operators(snapshot=None):
             path.chmod(0o600)
         except OSError:
             if result["success"]:
-                result["message"] = "同步成功，但本地同步时间未能保存"
+                result["message"] += "；本地同步记录未能保存"
         if not result["success"]:
             raise ValueError(result["message"])
         return result
diff --git a/docs/subsystems/growth-planning.md b/docs/subsystems/growth-planning.md
index 5fedf17b0..773963809 100644
--- a/docs/subsystems/growth-planning.md
+++ b/docs/subsystems/growth-planning.md
@@ -38,10 +38,14 @@ Chips never become workshop recipes. Each missing dual chip adds two same-profes
 
 - **[INV-WORKSHOP-01] Rejected Recipe Handoff**: Game-rejected recipes do not dispatch another worker against unchanged relevant inventory and configuration; rejections remain transient, renewed inventory observations permit retries without fabricated counts, and processing failures stop consecutive handoffs.
 
-- **[INV-GROWTH-02] Public Survey Isolation**: Public survey retrieval sends no local identity or credentials, missing survey rates remain unknown, and survey display or filtering never mutates plans; a configured write-only token permits one fixed-endpoint upload of game identity and progression after each successful Skland refresh or an explicit manual sync, without exposing the credential or invalidating local refresh success on upload failure.
+- **[INV-GROWTH-02] Public Survey Isolation**: Public survey retrieval sends no local identity or credentials, missing survey rates remain unknown, and survey display or filtering never mutates plans; a configured OAuth access token with `gama-data.write` permits at most one fixed-endpoint upload of game identity and progression after each successful Skland refresh or an explicit manual sync, without exposing the credential or invalidating local refresh success on upload failure.
 
 - **[INV-GROWTH-01] Shared Growth Budget**: Growth planning admits unready operators without dispatching training, counts shared prerequisites once, reserves stock in crafting-project order, emits only outstanding permitted recipes for fully supplied projects, and keeps manual chip conversion separate from automatic crafting.
 
+- **[INV-GROWTH-04] Local Progression Sync Check**: Automatic and manual Yituliu sync validate the upload payload locally and send nothing when it matches the last confirmed upload for the configured token, while failed uploads never advance the comparison baseline.
+
+- **[INV-GROWTH-05] Confirmed OAuth Upload**: Yituliu synchronization sends only bound game UID and validated operator fields to the fixed OAuth save endpoint with a Bearer token, and advances its success baseline only after an integer business code of 200 and complete nonnegative save counts.
+
 - **[INV-GROWTH-03] Ordered Crafting Prerequisites**: The saved unified plan order determines crafting priority and relative skill training priority, active training remains fixed first, each admitted project prepares its minimum unsatisfied promotion and basic-skill prerequisites before its own costs without counting shared prerequisites twice, and an unstarted shortage skips that project while a protected training shortage blocks later preparation.
 
 - **[INV-STOCK-01] Confirmed Workshop Inventory**: A later cloud request timestamp alone never replaces locally confirmed crafting changes. Pending outputs and consumed ingredients remain protected until single-direction cloud counts reach the predicted inventory in that direction, or a newer actual inventory read reconciles them. Items both produced and consumed require exact predicted cloud counts or a newer actual inventory read. Workshop upper and lower limits remain absolute inventory thresholds.
@@ -66,11 +70,13 @@ The UI links the [Yituliu survey](https://ark.yituliu.cn/survey/operators) and [
 
 ## 6. Authorized Progression Synchronization
 
-`YituliuSyncSettings.vue` appears immediately below Skland accounts in Mower settings. A configured write-only token enables one upload after each actual successful Skland refresh. Saving the token and reading existing caches do not upload. A process-shared lock serializes the complete remote fetch, local persistence and upload sequence across concurrent refresh requests. After local cache and inventory writes finish, `cultivate.start` passes that exact refresh snapshot to `sync_after_cultivate`; the upload does not reread a potentially replaced cache. A delayed response from one refresh cannot overtake a later refresh and replace newer remote progression. An upload failure preserves local data and the successful Skland result. `/cultivate-fetch` reports the separate `yituliu_sync` result.
+`YituliuSyncSettings.vue` appears immediately below Skland accounts in Mower settings. A configured OAuth access token with `gama-data.write` enables a local payload check after each actual successful Skland refresh. Saving the token and reading existing caches do not upload. A process-shared lock serializes the complete remote fetch, local persistence and upload sequence across concurrent refresh requests. After local cache and inventory writes finish, `cultivate.start` passes that exact refresh snapshot to `sync_after_cultivate`; the upload does not reread a potentially replaced cache. A delayed response from one refresh cannot overtake a later refresh and replace newer remote progression. An upload failure preserves local data and the successful Skland result. `/cultivate-fetch` reports the separate `yituliu_sync` result.
 
-The locally authenticated `/growth-sync-token` supports `GET`, `PUT` and `DELETE`. The token resides only in `@app/config/yituliu_sync.json` with mode `0600`, outside the general configuration response. Status returns `configured`, `last_synced_at`, `last_synced_count`, `last_attempt_at` and `last_sync_error`, with no complete or partial token. Local settings and upload errors do not expose credentials or cached payloads in responses or logs. Deleting the token disables future uploads. Authenticated `POST /growth-sync` with `confirmed: true` performs the separate manual action against the current cache.
+The locally authenticated `/growth-sync-token` supports `GET`, `PUT` and `DELETE`. The token resides only in `@app/config/yituliu_sync.json` with mode `0600`, outside the general configuration response. Status returns `configured`, `last_synced_at`, `last_synced_count`, `last_attempt_at` and `last_sync_error`, with no complete or partial token. Local settings and upload errors do not expose credentials or cached payloads in responses or logs. Deleting the token disables future uploads. Authenticated `POST /growth-sync` with `confirmed: true` performs the separate manual action against the current cache. Both automatic and manual actions validate the complete upload payload before comparing its SHA-256 digest against the last confirmed upload for the configured token. Deterministic keys and operator ordering exclude irrelevant ordering changes; inventory and cache timestamps never enter the payload. Matching content returns `success: true`, `skipped: true`, the original `synced_at`, a count and a readable no-transfer message without any network request. Changed content uploads once; only confirmed success advances the persisted digest. Existing installations without a digest upload once to establish it. Saving the same token preserves the baseline; token replacement or deletion resets it.
 
-Uploads use only `POST https://backend.yituliu.cn/open-api/operator/upload`, with the raw write-only token in `Authorization`. The verified contract is the provider's [published OpenAPI document](https://backend.yituliu.cn/v3/api-docs). The payload contains game UID, nickname, channel/server identity and `operatorDataList` entries for ownership, level, elite phase, potential, rarity, basic-skill level, mastery and module levels. It excludes warehouse inventory, account passwords and Skland credentials. Explicit player binding is stored in the refresh snapshot; older caches without binding require a new successful Skland refresh before upload. Uploads reject redirects, have finite connect/read timeouts, and do not retry uncertain requests. The status records success or a readable failure independently of the refresh result.
+Uploads use only `POST https://auth.yituliu.cn/oauth2/ak-accounts/operators/save`, with `Authorization: Bearer <access_token>` and JSON content type. The provider's [OAuth game-data contract](https://github.com/Arknights-yituliu/UserCenterV1/blob/main/docs/oauth/OAuth%E6%B8%B8%E6%88%8F%E6%95%B0%E6%8D%AE%E6%8E%A5%E5%8F%A3%E6%96%87%E6%A1%A3.md) requires `gama-data.write`. The payload contains only `playerInfo.akUid` and nonempty `operators` entries: `id`, `rarity`, `level`, `evolvePhase`, `mainSkillLevel`, `potentialRank`, `skill1` through `skill3` and `equipX/Y/D/A/B`. UID and operator identifiers follow the provider's visible-ASCII limits of 32 and 64 characters. Cached zero-based potential rank is preserved. Present skills use basic skill level plus mastery stage (7 through 10 at basic level 7); absent skills use zero. Every equipment branch is explicit, including zero, because missing numeric fields reset to zero remotely. Nickname, channel, warehouse inventory, account passwords and Skland credentials are excluded. Explicit player binding is stored in the refresh snapshot; older caches without a UID require a new successful Skland refresh before upload. Changing only excluded fields does not trigger another upload. The changed schema invalidates legacy upload digests naturally, establishing the OAuth baseline on the next confirmed upload.
+
+HTTP 200 alone does not confirm an upload: the response requires integer business `code: 200`, nonnegative integer `createdCount`, `updatedCount` and `unchangedCount` in `data`, and their sum equal to the submitted operator count. The local result reports those counts in its message. Business codes `80001`, `80008`, `10002`, `30006`, `40003`, `40004` and `40001` produce local guidance for expired authorization, missing write scope, invalid fields, rate limits, unavailable rate limiting, save conflicts and service failure. A valid `retryAfterSeconds` from 1 to 3600 appears in rate-limit guidance; there is no automatic retry. Remote text is never reflected. Token expiry requires the user to obtain and save a new access token; Mower does not hold a client secret or refresh token. Uploads reject redirects and retain three-second connect and fifteen-second read timeouts. Failures preserve the confirmed digest and local refresh success. The [OAuth upload decision](../../.agents/notes/implemented/simplification/2026-10-11-yituliu-oauth-upload.md) records the direct adapter replacement.
 
 The [growth-planning decision](../../.agents/notes/implemented/feature/2026-10-07-operator-growth-planning.md) defines the shared planning boundary. The [survey and synchronization decision](../../.agents/notes/implemented/feature/2026-10-07-yituliu-growth-survey.md) and [single-surface simplification](../../.agents/notes/implemented/simplification/2026-10-07-single-growth-survey-surface.md) define the statistics replacement. The [inventory correction](../../.agents/notes/implemented/bug-fix/2026-10-07-workshop-delayed-cloud-inventory.md) covers delayed cloud reconciliation, and the [budget simplification](../../.agents/notes/implemented/simplification/2026-10-07-shared-growth-material-budget.md) records removed duplicate calculators.
 
@@ -79,3 +85,5 @@ The [low-rarity extension](../../.agents/notes/implemented/feature/2026-10-08-lo
 The operator list retains viewport-relative minimum height so short filtered results can scroll above the bottom edge without stretching cards. Reset and batch-plan actions use standard compact buttons. Reset sits beside the idle-state selector inside the filter panel. The automation switch controls training and growth crafting; promotion, basic skills and module upgrades remain manual.
 
 The [ordered crafting decision](../../.agents/notes/implemented/feature/2026-10-08-ordered-growth-crafting.md) defines the independent project boundary; the [shared project budget simplification](../../.agents/notes/implemented/simplification/2026-10-08-shared-crafting-project-budget.md) records reuse of the existing material calculator.
+
+The [local synchronization decision](../../.agents/notes/implemented/simplification/2026-10-10-local-growth-sync-deduplication.md) defines local upload deduplication while preserving automatic Skland refresh.
diff --git a/ui/src/components/YituliuSyncSettings.vue b/ui/src/components/YituliuSyncSettings.vue
index 44b55b3a8..2df596bb9 100644
--- a/ui/src/components/YituliuSyncSettings.vue
+++ b/ui/src/components/YituliuSyncSettings.vue
@@ -29,7 +29,7 @@ async function act(action) {
         await axios.put(`${base}/growth-sync-token`, { token: token.value.trim() })
       ).data
       token.value = ''
-      feedback.value = '只写 Token 已保存，下次森空岛刷新成功后自动同步'
+      feedback.value = 'OAuth access_token 已保存，下次森空岛刷新成功后自动同步'
     } else if (action === 'clear') {
       status.value = (await axios.delete(`${base}/growth-sync-token`)).data
       token.value = ''
@@ -48,7 +48,7 @@ async function act(action) {
     }
   } catch (error) {
     failed.value = true
-    feedback.value = error.response?.data?.message || '操作未成功，请检查本地连接或只写 Token'
+    feedback.value = error.response?.data?.message || '操作未成功，请检查本地连接或 OAuth 令牌'
   } finally {
     busy.value = false
   }
@@ -61,11 +61,11 @@ onMounted(loadStatus)
   <n-card title="一图流干员同步">
     <n-space vertical :size="14">
       <n-text depth="3">
-        在一图流账号页生成“干员数据写入”权限的只写 Token
-        后填入。保存后，每次成功刷新森空岛数据都会自动同步至一图流；清除 Token
-        即可停止。保存本身不会上传。
-        <n-a href="https://ark.yituliu.cn" target="_blank" rel="noopener noreferrer"
-          >打开一图流</n-a
+        填入已授权 gama-data.write（干员数据写入）的一图流 OAuth
+        access_token。保存后，成功刷新森空岛数据时自动检查同步；与上次成功上传的内容相同则不传输。清除
+        Token 即可停止。保存本身不会上传。
+        <n-a href="https://auth.yituliu.cn" target="_blank" rel="noopener noreferrer"
+          >打开一图流用户中心</n-a
         >
       </n-text>
       <n-input
@@ -75,9 +75,11 @@ onMounted(loadStatus)
         autocomplete="new-password"
         :disabled="busy"
         :placeholder="
-          status.configured ? '••••••••（已保存，输入新 Token 可替换）' : '粘贴一图流只写 Token'
+          status.configured
+            ? '••••••••（已保存，输入新 Token 可替换）'
+            : '粘贴一图流 OAuth access_token'
         "
-        aria-label="一图流只写 Token"
+        aria-label="一图流 OAuth access_token"
       />
       <n-space align="center" :size="8">
         <n-button :disabled="busy || !token.trim()" @click="act('save')">保存 Token</n-button>
@@ -96,9 +98,10 @@ onMounted(loadStatus)
         </n-tag>
       </n-space>
       <n-alert type="info" :bordered="false">
-        将当前森空岛缓存中的游戏 UID、昵称、区服和全部已拥有干员的等级、精英化、潜能、技能及模组练度
-        上传至一图流，更新对应账号的干员数据。不会上传仓库、养成计划、森空岛账号密码或登录凭据。
-        旧缓存缺少游戏账号信息时，请先重新同步一次森空岛。
+        将当前森空岛缓存中的游戏 UID 和全部已拥有干员的等级、精英化、潜能、技能及模组练度
+        在本地校验后上传至一图流，更新对应账号的干员数据；与上次成功上传的内容相同则跳过。
+        不会上传仓库、养成计划、森空岛账号密码或登录凭据。
+        旧缓存缺少游戏账号信息时，请先重新同步一次森空岛。令牌失效后请重新获取并保存。
       </n-alert>
       <n-text v-if="status.last_synced_at" depth="3">
         最近同步：{{ new Date(status.last_synced_at * 1000).toLocaleString() }} ·
```
