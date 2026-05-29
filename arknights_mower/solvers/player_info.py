import datetime
import math
from dataclasses import asdict, dataclass
from urllib.parse import urlencode

import requests

from arknights_mower.utils import config
from arknights_mower.utils.log import logger
from arknights_mower.utils.skland import (
    get_binding_list,
    get_sign_header,
    header,
    player_info_url,
    refresh_session,
    restore_cached_session,
)

MAX_AP = 210

player_info_cache: dict[str, dict] = {}


@dataclass
class PlayerInfoSnapshot:
    account: str
    uid: str
    channel: str
    nickname: str
    current_ap: int
    full_recovery_time: datetime.datetime
    fetched_at: datetime.datetime
    raw_ap: dict


class PlayerInfoClient:
    def __init__(self) -> None:
        self.sign_token = ""

    def _ensure_session(self, item, force_refresh: bool = False):
        if not force_refresh:
            session = restore_cached_session(item.account)
            if session:
                self.sign_token = session["sign_token"]
                header["cred"] = session["cred"]
                return

        session_data = refresh_session(item)
        header["cred"] = session_data["cred"]
        self.sign_token = session_data["sign_token"]

    def _request_signed_json(
        self,
        item,
        method: str,
        url: str,
        body: dict | None = None,
        retry_on_failure: bool = True,
    ):
        self._ensure_session(item)
        request_header = get_sign_header(
            url,
            method,
            body if method.lower() != "get" else None,
            self.sign_token,
            header,
        )
        try:
            response = requests.request(
                method.upper(),
                url,
                headers=request_header,
                json=body,
                timeout=30,
            ).json()
        except Exception as exc:
            if retry_on_failure:
                logger.info(
                    "player info request retry after refresh | account=%s | method=%s | url=%s | error=%s",
                    item.account,
                    method.upper(),
                    url,
                    exc,
                )
                self._ensure_session(item, force_refresh=True)
                return self._request_signed_json(
                    item,
                    method,
                    url,
                    body=body,
                    retry_on_failure=False,
                )
            raise
        if response.get("code") != 0 and retry_on_failure:
            logger.info(
                "player info response retry after refresh | account=%s | code=%s | message=%s",
                item.account,
                response.get("code"),
                response.get("message"),
            )
            self._ensure_session(item, force_refresh=True)
            return self._request_signed_json(
                item,
                method,
                url,
                body=body,
                retry_on_failure=False,
            )
        return response

    def _get_binding_list_with_retry(self, item):
        self._ensure_session(item)
        try:
            bindings = get_binding_list(self.sign_token)
            if bindings:
                return bindings
        except Exception as exc:
            logger.info(
                "player info binding retry | account=%s | error=%s",
                item.account,
                exc,
            )
        self._ensure_session(item, force_refresh=True)
        return get_binding_list(self.sign_token)

    @staticmethod
    def get_recover_time(resp: dict, max_ap: int = MAX_AP):
        now_utc = datetime.datetime.now(datetime.timezone.utc)
        ap = resp.get("data", {}).get("status", {}).get("ap", {})
        raw_recover_time = ap.get("completeRecoveryTime")

        if raw_recover_time is None:
            return now_utc, max_ap

        try:
            full_recovery_time = datetime.datetime.fromtimestamp(
                int(raw_recover_time), datetime.timezone.utc
            )
        except (TypeError, ValueError, OSError, OverflowError):
            return now_utc, max_ap

        if full_recovery_time <= now_utc:
            return now_utc, max_ap

        total_minutes = max(
            0,
            (full_recovery_time - now_utc).total_seconds() / 60,
        )
        missing_ap = math.ceil(total_minutes / 6)
        current_ap = max(0, min(max_ap, max_ap - missing_ap))
        return full_recovery_time, current_ap

    @staticmethod
    def _binding_enabled(item, binding: dict) -> bool:
        if binding.get("gameId") != 1 or not binding.get("uid"):
            return False
        if not item.arknights_isCheck:
            return False
        channel_name = binding.get("channelName")
        if channel_name == "bilibili服" and not item.sign_in_bilibili:
            return False
        if channel_name == "官服" and not item.sign_in_official:
            return False
        # 读取第一个账户选择的森空岛仓库读取服务器作为理智获取服务器 true: official | false: bilibili
        if item.cultivate_select and binding.get("channelName") != "官服":
            return False
        if not item.cultivate_select and binding.get("channelName") != "bilibili服":
            return False
        return True

    def fetch_snapshot(self, item, binding: dict) -> PlayerInfoSnapshot:
        uid = binding.get("uid")
        if not uid:
            raise ValueError("uid missing")
        url = f"{player_info_url}?{urlencode({'uid': uid})}"
        resp = self._request_signed_json(item, "get", url)
        if resp.get("code") != 0:
            raise RuntimeError(resp.get("message") or "player/info failed")

        ap = resp.get("data", {}).get("status", {}).get("ap", {})
        full_recovery_time, computed_ap = self.get_recover_time(resp)
        raw_current = ap.get("current")
        current_ap = computed_ap
        if isinstance(raw_current, int):
            normalized_raw_current = max(0, min(MAX_AP, raw_current))
            if abs(normalized_raw_current - computed_ap) <= 1:
                current_ap = normalized_raw_current
            else:
                logger.warning(
                    "player info ap mismatch, fallback to computed ap | account=%s | uid=%s | raw_current=%s | computed_ap=%s | completeRecoveryTime=%s",
                    item.account,
                    uid,
                    normalized_raw_current,
                    computed_ap,
                    ap.get("completeRecoveryTime"),
                )

        snapshot = PlayerInfoSnapshot(
            account=item.account,
            uid=uid,
            channel=binding.get("channelName") or "",
            nickname=binding.get("nickName") or "",
            current_ap=current_ap,
            full_recovery_time=full_recovery_time,
            fetched_at=datetime.datetime.now(datetime.timezone.utc),
            raw_ap=ap,
        )
        cache_key = f"{snapshot.account}:{snapshot.uid}"
        player_info_cache[cache_key] = asdict(snapshot)
        player_info_cache["latest"] = player_info_cache[cache_key]
        return snapshot

    def log_snapshot(self, snapshot: PlayerInfoSnapshot):
        logger.info(
            "森空岛理智状态 | 账号=%s | uid=%s | 角色=%s | 渠道=%s | current=%s | full_recovery_local=%s | raw_ap=%s",
            snapshot.account,
            snapshot.uid,
            snapshot.nickname,
            snapshot.channel,
            snapshot.current_ap,
            snapshot.full_recovery_time.astimezone().strftime("%Y-%m-%d %H:%M:%S %z"),
            snapshot.raw_ap,
        )

    def iter_account_snapshots(self):
        for item in config.conf.skland_info:
            if not item.arknights_isCheck:
                continue
            for binding in self._get_binding_list_with_retry(item):
                if not self._binding_enabled(item, binding):
                    continue
                try:
                    yield self.fetch_snapshot(item, binding)
                except Exception as exc:
                    logger.exception(
                        "fetch player info failed | account=%s | uid=%s | error=%s",
                        item.account,
                        binding.get("uid"),
                        exc,
                    )

    def get_first_available_snapshot(self) -> PlayerInfoSnapshot | None:
        logger.info("start fetching first available skland player snapshot")
        for snapshot in self.iter_account_snapshots():
            logger.info(
                "selected skland player snapshot | account=%s | uid=%s | current_ap=%s",
                snapshot.account,
                snapshot.uid,
                snapshot.current_ap,
            )
            return snapshot
        logger.warning("no available skland player snapshot was found")
        return None

    def log_selected_accounts_ap_status(self):
        for snapshot in self.iter_account_snapshots():
            self.log_snapshot(snapshot)

    def probe_accounts(self) -> list[str]:
        results: list[str] = []
        for item in config.conf.skland_info:
            try:
                results.append(f"账号 {item.account}：")
                found = False
                for binding in self._get_binding_list_with_retry(item):
                    if not self._binding_enabled(item, binding):
                        continue
                    snapshot = self.fetch_snapshot(item, binding)
                    found = True
                    results.append(
                        " - {} 连接成功 | AP={} | 恢复完成={}".format(
                            snapshot.nickname or snapshot.uid,
                            snapshot.current_ap,
                            snapshot.full_recovery_time.astimezone().strftime(
                                "%Y-%m-%d %H:%M:%S %z"
                            ),
                        )
                    )
                if not found:
                    results.append(" - 未找到可用的明日方舟角色绑定")
            except Exception as exc:
                msg = f"{item.account} 无法连接 - {exc}"
                logger.exception(msg)
                results.append(msg)
        return results
