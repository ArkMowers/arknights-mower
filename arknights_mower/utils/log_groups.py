"""按日志来源模块派生实时日志的业务分组。

分组值通常是 docs/subsystems/ 下子系统说明的文件名去掉 .md；细分业务组
由 BUSINESS_GROUP_OWNERS 指向其所属子系统。前端 ui/src/utils/logGroups.js
按同一取值显示名称与颜色。调用方通过
extra={"log_group": ...} 指定的分组优先；调用方没有指定时，
log._build_log_record 用 group_for_pathname() 按 record.pathname 集中派生，
混合业务模块在调用点显式声明实际业务，路径映射继续作为兜底。

映射按前缀匹配，前缀越长越优先，因此具体模块可以覆盖它所在的目录。
未登记的模块返回 None，结构化记录不写 group 键。
"""

from __future__ import annotations

# 业务展示分组的规则仍由现有子系统说明负责。
BUSINESS_GROUP_OWNERS = {"clue": "base-scheduler", "credit-shop": "base-scheduler"}

# 有序映射表：包内相对路径前缀 -> 日志业务分组。
# 仓库根目录的入口模块（server.py、webview_ui.py）不在 arknights_mower 包内，
# 按文件名匹配；其余键都是包内相对路径。
LOG_GROUP_PREFIXES: tuple[tuple[str, str], ...] = (
    # 基建排班：排班求解、调度任务与心情计算
    ("solvers/base_schedule.py", "base-scheduler"),
    ("solvers/emergency.py", "base-scheduler"),
    ("solvers/base_mixin.py", "base-scheduler"),
    ("utils/scheduler_task.py", "base-scheduler"),
    ("utils/calculated_mood.py", "base-scheduler"),
    ("solvers/report.py", "base-scheduler"),
    ("solvers/trust_rotation.py", "base-scheduler"),
    # Mower 本地作战、日常与玩家信息
    ("solvers/operation.py", "local-operation"),
    ("solvers/player_info.py", "local-operation"),
    ("solvers/local_operation.py", "local-operation"),
    ("solvers/mail.py", "local-operation"),
    ("solvers/event_sign_in.py", "local-operation"),
    ("solvers/credit.py", "local-operation"),
    ("solvers/credit_fight.py", "local-operation"),
    ("solvers/mission.py", "local-operation"),
    ("solvers/skland.py", "local-operation"),
    # 森空岛养成数据同步独立于每日签到和仓库扫描
    ("solvers/cultivate_depot.py", "growth-planning"),
    # 识别、场景图与联网等待
    ("utils/recognize.py", "recognition"),
    ("utils/rapidocr.py", "recognition"),
    ("utils/scene.py", "recognition"),
    ("utils/graph.py", "recognition"),
    ("utils/matcher.py", "recognition"),
    ("utils/solver.py", "recognition"),
    ("utils/run_order_network.py", "recognition"),
    ("utils/network_adaptation.py", "recognition"),
    # 设备控制：设备后端目录、管理端通用设置与截图存储
    ("utils/device/", "device-control"),
    ("utils/manager_common.py", "device-control"),
    ("utils/screenshot.py", "device-control"),
    # 公开招募
    ("solvers/recruit.py", "recruitment"),
    # 线索搜集与交流
    ("solvers/clue_credit.py", "clue"),
    ("solvers/clue_gift.py", "clue"),
    ("solvers/shop.py", "credit-shop"),
    # 仓库识别
    ("solvers/depotREC.py", "depot-recognition"),
    # 资源更新：资源 OTA、资源包安装、版本检测与手动更新包
    ("utils/resource_ota.py", "resource-update"),
    ("utils/resource_pkg.py", "resource-update"),
    ("utils/resource_store.py", "resource-update"),
    ("utils/resource_update_job.py", "resource-update"),
    ("utils/resource_version.py", "resource-update"),
    ("utils/res_version.py", "resource-update"),
    ("utils/manual_update.py", "resource-update"),
    # 软件更新：发布检查、安装器、更新协调与下载代理；
    # MAA 核心与资源的安装器属于软件更新子系统
    ("utils/software_update.py", "software-update"),
    ("utils/software_update_package.py", "software-update"),
    ("utils/software_update_progress.py", "software-update"),
    ("utils/software_update_worker.py", "software-update"),
    ("utils/update.py", "software-update"),
    ("utils/update_notice.py", "software-update"),
    ("utils/update_runtime.py", "software-update"),
    ("utils/github_download.py", "software-update"),
    ("utils/maa_update.py", "software-update"),
    ("utils/maa_resource_update.py", "software-update"),
    # MAA 运行：桌面 worker、核心校验与备份回收
    ("utils/maa_runtime.py", "maa-runtime"),
    ("utils/maa_process.py", "maa-runtime"),
    ("utils/maa_backup.py", "maa-runtime"),
    ("utils/maa_check.py", "maa-runtime"),
    # MAA 集成：回调翻译、委托上报、脚本与任务参数
    ("utils/maa_callback.py", "maa-integration"),
    ("utils/maa_report.py", "maa-integration"),
    ("utils/maa_copilot.py", "maa-integration"),
    ("utils/maa_sss.py", "maa-integration"),
    ("utils/maa_stage_inventory.py", "maa-integration"),
    ("utils/maa_inventory.py", "maa-integration"),
    ("utils/maa_event_shop.py", "maa-integration"),
    # Web 访问：HTTP/WebSocket 服务、认证、日志推送与桌面入口
    ("utils/web_auth.py", "web-access"),
    ("utils/log_stream.py", "web-access"),
    ("server.py", "web-access"),
    ("webview_ui.py", "web-access"),
    # AI 助手
    ("agent/", "ai-assistant"),
)

# 匹配顺序：前缀越长越优先，避免目录级前缀覆盖更具体的模块。
_ORDERED_PREFIXES = tuple(
    sorted(LOG_GROUP_PREFIXES, key=lambda entry: len(entry[0]), reverse=True)
)
_PACKAGE_MARKER = "arknights_mower/"


def _match_prefix(relative: str) -> str | None:
    """按前缀顺序匹配包内相对路径；未命中时返回 None。"""
    for prefix, group in _ORDERED_PREFIXES:
        if relative.startswith(prefix):
            return group
    return None


def group_for_pathname(pathname: str | None) -> str | None:
    """返回 pathname 所属的日志业务分组；未登记时返回 None。

    record.pathname 通常是绝对路径，先统一分隔符，再取最后一个
    arknights_mower/ 之后的部分。已经是包内相对路径的调用直接匹配；
    仓库根目录的入口模块（server.py、webview_ui.py）不在包目录内，
    按文件名匹配。
    """
    if not pathname:
        return None
    normalized = str(pathname).replace("\\", "/")
    index = normalized.rfind(_PACKAGE_MARKER)
    if index >= 0:
        return _match_prefix(normalized[index + len(_PACKAGE_MARKER) :])
    return _match_prefix(normalized) or _match_prefix(normalized.rsplit("/", 1)[-1])
