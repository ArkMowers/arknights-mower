"""不连接游戏、服务器、排班数据库的鸿雪组效率纠偏回归测试。"""

import ast
import json
from datetime import datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from typing import Literal

import pytest
from pydantic import BaseModel, Field, ValidationError, model_validator

from arknights_mower.utils.trade_efficiency import (
    EXPECTED_LOSS,
    canonical_key,
    decide,
    key_for,
    load_history,
    migrate_reference,
    monitored_rooms,
    parse_bonus,
    save_history,
)

ROOT = Path(__file__).parents[1]


class Logger:
    def __init__(self):
        self.events = []

    def info(self, *args, **kwargs):
        self.events.append(("INFO", args))

    def warning(self, *args, **kwargs):
        self.events.append(("WARNING", args))

    def error(self, *args, **kwargs):
        self.events.append(("ERROR", args))

    def debug(self, *args, **kwargs):
        pass


def compiled_runtime():
    """从真实生产模块抽取原函数，替换游戏侧依赖而非伪造被测算法。"""
    src = ROOT / "utils/trade_efficiency_runtime.py"
    tree = ast.parse(src.read_text(encoding="utf8"))
    nodes = [n for n in tree.body if isinstance(n, ast.FunctionDef)]
    env = {
        "datetime": datetime,
        "timedelta": timedelta,
        "logger": Logger(),
        "EXPECTED_LOSS": EXPECTED_LOSS,
        "OCR_TOLERANCE": 1.5,
        "PAIR": frozenset(("绮良", "鸿雪")),
        "decide": decide,
        "key_for": key_for,
        "canonical_key": canonical_key,
        "migrate_reference": migrate_reference,
        "monitored_rooms": monitored_rooms,
        "parse_bonus": parse_bonus,
        "load_history": lambda: {},
        "save_history": lambda value: None,
        "configured_rule": lambda rules, room: next(
            (r for r in rules if r.enabled and r.room == room), None
        ),
        "SchedulerTask": lambda **kwargs: SimpleNamespace(
            time=kwargs["time"],
            plan=kwargs["task_plan"],
            type=kwargs["task_type"],
            meta_data=kwargs["meta_data"],
        ),
        "TaskTypes": SimpleNamespace(RE_ORDER="RE_ORDER"),
        "rapidocr": SimpleNamespace(engine=None),
        "config": SimpleNamespace(conf=SimpleNamespace(trade_efficiency_rules=[])),
    }
    exec(
        compile(
            ast.fix_missing_locations(ast.Module(body=nodes, type_ignores=[])),
            str(src),
            "exec",
        ),
        env,
    )
    return env


def rule(
    *,
    room="room_1_1",
    mode="auto",
    baseline=None,
    related=("room_1_2",),
    enabled=True,
    retry_limit=2,
):
    return SimpleNamespace(
        room=room,
        enabled=enabled,
        baseline_mode=mode,
        manual_percent=baseline,
        retry_limit=retry_limit,
        related_rooms=list(related),
    )


def sample(room="room_1_1", roster=("伺夜", "绮良", "鸿雪"), value=92, related=None):
    roster = list(roster)
    key = key_for(room, roster, "lmd", related or {"room_1_2": ["图耶"]})
    return {"room": room, "roster": roster, "key": key, "percent": value}


def solver():
    return SimpleNamespace(
        _trade_efficiency_pending={},
        _trade_efficiency_repair=None,
        tasks=[],
        task=None,
        no_pending_task=lambda minute: True,
    )


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("+47%", 47),
        ("+112％", 112),
        ("92", 92),
        ("+107.5%", 107.5),
        ("+1,2%", 1.2),
        ("+117%±", 117),
        ("+112%↗", 112),
        ("+87%↑", 87),
        ("+117%±↑", 117),
    ],
)
def test_ocr_percent_parser(raw, expected):
    assert parse_bonus(raw) == expected


@pytest.mark.parametrize(
    "raw",
    [
        "",
        "12:30",
        "100+20%",
        "2,300%",
        "+112%+5",
        "订单112",
        "-30%",
        "+117%±7",
        "+117%+3",
        "112%订单",
    ],
)
def test_ocr_rejects_ambiguous_text(raw):
    assert parse_bonus(raw) is None


