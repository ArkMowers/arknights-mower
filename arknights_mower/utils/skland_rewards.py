from collections import Counter
from urllib.parse import urlencode

import requests

from arknights_mower.utils import skland
from arknights_mower.utils.skland_log import (
    mask_account,
    redact_signing_text,
    sign_role_key,
    skland_day,
)

_REQUEST_TIMEOUT = 10
_CHANNELS = {
    (1, "官服"): ("明日方舟官服", "arknights_isCheck", "sign_in_official"),
    (1, "bilibili服"): ("明日方舟bilibili服", "arknights_isCheck", "sign_in_bilibili"),
    (3, "官服"): ("终末地官服", "endfield_isCheck", "sign_in_endfield_official"),
    (3, "bilibili服"): (
        "终末地bilibili服",
        "endfield_isCheck",
        "sign_in_endfield_bilibili",
    ),
}


def _read_bindings(session):
    headers = {**skland.header, "cred": session["cred"]}
    bindings = skland.get_binding_list(
        session["sign_token"], old_header=headers, timeout=_REQUEST_TIMEOUT
    )
    return bindings, headers


def _load_bindings(account):
    session = skland.restore_cached_session(account.account)
    if session:
        bindings, headers = _read_bindings(session)
        if bindings:
            return bindings, headers, session["sign_token"]

    session = skland.refresh_session(account)
    bindings, headers = _read_bindings(session)
    return bindings, headers, session["sign_token"]


def _reward_targets(bindings, enabled):
    for binding in bindings:
        if not isinstance(binding, dict):
            continue
        game_id = binding.get("gameId")
        channel = binding.get("channelName")
        if game_id not in (1, 3) or not isinstance(channel, str):
            continue
        game = enabled.get((game_id, channel))
        if not game:
            continue
        if game_id == 1:
            if uid := binding.get("uid"):
                query = urlencode({"gameId": 1, "uid": uid})
                yield (
                    game,
                    game_id,
                    f"{skland.sign_url}?{query}",
                    "",
                    binding.get("nickName"),
                    str(uid),
                    "",
                )
            continue
        roles = binding.get("roles")
        for role in roles if isinstance(roles, list) else ():
            if not isinstance(role, dict):
                continue
            role_id = role.get("roleId")
            server_id = role.get("serverId")
            if role_id and server_id not in (None, ""):
                yield (
                    game,
                    game_id,
                    skland.sign_endfield_url,
                    f"3_{role_id}_{server_id}",
                    role.get("nickname"),
                    str(role_id),
                    str(server_id),
                )


def _calendar_entries(data, game_id):
    if not isinstance(data, dict) or not isinstance(data.get("calendar"), list):
        raise ValueError("森空岛响应缺少本月奖励")
    entries = [entry if isinstance(entry, dict) else {} for entry in data["calendar"]]
    if game_id == 1:
        entries = [entry for entry in entries if entry.get("type") == "daily"]
    return entries


def _reward_slots(data, game_id, entries):
    resources = data.get("resourceInfoMap")
    resources = resources if isinstance(resources, dict) else {}
    slots = []
    for index, entry in enumerate(entries, start=1):
        resource_id = entry.get("resourceId" if game_id == 1 else "awardId")
        resource = resources.get(str(resource_id))
        rewards = []
        if isinstance(resource, dict):
            count = entry.get("count", 0) if game_id == 1 else resource.get("count", 0)
            name = resource.get("name")
            if (
                isinstance(name, str)
                and name.strip()
                and type(count) is int
                and count >= 0
            ):
                rewards.append({"item": name, "count": count})
        slots.append(
            {
                "index": index,
                "done": entry.get("done") is True,
                "available": entry.get("available") is True,
                "rewards": rewards,
            }
        )
    return slots


def _sign_date(timestamp):
    if type(timestamp) not in (int, str):
        return None
    try:
        seconds = int(timestamp)
        if seconds > 0:
            return skland_day(seconds)
    except (ValueError, OverflowError, OSError):
        pass
    return None


