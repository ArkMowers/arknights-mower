"""全局运行配置中随排班文件携带的高级设置。"""

from arknights_mower.utils.config.conf import Conf

ADVANCED_SETTING_KEYS = (
    "product_switching",
    "drone_count_limit",
    "drone_interval",
    "reload_room",
    "resting_threshold",
    "version_update_resting_threshold",
    "version_update_threshold_advance_hours",
    "free_room",
    "experimental_dorm_logic",
    "dorm_order",
    "merge_interval",
    "group_rest_in_full_on_mood_gap",
    "group_mood_gap_max_extra_wait_hours",
    "fia_fool",
    "refresh_backup_plan_after_mood",
    "assistant_follows_schedule",
    "fia_threshold",
    "rescue_threshold",
    "favorite",
)


def export_advanced_settings(conf: Conf) -> dict:
    data = conf.model_dump()
    return {key: data[key] for key in ADVANCED_SETTING_KEYS}


def apply_advanced_settings(conf: Conf, settings: dict | None) -> Conf:
    """校验导入值，且只修改排班允许携带的字段。"""
    if settings is None:
        return conf
    unknown = settings.keys() - ADVANCED_SETTING_KEYS
    if unknown:
        raise ValueError(f"未知的高级设置：{', '.join(sorted(unknown))}")
    return Conf.model_validate({**conf.model_dump(), **settings})