def test_context_separates_facilities_operators_and_related_rooms():
    a = sample()
    assert a["key"] == sample(roster=("鸿雪", "伺夜", "绮良"))["key"]
    assert a["key"] == sample(roster=("吉星", "绮良", "鸿雪"))["key"]
    assert a["key"] != key_for(
        "room_1_1", ["绮良", "鸿雪"], "orundum", {"room_1_2": ["图耶"]}
    )
    assert a["key"] != sample(related={"room_1_2": []})["key"]


def test_absolute_efficiency_not_hardcoded():
    r = rule()
    for expected in (107, 112, 137):
        key = sample(value=expected)["key"]
        history = {key: {"verified_baseline": expected}}
        assert decide(r, key, expected - 20, history) == "repair"
        assert decide(r, key, expected, history) == "normal"
        assert decide(r, key, expected - 12, history) == "uncertain"


def test_initial_unknown_baseline_calibrates_once():
    data = solver()
    env = compiled_runtime()
    r = rule()
    env["config"].conf.trade_efficiency_rules = [r]
    env["_snapshot"] = lambda owner, setting: sample(value=92)
    records = {}
    env["load_history"] = lambda: records
    env["save_history"] = lambda current: records.update(current)
    env["audit_when_idle"](data)
    assert data._trade_efficiency_repair["stage"] == "swap_pending"
    assert data.tasks[0].plan == {"room_1_1": ["Current", "鸿雪", "绮良"]}
    data.task = data.tasks.pop()
    env["on_arrangement_completed"](data, "room_1_1")
    assert data._trade_efficiency_repair["stage"] == "restore_pending"
    assert data.tasks[0].plan == {"room_1_1": ["Current", "绮良", "鸿雪"]}
    data.task = data.tasks.pop()
    env["on_arrangement_completed"](data, "room_1_1")
    assert data._trade_efficiency_repair["stage"] == "read_pending"
    env["_snapshot"] = lambda owner, setting: sample(value=112)
    env["audit_when_idle"](data)
    assert data._trade_efficiency_repair is None
    assert records[sample()["key"]]["verified_baseline"] == 112
    assert data._trade_efficiency_pending == {}


def test_failed_calibration_never_loops():
    data = solver()
    env = compiled_runtime()
    r = rule()
    env["config"].conf.trade_efficiency_rules = [r]
    env["_snapshot"] = lambda owner, setting: sample(value=92)
    records = {}
    env["load_history"] = lambda: records
    env["save_history"] = lambda current: records.update(current)
    env["audit_when_idle"](data)
    data.task = data.tasks.pop()
    env["on_arrangement_completed"](data, r.room)
    data.task = data.tasks.pop()
    env["on_arrangement_completed"](data, r.room)
    env["audit_when_idle"](data)
    assert records[sample()["key"]]["provisional_baseline"] == 92
    assert records[sample()["key"]]["unresolved"] is False
    env["mark_changed"](data, r.room)
    env["audit_when_idle"](data)
    assert not data.tasks  # unchanged roster never repeats calibration
    env["_snapshot"] = lambda owner, setting: sample(value=72)
    env["mark_changed"](data, r.room)
    env["audit_when_idle"](data)
    assert len(data.tasks) == 1  # later genuine 20 point loss remains detectable


def test_related_room_arrangement_marks_primary_facility():
    env = compiled_runtime()
    data = solver()
    env["config"].conf.trade_efficiency_rules = [rule()]
    env["mark_changed"](data, "room_1_2")
    assert list(data._trade_efficiency_pending) == ["room_1_1"]


def test_nearby_urgent_tasks_defer_ocr_and_swaps():
    env = compiled_runtime()
    data = solver()
    data.no_pending_task = lambda minutes: False
    data._trade_efficiency_pending = {"room_1_1": datetime.now()}
    env["config"].conf.trade_efficiency_rules = [rule()]
    env["_snapshot"] = lambda *args: pytest.fail("should never enter room")
    env["audit_when_idle"](data)
    assert data._trade_efficiency_pending and not data.tasks


