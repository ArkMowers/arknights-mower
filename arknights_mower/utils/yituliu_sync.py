"""Upload operator progression after authorized refreshes or manual requests."""

import json
import re
from threading import RLock
from time import time

import requests

from arknights_mower.utils.config import atomic_write
from arknights_mower.utils.path import get_path

UPLOAD_URL = "https://backend.yituliu.cn/open-api/operator/upload"
PLAYER_FIELDS = ("uid", "nickName", "channelName", "channelMasterId")
_lock = RLock()


def _settings():
    path = get_path("@app/config/yituliu_sync.json")
    if not path.exists():
        return {}
    try:
        saved = json.loads(path.read_text("utf-8"))
        if not isinstance(saved, dict) or not isinstance(saved.get("token", ""), str):
            raise ValueError()
        return saved
    except (ValueError, OSError):
        raise ValueError("一图流本地设置无法读取，请重新保存 Token") from None


def _snapshot():
    try:
        return json.loads(get_path("@app/tmp/cultivate.json").read_text("utf-8"))
    except (ValueError, OSError):
        raise ValueError("没有可用的干员缓存，请先同步森空岛数据") from None


def token_status():
    with _lock:
        saved = _settings()
        return {
            "configured": bool(saved.get("token")),
            "last_synced_at": saved.get("last_synced_at"),
            "last_synced_count": saved.get("last_synced_count", 0),
            "last_attempt_at": saved.get("last_attempt_at"),
            "last_sync_error": saved.get("last_sync_error"),
        }


def save_token(token):
    if not isinstance(token, str) or not re.fullmatch(
        r"[A-Za-z0-9._~-]{16,512}", token.strip()
    ):
        raise ValueError("请输入有效的一图流只写 Token，不要填写森空岛凭据")
    with _lock:
        path = get_path("@app/config/yituliu_sync.json")
        atomic_write(path, lambda stream: json.dump({"token": token.strip()}, stream))
        path.chmod(0o600)
        return token_status()


def clear_token():
    with _lock:
        get_path("@app/config/yituliu_sync.json").unlink(missing_ok=True)
        return token_status()


def _integer(value, lower, upper, label):
    if type(value) is not int or not lower <= value <= upper:
        raise ValueError(f"干员缓存中的{label}无效，请重新同步森空岛")
    return value


def build_upload_payload(snapshot, definitions):
    """Map cached fields to the official PlayerInfoDTO without account secrets."""
    player = snapshot.get("_mower_player") if isinstance(snapshot, dict) else None
    if not isinstance(player, dict) or any(key not in player for key in PLAYER_FIELDS):
        raise ValueError(
            "当前缓存缺少游戏账号信息，请先重新同步一次森空岛，再立即同步一图流"
        )
    uid = str(player["uid"])
    if not re.fullmatch(r"[0-9]{1,20}", uid):
        raise ValueError("缓存中的游戏 UID 无效，请重新同步森空岛")
    for key in ("nickName", "channelName"):
        if not isinstance(player[key], str) or len(player[key]) > 100:
            raise ValueError("缓存中的游戏账号信息无效，请重新同步森空岛")
    try:
        channel = int(player["channelMasterId"])
    except (TypeError, ValueError):
        raise ValueError("缓存中的区服信息无效，请重新同步森空岛") from None
    if channel < 0 or channel > 100 or type(player["channelMasterId"]) is bool:
        raise ValueError("缓存中的区服信息无效，请重新同步森空岛")
    data = snapshot.get("data")
    chars = data.get("characters") if isinstance(data, dict) else None
    if not isinstance(chars, list) or not 1 <= len(chars) <= 2000:
        raise ValueError("干员缓存为空或无效，请重新同步森空岛")
    rows, seen = [], set()
    for char in chars:
        if not isinstance(char, dict) or not isinstance(char.get("id"), str):
            raise ValueError("干员缓存格式无效，请重新同步森空岛")
        cid = char["id"]
        definition = definitions.get(cid)
        if not definition or cid in seen:
            raise ValueError("部分干员资源缺失或缓存重复，请更新资源并重新同步森空岛")
        seen.add(cid)
        row = {
            "charId": cid,
            "own": True,
            "level": _integer(char.get("level"), 1, 90, "等级"),
            "elite": _integer(char.get("evolvePhase"), 0, 2, "精英化阶段"),
            "potential": _integer(char.get("potentialRank"), 0, 5, "潜能等级") + 1,
            "rarity": _integer(definition.get("rarity"), 1, 6, "星级"),
            "mainSkill": _integer(char.get("mainSkillLevel"), 1, 7, "基础技能等级"),
            **{f"mod{branch}": 0 for branch in "XYDAB"},
            **{f"skill{index}": 0 for index in range(1, 4)},
        }
        skills, equips = char.get("skills"), char.get("equips")
        if (
            not isinstance(skills, list)
            or len(skills) > 3
            or not isinstance(equips, list)
        ):
            raise ValueError("干员技能或模组缓存无效，请重新同步森空岛")
        for index, skill in enumerate(skills, 1):
            if not isinstance(skill, dict):
                raise ValueError("干员技能缓存无效，请重新同步森空岛")
            row[f"skill{index}"] = _integer(skill.get("level"), 0, 3, "专精等级")
        modules = {m["id"]: m for m in definition.get("modules", [])}
        for equip in equips:
            if not isinstance(equip, dict) or not isinstance(equip.get("id"), str):
                raise ValueError("干员模组缓存无效，请重新同步森空岛")
            level = _integer(equip.get("level"), 0, 3, "模组等级")
            if not level or equip["id"].startswith("uniequip_001_"):
                continue
            branch = modules.get(equip["id"], {}).get("type", "").rsplit("-", 1)[-1]
            if branch not in ("X", "Y", "D", "A", "B"):
                raise ValueError("部分模组资源缺失，请更新资源后再同步一图流")
            row[f"mod{branch}"] = max(row[f"mod{branch}"], level)
        rows.append(row)
    return {
        "uid": uid,
        "nickName": player["nickName"],
        "channelName": player["channelName"],
        "channelMasterId": channel,
        "operatorDataList": rows,
    }


