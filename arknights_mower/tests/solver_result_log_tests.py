"""已确认业务结果保留完整可读日志，内部容器与点击坐标留在 DEBUG。"""

import csv
import importlib
import json
import logging
from copy import deepcopy
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from arknights_mower.tests import automatic_rescue_tests as rescue
from arknights_mower.tests.base_report_read_tests import (
    recording_solver as recording_solver,
)
from arknights_mower.tests.depot_scene_tests import offline_io as offline_io
from arknights_mower.tests.depot_scene_tests import scan as scan
from arknights_mower.tests.local_operation_inventory_tests import native as native
from arknights_mower.utils import config, log

rescue_offline = rescue.offline
rescue_solver = rescue.solver


@pytest.fixture(autouse=True)
def capture_only(monkeypatch, caplog):
    monkeypatch.setattr(log.logger, "handlers", [caplog.handler])
    monkeypatch.setattr(log.logger, "propagate", False)
    caplog.set_level(logging.DEBUG, logger=log.logger.name)


def infos(caplog):
    return [record for record in caplog.records if record.levelno == logging.INFO]


def messages(caplog):
    return [record.getMessage() for record in infos(caplog)]


def test_depot_scan_describes_every_confirmed_item_without_a_python_dictionary(
    scan, caplog
):
    assert scan.solver.run() is True

    result = next(
        record for record in infos(caplog) if "已识别2种物品" in record.getMessage()
    )
    assert result.getMessage() == (
        "仓库扫描：已识别2种物品\n应急理智顶液：3\n龙门币：100000000"
    )
    assert "已保存" not in result.getMessage()
    with scan.path.open(encoding="utf-8", newline="") as stream:
        rows = list(csv.reader(stream))
    assert json.loads(rows[-1][1]) == {"应急理智顶液": 3, "龙门币": 100000000}
    assert not any("{'" in text for text in messages(caplog))


def test_confirmed_empty_depot_is_readable_without_inventing_items(scan, caplog):
    scan.state.empty_tabs = {1, 2}

    assert scan.solver.run() is True

    assert "仓库扫描：两个分类均为空，未发现物品" in messages(caplog)
    assert scan.solver.结果字典 == {}


def test_report_is_announced_once_after_storage_with_zero_and_unread_fields(
    recording_solver, monkeypatch, caplog
):
    solver = recording_solver
    solver.report_res.update({"作战录像": 42, "赤金": 0, "龙门币订单": 1000})
    solver.find = Mock(return_value=True)
    solver.crop_report = Mock()
    from arknights_mower.utils import csv_utils

    append = csv_utils.append_dated_row

    def save(*args, **kwargs):
        assert not any("已保存" in text for text in messages(caplog))
        return append(*args, **kwargs)

    monkeypatch.setattr(csv_utils, "append_dated_row", save)

    assert solver.read_report() is True

    result = [text for text in messages(caplog) if "基报" in text and "已保存" in text]
    assert result == [
        "已保存 2026-10-02 的基报：\n作战录像：42 经验\n赤金制造价值：0 龙门币\n"
        "龙门币订单金额：1000 龙门币\n龙门币订单数：未读出\n合成玉：未读出\n"
        "合成玉订单数：未读出"
    ]
    result_record = next(
        record for record in infos(caplog) if "已保存" in record.getMessage()
    )
    assert result_record.log_event == {
        "type": "base-report",
        "date": "2026-10-02",
        "items": [
            {"name": "作战录像", "value": 42, "unit": "经验", "item": "中级作战记录"},
            {"name": "赤金制造价值", "value": 0, "unit": "龙门币", "item": "赤金"},
            {
                "name": "龙门币订单金额",
                "value": 1000,
                "unit": "龙门币",
                "item": "龙门币",
            },
            {"name": "龙门币订单数", "value": None, "unit": "笔", "item": "龙门币"},
            {"name": "合成玉", "value": None, "unit": "个", "item": "合成玉"},
            {"name": "合成玉订单数", "value": None, "unit": "笔", "item": "合成玉"},
        ],
    }
    assert solver._stored is True
    assert "{'" not in "\n".join(messages(caplog))
    with solver.record_path.open(encoding="gbk", newline="") as stream:
        row = next(csv.DictReader(stream))
    assert row["作战录像"] == "42" and row["赤金"] == "0"
    assert row["合成玉订单数量"] == "" and "合成玉订单数" not in row
    assert (
        "合成玉订单数量" in solver.report_res
        and "合成玉订单数" not in solver.report_res
    )


