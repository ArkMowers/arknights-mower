"""Purchase the exact catalyst shortage through a bounded MAA Custom task."""

import json
from contextlib import contextmanager
from contextvars import ContextVar
from uuid import uuid4

CATALYST = "芯片助剂"
VOUCHER = "采购凭证"
PRICE = 90
ENTRY = "MowerGrowthCatalyst@Begin"
RECEIPT = "MowerGrowthCatalyst@Obtained"
TASK_QUANTITY = ContextVar("maa_catalyst_quantity", default=1)
MAX_PURCHASE = 99


def custom_tasks(count=None):
    """Build the exact-quantity Custom chain for this resource-loading scope."""
    count = TASK_QUANTITY.get() if count is None else count
    entry_for_count(count)
    tasks = {
        ENTRY: {
            "algorithm": "OcrDetect",
            "text": ["凭证交易所"],
            "roi": [730, 38, 215, 134],
            "action": "ClickSelf",
            "postDelay": 1000,
            "next": ["MowerGrowthCatalyst@RedTickets"],
        },
        "MowerGrowthCatalyst@RedTickets": {
            "algorithm": "OcrDetect",
            "text": ["采购凭证区"],
            "roi": [49, 451, 176, 78],
            "action": "ClickSelf",
            "postDelay": 1000,
            "next": ["MowerGrowthCatalyst@Find", "MowerGrowthCatalyst@Swipe"],
        },
        "MowerGrowthCatalyst@Find": {
            "algorithm": "FeatureMatch",
            "template": "items/32001.png",
            "detector": "BRISK",
            "count": 20,
            "roi": [318, 139, 956, 484],
            "action": "ClickSelf",
            "postDelay": 800,
            "next": ["MowerGrowthCatalyst@Quantity"],
        },
        "MowerGrowthCatalyst@Swipe": {
            "algorithm": "JustReturn",
            "action": "Swipe",
            "specificRect": [1057, 355, 20, 20],
            "rectMove": [286, 355, 20, 20],
            "specialParams": [400, 1, 2, 0],
            "postDelay": 1500,
            "maxTimes": 5,
            "exceededNext": [],
            "next": ["MowerGrowthCatalyst@Find", "MowerGrowthCatalyst@Swipe"],
        },
        "MowerGrowthCatalyst@Quantity": {
            "algorithm": "OcrDetect",
            "text": ["1"],
            "fullMatch": True,
            "roi": [876, 405, 85, 51],
            "next": ["MowerGrowthCatalyst@Purchase"],
        },
        "MowerGrowthCatalyst@Purchase": {
            "algorithm": "OcrDetect",
            "text": ["购买物品"],
            "roi": [872, 556, 137, 48],
            "action": "ClickSelf",
            "postDelay": 1000,
            "maxTimes": 1,
            "exceededNext": [],
            "next": [RECEIPT],
        },
        RECEIPT: {
            "baseTask": "CreditShop-Bought",
            "next": [],
        },
    }

    result = {}
    prefix = entry_for_count(count).removesuffix("Begin")
    for name, definition in tasks.items():
        definition = json.loads(json.dumps(definition))
        for field in ("next", "exceededNext"):
            if field in definition:
                definition[field] = [
                    value.replace("MowerGrowthCatalyst@", prefix)
                    for value in definition[field]
                ]
        result[name.replace("MowerGrowthCatalyst@", prefix)] = definition
    result[prefix + "Quantity"]["text"] = [str(count)]
    if count > 1:
        result[prefix + "Find"]["next"] = [prefix + "Increase1"]
    for step in range(1, count):
        result[prefix + f"Increase{step}"] = {
            "algorithm": "JustReturn",
            "action": "ClickRect",
            "specificRect": [955, 400, 77, 66],
            "postDelay": 200,
            "maxTimes": 1,
            "exceededNext": [],
            "next": [
                prefix + (f"Increase{step + 1}" if step + 1 < count else "Quantity")
            ],
        }
    return result


def entry_for_count(count):
    if type(count) is not int or not 1 <= count <= MAX_PURCHASE:
        raise ValueError("芯片助剂单次兑换数量必须为一至99个")
    return ENTRY if count == 1 else f"MowerGrowthCatalyst{count}@Begin"


def receipt_for_count(count):
    return entry_for_count(count).removesuffix("Begin") + "Obtained"


@contextmanager
def task_quantity(count):
    entry_for_count(count)
    token = TASK_QUANTITY.set(count)
    try:
        yield
    finally:
        TASK_QUANTITY.reset(token)


def _read(conn):
    row = conn.execute(
        "SELECT payload FROM growth_catalyst_execution WHERE id=1"
    ).fetchone()
    return json.loads(row[0]) if row else None


def _write(conn, value):
    conn.execute(
        "INSERT INTO growth_catalyst_execution (id, payload) VALUES (1, ?) "
        "ON CONFLICT(id) DO UPDATE SET payload=excluded.payload",
        (json.dumps(value, ensure_ascii=False),),
    )


