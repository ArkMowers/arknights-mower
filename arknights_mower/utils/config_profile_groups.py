"""Selectable settings and persistent-data groups for saved configurations."""

CONF_GROUPS = {
    "device": set(
        "adb custom_screenshot device droidcast fix_mumu12_adb_disconnect maa_adb_path mumu12IPC package_type simulator tap_to_launch_game touch_method".split()
    ),
    "runtime": set(
        "close_simulator_when_idle exit_game_when_idle low_frame_rate_mode performance_mode return_home_when_idle screenshot_interval selection_poll_interval selection_transition_timeout start_automatically waiting_scene".split()
    ),
    "daily": set(
        "check_mail_enable mail_skip_clear_read maa_depot_enable maa_enable maa_gap maa_mail maa_mining maa_orundum maa_recruit maa_specialaccess report_enable sign_in skland_enable".split()
    ),
    "trust": set(
        "trust_rotation_enable trust_rotation_interval trust_rotation_prefer_low trust_rotation_threshold".split()
    ),
    "recruit": set(
        "recruit_auto_5 recruit_auto_only5 recruit_enable recruit_gap recruit_robot recruitment_permit".split()
    ),
    "credit": set(
        "clue_credit_on_demand credit_fight credit_shop_by_value credit_shop_value_threshold maa_credit_fight maa_mall_blacklist maa_mall_buy maa_mall_enable maa_mall_ignore_blacklist_when_full maa_mall_mode maa_mall_only_buy_discount maa_mall_reserve_max_credit visit_friend_enable visit_friend_mode visit_friend".split()
    ),
    "clue": {"enable_party", "leifeng_mode"},
    "weekly_plan": set(
        "ap_fallback maa_eat_stone maa_penguin_id maa_report_to_penguin maa_report_to_yituliu maa_stage_inventory_enable maa_stage_limit_rules maa_stage_ratio_rules maa_weekly_plan maa_yituliu_id medicine_expire_days stage_plan_enable stage_plan_runner".split()
    ),
    "maa": set(
        "maa_auto_check_update maa_auto_update maa_conn_preset maa_mirrorchyan_token maa_path maa_resource_auto_check_update maa_resource_auto_update maa_restore_theme maa_restore_theme_enable maa_touch_option maa_update_channel".split()
    ),
    "long": set(
        "maa_long_task_type maa_rcl_theme maa_rg_enable maa_rg_sleep_max maa_rg_sleep_min maa_rg_theme rcl reclamation_algorithm rogue secret_front sss".split()
    ),
    "accounts": {"skland_info"},
    "notifications": set(
        "account custom_smtp_server mail_enable mail_subject notification_level pass_code recipient timezone_offset".split()
    ),
    "assistant": set(
        "ai_base_url ai_custom_key ai_deepseek_model ai_key ai_model ai_type".split()
    ),
    "appearance": {"theme", "webview"},
    "maintenance": set(
        "depot_history_keep depot_history_limit hot_update resource_update screenshot screenshot_archive_limit_mb".split()
    ),
    "rescue_plan": {"automatic_rescue_enable"},
    "base": set(
        "assistant_follows_schedule dorm_isolation enable_mastery favorite fia_fool fia_threshold free_blacklist free_room group_mood_gap_exclusions group_mood_gap_max_extra_wait_hours group_mood_gap_threshold_minutes group_rest_in_full_on_mood_gap merge_interval product_switching rescue_threshold resting_threshold right_side_room_order swap_contact_train test_mood_calculation version_update_resting_threshold version_update_threshold_advance_hours".split()
    ),
    "runorder": {"run_order_delay", "run_order_grandet_mode"},
    "drone": {"drone_count_limit", "drone_interval", "drone_room"},
    "workshop": set(
        "book_operators fodder_operators growth_crafting_order t5_operators workshop_auto_active workshop_deer_fodder workshop_generation workshop_manual_backup workshop_manual_revision workshop_manual_settings workshop_manual_settings_revision workshop_min_bonus workshop_preset_migrated workshop_protect_t2_device_rock workshop_settings".split()
    ),
}