def test_report_log_preserves_read_counts_units_and_additional_stored_details(
    recording_solver, caplog
):
    solver = recording_solver
    readings = {
        "作战录像": 0,
        "赤金": 42,
        "龙门币订单": 0,
        "龙门币订单数": 0,
        "合成玉": 8,
        "合成玉订单数量": 1,
        "额外明细": 3,
    }
    solver.find = Mock(return_value=True)
    solver.crop_report = Mock(side_effect=lambda: solver.report_res.update(readings))

    assert solver.read_report() is True

    record = next(record for record in infos(caplog) if "已保存" in record.getMessage())
    assert record.getMessage() == (
        "已保存 2026-10-02 的基报：\n作战录像：0 经验\n赤金制造价值：42 龙门币\n"
        "龙门币订单金额：0 龙门币\n龙门币订单数：0 笔\n合成玉：8 个\n"
        "合成玉订单数：1 笔\n额外明细：3"
    )
    assert record.log_event["items"][5] == {
        "name": "合成玉订单数",
        "value": 1,
        "unit": "笔",
        "item": "合成玉",
    }
    assert record.log_event["items"][-1] == {
        "name": "额外明细",
        "value": 3,
        "unit": "",
        "item": "额外明细",
    }
    with solver.record_path.open(encoding="gbk", newline="") as stream:
        row = next(csv.DictReader(stream))
    assert {name: int(row[name]) for name in readings} == readings
    assert "合成玉订单数" not in row and solver.report_res == readings


def test_failed_report_storage_does_not_announce_saved_readings(
    recording_solver, monkeypatch, caplog
):
    from arknights_mower.utils import csv_utils

    recording_solver.report_res["赤金"] = 0
    monkeypatch.setattr(
        csv_utils, "append_dated_row", Mock(side_effect=PermissionError("occupied"))
    )

    assert recording_solver.record_report() is False

    assert not recording_solver._stored
    assert not any("已保存" in text for text in messages(caplog))
    assert not any(getattr(record, "log_event", None) for record in infos(caplog))


def test_native_drop_log_preserves_batch_quantities_and_receipt_idempotency(
    native, caplog
):
    native.record.save_inventory_counts({"采购凭证": 10, "固源岩": 7})
    native.reader.return_value = {"采购凭证": 3, "固源岩": 2}
    native.solver.current_batch_repeat_count = 6
    caplog.clear()

    native.solver._record_batch_drops()
    native.solver._record_batch_drops()

    assert messages(caplog) == [
        "本次Mower刷理智掉落结果已计入库存：采购凭证×3、固源岩×2"
    ]
    assert infos(caplog)[0].log_event == {
        "type": "operation-drops",
        "items": [{"name": "采购凭证", "count": 3}, {"name": "固源岩", "count": 2}],
    }
    assert native.record.get_inventory_counts() == {"采购凭证": 13, "固源岩": 9}
    assert native.reader.call_count == 2


@pytest.fixture
def signing_date(monkeypatch):
    module = importlib.import_module("arknights_mower.solvers.skland")
    monkeypatch.setattr(
        module,
        "datetime",
        SimpleNamespace(
            datetime=SimpleNamespace(now=lambda: datetime(2026, 11, 5, 12))
        ),
    )
    return "2026/11/05"


