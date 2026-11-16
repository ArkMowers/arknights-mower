"""Admit supplied MAA growth actions and retain confirmed local progression."""

import copy
import json
from collections import Counter

from arknights_mower.utils.growth import (
    LEVEL_GOALS,
    growth_data,
    growth_resources,
    inventory_counts,
    level_goal_targets,
    material_entries,
    promotion_materials,
)

EXP_IDS = ("2001", "2002", "2003", "2004")
ROLES = {
    "PIONEER": "Pioneer",
    "WARRIOR": "Warrior",
    "TANK": "Tank",
    "SNIPER": "Sniper",
    "CASTER": "Caster",
    "MEDIC": "Medic",
    "SUPPORT": "Support",
    "SPECIAL": "Special",
}


def _uid(snapshot):
    return str(snapshot.get("_mower_player", {}).get("uid", ""))


def _rows():
    from arknights_mower.solvers.record import _conn

    with _conn() as conn:
        return [
            json.loads(row[0])
            for row in conn.execute("SELECT payload FROM growth_execution")
        ]


def action_key(action):
    return json.dumps(
        [action["uid"], action["char_id"], action["field"], action["target"]]
    )


def _store(conn, action):
    conn.execute(
        "INSERT INTO growth_execution (id, payload) VALUES (?, ?) "
        "ON CONFLICT(id) DO UPDATE SET payload=excluded.payload",
        (action_key(action), json.dumps(action, ensure_ascii=False)),
    )


def evidence(action):
    from arknights_mower.solvers import record

    with record._conn() as conn:
        return _evidence(conn, action)


def _evidence(conn, action):
    from arknights_mower.utils import config
    from arknights_mower.utils.path import get_path

    stock = dict(conn.execute("SELECT item_name, count FROM inventory"))
    times = dict(
        conn.execute("SELECT item_name, observed_at FROM workshop_inventory_updates")
    )
    target = get_path(config.conf.maa_path)
    try:
        installed_at = target.stat().st_mtime_ns
    except OSError:
        installed_at = None
    return {
        "stock": [
            [name, stock.get(name), times.get(name)]
            for name in sorted(action["affected"])
        ],
        "maa_path": config.conf.maa_path,
        "installed_at": installed_at,
    }


def blocked(action):
    for row in _rows():
        if action_key(row) == action_key(action):
            return row["status"] in ("running", "completed") or (
                row["status"] == "failed" and row.get("evidence") == evidence(action)
            )
    return False


def save_attempt(action):
    from arknights_mower.solvers import record

    with record._conn() as conn:
        conn.execute("BEGIN IMMEDIATE")
        _store(conn, {**action, "status": "running", "pending": True})
        conn.commit()


def reject_attempt(action):
    """Do not retry an unavailable core against unchanged relevant observations."""
    from arknights_mower.solvers import record

    row = {**action, "status": "failed", "pending": False, "evidence": evidence(action)}
    with record._conn() as conn:
        _store(conn, row)
        conn.commit()


def recover_attempts():
    """A previous process may have stopped after payment but before its callback."""
    for row in _rows():
        if row["status"] == "running":
            finish_attempt(row)


def finish_attempt(action, *, success=False, already=False, payment_known=True):
    """Commit progression and payment together; duplicate receipts pay nothing."""
    from arknights_mower.solvers import record

    with record._conn() as conn:
        conn.execute("BEGIN IMMEDIATE")
        found = conn.execute(
            "SELECT payload FROM growth_execution WHERE id=?", (action_key(action),)
        ).fetchone()
        previous = json.loads(found[0]) if found else {}
        if previous.get("status") == "completed":
            return False
        stock = dict(conn.execute("SELECT item_name, count FROM inventory"))
        unknown = set(action["uncertain"])
        if success and not already and payment_known:
            costs = action["costs"]
            unknown.update(
                name for name, count in costs.items() if stock.get(name, -1) < count
            )
            record._apply_inventory_delta(
                conn,
                {name: -count for name, count in costs.items() if name not in unknown},
            )
        else:
            # An interruption or AlreadySatisfied does not prove what this run paid.
            unknown.update(action["affected"])
        conn.executemany(
            "DELETE FROM inventory WHERE item_name=?", [(name,) for name in unknown]
        )
        conn.executemany(
            "DELETE FROM workshop_inventory_pending WHERE item_name=?",
            [(name,) for name in unknown],
        )
        record._mark_workshop_inventory(conn, unknown)
        row = {
            **action,
            "status": "completed" if success else "failed",
            "pending": success,
        }
        if not success:
            row["evidence"] = _evidence(conn, action)
        _store(conn, row)
        conn.commit()
    record.workshop_inventory_changed.set()
    return True