def _evidence(conn):
    from arknights_mower.utils import config
    from arknights_mower.utils.maa_backup import installation_identity
    from arknights_mower.utils.path import get_path

    stock = dict(conn.execute("SELECT item_name, count FROM inventory"))
    times = dict(
        conn.execute("SELECT item_name, observed_at FROM workshop_inventory_updates")
    )
    return {
        "stock": [
            [name, stock.get(name), times.get(name)] for name in (CATALYST, VOUCHER)
        ],
        "installation": json.loads(
            json.dumps(installation_identity(get_path(config.conf.maa_path)))
        ),
    }


def begin_purchase(uid, count=1):
    from arknights_mower.solvers import record

    entry_for_count(count)
    with record._conn() as conn:
        conn.execute("BEGIN IMMEDIATE")
        previous = _read(conn)
        if previous and previous["status"] == "running":
            _fail(conn, previous)
            conn.commit()
            return None
        if (
            previous
            and previous["uid"] == uid
            and previous["status"] == "failed"
            and previous["count"] == count
            and previous["evidence"] == _evidence(conn)
        ):
            return None
        stock = dict(conn.execute("SELECT item_name, count FROM inventory"))
        if CATALYST not in stock or stock.get(VOUCHER, 0) < PRICE * count:
            return None
        value = {
            "uid": uid,
            "token": uuid4().hex,
            "count": count,
            "status": "running",
            "pending": bool(
                previous and previous["uid"] == uid and previous.get("pending")
            ),
            "expected": previous.get("expected", {}) if previous else {},
        }
        _write(conn, value)
        conn.commit()
        return value["token"]


def recover_purchase():
    from arknights_mower.solvers import record

    with record._conn() as conn:
        conn.execute("BEGIN IMMEDIATE")
        value = _read(conn)
        if not value or value["status"] != "running":
            return
        _fail(conn, value)
        conn.commit()
    record.workshop_inventory_changed.set()


def cancel_purchase(token):
    """Release an unsubmitted attempt when dispatch yields before MAA startup."""
    from arknights_mower.solvers import record

    with record._conn() as conn:
        conn.execute("BEGIN IMMEDIATE")
        value = _read(conn)
        if value and value["token"] == token and value["status"] == "running":
            if value.get("pending"):
                value["status"] = "completed"
                _write(conn, value)
            else:
                conn.execute("DELETE FROM growth_catalyst_execution WHERE id=1")
            conn.commit()


def _fail(conn, value):
    from arknights_mower.solvers import record

    for name in (CATALYST, VOUCHER):
        conn.execute("DELETE FROM inventory WHERE item_name=?", (name,))
        conn.execute(
            "DELETE FROM workshop_inventory_pending WHERE item_name=?", (name,)
        )
    record._mark_workshop_inventory(conn, (CATALYST, VOUCHER))
    value.update(status="failed", evidence=_evidence(conn))
    _write(conn, value)


def finish_purchase(token, *, success=False, accepted=True):
    from arknights_mower.solvers import record

    with record._conn() as conn:
        conn.execute("BEGIN IMMEDIATE")
        value = _read(conn)
        if not value or value["token"] != token or value["status"] != "running":
            return False
        if success:
            record._apply_inventory_delta(
                conn, {CATALYST: value["count"], VOUCHER: -PRICE * value["count"]}
            )
            stock = dict(conn.execute("SELECT item_name, count FROM inventory"))
            value.update(
                status="completed",
                expected={name: stock.get(name) for name in (CATALYST, VOUCHER)},
                pending=True,
            )
            _write(conn, value)
        elif accepted:
            _fail(conn, value)
        else:
            value.update(status="failed", evidence=_evidence(conn))
            _write(conn, value)
        conn.commit()
    record.workshop_inventory_changed.set()
    return True


def preserve_cloud(snapshot):
    from arknights_mower.solvers import record

    uid = str(snapshot.get("_mower_player", {}).get("uid", ""))
    with record._conn() as conn:
        conn.execute("BEGIN IMMEDIATE")
        value = _read(conn)
        if not value or value["uid"] != uid or not value.get("pending"):
            return set()
        counts = {
            item["id"]: item.get("count") for item in snapshot["data"].get("items", [])
        }
        current = dict(conn.execute("SELECT item_name, count FROM inventory"))
        expected = value["expected"]
        if (
            type(counts.get("4006")) is int
            and expected[VOUCHER] is not None
            and counts["4006"] <= expected[VOUCHER]
            and (
                current.get(CATALYST) is None
                or counts.get("32001") == current[CATALYST]
            )
        ):
            value["pending"] = False
            _write(conn, value)
            conn.commit()
            return set()
    return {CATALYST, VOUCHER}


def record_callback(solver, message, payload, generation):
    run = getattr(solver, "maa_catalyst_run", None)
    if (
        not isinstance(run, dict)
        or run.get("confirmed")
        or generation is not run["generation"]
        or generation is not getattr(solver, "_maa_activity_generation", None)
        or payload.get("taskchain") != "Custom"
        or type(payload.get("taskid")) is not int
        or payload["taskid"] != run["task_id"]
        or message != 20002
        or payload.get("subtask") != "ProcessTask"
    ):
        return
    details = payload.get("details")
    if isinstance(details, dict) and details.get("task") == receipt_for_count(
        run["count"]
    ):
        run["confirmed"] = finish_purchase(run["token"], success=True)