def test_manual_baseline_shared_across_third_slot_variants_only():
    manual = rule(mode="manual", baseline=112)
    base = sample()["key"]
    changed = sample(roster=("吉星", "绮良", "鸿雪"))["key"]
    unrelated = sample(related={"room_1_2": []})["key"]
    records = {"_manual_binding": {"room_1_1": base}}
    assert base == changed
    assert decide(manual, base, 92, records) == "repair"
    assert decide(manual, changed, 87, records) == "repair"
    assert decide(manual, unrelated, 92, records) == "uncertain"


def test_config_schema_rules_are_opt_in():
    tree = ast.parse((ROOT / "utils/config/conf.py").read_text(encoding="utf8"))
    cls = next(
        node
        for node in tree.body
        if isinstance(node, ast.ClassDef) and node.name == "TradeEfficiencyRule"
    )
    globals_ = {
        "ConfModel": BaseModel,
        "Field": Field,
        "model_validator": model_validator,
        "Literal": Literal,
    }
    exec(
        compile(
            ast.fix_missing_locations(ast.Module(body=[cls], type_ignores=[])),
            "trade_efficiency_conf.py",
            "exec",
        ),
        globals_,
    )
    Model = globals_["TradeEfficiencyRule"]
    assert not Model(room="room_1_1").enabled
    assert Model(room="room_1_1").retry_limit == 2
    assert Model(enabled=True, room="room_1_1", related_rooms=["room_1_2"]).enabled
    assert Model(enabled=True, room="room_1_1", retry_limit=5).retry_limit == 5
    with pytest.raises(ValidationError):
        Model(enabled=True, room="room_1_1", retry_limit=0)
    with pytest.raises(ValidationError):
        Model(enabled=True, room="room_1_1", retry_limit=6)
    with pytest.raises(ValidationError):
        Model(enabled=True, room="invalid")
    with pytest.raises(ValidationError):
        Model(enabled=True, room="room_1_1", baseline_mode="manual")
    with pytest.raises(ValidationError):
        Model(enabled=True, room="room_1_1", related_rooms=["room_1_1"])


def test_baseline_file_roundtrip_isolated(tmp_path):
    path = tmp_path / "config" / "efficiency.json"
    current = {"x": {"verified_baseline": 112}}
    save_history(current, path)
    assert load_history(path) == current


def test_real_scheduler_hooks_once_in_confirm_and_idle():
    source = ast.parse((ROOT / "solvers/base_schedule.py").read_text(encoding="utf8"))
    functions = [
        n
        for cls in source.body
        if isinstance(cls, ast.ClassDef)
        for n in cls.body
        if isinstance(n, ast.FunctionDef)
    ]
    arrange = next(n for n in functions if n.name == "agent_arrange_room")
    main = next(n for n in functions if n.name == "infra_main")
    assert (
        sum(
            isinstance(n, ast.Call)
            and isinstance(n.func, ast.Name)
            and n.func.id == "on_arrangement_completed"
            for n in ast.walk(arrange)
        )
        == 2
    )
    assert (
        sum(
            isinstance(n, ast.Call)
            and isinstance(n.func, ast.Name)
            and n.func.id == "audit_when_idle"
            for n in ast.walk(main)
        )
        == 1
    )


def test_ocr_accepts_both_rapidocr_payload_shapes():
    env = compiled_runtime()
    read = env["_ocr_value"]
    assert read([["112%", 0.98]]) == 112
    assert read([[[[0, 0], [1, 1]], "+47%", 0.91]]) == 47
    assert read([["+117%±", 0.8527356882890066]]) == 117
    assert read([["+117%±", 0.8527356882890066], ["42%", 0.8]]) is None
    assert read([["112%", 0.3]]) is None
    assert read([["112%", 0.95], ["72%", 0.95]]) is None


def test_manual_mode_compares_only_blue_bonus():
    env = compiled_runtime()
    data = solver()
    r = rule(mode="manual", baseline=112)
    env["config"].conf.trade_efficiency_rules = [r]
    shot = sample(value=92)
    shot["total_percent"] = 400  # white bonus must not influence the decision
    env["_snapshot"] = lambda *_: shot.copy()
    records = {}
    env["load_history"] = lambda: dict(records)
    env["save_history"] = lambda value: records.clear() or records.update(value)
    env["audit_when_idle"](data)
    assert data._trade_efficiency_repair["metric"] == "blue"
    assert data._trade_efficiency_repair["before"] == 92
    data.task = data.tasks.pop()
    env["on_arrangement_completed"](data, r.room)
    data.task = data.tasks.pop()
    env["on_arrangement_completed"](data, r.room)
    env["_snapshot"] = lambda *_: {**shot, "percent": 112, "total_percent": None}
    env["audit_when_idle"](data)
    assert data._trade_efficiency_repair is None
    assert records[shot["key"]]["verified_baseline"] == 112


