from datetime import datetime, timedelta

import pytest
from pydantic import ValidationError

from arknights_mower.utils.config.conf import Conf
from arknights_mower.utils.long_task_windows import long_task_schedule, long_task_window


def moment(value):
    return datetime.strptime("2026-11-" + value, "%Y-%m-%d %H:%M")


def test_adjacent_different_tasks_keep_their_own_cutoff_and_next_opening():
    conf = Conf(
        maa_rg_enable=1,
        maa_long_task_type="rogue",
        maa_long_task_weekly_windows=[
            {"start": "22:00", "end": "02:00", "weekdays": [6]},
            {"start": "02:00", "end": "05:00", "weekdays": [0], "task_type": "sss"},
        ],
    )
    assert long_task_schedule(conf, moment("23 01:00")) == (
        "rogue",
        moment("23 02:00"),
        moment("23 02:00"),
    )
    assert long_task_schedule(conf, moment("23 02:00")) == (
        "sss",
        moment("23 05:00"),
        moment("29 22:00"),
    )
    assert (
        long_task_schedule(conf.updated({"maa_rg_enable": 0}), moment("23 02:00"))[0]
        is None
    )


def test_default_type_changes_cannot_create_cross_week_conflicts():
    conf = Conf(
        maa_long_task_type="rogue",
        maa_long_task_weekly_windows=[
            {"start": "22:00", "end": "02:00", "weekdays": [6]},
            {"start": "01:00", "end": "03:00", "weekdays": [0], "task_type": "rogue"},
        ],
    )
    assert long_task_window(conf, moment("23 01:00"))[0] == moment("23 03:00")
    with pytest.raises(ValidationError, match="大型任务"):
        conf.updated({"maa_long_task_type": "sss"})


def test_conflicting_windows_do_not_replace_the_saved_plan(monkeypatch):
    from unittest.mock import Mock

    from arknights_mower.utils import workshop_config

    saved = Conf(maa_rg_enable=1, workshop_preset_migrated=True)
    persist = Mock()
    monkeypatch.setattr(workshop_config.config, "conf", saved)
    monkeypatch.setattr(workshop_config, "save_conf", persist)
    with pytest.raises(ValidationError, match="大型任务"):
        workshop_config.save_user_config(
            {
                "maa_long_task_weekly_windows": [
                    {"start": "08:00", "end": "12:00", "weekdays": [0]},
                    {
                        "start": "11:00",
                        "end": "14:00",
                        "weekdays": [0],
                        "task_type": "sss",
                    },
                ]
            }
        )
    persist.assert_not_called()
    assert workshop_config.config.conf is saved


@pytest.mark.parametrize(
    "now,cutoff,opening",
    [
        ("18 01:59", "18 02:00", "18 08:00"),
        ("18 02:00", "18 02:00", "18 08:00"),
        ("18 08:00", "18 13:00", "18 22:00"),
        ("18 12:59", "18 13:00", "18 22:00"),
        ("18 13:00", "18 13:00", "18 22:00"),
        ("18 23:00", "19 02:00", "19 08:00"),
    ],
)
def test_daily_windows_merge_overlap_and_adjacent_overnight(now, cutoff, opening):
    conf = Conf(
        maa_rg_sleep_max="08:00",
        maa_rg_sleep_min="10:00",
        maa_long_task_extra_windows=[
            {"start": "22:00", "end": "0:00"},
            {"start": "0:00", "end": "02:00"},
            {"start": "09:30", "end": "12:00"},
            {"start": "12:00", "end": "13:00"},
        ],
    )
    assert long_task_window(conf, moment(now)) == (moment(cutoff), moment(opening))


@pytest.mark.parametrize("extra_end", ["08:00", "18:00"])
def test_equal_times_or_contiguous_full_coverage_allow_all_day(extra_end):
    conf = Conf(
        maa_rg_sleep_max="18:00",
        maa_rg_sleep_min="08:00",
        maa_long_task_extra_windows=[{"start": "08:00", "end": extra_end}],
    )
    now = moment("18 14:00")
    assert long_task_window(conf, now) == (now + timedelta(days=1), None)


def test_single_window_round_trips_with_additional_windows():
    legacy = Conf(maa_rg_sleep_max="9:00", maa_rg_sleep_min="10:00")
    now = moment("18 14:00")
    assert long_task_window(legacy, now) == (now, moment("19 09:00"))
    saved = legacy.updated(
        {"maa_long_task_extra_windows": [{"start": "13:00", "end": "16:00"}]}
    )
    assert long_task_window(Conf(**saved.model_dump()), now) == (
        moment("18 16:00"),
        moment("19 09:00"),
    )
    with pytest.raises(ValidationError):
        legacy.updated(
            {"maa_long_task_extra_windows": [{"start": "25:01", "end": "1:00"}]}
        )