@pytest.mark.parametrize("failed_entry", [None, 0, 1])
def test_sign_results_follow_save_outcome_and_keep_status_and_account_groups(
    monkeypatch, caplog, tmp_path, signing_date, failed_entry
):
    module = importlib.import_module("arknights_mower.solvers.skland")
    from arknights_mower.utils import csv_utils

    solver = object.__new__(module.SKLand)
    solver.record_path = tmp_path / "skland.csv"
    solver._log_secrets = {"secret-token"}
    solver.reward = [
        {
            "nickName": "13800138000",
            "game": "明日方舟官服",
            "reward": "赤金×2",
            "status": "success",
            "code": 0,
        },
        {
            "nickname": "13800138000",
            "game": "终末地官服",
            "reward": "secret-token 已失效",
            "status": "failure",
            "code": 1000,
        },
    ]
    before = deepcopy(solver.reward)
    append = csv_utils.append_dated_row
    written = 0
    write_fails = failed_entry is not None

    def save(*args, **kwargs):
        nonlocal written
        assert not any(text.startswith("已保存 ") for text in messages(caplog))
        if written == failed_entry:
            raise PermissionError("occupied")
        result = append(*args, **kwargs)
        written += 1
        return result

    monkeypatch.setattr(csv_utils, "append_dated_row", save)

    assert solver.record_log() is True

    results = [text for text in messages(caplog) if "    账号 " in text]
    assert len(results) == 1
    result = results[0]
    assert result.count("    账号 138****8000：") == 1
    assert result.splitlines()[1] == "    账号 138****8000："
    assert result.splitlines()[2] == "        明日方舟官服：签到成功，赤金×2"
    assert result.splitlines()[3].startswith("        终末地官服：签到失败，")
    assert (
        "已失效" in result
        and "登录凭据失效" not in result
        and "token失效" not in result
    )
    if write_fails:
        assert (
            result.splitlines()[0]
            == f"{signing_date} 的森空岛签到记录保存失败，本次签到结果如下："
        )
        assert "记录未保存" not in result
        assert caplog.records.index(
            next(
                record for record in caplog.records if "写入失败" in record.getMessage()
            )
        ) < caplog.records.index(
            next(
                record for record in infos(caplog) if "    账号 " in record.getMessage()
            )
        )
    else:
        assert (
            result.splitlines()[0]
            == f"已保存 {signing_date} 的森空岛签到记录，共 2 条："
        )
    all_text = "\n".join(record.getMessage() for record in caplog.records)
    assert "secret-token" not in all_text
    assert "13800138000" not in all_text
    assert not any("{'" in text or "[{" in text for text in messages(caplog))
    assert any(text.startswith("已保存 ") for text in messages(caplog)) is (
        not write_fails
    )
    assert solver.reward == before
    assert solver.test_writecsv is (not write_fails)
    rows = []
    if solver.record_path.exists():
        with solver.record_path.open(encoding="gbk", newline="") as stream:
            rows = list(csv.reader(stream))
    assert len(rows) == (2 if failed_entry is None else failed_entry)
    if rows:
        assert rows[0][-2:] == ["success", "0"]