def _upload(snapshot, token):
    from arknights_mower.utils.growth import growth_data
    from arknights_mower.utils.mastery_recommendation import get_skill_data

    payload = build_upload_payload(
        snapshot, growth_data(get_skill_data())["characters"]
    )
    try:
        with requests.Session() as session:
            session.trust_env = False
            with session.post(
                UPLOAD_URL,
                headers={"Authorization": token},
                json=payload,
                timeout=(3, 15),
                allow_redirects=False,
            ) as response:
                response.raise_for_status()
                if response.status_code != 200:
                    raise ValueError()
                result = response.json()
    except requests.RequestException:
        raise ValueError(
            "同步请求未得到确认，请核对一图流数据和 Token 权限后重试；未自动重试"
        ) from None
    except (TypeError, ValueError):
        raise ValueError("一图流返回无效响应，同步结果尚未确认") from None
    if not isinstance(result, dict) or result.get("code") != 200:
        raise ValueError("一图流未确认同步成功，请检查只写 Token 的有效性及写入权限")
    count = len(payload["operatorDataList"])
    return {
        "success": True,
        "count": count,
        "synced_at": time(),
        "message": f"已同步 {count} 名干员的练度至一图流",
    }


def sync_cached_operators(snapshot=None):
    with _lock:
        saved = _settings()
        if not saved.get("token"):
            raise ValueError("请先保存一图流只写 Token")
        try:
            result = _upload(
                _snapshot() if snapshot is None else snapshot, saved["token"]
            )
        except ValueError as exc:
            result = {"success": False, "message": str(exc)}
        except Exception:
            # Never expose an exception containing request headers or cached data.
            result = {
                "success": False,
                "message": "一图流同步未完成，请检查本地缓存和资源后重试",
            }
        saved.update(
            last_attempt_at=time(),
            last_sync_error=None if result["success"] else result["message"],
        )
        if result["success"]:
            saved.update(
                last_synced_at=result["synced_at"], last_synced_count=result["count"]
            )
        try:
            path = get_path("@app/config/yituliu_sync.json")
            atomic_write(path, lambda stream: json.dump(saved, stream))
            path.chmod(0o600)
        except OSError:
            if result["success"]:
                result["message"] = "同步成功，但本地同步时间未能保存"
        if not result["success"]:
            raise ValueError(result["message"])
        return result


def sync_after_cultivate(snapshot):
    """A failed automatic upload never changes the completed Skland refresh."""
    with _lock:
        try:
            if not _settings().get("token"):
                return None
            return sync_cached_operators(snapshot)
        except ValueError as exc:
            return {"success": False, "message": str(exc)}
        except Exception:
            return {"success": False, "message": "一图流同步未完成；森空岛数据已保留"}
