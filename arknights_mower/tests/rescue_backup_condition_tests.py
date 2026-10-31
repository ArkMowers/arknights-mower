"""救急条件副表退役保持其他副表与原始文档。"""

from copy import deepcopy

from arknights_mower.utils.config.plan import (
    PlanModel,
    contains_retired_rescue_condition,
    retire_rescue_backups,
)


def test_nested_actual_call_is_retired_without_rewriting_other_conditions():
    trigger = {
        "left": {"left": "op_data.rescue_needed()", "operator": "==", "right": "True"},
        "operator": "and",
        "right": "True",
    }
    raw = {
        "plan1": {},
        "backup_plans": [
            {"name": "old", "trigger": trigger},
            {
                "name": "keep",
                "trigger": {
                    "left": "op_data.group_min_mood('组')",
                    "operator": "<",
                    "right": "10",
                },
            },
        ],
    }
    before = deepcopy(raw)
    result, indices = retire_rescue_backups(raw)
    assert indices == {1: 0}
    assert result["backup_plans"] == raw["backup_plans"][1:]
    assert raw == before
    assert [backup.name for backup in PlanModel(**raw).backup_plans] == ["keep"]


def test_quoted_text_and_other_object_calls_do_not_retire_backups():
    for value in [
        "'op_data.rescue_needed()'",
        "other.rescue_needed()",
        "op_data.rescue_needed",
        "invalid(",
    ]:
        assert not contains_retired_rescue_condition(value)
    assert contains_retired_rescue_condition("not op_data.rescue_needed() or True")


def test_snapshot_task_conditions_remap_by_names_and_retire_only_derived_shifts():
    from arknights_mower.utils.config.plan import migrate_backup_tasks
    from arknights_mower.utils.scheduler_task import SchedulerTask, TaskTypes

    backup = SchedulerTask(
        task_type=TaskTypes.SELF_CORRECTION, task_plan={"central": ["阿米娅"]}
    )
    backup.backup_shift_conditions = [True, False]
    special = SchedulerTask(task_type=TaskTypes.FIAMMETTA, meta_data="歌蕾蒂娅")
    mapped = migrate_backup_tasks([backup, special], ["one", "two"], ["two", "one"], {})
    assert mapped[0].backup_shift_conditions == [False, True]
    assert (
        len(migrate_backup_tasks([backup, special], [], ["two"], {1: 0}, retired=True))
        == 1
    )
    assert backup.backup_shift_conditions == [True, False]