@pytest.mark.parametrize("game_id", [1, 3])
@pytest.mark.parametrize("code", [0, 1000])
def test_sign_response_status_reaches_saved_grouped_summary(
    monkeypatch, caplog, tmp_path, signing_date, game_id, code
):
    module = importlib.import_module("arknights_mower.solvers.skland")
    account = SimpleNamespace(
        account="13800138000",
        arknights_isCheck=game_id == 1,
        endfield_isCheck=game_id == 3,
        sign_in_bilibili=False,
        sign_in_official=True,
        sign_in_endfield_bilibili=False,
        sign_in_endfield_official=True,
    )
    role = {
        "gameId": game_id,
        "channelName": "官服",
        "uid": "offline-role",
        "roles": [{"roleId": "offline-role", "serverId": "offline-server"}],
    }
    rewards = (
        {"awards": [{"resource": {"name": "赤金"}, "count": 2}]}
        if game_id == 1
        else {
            "awardIds": [{"id": "reward-1"}],
            "resourceInfoMap": {"reward-1": {"name": "赤金", "count": 2}},
        }
    )
    response = {
        "code": code,
        "message": "offline-secret 已失效",
        "data": rewards,
    }
    monkeypatch.setattr(module.config, "conf", SimpleNamespace(skland_info=[account]))
    monkeypatch.setattr(module, "header", {})
    monkeypatch.setattr(module, "log", Mock(return_value="offline-secret"))
    monkeypatch.setattr(
        module,
        "get_cred_by_token",
        Mock(return_value={"cred": "offline-cred", "token": "offline-sign"}),
    )
    monkeypatch.setattr(module, "get_binding_list", Mock(return_value=[role]))
    monkeypatch.setattr(module, "get_sign_header", Mock(return_value={}))
    monkeypatch.setattr(
        module.requests,
        "post",
        Mock(return_value=SimpleNamespace(json=lambda: response)),
    )
    solver = module.SKLand()
    solver.record_path = tmp_path / "skland.csv"

    assert solver.start() is True

    assert solver.reward[0]["code"] == code
    assert solver.reward[0]["status"] == ("failure" if code else "success")
    result = next(text for text in messages(caplog) if "    账号 " in text)
    assert (
        result.splitlines()[0] == f"已保存 {signing_date} 的森空岛签到记录，共 1 条："
    )
    assert ("签到失败，" in result) is bool(code)
    assert ("签到成功，赤金×2" in result) is (not code)
    assert "登录凭据失效" not in result
    assert "offline-secret" not in result and "13800138000" not in result
    with solver.record_path.open(encoding="gbk", newline="") as stream:
        row = next(csv.reader(stream))
    assert row[-2:] == ["failure" if code else "success", str(code)]


@pytest.mark.parametrize(
    "entry,outcome",
    [
        ({"game": "明日方舟官服"}, "签到结果，未返回结果"),
        (
            {
                "game": "明日方舟官服",
                "reward": "上游原文已失效",
                "status": "success",
                "code": 1,
            },
            "签到结果，上游原文已失效",
        ),
    ],
)
def test_sign_summary_preserves_unknown_result_and_missing_account_fallback(
    caplog, tmp_path, signing_date, entry, outcome
):
    module = importlib.import_module("arknights_mower.solvers.skland")
    solver = module.SKLand()
    solver.record_path = tmp_path / "skland.csv"
    solver.reward = [deepcopy(entry)]

    assert solver.record_log() is True

    result = next(text for text in messages(caplog) if "    账号 " in text)
    assert result == (
        f"已保存 {signing_date} 的森空岛签到记录，共 1 条：\n"
        f"    账号 未标明账号：\n        明日方舟官服：{outcome}"
    )
    assert solver.reward == [entry]


def test_emergency_entry_names_every_trigger_without_changing_admission(
    rescue_solver, rescue_offline, monkeypatch, caplog
):
    rescue.setup_startup(rescue_solver)
    config.conf.automatic_rescue_enable = True
    monkeypatch.setattr(
        rescue.emergency,
        "native_opportunity",
        lambda *args, **kwargs: rescue.NativeProjection(None, True, "blocked"),
    )

    rescue_solver._emergency_startup()

    result = next(
        record for record in infos(caplog) if "启动自动救急：" in record.getMessage()
    )
    assert result.log_agents == rescue.PRIMARY
    assert all(f"[[operator:{name}]]" in result.getMessage() for name in rescue.PRIMARY)
    assert "['" not in result.getMessage()
    assert rescue_solver.emergency_state["phase"] == "staffing"
    rescue_solver._emergency_schedule_staffing.assert_not_called()


def test_emergency_queued_staffing_keeps_the_complete_ordered_plan_in_info(
    rescue_solver, rescue_offline, caplog
):
    state = rescue.make_episode(rescue_solver)
    state.update(staffing_complete=False, takeover_complete=False)
    rescue_solver.op_data.facility_states = {
        "room_1_1": {"facility": "manufacture"},
        "room_1_2": {"facility": "trade"},
    }
    rescue_solver.op_data.plan["room_1_3"][0].facility = "发电站"

    assert rescue_solver._emergency_schedule_staffing() is True

    task = rescue_solver.tasks[-1]
    result = next(
        record
        for record in infos(caplog)
        if "已生成救急换班任务，等待执行：" in record.getMessage()
    )
    assert [(room["id"], room["agents"]) for room in result.log_task["rooms"]] == list(
        task.plan.items()
    )
    assert all(
        f"{room['label']}：{'、'.join(room['agents'])}" in result.getMessage()
        for room in result.log_task["rooms"]
    )
    assert result.getMessage().startswith("已生成救急换班任务，等待执行：\n")
    assert "制造站 B101：陈" in result.getMessage()
    assert "贸易站 B102：槐琥" in result.getMessage()
    assert "发电站 B103：斥罪" in result.getMessage()
    assert "\nB201：结城理" in result.getMessage()
    snapshot = deepcopy(result.log_task)
    task.plan.clear()
    assert result.log_task == snapshot
    assert state["phase"] == "staffing"


