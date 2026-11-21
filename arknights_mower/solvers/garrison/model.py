import hashlib
import json
from functools import lru_cache
from pathlib import Path

SEASON = "act3autochess"


class GarrisonError(RuntimeError):
    """当前画面不能支持下一步操作。"""


@lru_cache(maxsize=1)
def catalogue():
    path = Path(__file__).resolve().parents[2] / "data" / "garrison.json"
    return json.loads(path.read_text(encoding="utf-8"))


def normal_name(value):
    return "".join(c for c in value if c not in ' \t\r\n“”"·.：:').lower()


def identity_key(conf):
    device = conf.device.model_dump(mode="json")
    # 只绑定显式设备身份；截图、触控与恢复设置变化不创建新对局。
    identity = {
        k: device.get(k)
        for k in (
            "preset_id",
            "instance_name",
            "instance_id",
            "installation_path",
            "manager_path",
            "config_path",
            "instance_uuid",
            "topology_fingerprint",
            "mumu_manual_serial",
            "mumu_created_timestamp",
            "game_package",
        )
    }
    if device.get("preset_id", "").startswith("manual."):
        identity["last_serial"] = device.get("last_serial")
    return hashlib.sha256(
        json.dumps(
            [SEASON, identity, conf.package_type, conf.account], sort_keys=True
        ).encode()
    ).hexdigest()


def run_key(conf):
    target = "matches" if conf.garrison.mode == "matches" else conf.garrison.target_wins
    if conf.garrison.mode.startswith("maa_"):
        target = (
            [conf.garrison.mode, conf.garrison.target_wins]
            if conf.garrison.mode == "maa_medals"
            else "maa_score"
        )
    return [identity_key(conf), target, conf.garrison.run_id]


def goal_counts(progress, target_wins, match_limit, mode="medals"):
    if mode == "maa_score":
        return 0, 0
    if mode == "maa_medals" and progress.get("maa_badge_target", 0) >= target_wins:
        total = len(catalogue()["strategies"])
        return total, total
    if match_limit is not None:
        return progress.get("matches_played", 0), match_limit
    wins = progress.get("wins", {})
    strategies = catalogue()["strategies"]
    return sum(
        type(wins.get(s["id"])) is int and wins[s["id"]] >= target_wins
        for s in strategies
    ), len(strategies)


def goal_reached(progress, target_wins, match_limit, mode="medals"):
    count, total = goal_counts(progress, target_wins, match_limit, mode)
    return total > 0 and count >= total


def status(conf, progress):
    prepared = prepare_progress(conf, progress)
    settings = conf.garrison
    matches = settings.mode == "matches"
    count, total = goal_counts(
        prepared,
        settings.target_wins,
        settings.match_limit if matches else None,
        settings.mode,
    )
    return {
        **({"mode": settings.mode} if settings.mode != "medals" else {}),
        "completed": total > 0
        and count >= total
        and not prepared.get("original_theme"),
        "count": count,
        "total": total,
        "failed": False,
        "message": prepared.get("error", ""),
    }


def prepare_progress(conf, saved):
    progress = (
        dict(saved)
        if saved.get("identity") == identity_key(conf)
        else {
            "identity": identity_key(conf),
            "wins": {},
            "match": None,
        }
    )
    progress.pop("failed", None)
    progress.pop("theme_restore_blocked", None)
    if progress.get("key") != run_key(conf):
        if progress.get("key", [None, None, None])[-1] != conf.garrison.run_id:
            progress.pop("maa_badge_target", None)
            if conf.garrison.mode == "matches":
                progress["matches_played"] = 0
            else:
                progress["wins"] = {}
        progress.update(key=run_key(conf), error="", attempts=0)
    return progress


def record_wins(progress, strategy, wins):
    allowed = {s["id"] for s in catalogue()["strategies"]}
    if strategy not in allowed or type(wins) is not int or not 0 <= wins <= 999:
        raise GarrisonError("策略胜场未确认")
    progress.setdefault("wins", {})[strategy] = wins