def test_manual_mode_never_requires_white_bonus():
    env = compiled_runtime()
    data = solver()
    r = rule(mode="manual", baseline=112)
    env["config"].conf.trade_efficiency_rules = [r]
    env["_snapshot"] = lambda *_: {**sample(value=92), "total_percent": None}
    env["audit_when_idle"](data)
    assert len(data.tasks) == 1
    assert data._trade_efficiency_repair["metric"] == "blue"


def test_missing_swap_task_recovers_original_at_most_once():
    env = compiled_runtime()
    data = solver()
    r = rule()
    env["config"].conf.trade_efficiency_rules = [r]
    snapshot = sample()
    records = {}
    env["load_history"] = lambda: dict(records)
    env["save_history"] = lambda value: records.clear() or records.update(value)
    env["_snapshot"] = lambda *_: snapshot
    env["audit_when_idle"](data)
    assert data.tasks[0].meta_data.startswith("trade-efficiency-swap:")
    data.tasks.clear()  # scheduler exhausted retry after a partial/unknown game operation
    env["audit_when_idle"](data)
    assert len(data.tasks) == 1
    assert data.tasks[0].meta_data.startswith("trade-efficiency-restore:")
    assert data.tasks[0].plan[r.room] == ["Current", "绮良", "鸿雪"]
    data.tasks.clear()  # even recovery exhausted; never enter an infinite loop
    env["audit_when_idle"](data)
    assert records[snapshot["key"]]["unresolved"] is True
    assert data._trade_efficiency_repair is None
    assert not data.tasks


def test_disabled_rule_during_pending_restore_still_restores_original():
    env = compiled_runtime()
    data = solver()
    env["config"].conf.trade_efficiency_rules = []
    data._trade_efficiency_repair = {
        "room": "room_1_1",
        "stage": "restore_pending",
        "original": ["伺夜", "绮良", "鸿雪"],
        "key": sample()["key"],
        "metric": "blue",
        "before": 92,
        "kind": "repair",
        "recovery_attempts": 0,
    }
    env["audit_when_idle"](data)
    assert len(data.tasks) == 1
    assert data.tasks[0].plan == {"room_1_1": ["Current", "绮良", "鸿雪"]}


def test_manual_expected_change_can_rebind_to_new_conditions():
    env = compiled_runtime()
    data = solver()
    r = rule(mode="manual", baseline=112)
    env["config"].conf.trade_efficiency_rules = [r]
    current = sample()
    records = {"_manual_binding": {"room_1_1": {"key": "old-roster", "percent": 107}}}
    env["load_history"] = lambda: dict(records)
    env["save_history"] = lambda value: records.clear() or records.update(value)
    env["_snapshot"] = lambda *_: {**current, "percent": 112, "total_percent": None}
    env["audit_when_idle"](data)
    assert records["_manual_binding"]["room_1_1"] == {
        "key": current["key"],
        "percent": 112,
    }
    assert not data.tasks


def test_existing_pending_repair_loaded_before_early_disabled_return():
    env = compiled_runtime()
    data = solver()
    env["config"].conf.trade_efficiency_rules = []
    active = {
        "room": "room_1_1",
        "stage": "swap_pending",
        "original": ["伺夜", "绮良", "鸿雪"],
        "key": sample()["key"],
        "metric": "blue",
        "before": 92,
        "kind": "calibrate",
        "recovery_attempts": 0,
    }
    history = {"_active_repair": active}
    env["load_history"] = lambda: dict(history)
    env["save_history"] = lambda value: history.update(value)
    env["audit_when_idle"](data)
    assert len(data.tasks) == 1
    assert data.tasks[0].plan == {"room_1_1": ["Current", "绮良", "鸿雪"]}