def test_captcha_candidates_and_prepared_words_keep_the_real_click_order(
    monkeypatch, caplog
):
    module = importlib.import_module("arknights_mower.solvers.captcha_solver")
    solver = object.__new__(module.CaptchaClickSolver)
    solver.recog = SimpleNamespace(img=object())
    solver._title_text = ""
    solver._recognize_title = Mock(return_value="开门开")
    items = [
        {"word": "门", "coords": (0, 0, 20, 20)},
        {"word": "开", "coords": (20, 0, 40, 20)},
        {"word": "开", "coords": (40, 0, 60, 20)},
    ]
    solver._detect_click_items = Mock(return_value=items)
    solver.debug = False
    solver.tap = Mock()
    monkeypatch.setattr(module, "match_captcha_order", Mock(return_value=[2, 0, 1]))

    assert solver._do_detect() is False

    assert "识别到3个候选汉字：门、开、开" in messages(caplog)
    assert "准备按顺序点击：开 → 门 → 开" in messages(caplog)
    assert solver._click_order == [2, 0, 1]
    assert solver._phase == "click"
    assert not any("通过" in text for text in messages(caplog))
    assert not any("coords" in text or "[2, 0, 1]" in text for text in messages(caplog))
    expected = ["点击汉字：开（1/3）", "点击汉字：门（2/3）", "点击汉字：开（3/3）"]
    clicked = []

    def tap(position, *, interval):
        assert messages(caplog)[-1] == expected[len(clicked)]
        assert solver._click_idx == len(clicked)
        clicked.append((position, interval))

    solver.tap.side_effect = tap
    for _ in items:
        assert solver._do_click() is False
    assert [
        text for text in messages(caplog) if text.startswith("点击汉字：")
    ] == expected
    assert not any("点击 [" in text or "(50,10)" in text for text in messages(caplog))
    assert any(
        record.levelno == logging.DEBUG
        and "点击 [2]" in record.getMessage()
        and "(50,10)" in record.getMessage()
        and "[1/3]" in record.getMessage()
        for record in caplog.records
    )
    assert clicked == [((50, 10), 0.3), ((10, 10), 0.3), ((30, 10), 0.3)]
    assert solver.tap.call_args_list[0].args[0] == (50, 10)
    assert solver.tap.call_args_list[1].args[0] == (10, 10)
    assert solver.tap.call_args_list[2].args[0] == (30, 10)


