"""通过普通换班派发复核训练位缺卡后的源床、练度和候选名单。"""

import pickle
from datetime import timedelta
from unittest.mock import Mock

import pytest

from arknights_mower.tests import schedule_roster_tests, training_submission_tests
from arknights_mower.utils import schedule_roster
from arknights_mower.utils.operators import Operator
from arknights_mower.utils.scheduler_task import find_next_task

base = training_submission_tests.base
solver = training_submission_tests.solver
scheduler = training_submission_tests.scheduler
training_reader = training_submission_tests.training_reader
training_dispatch = training_submission_tests.training_dispatch
roster_path = schedule_roster_tests.roster_path


@pytest.fixture
def missing_card(training_dispatch, roster_path):
    instance, task, depot = training_dispatch
    # 房间读回反映已有驻员。选人只替换画面操作，保留实际候选和搜索失败路径。
    instance.get_agent_from_room = Mock(
        side_effect=lambda room, *args, **kwargs: [
            {"agent": name} for name in instance.op_data.get_current_room(room, True)
        ]
    )
    instance.detect_arrange_order = Mock(return_value=("等级", False))
    instance.profession_filter = Mock()
    instance._close_profession_filter = Mock()
    instance.choose_train = lambda agents, *, fast_mode, choose_error: (
        instance.choose_train_ope(agents[1], choose_error=choose_error)
    )
    instance.scan_agent = Mock(
        side_effect=base.AgentPageNotAdvanced("训练干员列表已到末尾")
    )
    return instance, task, depot


def test_failed_source_room_keeps_training_wait_after_same_resident_read(missing_card):
    instance, task, depot = missing_card
    data = instance.op_data
    source = "dormitory_1"
    trainee = Operator(
        "迷迭香", "", current_room=source, current_index=2, mood=9, time_stamp=task.time
    )
    data.add(trainee)
    task.plan = {
        "train": ["Current", trainee.name],
        source: ["Current", "Current", "深巡", "Current", "Current"],
        "dormitory_2": ["伺夜"],
    }
    original_time = task.time
    arrange_room = instance.agent_arrange_room
    visits = []

    def arrange(new_plan, room, plan, **kwargs):
        visits.append(room)
        if room == "train":
            return arrange_room(new_plan, room, plan, **kwargs)
        if room == source:
            raise base.RoomArrangementDeferred(
                room, base.AgentPageNotAdvanced("宿舍选人失败")
            )
        del plan[room]
        return new_plan

    instance.agent_arrange_room = arrange
    for _ in range(3):
        instance.task = task
        instance.infra_main()
    assert visits == ["train", source, "dormitory_2"]
    assert instance.scan_agent.call_count == 1
    assert set(task.plan) == {"train", source}
    assert find_next_task(instance.tasks) is depot

    task = pickle.loads(pickle.dumps(task))
    instance.tasks = [task, depot]
    for _ in range(3):
        # 每次宿舍复读都允许宿舍重试，但原床的迷迭香还没有离开。
        trainee.mood += 1
        trainee.time_stamp += timedelta(minutes=1)
        data.room_observations[source] += 1
        data.room_observations["train"] += 1
        instance._resume_failed_tasks()
        assert find_next_task([task]) is task
        instance.task = task
        instance.infra_main()
        assert visits[-1] == source
        assert instance.scan_agent.call_count == 1
        assert find_next_task(instance.tasks) is depot
    assert task.time == original_time
    trainee.current_room, trainee.current_index = "", -1
    instance._resume_failed_tasks()
    assert find_next_task([task]) is task
    instance.task = task
    instance.infra_main()
    assert visits[-1] == "train" and instance.scan_agent.call_count > 1
    assert task.time == original_time


@pytest.mark.parametrize("recovery", ["local_skill", "room_read"])
@pytest.mark.parametrize("shared_source_replacement", [False, True])
def test_named_card_without_dispatchable_source_keeps_both_recovery_paths(
    missing_card,
    roster_path,
    bundled_mastery_skills,
    recovery,
    shared_source_replacement,
):
    instance, task, depot = missing_card
    data = instance.op_data
    data.add(Operator("能天使", "", current_room="dormitory_1", current_index=2))
    task.plan = {"train": ["Current", "能天使"]}
    if shared_source_replacement:
        # 克莱门莎还在训练位，这个源床替换本身也依赖训练室。
        task.plan["dormitory_1"] = [
            "Current",
            "Current",
            "克莱门莎",
            "Current",
            "Current",
        ]
    original_time = task.time
    schedule_roster_tests.write_training_roster(roster_path, level=6, masteries=(0,))
    instance.infra_main()
    attempts = instance.scan_agent.call_count
    assert attempts > 1 and find_next_task(instance.tasks) is depot
    assert "基础技能仅 6 级" in task.execution_failure["reason"]
    task = pickle.loads(pickle.dumps(task))
    instance.task, instance.tasks = depot, [task, depot]
    schedule_roster_tests.write_training_roster(roster_path, level=None)
    for _ in range(3):
        instance._resume_failed_tasks()
        assert find_next_task(instance.tasks) is depot
    if recovery == "room_read":
        data.room_observations["train"] += 1
    else:
        schedule_roster_tests.write_training_roster(roster_path)
    instance._resume_failed_tasks()
    assert find_next_task([task]) is task
    instance.task = task
    instance.infra_main()
    assert instance.scan_agent.call_count > attempts and task.time == original_time