def test_repair_tasks_sorted_before_later_normal_jobs():
    env = compiled_runtime()
    data = solver()
    env["config"].conf.trade_efficiency_rules = [rule()]
    data.tasks.append(
        SimpleNamespace(
            time=datetime.now() + timedelta(minutes=4), meta_data="normal-task"
        )
    )
    env["_snapshot"] = lambda owner, setting: sample(value=92)
    env["audit_when_idle"](data)
    assert data.tasks[0].meta_data.startswith("trade-efficiency-swap:")
    assert data.tasks[1].meta_data == "normal-task"


def test_first_calibration_can_induce_loss_and_gets_one_recovery_attempt():
    data = solver()
    env = compiled_runtime()
    rule_ = rule()
    env["config"].conf.trade_efficiency_rules = [rule_]
    records = {}
    env["load_history"] = lambda: dict(records)
    env["save_history"] = lambda value: records.clear() or records.update(value)
    env["_snapshot"] = lambda *_: sample(value=112)
    env["audit_when_idle"](data)
    data.task = data.tasks.pop()
    env["on_arrangement_completed"](data, rule_.room)
    data.task = data.tasks.pop()
    env["on_arrangement_completed"](data, rule_.room)
    env["_snapshot"] = lambda *_: sample(value=92)
    env["audit_when_idle"](data)
    assert records[sample()["key"]]["verified_baseline"] == 112
    assert rule_.room in data._trade_efficiency_pending
    env["audit_when_idle"](data)
    assert len(data.tasks) == 1  # single rescue swap; later failure marks unresolved


@pytest.mark.parametrize(
    "reference,actual,expected",
    [
        (117, 117, "normal"),
        (117, 112, "normal"),
        (117, 97, "repair"),
        (117, 92, "repair"),
        (117, 107, "uncertain"),
        (117, 102, "uncertain"),
        (112, 117, "normal"),
        (112, 92, "repair"),
        (112, 97, "uncertain"),
    ],
)
def test_five_point_variant_is_not_an_efficiency_bug(reference, actual, expected):
    k = sample()["key"]
    assert decide(rule(), k, actual, {k: {"verified_baseline": reference}}) == expected


def test_legacy_verified_117_reused_for_gixing_without_first_swap():
    k = key_for("room_1_1", ["吉星", "绮良", "鸿雪"], "lmd", {})
    legacy = json.dumps(
        ["room_1_1", sorted(["伺夜", "绮良", "鸿雪"]), "lmd", {}],
        ensure_ascii=False,
        separators=(",", ":"),
    )
    records = {legacy: {"verified_baseline": 117, "confirmed_by_user": True}}
    assert canonical_key(legacy) == k
    assert migrate_reference(records, k)
    assert records[k]["verified_baseline"] == 117
    assert decide(rule(), k, 112, records) == "normal"
    assert decide(rule(), k, 92, records) == "repair"


def test_migration_rejects_different_product_related_context_and_conflicting_bases():
    k = key_for("room_1_1", ["伺夜", "绮良", "鸿雪"], "lmd", {})

    def old(names, product="lmd", related=None):
        return json.dumps(
            ["room_1_1", sorted(names), product, related or {}],
            ensure_ascii=False,
            separators=(",", ":"),
        )

    no_match = {
        old(["伺夜", "绮良", "鸿雪"], "orundum"): {"verified_baseline": 117},
        old(["伺夜", "绮良", "鸿雪"], related={"room_1_2": ["图耶"]}): {
            "verified_baseline": 117
        },
    }
    assert not migrate_reference(no_match, k)
    contradictory = {
        old(["伺夜", "绮良", "鸿雪"]): {"verified_baseline": 117},
        old(["吉星", "绮良", "鸿雪"]): {"verified_baseline": 107},
    }
    assert not migrate_reference(contradictory, k)