CONFIG_FILE_GROUPS = {
    "plan.json": "normal_plan",
    "rescue_plan.json": "rescue_plan",
    "growth_plan.json": "growth",
    "workshop_preset.json": "workshop",
    "weekly_plans.yml": "weekly_plan",
    "yituliu_sync.json": "accounts",
    "recycling_report/state.json": "recycling_history",
}

_DEFINITIONS = (
    (
        "连接与运行",
        "device",
        "设备与游戏连接",
        "整组保留设备身份、路径、截图与触控方式、游戏及启动参数",
    ),
    ("连接与运行", "runtime", "运行参数", "性能、采样与等待、自动启动及空闲动作"),
    ("任务配置", "base", "基建调度", "换班、心情、菲亚梅塔及基建调度规则"),
    ("任务配置", "runorder", "跑单", "跑单间隔与插拔策略"),
    ("任务配置", "drone", "无人机加速", "无人机使用房间、间隔及保留数量"),
    ("任务配置", "clue", "线索", "线索赠送与交流规则"),
    ("任务配置", "trust", "信赖轮换", "信赖轮换开关、间隔及筛选规则"),
    ("任务配置", "daily", "日常任务", "日常任务开关与执行间隔"),
    ("任务配置", "recruit", "公开招募", "招募星级、机器人及许可保留规则"),
    ("任务配置", "credit", "访友与信用", "访友、信用获取及商店购买规则"),
    (
        "任务配置",
        "weekly_plan",
        "刷理智与周计划",
        "关卡、理智药、库存选关规则、全部周计划及当前选中方案",
    ),
    ("任务配置", "maa", "MAA 核心", "MAA 安装路径、更新、资源及控制方式"),
    ("任务配置", "long", "长任务", "集成战略、生息演算及其他长任务参数"),
    (
        "任务配置",
        "workshop",
        "加工与专精参数",
        "加工干员、材料保护、自动加工与手动加工配置",
    ),
    ("排班", "normal_plan", "正常排班", "正常主表、副表、房间与排班规则"),
    ("排班", "rescue_plan", "救急排班", "自动救急开关、救急主表与副表"),
    ("Mower 设置", "accounts", "森空岛账号与同步", "森空岛账号与一图流同步配置"),
    ("Mower 设置", "notifications", "邮件通知", "发信账号、收件人、邮件服务及通知规则"),
    ("Mower 设置", "assistant", "AI 模型服务", "AI 服务地址、模型与密钥"),
    (
        "Mower 设置",
        "appearance",
        "界面与窗口",
        "主题与窗口偏好；保留本机访问端口、令牌和托盘设置",
    ),
    ("Mower 设置", "maintenance", "更新与保留规则", "资源更新、截图与库存历史保留规则"),
    (
        "Mower 设置",
        "other_settings",
        "其他设置",
        "未归入其他项目的配置字段与附加配置文件",
    ),
    ("数据", "inventory", "材料库存", "材料数量、更新时间、扣减凭证与库存 CSV 快照"),
    ("数据", "operators", "干员与设施快照", "森空岛干员练度、设施与玩家快照"),
    ("数据", "growth", "养成目标", "已保存的干员养成目标"),
    ("数据", "mastery", "专精计划", "专精计划、执行状态及对应通知记录"),
    ("数据", "mastery_routes", "专精路线", "职业专精辅助路线与默认选择"),
    ("数据", "recycling", "回收材料估值", "回收站材料估值设置"),
    ("历史记录", "mood_history", "心情历史", "干员心情与换班记录"),
    ("历史记录", "trading_history", "贸易历史", "贸易站订单收益记录"),
    ("历史记录", "operation_history", "作战历史", "关卡作战、掉落与耗时记录"),
    (
        "历史记录",
        "recycling_history",
        "回收历史",
        "回收站收取记录、上报标识与上传进度",
    ),
    ("历史记录", "report_history", "基报历史", "已保存的基建报告"),
    ("历史记录", "skland_history", "签到历史", "森空岛签到记录"),
    ("历史记录", "growth_history", "养成历史", "养成计划完成统计"),
    ("历史记录", "other_history", "其他历史", "旧日志及未归入其他项目的数据库表"),
)

GROUPS = [
    {"key": key, "label": label, "description": description, "section": section}
    for section, key, label, description in _DEFINITIONS
]