@pytest.mark.parametrize(
    "change", ["source_plan", "train_plan", "in_train", "local_skill"]
)
def test_named_source_wait_resumes_on_relevant_changes(
    missing_card, roster_path, bundled_mastery_skills, change
):
    instance, task, _ = missing_card
    data = instance.op_data
    trainee = Operator("能天使", "", current_room="dormitory_1", current_index=2)
    data.add(trainee)
    task.plan = {
        "train": ["Current", trainee.name],
        "dormitory_1": ["Current", "Current", "深巡", "Current", "Current"],
    }
    schedule_roster_tests.write_training_roster(roster_path, level=6, masteries=(0,))
    instance.infra_main()
    assert instance.scan_agent.call_count == 1
    task.plan["dormitory_1"][3] = "伺夜"
    schedule_roster_tests.write_training_roster(roster_path, level=5)
    instance._resume_failed_tasks()
    assert "train" in instance._blocked_arrangement_rooms(task)

    if change == "source_plan":
        task.plan["dormitory_1"][2] = "杜林"
    elif change == "train_plan":
        task.plan["train"][1] = "迷迭香"
    elif change == "in_train":
        previous = data.get_current_operator("train", 1)
        previous.current_room, previous.current_index = "", -1
        trainee.current_room, trainee.current_index = "train", 1
    else:
        schedule_roster_tests.write_training_roster(roster_path, masteries=(2,))
    instance._resume_failed_tasks()
    assert "train" not in instance._blocked_arrangement_rooms(task)


@pytest.mark.parametrize("change", ["added_to_empty", "removed", "slot_filled"])
def test_free_uses_the_scanned_candidates_for_the_retained_task(
    missing_card, monkeypatch, change
):
    instance, task, depot = missing_card
    data = instance.op_data
    previous = data.get_current_operator("train", 1)
    previous.current_room, previous.current_index, previous.mood = "", -1, 24
    task.plan = {"train": ["Current", "Free"]}
    task.backup_retention_releases = ["砾"]
    for name, mood in (("芬", 6), ("香草", 12), ("砾", 5)):
        if name != "砾" and change == "added_to_empty":
            mood = 24
        data.add(Operator(name, "", mood=mood, time_stamp=task.time))
    monkeypatch.setattr(
        schedule_roster,
        "get_path",
        Mock(side_effect=AssertionError("Free 不读取具名干员的练度")),
    )
    original_time = task.time
    instance.infra_main()
    expected = [] if change == "added_to_empty" else ["芬", "香草"]
    assert instance.scan_agent.call_args.args[0] == expected
    attempts = instance.scan_agent.call_count
    assert attempts > 0 and find_next_task(instance.tasks) is depot

    task = pickle.loads(pickle.dumps(task))
    instance.tasks, instance.task = [task, depot], task
    if expected:
        data.operators["芬"].mood = 15
        assert instance.get_free_list([]) == ["香草", "芬"]
    instance.task = depot
    assert "砾" in instance.get_free_list([])
    for _ in range(3):
        data.room_observations["train"] += 1
        instance._resume_failed_tasks()
        assert instance.task is depot and find_next_task(instance.tasks) is depot
    if change == "added_to_empty":
        data.operators["芬"].mood = 7
    elif change == "removed":
        data.operators["芬"].mood = 24
    else:
        previous.current_room, previous.current_index = "train", 1
    instance._resume_failed_tasks()
    assert find_next_task([task]) is task
    instance.task = task
    instance.infra_main()
    assert task.time == original_time
    if change == "slot_filled":
        assert task not in instance.tasks and instance.scan_agent.call_count == attempts
    else:
        assert instance.scan_agent.call_count > attempts
        assert instance.scan_agent.call_args.args[0] == (
            ["芬"] if change == "added_to_empty" else ["香草"]
        )
