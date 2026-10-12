"""Upload operator progression after authorized refreshes or manual requests."""

import json
import re
from hashlib import sha256
from threading import RLock
from time import time

import requests

from arknights_mower.utils import config
from arknights_mower.utils.path import get_path

UPLOAD_URL = "https://auth.yituliu.cn/oauth2/ak-accounts/operators/save"
_lock = RLock()
_LEGACY_SETTINGS_PATH = "@app/config/yituliu_sync.json"


def _settings_model():
    return config.conf.yituliu_sync


def _settings_dict():
    return _settings_model().model_dump(exclude_none=True, exclude_defaults=True)


def _settings():
    saved = _settings_dict()
    path = get_path(_LEGACY_SETTINGS_PATH)
    if saved.get("token"):
        try:
            path.unlink(missing_ok=True)
        except OSError:
            pass
        return saved
    if not path.exists():
        return saved
    try:
        legacy = json.loads(path.read_text("utf-8"))
        if not isinstance(legacy, dict) or not isinstance(legacy.get("token", ""), str):
            raise ValueError()
        config.conf.yituliu_sync = type(_settings_model())(**legacy)
        config.conf.model_fields_set.add("yituliu_sync")
        config.save_conf()
        path.unlink(missing_ok=True)
        return _settings_dict()
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
        raise ValueError("请输入有效的一图流 OAuth access_token，不要填写森空岛凭据")
    with _lock:
        try:
            saved = _settings()
        except ValueError:
            saved = {}
        if saved.get("token") == token.strip():
            return token_status()
        config.conf.yituliu_sync = type(_settings_model())(token=token.strip())
        config.conf.model_fields_set.add("yituliu_sync")
        config.save_conf()
        get_path(_LEGACY_SETTINGS_PATH).unlink(missing_ok=True)
        return token_status()


def clear_token():
    with _lock:
        config.conf.yituliu_sync = type(_settings_model())()
        config.conf.model_fields_set.discard("yituliu_sync")
        config.save_conf()
        get_path(_LEGACY_SETTINGS_PATH).unlink(missing_ok=True)
        return token_status()


def _integer(value, lower, upper, label):
    if type(value) is not int or not lower <= value <= upper:
        raise ValueError(f"干员缓存中的{label}无效，请重新同步森空岛")
    return value