def test_saved_reference_and_log_when_jixing_blue_112():
    env = compiled_runtime()
    data = solver()
    env["config"].conf.trade_efficiency_rules = [rule(related=())]
    k = key_for("room_1_1", ["吉星", "绮良", "鸿雪"], "lmd", {})
    legacy = json.dumps(
        ["room_1_1", sorted(["伺夜", "绮良", "鸿雪"]), "lmd", {}],
        ensure_ascii=False,
        separators=(",", ":"),
    )
    history = {legacy: {"verified_baseline": 117}}
    env["load_history"] = lambda: history
    env["save_history"] = lambda value: history.update(value)
    env["_snapshot"] = lambda *_: {
        "room": "room_1_1",
        "roster": ["吉星", "绮良", "鸿雪"],
        "percent": 112.0,
        "key": k,
    }
    env["audit_when_idle"](data)
    assert not data.tasks and data._trade_efficiency_repair is None
    assert history[k]["verified_baseline"] == 117
    assert any(
        fmt == "贸易站效率自检：%s %g%%（%s）"
        and tuple(args) == ("room_1_1", 112.0, "符合预期")
        for level, (fmt, *args) in env["logger"].events
        if level == "INFO"
    )


def test_promote_normal_five_point_high_watermark_before_detecting_loss():
    env = compiled_runtime()
    data = solver()
    env["config"].conf.trade_efficiency_rules = [rule()]
    observed = sample(value=117)
    history = {observed["key"]: {"verified_baseline": 112}}
    env["load_history"] = lambda: history
    env["save_history"] = lambda value: history.update(value)
    env["_snapshot"] = lambda *_: observed
    env["audit_when_idle"](data)
    assert history[observed["key"]]["verified_baseline"] == 117
    assert not data.tasks
    data._trade_efficiency_pending["room_1_1"] = datetime.now()
    env["_snapshot"] = lambda *_: sample(value=97)
    env["audit_when_idle"](data)
    assert data.tasks and data._trade_efficiency_repair["before"] == 97


def test_20_point_recovery_keeps_previously_confirmed_higher_reference():
    env = compiled_runtime()
    data = solver()
    data._trade_efficiency_pending["room_1_1"] = datetime.now()
    k = sample(value=112)["key"]
    history = {k: {"verified_baseline": 117}}
    env["save_history"] = lambda value: history.update(value)
    repair = {
        "room": "room_1_1",
        "key": k,
        "metric": "blue",
        "before": 92,
        "kind": "repair",
        "original": ["吉星", "绮良", "鸿雪"],
    }
    env["_complete"](data, repair, sample(value=112), history)
    assert history[k]["verified_baseline"] == 117


def test_manual_lower_variant_promotes_high_reference_without_changing_setting():
    env = compiled_runtime()
    data = solver()
    manual = rule(mode="manual", baseline=112)
    env["config"].conf.trade_efficiency_rules = [manual]
    observed = sample(value=117)
    records = {}
    env["load_history"] = lambda: records
    env["save_history"] = lambda value: records.update(value)
    env["_snapshot"] = lambda *_: observed
    env["audit_when_idle"](data)
    assert not data.tasks
    assert manual.manual_percent == 112
    assert records[observed["key"]]["verified_baseline"] == 117
    data._trade_efficiency_pending["room_1_1"] = datetime.now()
    env["_snapshot"] = lambda *_: sample(roster=("吉星", "绮良", "鸿雪"), value=97)
    env["audit_when_idle"](data)
    assert data._trade_efficiency_repair["kind"] == "repair"
    assert data._trade_efficiency_repair["before"] == 97


def test_normal_audit_has_single_info_verdict():
    env = compiled_runtime()
    data = solver()
    setting = rule(related=())
    env["config"].conf.trade_efficiency_rules = [setting]
    current = sample(value=117, related={})
    history = {current["key"]: {"verified_baseline": 117}}
    env["load_history"] = lambda: history
    env["save_history"] = lambda value: history.update(value)
    env["_snapshot"] = lambda *_: current
    env["audit_when_idle"](data)
    infos = [event for event in env["logger"].events if event[0] == "INFO"]
    assert infos == [
        (
            "INFO",
            (
                "贸易站效率自检：%s %g%%（%s）",
                "room_1_1",
                117,
                "符合预期",
            ),
        )
    ]