def reconcile_snapshot(snapshot):
    """Keep cloud inventory behind a local receipt until cloud progression catches up."""
    from arknights_mower.solvers import record

    result = copy.deepcopy(snapshot)
    chars = {char["id"]: char for char in result["data"]["characters"]}
    protected = set()
    with record._conn() as conn:
        conn.execute("BEGIN IMMEDIATE")
        rows = [
            json.loads(row[0])
            for row in conn.execute("SELECT payload FROM growth_execution")
        ]
        for row in rows:
            if row["uid"] != _uid(snapshot) or row["char_id"] not in chars:
                continue
            char = chars[row["char_id"]]
            field, target = row["field"], row["target"]
            caught_up = type(char.get(field)) is int and char[field] >= target
            if row.get("pending") and caught_up:
                row["pending"] = False
                _store(conn, row)
            elif not caught_up and (row.get("pending") or row["status"] == "completed"):
                protected.update(row["affected"])
            if row["status"] == "completed":
                if field == "evolvePhase" and char.get(field, 0) < target:
                    char.update(evolvePhase=target, level=1, exp=0)
                elif field == "mainSkillLevel":
                    char[field] = max(char.get(field, 1), target)
        conn.commit()
    from arknights_mower.utils.maa_catalyst import preserve_cloud

    return result, protected | preserve_cloud(snapshot)


def publish_progress():
    """Materialize confirmed observations for all existing BOX readers."""
    from arknights_mower.solvers.cultivate_depot import _refresh_lock
    from arknights_mower.utils.config import atomic_write
    from arknights_mower.utils.growth import remove_completed_goals
    from arknights_mower.utils.mastery_recommendation import get_skill_data
    from arknights_mower.utils.path import get_path

    with _refresh_lock:
        path = get_path("@app/tmp/cultivate.json")
        snapshot = json.loads(path.read_text("utf-8"))
        # This is a cached payload, not a fresh cloud observation.
        original = _rows()
        result = copy.deepcopy(snapshot)
        chars = {char["id"]: char for char in result["data"]["characters"]}
        for row in original:
            char = chars.get(row["char_id"])
            if (
                row["uid"] != _uid(snapshot)
                or row["status"] != "completed"
                or char is None
            ):
                continue
            field, target = row["field"], row["target"]
            if field == "evolvePhase" and char.get(field, 0) < target:
                char.update(evolvePhase=target, level=1, exp=0)
            elif field == "mainSkillLevel":
                char[field] = max(char.get(field, 1), target)
        if result != snapshot:
            atomic_write(path, lambda file: json.dump(result, file, ensure_ascii=False))
        remove_completed_goals(result["data"], get_skill_data())