def build_upload_payload(snapshot, definitions):
    """Map the bound UID and progression to the OAuth save request."""
    player = snapshot.get("_mower_player") if isinstance(snapshot, dict) else None
    if not isinstance(player, dict) or "uid" not in player:
        raise ValueError(
            "当前缓存缺少游戏账号信息，请先重新同步一次森空岛，再立即同步一图流"
        )
    uid = player["uid"]
    if not isinstance(uid, str) or not re.fullmatch(r"[\x21-\x7e]{1,32}", uid):
        raise ValueError("缓存中的游戏 UID 无效，请重新同步森空岛")
    data = snapshot.get("data")
    chars = data.get("characters") if isinstance(data, dict) else None
    if not isinstance(chars, list) or not 1 <= len(chars) <= 2000:
        raise ValueError("干员缓存为空或无效，请重新同步森空岛")
    rows, seen = [], set()
    for char in chars:
        if not isinstance(char, dict) or not isinstance(char.get("id"), str):
            raise ValueError("干员缓存格式无效，请重新同步森空岛")
        cid = char["id"]
        if not re.fullmatch(r"[\x21-\x7e]{1,64}", cid):
            raise ValueError("干员编码无效，请重新同步森空岛")
        definition = definitions.get(cid)
        if not definition or cid in seen:
            raise ValueError("部分干员资源缺失或缓存重复，请更新资源并重新同步森空岛")
        seen.add(cid)
        row = {
            "id": cid,
            "level": _integer(char.get("level"), 1, 90, "等级"),
            "evolvePhase": _integer(char.get("evolvePhase"), 0, 2, "精英化阶段"),
            "potentialRank": _integer(char.get("potentialRank"), 0, 5, "潜能等级"),
            "rarity": _integer(definition.get("rarity"), 1, 6, "星级"),
            "mainSkillLevel": _integer(
                char.get("mainSkillLevel"), 1, 7, "基础技能等级"
            ),
            **{f"equip{branch}": 0 for branch in "XYDAB"},
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
            row[f"skill{index}"] = row["mainSkillLevel"] + _integer(
                skill.get("level"), 0, 3, "专精等级"
            )
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
            row[f"equip{branch}"] = max(row[f"equip{branch}"], level)
        rows.append(row)
    return {
        "playerInfo": {"akUid": uid},
        "operators": rows,
    }


def _upload(payload, token):
    try:
        with requests.Session() as session:
            session.trust_env = False
            with session.post(
                UPLOAD_URL,
                headers={"Authorization": f"Bearer {token}"},
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
    if not isinstance(result, dict) or type(result.get("code")) is not int:
        raise ValueError("一图流返回无效响应，同步结果尚未确认")
    if result["code"] != 200:
        messages = {
            80001: "一图流 OAuth 令牌已失效，请重新获取并保存 access_token",
            80008: "一图流令牌缺少 gama-data.write 权限，请重新授权后保存 access_token",
            10002: "一图流拒绝上传字段，请更新资源并重新同步森空岛",
            30006: "一图流上传过于频繁，请稍后手动重试",
            40003: "一图流限流服务暂不可用，请稍后手动重试",
            40004: "一图流数据保存冲突，请稍后重新同步",
            40001: "一图流服务繁忙，请稍后手动重试",
        }
        if result["code"] == 30006:
            data = result.get("data")
            delay = data.get("retryAfterSeconds") if isinstance(data, dict) else None
            if type(delay) is int and 1 <= delay <= 3600:
                raise ValueError(f"一图流上传过于频繁，请在 {delay} 秒后手动重试")
        raise ValueError(
            messages.get(result["code"], "一图流未确认同步成功，请稍后重试")
        )
    count = len(payload["operators"])
    data = result.get("data")
    if not isinstance(data, dict):
        raise ValueError("一图流返回无效保存计数，同步结果尚未确认")
    counts = [
        data.get(key) for key in ("createdCount", "updatedCount", "unchangedCount")
    ]
    if (
        any(type(value) is not int or value < 0 for value in counts)
        or sum(counts) != count
    ):
        raise ValueError("一图流返回无效保存计数，同步结果尚未确认")
    return {
        "success": True,
        "count": count,
        "synced_at": time(),
        "message": (
            f"已同步 {count} 名干员的练度至一图流"
            f"（新增 {counts[0]}，更新 {counts[1]}，未变更 {counts[2]}）"
        ),
    }


def sync_cached_operators(snapshot=None):
    with _lock:
        saved = _settings()
        if not saved.get("token"):
            raise ValueError(
                "请先保存具有 gama-data.write 权限的一图流 OAuth access_token"
            )
        try:
            from arknights_mower.utils.growth import growth_data
            from arknights_mower.utils.mastery_recommendation import get_skill_data

            payload = build_upload_payload(
                _snapshot() if snapshot is None else snapshot,
                growth_data(get_skill_data())["characters"],
            )
            canonical = {
                **payload,
                "operators": sorted(payload["operators"], key=lambda row: row["id"]),
            }
            fingerprint = sha256(
                json.dumps(canonical, sort_keys=True, separators=(",", ":")).encode()
            ).hexdigest()
            if fingerprint == saved.get("last_synced_fingerprint"):
                result = {
                    "success": True,
                    "skipped": True,
                    "count": len(payload["operators"]),
                    "synced_at": saved["last_synced_at"],
                    "message": "与上次成功同步的数据相同，已跳过上传，未传输数据",
                }
            else:
                result = _upload(payload, saved["token"])
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
                last_synced_at=result["synced_at"],
                last_synced_count=result["count"],
                last_synced_fingerprint=fingerprint,
            )
        try:
            config.conf.yituliu_sync = type(_settings_model())(**saved)
            config.conf.model_fields_set.add("yituliu_sync")
            config.save_conf()
            get_path(_LEGACY_SETTINGS_PATH).unlink(missing_ok=True)
        except OSError:
            if result["success"]:
                result["message"] += "；本地同步记录未能保存"
        if not result["success"]:
            raise ValueError(result["message"])
        return result


def refresh_and_sync_operators():
    """Refresh Skland now and return that refresh's single upload result."""
    if not token_status()["configured"]:
        raise ValueError("请先保存具有 gama-data.write 权限的一图流 OAuth access_token")
    try:
        from arknights_mower.solvers.cultivate_depot import cultivate

        syncer = cultivate()
        refreshed = syncer.start()
    except Exception:
        raise ValueError(
            "森空岛同步失败，请检查账号和网络后重试；未上传旧缓存"
        ) from None
    if not refreshed:
        raise ValueError(
            "未同步到干员数据，请检查森空岛账号及官服/B服选择；未上传旧缓存"
        )
    result = syncer.yituliu_sync_result
    if not result:
        raise ValueError(
            "森空岛已同步，一图流 Token 未配置或已被清除，请重新保存后重试"
        )
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
