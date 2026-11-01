import json
from threading import Lock
from time import time
from urllib.parse import urlencode

from arknights_mower.utils import config
from arknights_mower.utils.config import atomic_write
from arknights_mower.utils.log import logger
from arknights_mower.utils.path import get_path
from arknights_mower.utils.skland import (
    get_binding_list,
    get_cred_by_token,
    get_sign_header,
    header,
    log,
    player_info_url,
    request_with_retry,
)
from arknights_mower.utils.workshop_data import parse_roster

_refresh_lock = Lock()


class cultivate:
    def __init__(self):
        self.record_path = get_path("@app/tmp/cultivate.json")
        self.reward = []
        self.sign_token = ""
        self.all_recorded = True

    def start(self, *, force_inventory=False):
        # Keep request, local persistence and remote upload in the same order.
        with _refresh_lock:
            return self._refresh(force_inventory=force_inventory)

    def _refresh(self, *, force_inventory=False):
        self.yituliu_sync_result = None
        if not config.conf.skland_info:
            return False
        updated = False
        item = config.conf.skland_info[0]
        self.save_param(get_cred_by_token(log(item)))
        for i in get_binding_list(self.sign_token):
            if i.get("gameId") == 1 and item.cultivate_select == i.get("isOfficial"):
                body = {"gameId": 1, "uid": i.get("uid")}
                ingame = f"https://zonai.skland.com/api/v1/game/cultivate/player?uid={i.get('uid')}"
                observed_at = time()
                resp = request_with_retry(
                    "get",
                    ingame,
                    headers=get_sign_header(ingame, "get", body, self.sign_token),
                ).json()

                if isinstance(resp, dict) and resp.get("code") != 0:
                    raise ValueError(resp.get("message") or "森空岛返回的干员数据无效")
                parse_roster(resp)
                from arknights_mower.utils.building_skills import parse_base_conditions

                conditions = parse_base_conditions(resp.get("data", {}).get("building"))
                if not conditions:
                    info_url = f"{player_info_url}?{urlencode({'uid': i['uid']})}"
                    try:
                        info = request_with_retry(
                            "get",
                            info_url,
                            headers=get_sign_header(
                                info_url, "get", None, self.sign_token
                            ),
                            timeout=10,
                        ).json()
                        if isinstance(info, dict) and info.get("code") == 0:
                            conditions = parse_base_conditions(
                                info.get("data", {}).get("building")
                            )
                    except Exception as exc:
                        logger.warning(
                            "森空岛基建设施读取失败，保留干员同步结果：%s",
                            type(exc).__name__,
                        )
                if conditions:
                    resp = {**resp, "_mower_base_conditions": conditions}
                player_fields = ("uid", "nickName", "channelName", "channelMasterId")
                if all(key in i for key in player_fields):
                    resp = {
                        **resp,
                        "_mower_player": {key: i[key] for key in player_fields},
                    }
                items = resp.get("data", {}).get("items")
                if items is not None:
                    if not isinstance(items, list) or any(
                        not isinstance(entry, dict)
                        or not isinstance(entry.get("id"), str)
                        or not str(entry.get("count", "")).isdigit()
                        for entry in items
                    ):
                        raise ValueError("森空岛返回的库存数据无效")
                    # Use request start, not completion: a concurrent craft must win.
                    resp = {**resp, "_mower_inventory_observed_at": observed_at}

                from arknights_mower.utils.growth import (
                    completed_manual_goals,
                    load_goals,
                    remove_completed_goals,
                    save_statistics,
                )
                from arknights_mower.utils.mastery_db import (
                    complete_synced_mastery_plans,
                    has_synced_mastery_completion,
                )
                from arknights_mower.utils.mastery_recommendation import get_skill_data

                skills = get_skill_data()
                completed = completed_manual_goals(resp["data"], skills, load_goals())
                calibrate = bool(completed) or has_synced_mastery_completion(
                    resp["data"]
                )
                if force_inventory and items is None:
                    if calibrate:
                        from arknights_mower.solvers.record import save_inventory_counts

                        save_inventory_counts(
                            {},
                            scanned_counts={},
                            cloud_counts={},
                            cloud_at=observed_at,
                            force_cloud=True,
                            invalidate_missing=True,
                        )
                    raise ValueError("森空岛未返回库存，无法完成库存同步")

                def dump(file):
                    json.dump(resp, file, ensure_ascii=False, indent=4)

                # Manual refresh and warehouse tasks share this atomic cache write.
                atomic_write(self.record_path, dump)
                try:
                    save_statistics(
                        resp,
                        self.record_path.with_name("growth_history.json"),
                        observed_at,
                        skills,
                    )
                except (OSError, ValueError, KeyError):
                    logger.exception("养成统计缓存保存失败")
                if calibrate or items is not None:
                    from arknights_mower.solvers.record import save_inventory_counts
                    from arknights_mower.utils.depot import cloud_inventory_snapshot

                    counts, timestamp = cloud_inventory_snapshot(resp)
                    save_inventory_counts(
                        counts,
                        scanned_counts={},
                        cloud_counts=counts,
                        cloud_at=observed_at if calibrate else timestamp,
                        force_cloud=force_inventory or calibrate,
                        invalidate_missing=calibrate,
                    )
                if completed:
                    remove_completed_goals(resp["data"], skills)
                if complete_synced_mastery_plans(resp["data"]):
                    from arknights_mower.solvers.record import (
                        workshop_inventory_changed,
                    )

                    workshop_inventory_changed.set()
                    config.wake_scheduler.set()
                updated = True
                from arknights_mower.utils.yituliu_sync import sync_after_cultivate

                self.yituliu_sync_result = sync_after_cultivate(resp)
        return updated

    def save_param(self, cred_resp):
        header["cred"] = cred_resp["cred"]
        self.sign_token = cred_resp["token"]