@pytest.mark.parametrize(
    "now,cutoff,opening",
    [
        ("16 07:59", "16 07:59", "16 08:00"),
        ("16 08:00", "16 14:00", "20 10:00"),
        ("16 11:00", "16 14:00", "20 10:00"),
        ("16 14:00", "16 14:00", "20 10:00"),
        ("17 10:00", "17 10:00", "20 10:00"),
    ],
)
def test_weekly_windows_union_only_days_with_shared_time(now, cutoff, opening):
    conf = Conf(
        maa_long_task_weekly_windows=[
            {"start": "08:00", "end": "11:00", "weekdays": [0]},
            {"start": "10:00", "end": "13:00", "weekdays": [0, 4]},
            {"start": "13:00", "end": "14:00", "weekdays": [0]},
        ],
    )
    assert long_task_window(conf, moment(now)) == (moment(cutoff), moment(opening))


@pytest.mark.parametrize("now", ["22 23:00", "23 01:00", "23 02:00"])
def test_sunday_overnight_merges_into_monday_across_week_boundary(now):
    conf = Conf(
        maa_long_task_weekly_windows=[
            {"start": "22:00", "end": "02:00", "weekdays": [6]},
            {"start": "01:00", "end": "03:00", "weekdays": [0]},
        ],
    )
    assert long_task_window(conf, moment(now)) == (
        moment("23 03:00"),
        moment("29 22:00"),
    )


def test_overnight_tail_does_not_require_selecting_the_next_day():
    conf = Conf(
        maa_long_task_weekly_windows=[
            {"start": "22:00", "end": "02:00", "weekdays": [4]},
        ],
    )
    assert long_task_window(conf, moment("21 01:00")) == (
        moment("21 02:00"),
        moment("27 22:00"),
    )
    assert long_task_window(conf, moment("21 02:00")) == (
        moment("21 02:00"),
        moment("27 22:00"),
    )


@pytest.mark.parametrize("weekdays", [[2], list(range(7)), []])
def test_equal_times_are_all_day_only_on_selected_weekdays(weekdays):
    conf = Conf(
        maa_long_task_weekly_windows=[
            {"start": "8:00", "end": "08:00", "weekdays": weekdays},
        ],
    )
    now = moment("18 02:00")
    if weekdays == [2]:
        assert long_task_window(conf, now) == (moment("19 00:00"), moment("25 00:00"))
    elif weekdays:
        assert long_task_window(conf, now) == (now + timedelta(days=1), None)
    else:
        assert long_task_window(conf, now) == (now, None)


def test_explicit_empty_weekly_plan_does_not_fall_back_to_daily_windows():
    legacy = Conf(maa_rg_sleep_max="08:00", maa_rg_sleep_min="13:00")
    paused = legacy.updated({"maa_long_task_weekly_windows": []})
    now = moment("18 09:00")
    assert long_task_window(legacy, now) == (moment("18 13:00"), moment("19 08:00"))
    assert long_task_window(Conf(**paused.model_dump()), now) == (now, None)


def test_continuous_days_keep_execution_limit_without_creating_extra_openings():
    conf = Conf(
        maa_long_task_weekly_windows=[
            {"start": "00:00", "end": "00:00", "weekdays": [0, 1, 2]},
        ],
    )
    assert long_task_window(conf, moment("16 04:00")) == (
        moment("17 04:00"),
        moment("23 00:00"),
    )


@pytest.mark.parametrize("days", [[-1], [7], [True], ["2"]])
def test_invalid_weekday_is_rejected_before_saving(days):
    with pytest.raises(ValidationError, match="weekdays"):
        Conf(
            maa_long_task_weekly_windows=[
                {"start": "08:00", "end": "10:00", "weekdays": days}
            ]
        )


@pytest.mark.parametrize(
    "edit",
    [
        {"maa_long_task_extra_windows": [{"start": "13:00", "end": "16:00"}]},
        {
            "maa_long_task_weekly_windows": [
                {"start": "13:00", "end": "16:00", "weekdays": [2]}
            ]
        },
    ],
)
def test_editing_enabled_windows_wakes_idle_scheduler_only_after_changed_save(
    monkeypatch,
    edit,
):
    from unittest.mock import Mock

    from arknights_mower.utils import workshop_config

    monkeypatch.setattr(
        workshop_config.config,
        "conf",
        Conf(maa_rg_enable=True, workshop_preset_migrated=True),
    )
    monkeypatch.setattr(workshop_config.config, "save_conf", Mock())
    wake = Mock()
    monkeypatch.setattr(workshop_config, "_wake_scheduler_if_running", wake)
    workshop_config.save_user_config(edit)
    workshop_config.save_user_config(edit)
    wake.assert_called_once()


def test_window_edits_stay_quiet_until_automatic_execution_is_enabled(monkeypatch):
    from unittest.mock import Mock

    from arknights_mower.utils import workshop_config

    monkeypatch.setattr(
        workshop_config.config,
        "conf",
        Conf(maa_rg_enable=0, workshop_preset_migrated=True),
    )
    monkeypatch.setattr(workshop_config.config, "save_conf", Mock())
    wake = Mock()
    monkeypatch.setattr(workshop_config, "_wake_scheduler_if_running", wake)
    workshop_config.save_user_config(
        {"maa_long_task_type": "sss", "maa_long_task_weekly_windows": []}
    )
    workshop_config.save_user_config({"maa_rg_enable": 1})
    wake.assert_not_called()
    workshop_config.save_user_config(
        {
            "maa_long_task_weekly_windows": [
                {"start": "11:00", "end": "12:00", "weekdays": [0]}
            ]
        }
    )
    wake.assert_called_once()