@pytest.mark.parametrize(
    ("arrangement", "description", "verify_only", "task_line"),
    [
        (None, "", False, ""),
        (
            {"train": ["夜莺", "Current"]},
            "",
            False,
            "保留协助位换人任务，原定 2026-11-06 15:00:00 安排[[operator:夜莺]]进驻",
        ),
        (
            {},
            "泡泡 换入夜莺",
            False,
            "保留协助位换人任务，原定 2026-11-06 15:00:00 执行「泡泡 换入夜莺」",
        ),
        (
            {},
            "泡泡 复核协助位换人",
            True,
            "保留协助位换人复核任务，原定 2026-11-06 15:00:00 执行",
        ),
        (
            {"train": ["Current", "泡泡"]},
            "",
            False,
            "保留协助位换人任务，原定 2026-11-06 15:00:00 执行，换入干员未确认",
        ),
    ],
)
def test_training_read_failure_retains_status_and_readable_observed_facts(
    caplog, arrangement, description, verify_only, task_line
):
    from arknights_mower.solvers import mastery_reader as reader
    from arknights_mower.utils.scheduler_task import SchedulerTask, TaskTypes

    original_time = datetime(2026, 11, 6, 15)
    room = reader.RoomState(
        state="training",
        panel=reader.RoomPanel(
            operator_name="泡泡",
            skill_name="挨打",
            mastery_tier=1,
            countdown_state="failed",
        ),
        read_failed=True,
        slots_read=True,
        slots_reliable=False,
    )
    solver = SimpleNamespace(tasks=[])
    if arrangement is not None:
        task = SchedulerTask(
            time=original_time,
            task_type=TaskTypes.SWAP_SUPPORT,
            task_plan=deepcopy(arrangement),
            meta_data=description,
        )
        task.plan_key = "demo-plan"
        task.mastery_swap_verify_only = verify_only
        solver.tasks.append(task)

    for _ in range(2):
        assert reader._reconcile(solver, room, None, []) == (None, True)

    expected = [
        "训练室：本次未能确认训练状态",
        "训练位　读到[[operator:泡泡]]的「挨打」专精一，剩余时间读取失败",
        "协助位　未能确认进驻干员和心情",
    ]
    if task_line:
        expected.append(task_line)
    results = [
        record for record in infos(caplog) if record.getMessage().startswith("训练室：")
    ]
    assert len(results) == 2
    for result in results:
        assert result.getMessage().splitlines() == expected
        assert result.log_room == "train"
    if arrangement is None:
        assert solver.tasks == []
    else:
        assert len(solver.tasks) == 1 and solver.tasks[0] is task
        assert task.time == original_time
        assert task.plan == arrangement
        assert task.meta_data == description
    assert room.panel.countdown is None
    assert room.state == "training" and room.read_failed


@pytest.mark.parametrize("retimed", [False, True])
def test_confirmed_training_judgment_reports_actual_swap_timing(
    monkeypatch, caplog, retimed
):
    from arknights_mower.solvers import mastery_reader as reader
    from arknights_mower.utils.scheduler_task import SchedulerTask, TaskTypes

    original_time = datetime(2026, 11, 6, 15)
    new_time = datetime(2026, 11, 6, 16)
    room = reader.RoomState(
        "training",
        reader.RoomPanel(
            operator_name="泡泡",
            skill_name="挨打",
            mastery_tier=1,
            countdown=datetime(2026, 11, 6, 20),
            countdown_state="active",
        ),
    )
    active = {
        "id": "demo-plan",
        "status": "training",
        "char_name": "泡泡",
        "skill_name": "挨打",
        "skill_index": reader.resolve_panel_skill("泡泡", "挨打"),
    }
    swap = SchedulerTask(
        time=original_time,
        task_type=TaskTypes.SWAP_SUPPORT,
        task_plan={"train": ["夜莺", "Current"]},
    )
    swap.plan_key = active["id"]
    other_swap = SchedulerTask(
        time=original_time,
        task_type=TaskTypes.SWAP_SUPPORT,
        task_plan={"train": ["年", "Current"]},
    )
    other_swap.plan_key = "other-plan"
    solver = SimpleNamespace(tasks=[other_swap, swap])
    monkeypatch.setattr(reader, "_update_expiry", Mock())

    def recover_swap(solver, plan, room):
        if retimed:
            swap.time = new_time
        return True

    monkeypatch.setattr(reader, "_maybe_recover_swap", recover_swap)

    assert reader._reconcile(solver, room, active, [active]) == (None, True)

    expected = (
        "调整协助位换人任务，原定 2026-11-06 15:00:00，改为 2026-11-06 16:00:00"
        if retimed
        else "保留协助位换人任务，原定 2026-11-06 15:00:00"
    )
    result = next(record for record in infos(caplog) if record.log_room == "train")
    assert result.getMessage().splitlines()[-1] == (
        f"{expected} 安排[[operator:夜莺]]进驻"
    )
    assert solver.tasks[0] is other_swap and solver.tasks[1] is swap
    assert other_swap.time == original_time
    assert swap.time == (new_time if retimed else original_time)
