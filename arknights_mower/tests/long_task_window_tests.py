from datetime import datetime, timedelta

import pytest
from pydantic import ValidationError

from arknights_mower.utils.config.conf import Conf
from arknights_mower.utils.long_task_windows import long_task_window


def moment(value):
    return datetime.strptime("2026-11-" + value, "%Y-%m-%d %H:%M")


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


def test_editing_enabled_windows_wakes_idle_scheduler_only_after_changed_save(
    monkeypatch,
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
    edit = {"maa_long_task_extra_windows": [{"start": "13:00", "end": "16:00"}]}
    workshop_config.save_user_config(edit)
    workshop_config.save_user_config(edit)
    wake.assert_called_once()