def test_default_two_attempts_retries_once_then_ends_cycle():
    env = compiled_runtime()
    data = solver()
    setting = rule(related=(), retry_limit=2)
    env["config"].conf.trade_efficiency_rules = [setting]
    bad = sample(value=97, related={})
    history = {bad["key"]: {"verified_baseline": 117}}
    env["load_history"] = lambda: history
    env["save_history"] = lambda value: None
    env["_snapshot"] = lambda *_: bad.copy()

    env["audit_when_idle"](data)
    repair = data._trade_efficiency_repair
    assert repair["attempt"] == 1 and repair["retry_limit"] == 2
    assert len(data.tasks) == 1

    # first swap -> restore -> read, still 97: schedule second/last swap
    data.task = data.tasks.pop()
    env["on_arrangement_completed"](data, setting.room)
    data.task = data.tasks.pop()
    env["on_arrangement_completed"](data, setting.room)
    env["audit_when_idle"](data)
    assert data._trade_efficiency_repair["attempt"] == 2
    assert len(data.tasks) == 1

    # second swap -> restore -> read, still 97: finish this cycle, no loop
    data.task = data.tasks.pop()
    env["on_arrangement_completed"](data, setting.room)
    data.task = data.tasks.pop()
    env["on_arrangement_completed"](data, setting.room)
    env["audit_when_idle"](data)
    assert data._trade_efficiency_repair is None
    assert not data.tasks
    assert "_active_repair" not in history
    assert history[bad["key"]]["unresolved"] is False
    warnings = [args for level, args in env["logger"].events if level == "WARNING"]
    assert any("本轮结束" in args[0] and args[-2:] == (2, 2) for args in warnings)


def test_retry_limit_one_never_retries():
    env = compiled_runtime()
    data = solver()
    setting = rule(related=(), retry_limit=1)
    env["config"].conf.trade_efficiency_rules = [setting]
    bad = sample(value=97, related={})
    history = {bad["key"]: {"verified_baseline": 117}}
    env["load_history"] = lambda: history
    env["save_history"] = lambda value: None
    env["_snapshot"] = lambda *_: bad.copy()
    env["audit_when_idle"](data)
    data.task = data.tasks.pop()
    env["on_arrangement_completed"](data, setting.room)
    data.task = data.tasks.pop()
    env["on_arrangement_completed"](data, setting.room)
    env["audit_when_idle"](data)
    assert data._trade_efficiency_repair is None
    assert not data.tasks


def test_retry_success_on_second_attempt_stops_immediately():
    env = compiled_runtime()
    data = solver()
    setting = rule(related=(), retry_limit=3)
    env["config"].conf.trade_efficiency_rules = [setting]
    bad = sample(value=97, related={})
    good = sample(value=117, related={})
    history = {bad["key"]: {"verified_baseline": 117}}
    env["load_history"] = lambda: history
    env["save_history"] = lambda value: None
    env["_snapshot"] = lambda *_: bad.copy()
    env["audit_when_idle"](data)

    data.task = data.tasks.pop()
    env["on_arrangement_completed"](data, setting.room)
    data.task = data.tasks.pop()
    env["on_arrangement_completed"](data, setting.room)
    env["audit_when_idle"](data)
    assert data._trade_efficiency_repair["attempt"] == 2

    data.task = data.tasks.pop()
    env["on_arrangement_completed"](data, setting.room)
    data.task = data.tasks.pop()
    env["on_arrangement_completed"](data, setting.room)
    env["_snapshot"] = lambda *_: good.copy()
    env["audit_when_idle"](data)
    assert data._trade_efficiency_repair is None
    assert not data.tasks
    infos = [args for level, args in env["logger"].events if level == "INFO"]
    assert any("已恢复" in args[0] and args[-2:] == (2, 3) for args in infos)


def test_retry_exhaustion_allows_next_future_trigger():
    env = compiled_runtime()
    data = solver()
    setting = rule(related=(), retry_limit=1)
    env["config"].conf.trade_efficiency_rules = [setting]
    bad = sample(value=97, related={})
    history = {bad["key"]: {"verified_baseline": 117}}
    env["load_history"] = lambda: history
    env["save_history"] = lambda value: None
    env["_snapshot"] = lambda *_: bad.copy()
    env["audit_when_idle"](data)
    data.task = data.tasks.pop()
    env["on_arrangement_completed"](data, setting.room)
    data.task = data.tasks.pop()
    env["on_arrangement_completed"](data, setting.room)
    env["audit_when_idle"](data)
    assert data._trade_efficiency_repair is None
    env["mark_changed"](data, setting.room)
    env["audit_when_idle"](data)
    assert data._trade_efficiency_repair["attempt"] == 1
    assert len(data.tasks) == 1