def candidates(snapshot, skills, plans, goals, order, stock, *, cumulative=False):
    """Only finished materials admit execution; mastery and modules stay in Mower."""
    from arknights_mower.utils.growth_order import crafting_projects

    data = growth_data(skills)
    resources = growth_resources(skills)
    counts = inventory_counts(
        snapshot["data"], resources, local=True, local_counts=stock
    )
    chars = {char["id"]: char for char in snapshot["data"]["characters"]}
    seen = set()
    admitted_chars = set()
    reserved = Counter()
    for project in crafting_projects(plans, goals, order):
        cid = project["char_id"]
        if cumulative and cid in admitted_chars:
            continue
        char, definition = chars.get(cid), data.get("characters", {}).get(cid)
        if not char or not definition or definition.get("integrated_strategy"):
            continue
        phase = char.get("evolvePhase")
        rank = char.get("mainSkillLevel")
        if (
            type(phase) is not int
            or type(rank) is not int
            or definition.get("profession") not in ROLES
        ):
            continue
        goal = project.get("goal", {}).get("module_id")
        target_phase, skill7 = 0, False
        if project["kind"] == "skill":
            if project["plan"].get("status") in (
                "completed",
                "failed",
            ):
                continue
            target_phase, skill7 = 2, True
        elif goal in LEVEL_GOALS:
            target_phase = level_goal_targets(definition).get(goal, (0, 1))[0]
        elif goal == "skill7":
            target_phase, skill7 = 1, True
        else:
            module = next(
                (m for m in definition.get("modules", []) if m["id"] == goal), None
            )
            target_phase = module["elite"] if module else 0
        field, target, uncertain = None, None, []
        if phase < target_phase:
            field, target = "evolvePhase", target_phase
            materials = promotion_materials(char, definition, data, (target, 1))
            needs_exp = any(
                m["id"] == "growth_exp" and m["count"] > 0 for m in materials
            )
            if needs_exp:
                uncertain = [resources["items"][iid]["name"] for iid in EXP_IDS] + [
                    "龙门币"
                ]
        elif skill7 and rank < 7 and phase >= 1:
            field, target = "mainSkillLevel", rank + 1
            levels = definition.get("basic_skills", [])
            if not 1 <= rank <= 6 or len(levels) < rank:
                continue
            materials = levels[rank - 1]
        else:
            # Earlier supplied projects retain their materials even when they need
            # no promotion/basic-skill action (notably an active mastery stage).
            project_cost = Counter()
            for _, before, own in material_entries(
                snapshot["data"],
                resources,
                [project["plan"]] if project["kind"] == "skill" else [],
                [project["goal"]] if project["kind"] == "goal" else [],
                separate_prerequisites=True,
            ):
                for material in before + own:
                    project_cost[material["id"]] += material["count"]
            if all(
                counts.get(iid, -1) - reserved[iid] >= n
                for iid, n in project_cost.items()
            ):
                reserved.update(project_cost)
            continue
        identity = (cid, field, target)
        if identity in seen:
            continue
        seen.add(identity)
        required = Counter()
        for material in materials:
            required[material["id"]] += material["count"]
        dual = {
            iid: n - max(0, counts.get(iid, 0) - reserved[iid])
            for iid, n in required.items()
            if iid.startswith("32")
            and iid.endswith("3")
            and n > max(0, counts.get(iid, 0) - reserved[iid])
        }
        if any(iid not in counts for iid in dual):
            continue
        admission = required.copy()
        for iid, missing in dual.items():
            admission[iid] -= missing
            admission[iid[:-1] + "2"] += missing * 2
            admission["32001"] += missing
        catalyst_purchase = 0
        if dual and "32001" in counts:
            catalyst_purchase = max(
                0, admission["32001"] - (counts["32001"] - reserved["32001"])
            )
            admission["32001"] -= catalyst_purchase
            admission["4006"] += 90 * catalyst_purchase
        if any(
            counts.get(iid, -1) - reserved[iid] < count
            for iid, count in admission.items()
            if count
        ):
            continue
        costs = {
            resources["items"][iid]["name"]: n
            for iid, n in required.items()
            if iid != "growth_exp"
        }
        affected = sorted(set(costs) | set(uncertain))
        for iid in dual:
            affected.extend(
                [
                    resources["items"][iid[:-1] + "2"]["name"],
                    resources["items"]["32001"]["name"],
                ]
            )
        action = {
            "uid": _uid(snapshot),
            "char_id": cid,
            "name": definition["name"],
            "role": ROLES[definition["profession"]],
            "field": field,
            "target": target,
            "from_phase": phase,
            "costs": costs,
            "uncertain": uncertain,
            "affected": affected,
            "dual": dual,
        }
        if catalyst_purchase:
            action["catalyst_purchase"] = catalyst_purchase
            action["affected"].append("采购凭证")
        if not blocked(action):
            if cumulative:
                reserved.update(admission)
                admitted_chars.add(cid)
            yield action


def guard_tasks():
    """A missing finished material ends MAA growth before any workshop or factory visit."""
    # Normalized template scores cannot reach two. Stop actions return success
    # in MAA ProcessTask, so they cannot represent a rejected growth substep.
    return {
        name: {
            "algorithm": "MatchTemplate",
            "template": "MaterialMissing.png",
            "templThreshold": 2.0,
            "action": "DoNothing",
            "next": [],
            "onErrorNext": [],
            "exceededNext": [],
        }
        for name in (
            "OperProgress@Dualchip",
            "OperProgress@EliteUpMaterial1",
            "OperProgress@EliteUpMaterial2",
            "OperProgress@SkillUpMaterial0",
            "OperProgress@SkillUpMaterial1",
            "OperProgress@SkillUpMaterial2",
        )
    }


def prepare_guard(cache, *, split):
    from pathlib import Path

    from arknights_mower.utils.config import atomic_write

    path = Path(cache) / "resource" / ("tasks/tasks.json" if split else "tasks.json")
    path.parent.mkdir(parents=True, exist_ok=True)
    previous = json.loads(path.read_text("utf-8")) if path.exists() else {}
    tasks = merge_growth_tasks(previous)
    if tasks != previous:
        atomic_write(path, lambda file: json.dump(tasks, file))


def growth_tasks():
    from arknights_mower.utils.maa_catalyst import custom_tasks

    return {**guard_tasks(), **custom_tasks()}


def merge_growth_tasks(previous):
    return {
        **{
            name: task
            for name, task in previous.items()
            if not name.startswith("MowerGrowthCatalyst")
        },
        **growth_tasks(),
    }