def _daily_sign_dates(data, today):
    records = data.get("records")
    if not isinstance(records, list):
        return []
    start = today.replace(day=1)
    dates = {
        date
        for record in records
        if isinstance(record, dict)
        and record.get("type") == "daily"
        and (date := _sign_date(record.get("ts"))) is not None
        and start <= date <= today
    }
    return sorted(dates)


def _signed_today(data, game_id, entries, today, daily_dates):
    if game_id == 3:
        state = data.get("hasToday")
        return state if isinstance(state, bool) else None

    if today in daily_dates:
        return True

    if any(entry.get("available") is True for entry in entries):
        return False
    return None


def _fetch_reward_calendar(game_id, url, role_header, headers, sign_token):
    if role_header:
        headers = {
            **headers,
            "sk-game-role": role_header,
            "Referer": "https://game.skland.com/",
            "Origin": "https://game.skland.com",
        }
    response = skland.request_with_retry(
        "get",
        url,
        timeout=_REQUEST_TIMEOUT,
        headers_factory=lambda: skland.get_sign_header(
            url, "get", None, sign_token, headers
        ),
    )
    received_date = skland_day()
    response.raise_for_status()
    payload = response.json()
    if not isinstance(payload, dict) or payload.get("code") != 0:
        raise ValueError("森空岛本月奖励读取失败")
    data = payload.get("data")
    entries = _calendar_entries(data, game_id)
    progress_date = _sign_date(data.get("currentTs")) or received_date
    daily_dates = _daily_sign_dates(data, progress_date) if game_id == 1 else []
    slots = _reward_slots(data, game_id, entries)
    calendar = {
        "reward_slots": slots,
        "signed_today": _signed_today(
            data, game_id, entries, progress_date, daily_dates
        ),
        "progress_date": progress_date.isoformat(),
    }
    if (
        daily_dates
        and all(slot["done"] == (slot["index"] <= len(daily_dates)) for slot in slots)
        and len(daily_dates) <= len(slots)
    ):
        calendar["signed_dates"] = [date.isoformat() for date in daily_dates]
    return calendar


def fetch_pair_rewards(accounts) -> tuple[list[dict], list[str]]:
    """读取已启用角色的本月签到奖励顺序。"""
    pairs = []
    warnings = []
    role_indices = Counter()
    masked_accounts = Counter(
        mask_account(name) for name in {item.account for item in accounts}
    )
    seen = set()
    for account in accounts:
        enabled = {
            key: game
            for key, (game, game_flag, channel_flag) in _CHANNELS.items()
            if getattr(account, game_flag) and getattr(account, channel_flag)
        }
        if not account.account or not enabled:
            continue
        name = mask_account(account.account)
        try:
            bindings, headers, sign_token = _load_bindings(account)
        except Exception:
            warnings.append(f"{name} 的森空岛角色读取失败")
            continue
        if not bindings:
            warnings.append(f"{name} 未读取到森空岛角色")
            continue

        matched = False
        for (
            game,
            game_id,
            url,
            role_header,
            nickname,
            role_id,
            server_id,
        ) in _reward_targets(bindings, enabled):
            matched = True
            role_key = sign_role_key(account.account, game, role_id, server_id)
            if role_key in seen:
                continue
            seen.add(role_key)
            role_indices[name, game] += 1
            index = role_indices[name, game]
            try:
                calendar = _fetch_reward_calendar(
                    game_id, url, role_header, headers, sign_token
                )
            except (ValueError, requests.RequestException):
                warnings.append(f"{name} · {game} · 角色 {index} 的本月奖励读取失败")
                continue
            pair = {
                "account": name,
                "game": game,
                "role_index": index,
                "role_key": role_key,
                **calendar,
            }
            if isinstance(nickname, str) and nickname.strip():
                pair["display_name"] = redact_signing_text(
                    nickname.strip(),
                    account.account,
                    account.password,
                    headers["cred"],
                    sign_token,
                )
            pairs.append(pair)
        if not matched:
            warnings.append(f"{name} 未读取到已启用区服的森空岛角色")
    for pair in pairs:
        if (
            masked_accounts[pair["account"]] > 1
            or role_indices[pair["account"], pair["game"]] > 1
        ):
            pair["progress_ambiguous"] = True
    return pairs, warnings
