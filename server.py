#!/usr/bin/env python3
import datetime
import json
import mimetypes
import os
import subprocess
import time
from functools import wraps
from io import BytesIO
from pathlib import Path
from threading import RLock, Thread

from flask import Flask, abort, request, send_file, send_from_directory
from flask_cors import CORS
from flask_sock import Sock
from werkzeug.exceptions import NotFound
from werkzeug.security import safe_join

from arknights_mower import __system__
from arknights_mower.solvers.record import clear_data, load_state, save_state
from arknights_mower.utils import config
from arknights_mower.utils.csv_utils import parse_cell_num, read_dicts
from arknights_mower.utils.datetime import get_server_time
from arknights_mower.utils.log import logger
from arknights_mower.utils.maa_check import (
    MAA_CHECK_TIMEOUT,
    maa_check_command,
    maa_check_timeout_result,
    parse_maa_check_output,
)
from arknights_mower.utils.operators import Operators, build_global_plan
from arknights_mower.utils.path import get_path
from arknights_mower.views.db_admin import db_admin_bp
from arknights_mower.views.mastery import mastery_bp
from arknights_mower.views.task import set_mower_thread, task_bp

mimetypes.add_type("text/html", ".html")
mimetypes.add_type("text/css", ".css")
mimetypes.add_type("application/javascript", ".js")

app = Flask(__name__, static_folder="ui/dist", static_url_path="")
sock = Sock(app)
CORS(app)


@app.errorhandler(500)
def handle_500(e):
    import traceback

    return {"error": str(e), "traceback": traceback.format_exc()}, 500


tmp_dir = get_path("@app/tmp")
tmp_dir.mkdir(parents=True, exist_ok=True)

if token := config.conf.webview.token:
    app.token = token

mower_thread = None
log_lines = []
ws_connections = []


def _mower_busy_response():
    """mower 正在运行任务时返回 409 拒绝；空闲返回 None。"""
    from arknights_mower.__main__ import base_scheduler

    if (
        mower_thread
        and mower_thread.is_alive()
        and base_scheduler
        and not base_scheduler.sleeping
    ):
        return {"ok": False, "message": "mower 正在运行任务，请稍后再试"}, 409
    return None


maa_check_job = {
    "id": None,
    "process": None,
    "status": "idle",
    "message": "",
    "started_at": None,
}
maa_check_lock = RLock()


def _collect_maa_check_result():
    with maa_check_lock:
        process = maa_check_job.get("process")
        if process is None:
            return

        if process.poll() is None:
            started_at = maa_check_job.get("started_at")
            if started_at and time.monotonic() - started_at > MAA_CHECK_TIMEOUT:
                process.kill()
                try:
                    process.communicate(timeout=1)
                except Exception:
                    pass
                result = maa_check_timeout_result(MAA_CHECK_TIMEOUT)
                maa_check_job.update(
                    {
                        "process": None,
                        "status": result["status"],
                        "message": result["message"],
                        "started_at": None,
                    }
                )
            return

        stdout, stderr = process.communicate()
        result = parse_maa_check_output(stdout, stderr, process.returncode)

        maa_check_job.update(
            {
                "process": None,
                "status": result["status"],
                "message": result["message"],
                "started_at": None,
            }
        )


def read_log():
    global log_lines
    global ws_connections

    while True:
        msg = config.log_queue.get()
        log_lines.append(msg)
        log_lines = log_lines[-100:]
        for ws in ws_connections:
            ws.send(
                json.dumps(
                    {"type": "log", "data": msg, "screenshot": get_latest_screenshot()}
                )
            )


Thread(target=read_log, daemon=True).start()


def _check_hot_update_on_launch():
    """打开 mower 时后台检查一次热更（config 开关 + 节流内置，不阻塞启动）。"""
    from arknights_mower.utils.hot_update import update as hot_update_update

    hot_update_update()


Thread(target=_check_hot_update_on_launch, daemon=True).start()


def require_token(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if hasattr(app, "token") and request.headers.get("token", "") != app.token:
            abort(403)
        return f(*args, **kwargs)

    return decorated_function


@app.route("/<path:path>")
def serve_index(path):
    return send_from_directory("ui/dist", path)


@app.before_request
def serve_resource_overlay():
    """资源包 webp（depot/avatar/building_skill）overlay 优先，刷新即生效。"""
    path = request.path.lstrip("/")
    if path.startswith(("depot/", "avatar/", "building_skill/")):
        base = Path(get_path("@install/tmp/resource/ui/public"))
        p = (base / path).resolve()
        if base.resolve() in p.parents and p.is_file():
            return send_file(p)


@app.after_request
def gzip_static(response):
    # ui/dist 里的文本类静态资源由 Flask 静态路由直接服务，
    # 通过 after_request 统一对支持 gzip 的客户端返回预压缩 .gz 文件。
    path = request.path.lstrip("/")
    # 根入口 / 对应 index.html，同样预压缩
    if not path:
        path = "index.html"
    if not path.endswith((".js", ".css", ".html", ".json", ".svg", ".map")):
        return response
    static_path = safe_join(app.static_folder, path)
    if (
        response.status_code != 200
        or static_path is None
        or not os.path.isfile(static_path)
    ):
        return response
    gz_path = static_path + ".gz"
    if not os.path.isfile(gz_path):
        return response

    # 同一 URL 有 gzip 与 identity 两种表示，两类响应都必须声明 Vary。
    response.vary.add("Accept-Encoding")
    if request.accept_encodings["gzip"] <= 0:
        return response

    # send_from_directory 可能返回 direct_passthrough 响应；替换内容前先关闭。
    response.direct_passthrough = False
    with open(gz_path, "rb") as f:
        response.set_data(f.read())
    response.headers["Content-Encoding"] = "gzip"
    response.headers["Content-Type"] = mimetypes.guess_type(path)[0] or (
        "application/octet-stream"
    )
    # ETag 基于原始文件，压缩表示不能复用。
    response.headers.pop("ETag", None)
    return response


@app.errorhandler(404)
def not_found(e):
    if (path := request.path).startswith("/docs"):
        try:
            return send_from_directory("ui/dist" + path, "index.html")
        except NotFound:
            return "<h1>404 Not Found</h1>", 404
    return send_from_directory("ui/dist", "index.html")


@app.route("/conf", methods=["GET", "POST"])
@require_token
def load_config():
    if request.method == "GET":
        try:
            from arknights_mower.utils.config.weekly_plan_loader import (
                get_weekly_plan_manager,
            )

            manager = get_weekly_plan_manager()
            manager.sync_active_plan_to_config()
        except Exception:
            logger.exception("Failed to sync active weekly plan before returning /conf")
            manager = None
        data = config.conf.model_dump()
        if manager is not None:
            data["maa_weekly_plan_active"] = manager.get_active_plan_key()
        return data
    else:
        req = dict(request.json or {})
        req["maa_weekly_plan"] = [
            item.model_dump() for item in config.conf.maa_weekly_plan
        ]
        config.conf = config.Conf(**req)
        config.save_conf()
        return "New config saved!"


@app.route("/plan", methods=["GET", "POST"])
@require_token
def load_plan_from_json():
    if request.method == "GET":
        return config.plan.model_dump(exclude_none=True)
    else:
        config.plan = config.PlanModel(**request.json)
        config.save_plan()
        return "New plan saved。"


@app.route("/operator")
def operator_list():
    from arknights_mower.data import agent_list

    return agent_list


@app.route("/shop")
def shop_list():
    from arknights_mower.data import shop_items

    return list(shop_items.keys())


@app.route("/item")
def item_list():
    from arknights_mower.data import workshop_formula

    return list(workshop_formula.keys())


@app.route("/depot/readdepot")
def read_depot():
    from datetime import datetime as _dt

    from arknights_mower.utils import depot

    cultivate_ok = False
    cultivate_msg = "未同步"
    cultivate_json = get_path("@app/tmp/cultivate.json")
    if os.path.exists(cultivate_json):
        cultivate_ok = True
        cultivate_msg = _dt.fromtimestamp(os.path.getmtime(cultivate_json)).strftime(
            "%Y-%m-%d %H:%M:%S"
        )

    data = depot.读取仓库()
    return {"depot": data, "cultivate_ok": cultivate_ok, "cultivate_msg": cultivate_msg}


@app.route("/stage/latest-activity")
def stage_latest_activity():
    """刷理智周计划：最近开启活动（stage_data_full 热更后最新）的选中关。

    返回 [{value, label, code, materials}]，按代号尾号大到小。材料仅 MATERIAL 常规掉落
    （剔 ACTIVITY_ITEM/COMPLETE）；库存取自 @app/tmp/cultivate.json（{id: count}）——
    该材料缺档或为 0 时不带 (库存:n)。
    """
    from arknights_mower.data import key_mapping, stage_data_full
    from arknights_mower.utils.weekly_stage import (
        build_options,
        select_latest_activity_stages,
    )

    in_path = get_path("@app/tmp/cultivate.json")
    inventory = {}
    if os.path.exists(in_path):
        try:
            with open(in_path, "r", encoding="utf-8") as f:
                cdata = json.load(f)
            for item in cdata.get("data", {}).get("items", []):
                count = int(item.get("count", 0))
                if count > 0:
                    inventory[item.get("id", "")] = count
        except (OSError, ValueError):
            inventory = {}

    selected = select_latest_activity_stages(
        list(stage_data_full), key_mapping, int(time.time())
    )
    return build_options(selected, inventory)


@app.route("/status")
def get_status():
    response = {
        "plan_condition": [],
        "status": "stopped",
        "next_task_time": None,
        "remaining_seconds": None,
    }
    if mower_thread and mower_thread.is_alive():
        from arknights_mower.__main__ import base_scheduler

        if base_scheduler and mower_thread.is_alive():
            response["plan_condition"] = list(base_scheduler.op_data.plan_condition)
            for idx, plan in enumerate(base_scheduler.op_data.backup_plans):
                if response["plan_condition"][idx]:
                    response["plan_condition"][idx] = plan.name
            response["plan_condition"] = [
                name for name in response["plan_condition"] if name
            ]

            # 添加工作状态信息
            response["status"] = "sleeping" if base_scheduler.sleeping else "working"
            if base_scheduler.tasks and len(base_scheduler.tasks) > 0:
                response["next_task_time"] = base_scheduler.tasks[0].time.strftime(
                    "%Y-%m-%d %H:%M:%S"
                )
                response["remaining_seconds"] = int(
                    (
                        base_scheduler.tasks[0].time - datetime.datetime.now()
                    ).total_seconds()
                )
    return response


@app.route("/start/<start_type>")
@require_token
def start(start_type):
    global mower_thread
    global log_lines

    if mower_thread and mower_thread.is_alive():
        return "false"
    # 创建 tmp 文件夹
    tmp_dir = get_path("@app/tmp")
    tmp_dir.mkdir(exist_ok=True)

    config.stop_mower.clear()
    saved_state = load_state()
    if saved_state is None or start_type == "2":
        saved_state = {}
    if start_type == "1":
        saved_state["tasks"] = []
    restart_after_mood_read = (
        start_type == "2" and config.conf.refresh_backup_plan_after_mood
    )
    from arknights_mower.__main__ import main

    mower_thread = Thread(
        target=main, args=(saved_state, restart_after_mood_read), daemon=True
    )
    # /task 路由（views/task.py）独立判定「mower 正在运行」，须与本模块同步
    set_mower_thread(mower_thread)
    mower_thread.start()

    log_lines = []

    return "true"


@app.route("/stop")
@require_token
@save_state
def stop():
    global mower_thread

    if mower_thread is None:
        return "true"

    config.stop_mower.set()

    mower_thread.join(10)
    if mower_thread.is_alive():
        logger.error("Mower线程仍在运行")
        return "false"
    else:
        logger.info("成功停止mower线程")
        mower_thread = None
        set_mower_thread(None)
        return "true"


@app.route("/stop-maa")
@require_token
def stop_maa():
    global mower_thread

    if mower_thread is None:
        return "true"

    config.stop_maa.set()
    return "OK"


@sock.route("/log")
def log(ws):
    global ws_connections
    global log_lines

    ws.send(
        json.dumps(
            {
                "type": "log",
                "data": "\n".join(log_lines),  # 发送完整日志
            }
        )
    )
    ws_connections.append(ws)

    from simple_websocket import ConnectionClosed

    try:
        while True:
            ws.receive()
    except ConnectionClosed:
        ws_connections.remove(ws)


@app.route("/screenshots/<path:filename>")
def serve_screenshot(filename):
    """
    提供截图文件的访问
    """
    screenshot_dir = get_path("@app/screenshot")
    return send_from_directory(screenshot_dir, filename)


@app.route("/latest-screenshot")
def get_latest_screenshot():
    """
    返回最新截图的路径
    """
    from arknights_mower.utils.log import last_screenshot

    if last_screenshot:
        return last_screenshot
    return ""


def conn_send(text):
    from arknights_mower.utils import config

    if not config.webview_process.is_alive():
        return ""

    config.parent_conn.send(text)
    return config.parent_conn.recv()


@app.route("/dialog/file")
@require_token
def open_file_dialog():
    return conn_send("file")


@app.route("/dialog/folder")
@require_token
def open_folder_dialog():
    return conn_send("folder")


@app.route("/import", methods=["POST"])
@require_token
def import_from_image():
    img = request.files["img"]
    if img.mimetype == "application/json":
        data = json.load(img)
    else:
        try:
            from PIL import Image

            from arknights_mower.utils import qrcode

            img = Image.open(img)
            data = qrcode.decode(img)
        except Exception as e:
            msg = f"排班表导入失败：{e}"
            logger.exception(msg)
            return msg
    if data:
        config.plan = config.PlanModel(**data)
        config.save_plan()
        return "排班已加载"
    else:
        return "排班表导入失败！"


@app.route("/sss-copilot", methods=["GET", "POST"])
@require_token
def upload_sss_copilot():
    copilot = get_path("@app/sss.json")
    if request.method == "GET":
        if copilot.is_file():
            with copilot.open("r", encoding="utf-8") as f:
                data = json.load(f)
        else:
            return {"exists": False}
    else:
        print(request.files)
        data = request.files["copilot"]
        data.save(copilot)
        data.seek(0)
        data = json.load(data)
    return {
        "exists": True,
        "title": data["doc"]["title"],
        "details": data["doc"]["details"],
        "operators": data["opers"],
    }


@app.route("/hot-update/manual", methods=["POST"])
@require_token
def hot_update_manual():
    """手动应用一份更新包（拖入/选择），按 zip 内容自动识别热更包/资源包。

    用于国内直连 GitHub 不稳时的人工兜底：热更走 apply_manual_zip，资源包走 overlay 原子安装。
    """
    from zipfile import ZipFile

    from arknights_mower.utils import hot_update as hu
    from arknights_mower.utils.resource_pkg import (
        _RESOURCE_MARKER,
        install_resource_pkg,
    )

    update_file = request.files.get("update")
    if update_file is None:
        return {"ok": False, "message": "没有收到更新包文件"}
    raw = update_file.read()
    try:
        with ZipFile(BytesIO(raw)) as z:
            names = z.namelist()
    except Exception:
        return {"ok": False, "message": "不是有效的 zip 包"}
    if hu._has_hotupdate_marker(names):
        if hu.apply_manual_zip(raw):
            return {"ok": True, "message": "热更包已应用"}
        return {
            "ok": False,
            "message": "热更包应用失败（请确认是有效的 hot_update.zip）",
        }
    if _RESOURCE_MARKER in names:
        busy = _mower_busy_response()
        if busy:
            return busy
        if install_resource_pkg(raw):
            return {"ok": True, "message": "资源包安装成功，重启后完全生效"}
        return {"ok": False, "message": "资源包安装失败（已回滚）"}
    return {
        "ok": False,
        "message": "无法识别的更新包（热更包需 nav_steps.json，资源包需 version.json）",
    }


@app.route("/dialog/save/img", methods=["POST"])
@require_token
def save_file_dialog():
    img = request.files["img"]

    from PIL import Image

    from arknights_mower.utils import qrcode

    upper = Image.open(img)

    img = qrcode.export(
        config.plan.model_dump(exclude_none=True), upper, config.conf.theme
    )
    buffer = BytesIO()
    img.save(buffer, format="JPEG")
    buffer.seek(0)
    return send_file(buffer, "image/jpeg")


@app.route("/export-json")
@require_token
def export_json():
    return send_file(config.plan_path)


@app.route("/validate-plan", methods=["POST"])
@require_token
def validate_backup_plans_route():
    try:
        global_plan = build_global_plan()
        op = Operators(global_plan)
        validation_msg = op.init_and_validate()
        if validation_msg is not None:
            return {"success": False, "message": validation_msg}
        result = op.validate_backup_plans()
        return result
    except Exception as e:
        logger.exception(e)
        return {"success": False, "message": f"验证过程中发生错误: {str(e)}"}


@app.route("/check-maa")
@require_token
def get_maa_adb_version():
    with maa_check_lock:
        _collect_maa_check_result()
        if maa_check_job["status"] == "running":
            return {
                "status": "running",
                "message": maa_check_job["message"] or "正在测试……",
            }

        try:
            process = subprocess.Popen(
                maa_check_command(),
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                close_fds=False,
                creationflags=(
                    subprocess.CREATE_NO_WINDOW if __system__ == "windows" else 0
                ),
            )
        except Exception as e:
            logger.exception(e)
            return {
                "status": "error",
                "message": f"Maa测试启动失败：{e}",
            }
        maa_check_job.update(
            {
                "id": time.time_ns(),
                "process": process,
                "status": "running",
                "message": "正在测试……",
                "started_at": time.monotonic(),
            }
        )
        return {"status": "running", "message": "正在测试……"}


@app.route("/check-maa/status")
@require_token
def get_maa_check_status():
    _collect_maa_check_result()
    return {
        "status": maa_check_job["status"],
        "message": maa_check_job["message"],
    }


@app.route("/maa-conn-preset")
@require_token
def get_maa_conn_presets():
    config_path = os.path.join(config.conf.maa_path, "resource", "config.json")
    if not os.path.exists(config_path):
        logger.warning(f"MAA 配置文件不存在，返回空预设: {config_path}")
        return []
    try:
        with open(config_path, "r", encoding="utf-8") as f:
            presets = [item["configName"] for item in json.load(f)["connection"]]
    except Exception as e:
        logger.exception(e)
        presets = []
    return presets


@app.route("/record/getMoodRatios")
def get_mood_ratios():
    from arknights_mower.solvers import record

    return record.get_mood_ratios()


@app.route("/report/restore-trading-history")
def restoreTradingHistory():
    from arknights_mower.utils.trading_order import TradingOrder

    trading = TradingOrder()
    return trading.restore_history()


@app.route("/report/trading_history")
def getTradingHistory():
    start_date = request.args.get("startDate")
    end_date = request.args.get("endDate")
    if not start_date or not end_date:
        end_date = str(get_server_time().date())
        start_date = str((get_server_time() - datetime.timedelta(days=8)).date())
    from arknights_mower.solvers import record

    return record.get_trading_history(start_date, end_date)


@app.route("/record/clear-data", methods=["DELETE"])
def clear_data_route():
    date_time_str = request.json.get("date_time")
    logger.info(date_time_str)
    if not date_time_str:
        return "日期时间参数缺失", 400
    try:
        date_time = datetime.datetime.fromtimestamp(date_time_str / 1000.0)
    except ValueError:
        return "日期时间格式不正确", 400

    clear_data(date_time)
    return "数据已清除", 200


@app.route("/getwatermark")
def getwatermark():
    from arknights_mower.__init__ import __version__

    return __version__


@app.route("/update-notice")
@require_token
def get_update_notice():
    from arknights_mower.utils.update_notice import UpdateNoticeManager

    return UpdateNoticeManager().get_notice()


@app.route("/update-notice/ack", methods=["POST"])
@require_token
def ack_update_notice():
    from arknights_mower.utils.update_notice import UpdateNoticeManager

    version = str((request.json or {}).get("version", "")).strip()
    if not version:
        return {"ok": False, "message": "missing version"}, 400
    try:
        return UpdateNoticeManager().acknowledge(version)
    except ValueError as exc:
        return {"ok": False, "message": str(exc)}, 400


@app.route("/resource-version")
@require_token
def get_resource_version():
    from arknights_mower.utils.resource_version import check_resource_update

    return check_resource_update()


@app.route("/resource/install", methods=["POST"])
@require_token
def install_resource():
    """下载并原子安装资源包（overlay 模型）；mower 运行任务时拒绝。"""
    busy = _mower_busy_response()
    if busy:
        return busy

    from arknights_mower.utils.resource_pkg import (
        download_resource_pkg,
        install_resource_pkg,
    )

    data = download_resource_pkg()
    if data is None:
        return {"ok": False, "message": "资源包下载失败，请检查网络"}
    if not install_resource_pkg(data):
        return {"ok": False, "message": "资源包安装失败（已回滚）"}
    return {"ok": True, "message": "安装成功，重启后完全生效"}


def str2date(target: str):
    try:
        return datetime.datetime.strptime(target, "%Y-%m-%d").date()
    except ValueError:
        return datetime.datetime.strptime(target, "%Y/%m/%d").date()


def date2str(target: datetime.date):
    try:
        return datetime.datetime.strftime(target, "%Y-%m-%d")
    except ValueError:
        return datetime.datetime.strftime(target, "%Y/%m/%d")


@app.route("/report/getReportData")
def get_report_data():
    record_path = get_path("@app/tmp/report.csv")
    try:
        format_data = []
        if os.path.exists(record_path) is False:
            logger.debug("基报不存在")
            return False
        data = read_dicts(record_path, encoding="gbk")
        for row in data:
            row["赤金"] = parse_cell_num(row["赤金"])
            row["作战录像"] = parse_cell_num(row["作战录像"])
            row["龙门币订单"] = parse_cell_num(row["龙门币订单"])
            row["龙门币订单数"] = parse_cell_num(row["龙门币订单数"])
        earliest_date = str2date(data[0]["Unnamed: 0"])

        for item in data:
            format_data.append(
                {
                    "日期": date2str(
                        str2date(item["Unnamed: 0"]) - datetime.timedelta(days=1)
                    ),
                    "作战录像": item["作战录像"],
                    "赤金": item["赤金"],
                    "制造总数": (
                        item["赤金"] + item["作战录像"]
                        if item["赤金"] is not None and item["作战录像"] is not None
                        else None
                    ),
                    "龙门币订单": item["龙门币订单"],
                    "反向作战录像": (
                        -item["作战录像"] if item["作战录像"] is not None else None
                    ),
                    "龙门币订单数": item["龙门币订单数"],
                    "每单获取龙门币": (
                        int(item["龙门币订单"] / item["龙门币订单数"])
                        if item["龙门币订单"] is not None
                        and item["龙门币订单数"]
                        and item["龙门币订单数"] != 0
                        else None
                    ),
                }
            )

        if len(format_data) < 15:
            for i in range(1, 16 - len(format_data)):
                format_data.insert(
                    0,
                    {
                        "日期": date2str(
                            earliest_date - datetime.timedelta(days=i + 1)
                        ),
                        "作战录像": "-",
                        "赤金": "-",
                        "龙门币订单": "-",
                        "龙门币订单数": "-",
                        "每单获取龙门币": "-",
                    },
                )
        logger.debug(format_data)
        return format_data
    except PermissionError:
        logger.info("report.csv正在被占用")


@app.route("/report/getOrundumData")
def get_orundum_data():
    record_path = get_path("@app/tmp/report.csv")
    try:
        format_data = []
        if os.path.exists(record_path) is False:
            logger.debug("基报不存在")
            return False
        data = read_dicts(record_path, encoding="gbk")
        earliest_date = datetime.datetime.now()

        begin_make_orundum = (earliest_date + datetime.timedelta(days=1)).date()
        for item in data:
            # 脏数据（读取失败为 None）保留行但置空，避免被当作 0 污染累计总量
            item["合成玉"] = parse_cell_num(item["合成玉"])
            item["合成玉订单数量"] = parse_cell_num(item["合成玉订单数量"])
            if item["合成玉"] is None:
                logger.debug("合成玉读取失败：{}".format(item.get("Unnamed: 0")))
        if len(data) >= 15:
            for i in range(len(data) - 1, -1, -1):
                if 0 < i < len(data) - 15:
                    data.pop(i)
                else:
                    logger.debug("合成玉{}".format(data[i]["合成玉"]))
                    if data[i]["合成玉"] is not None and data[i]["合成玉"] > 0:
                        begin_make_orundum = str2date(data[i]["Unnamed: 0"])
        else:
            for item in data:
                if item["合成玉"] is not None and item["合成玉"] > 0:
                    begin_make_orundum = str2date(item["Unnamed: 0"])
        if begin_make_orundum > earliest_date.date():
            return format_data
        total_orundum = 0
        for item in data:
            if item["合成玉"] is None:
                # 脏行保留、累计值断开，与赤金等字段的 null 表现一致
                format_data.append(
                    {
                        "日期": date2str(
                            str2date(item["Unnamed: 0"]) - datetime.timedelta(days=1)
                        ),
                        "合成玉": None,
                        "合成玉订单数量": None,
                        "抽数": None,
                        "累计制造合成玉": None,
                    }
                )
                continue
            total_orundum = total_orundum + item["合成玉"]
            format_data.append(
                {
                    "日期": date2str(
                        str2date(item["Unnamed: 0"]) - datetime.timedelta(days=1)
                    ),
                    "合成玉": item["合成玉"],
                    "合成玉订单数量": item["合成玉订单数量"],
                    "抽数": round((item["合成玉"] / 600), 1),
                    "累计制造合成玉": total_orundum,
                }
            )

        if len(format_data) < 15:
            earliest_date = str2date(data[0]["Unnamed: 0"])
            for i in range(1, 16 - len(format_data)):
                format_data.insert(
                    0,
                    {
                        "日期": date2str(
                            earliest_date - datetime.timedelta(days=i + 1)
                        ),
                        "合成玉": "-",
                        "合成玉订单数量": "-",
                        "抽数": "-",
                        "累计制造合成玉": 0,
                    },
                )
        logger.debug(format_data)
        return format_data
    except PermissionError:
        logger.info("report.csv正在被占用")


@app.route("/test-email")
@require_token
def test_email():
    from arknights_mower.utils.email import Email

    email = Email("mower测试邮件", config.conf.mail_subject + "测试邮件", None)
    try:
        email.send()
    except Exception as e:
        msg = "邮件发送失败！\n" + str(e)
        logger.exception(msg)
        return msg
    return "邮件发送成功！"


@app.route("/test-custom-screenshot")
@require_token
def test_custom_screenshot():
    import base64
    import subprocess

    import cv2
    import numpy as np

    command = config.conf.custom_screenshot.command

    start = time.time()
    data = subprocess.check_output(
        command,
        shell=True,
        creationflags=subprocess.CREATE_NO_WINDOW if __system__ == "windows" else 0,
    )
    end = time.time()
    elapsed = int((end - start) * 1000)

    data = np.frombuffer(data, np.uint8)
    data = cv2.imdecode(data, cv2.IMREAD_COLOR)
    _, data = cv2.imencode(".jpg", data, [int(cv2.IMWRITE_JPEG_QUALITY), 75])
    data = base64.b64encode(data)
    data = data.decode("ascii")

    return {"elapsed": elapsed, "screenshot": data}


@app.route("/check-skland")
@require_token
def test_skland():
    from arknights_mower.solvers.player_info import PlayerInfoClient

    return PlayerInfoClient().probe_accounts()


@app.route("/check-skland-sign")
@require_token
def test_skland_sign():
    from arknights_mower.solvers.skland import SKLand

    return SKLand().test_sign()


@app.route("/mastery-recommendation-debug")
def mastery_recommendation_debug():
    import json
    import os

    from arknights_mower.utils.mastery_recommendation import (
        _find_skill_data,
        get_mastery_recommendations,
    )
    from arknights_mower.utils.path import _install_dir, _internal_dir, get_path

    cultivate_path = get_path("@app/tmp/cultivate.json")
    skill_data_path = _find_skill_data()

    debug_info = {
        "install_dir": str(_install_dir),
        "internal_dir": str(_internal_dir),
        "cultivate_path": str(cultivate_path),
        "cultivate_exists": os.path.exists(cultivate_path),
        "skill_data_path": str(skill_data_path),
        "skill_data_exists": os.path.exists(skill_data_path),
    }

    if os.path.exists(cultivate_path):
        try:
            with open(cultivate_path, "r", encoding="utf-8") as f:
                cultivate_data = json.load(f)
            debug_info["cultivate_keys"] = list(cultivate_data.keys())
            data = cultivate_data.get("data", {})
            debug_info["data_keys"] = (
                list(data.keys()) if isinstance(data, dict) else str(type(data))
            )
            chars = data.get("characters", []) if isinstance(data, dict) else []
            items = data.get("items", []) if isinstance(data, dict) else []
            debug_info["chars_count"] = (
                len(chars) if isinstance(chars, list) else "not_list"
            )
            debug_info["items_count"] = (
                len(items) if isinstance(items, list) else "not_list"
            )
            if isinstance(chars, list) and len(chars) > 0:
                debug_info["first_char_keys"] = list(chars[0].keys())
                debug_info["first_char"] = {
                    k: chars[0][k]
                    for k in [
                        "id",
                        "level",
                        "evolvePhase",
                        "mainSkillLevel",
                        "potentialRank",
                    ]
                    if k in chars[0]
                }
                skills = chars[0].get("skills", [])
                debug_info["first_char_skills_count"] = (
                    len(skills) if isinstance(skills, list) else "not_list"
                )
        except Exception as e:
            debug_info["cultivate_read_error"] = str(e)

    if os.path.exists(skill_data_path):
        try:
            with open(skill_data_path, "r", encoding="utf-8") as f:
                sd = json.load(f)
            debug_info["skill_data_meta"] = sd.get("_meta", {})
        except Exception as e:
            debug_info["skill_data_read_error"] = str(e)

    result = get_mastery_recommendations()
    debug_info["result_error"] = result.get("error")
    debug_info["result_has_data"] = result.get("has_data")
    debug_info["result_ops_count"] = len(result.get("operators", []))

    return debug_info


@app.route("/mastery-recommendation")
def mastery_recommendation():
    from arknights_mower.utils.mastery_recommendation import get_mastery_recommendations

    return get_mastery_recommendations()


@app.route("/workshop-auto-config", methods=["POST"])
def workshop_auto_config():
    import traceback

    from arknights_mower.utils.mastery_recommendation import (
        compute_default_workshop_config,
        compute_workshop_config,
    )

    try:
        req = request.json or {}
        fodder_ops = req.get("fodder_operators", ["九色鹿"])
        t5_ops = req.get("t5_operators", ["年"])
        book_ops = req.get("book_operators", ["司霆惊蛰"])
        planned_skills = req.get("planned_skills", [])
        if planned_skills:
            settings = compute_workshop_config(
                fodder_operators=fodder_ops,
                t5_operators=t5_ops,
                book_operators=book_ops,
            )
        else:
            settings = compute_default_workshop_config(
                fodder_operators=fodder_ops,
                t5_operators=t5_ops,
                book_operators=book_ops,
            )
        return {"workshop_settings": settings, "t3_summary": []}
    except Exception as e:
        return {"error": str(e), "traceback": traceback.format_exc()}, 500


@app.route("/mastery-t3-summary", methods=["POST"])
def mastery_t3_summary():
    import json as _json
    from collections import defaultdict

    from arknights_mower.data import workshop_formula
    from arknights_mower.utils.mastery_recommendation import (
        _find_skill_data,
        get_mastery_recommendations,
    )

    req = request.json or {}
    planned_keys = req.get("planned_skills", [])
    if not planned_keys:
        return {"t3_summary": []}

    skill_data_path = _find_skill_data()
    with open(skill_data_path, "r", encoding="utf-8") as f:
        skill_data = _json.load(f)
    items = skill_data.get("items", {})

    t4_names = {
        n
        for n, e in workshop_formula.items()
        if e.get("tab") == "精英材料" and e.get("apCost") == 4.0
    }
    t5_names = {
        n: e
        for n, e in workshop_formula.items()
        if e.get("tab") == "精英材料" and e.get("apCost") == 8.0
    }

    result = get_mastery_recommendations()
    operators = result.get("operators", [])

    plan_set = set()
    for key in planned_keys:
        parts = key.rsplit("_", 1)
        if len(parts) == 2:
            try:
                plan_set.add((parts[0], int(parts[1])))
            except ValueError:
                pass

    # 步骤1: 读取计划内所有需求材料
    raw_demand = defaultdict(int)
    for op in operators:
        for rec in op.get("recommendations", []):
            if (op["char_id"], rec["skill_index"]) not in plan_set:
                continue
            for mat in rec.get("chain_needed_materials", []):
                raw_demand[mat["name"]] += mat["count"]

    # 加载仓库库存
    cultivate_path = get_path("@app/tmp/cultivate.json")
    inventory = defaultdict(int)
    if os.path.exists(cultivate_path):
        with open(cultivate_path, "r", encoding="utf-8") as f:
            cdata = _json.load(f)
        for item in cdata.get("data", {}).get("items", []):
            cnt = int(item.get("count", 0))
            if cnt > 0:
                inventory[item.get("id", "")] = cnt

    id_by_name = {}
    for iid, info in items.items():
        id_by_name[info.get("name", "")] = iid

    def inv_of(name):
        return inventory.get(id_by_name.get(name, ""), 0)

    # 步骤2: 分类 T5 / T4 / T3+
    demand_t5 = {n: c for n, c in raw_demand.items() if n in t5_names}
    demand_t4 = {n: c for n, c in raw_demand.items() if n in t4_names}
    demand_t3 = {
        n: c for n, c in raw_demand.items() if n not in t4_names and n not in t5_names
    }

    # 步骤3: T5缺失 → 拆解为T4间接缺失
    t4_indirect = defaultdict(int)
    for t5_name, t5_demand in demand_t5.items():
        t5_missing = max(0, t5_demand - inv_of(t5_name))
        formula = t5_names.get(t5_name, {})
        for child in formula.get("items", []):
            if child in t4_names:
                t4_indirect[child] += t5_missing

    # 步骤4: T4总需 = T4直接 + T4间接; T4缺失 = T4总需 - T4库存
    t4_total = defaultdict(int)
    for name in set(list(demand_t4.keys()) + list(t4_indirect.keys())):
        t4_total[name] = demand_t4.get(name, 0) + t4_indirect.get(name, 0)

    t4_missing_entries = []
    for name, demand in t4_total.items():
        missing = max(0, demand - inv_of(name))
        if missing > 0:
            t4_missing_entries.append((name, missing))

    # 步骤5: T4缺失 → 拆解为T3间接缺失（只拆到T3层级）
    t3_indirect = defaultdict(int)
    queue = list(t4_missing_entries)
    while queue:
        name, cnt = queue.pop(0)
        formula = workshop_formula.get(name)
        if not formula or not formula.get("items"):
            t3_indirect[name] += cnt
            continue
        is_high = name in t4_names or name in t5_names
        if not is_high:
            t3_indirect[name] += cnt
            continue
        for child in formula["items"]:
            queue.append((child, cnt))

    # 步骤6: T3总需 = T3直接 + T3间接; T3缺失 = T3总需 - T3库存
    t3_total = defaultdict(int)
    for name, count in demand_t3.items():
        t3_total[name] += count
    for name, count in t3_indirect.items():
        t3_total[name] += count

    t3_summary = []
    for name, need in sorted(t3_total.items(), key=lambda x: -x[1]):
        owned = inv_of(name)
        shortage = max(0, need - owned)
        if shortage > 0:
            t3_summary.append(
                {
                    "id": id_by_name.get(name, name),
                    "name": name,
                    "count": shortage,
                    "total": need,
                    "owned": owned,
                }
            )

    return {"t3_summary": t3_summary}


@app.route("/mastery-t3-debug", methods=["POST"])
def mastery_t3_debug():

    from arknights_mower.utils.mastery_recommendation import (
        _find_skill_data,
        get_mastery_recommendations,
    )

    req = request.json or {}
    planned_keys = req.get("planned_skills", [])
    skill_data_path = _find_skill_data()
    result = get_mastery_recommendations()
    return {
        "planned_keys": planned_keys,
        "has_data": result.get("has_data"),
        "error": result.get("error"),
        "operators_count": len(result.get("operators", [])),
        "skill_data_exists": os.path.exists(skill_data_path),
    }


@app.route("/workshop-preset", methods=["GET", "POST"])
def workshop_preset():
    import json as _json

    preset_path = get_path("@app/tmp/workshop_preset.json")
    if request.method == "GET":
        if os.path.exists(preset_path):
            try:
                with open(preset_path, "r", encoding="utf-8") as f:
                    return _json.load(f)
            except Exception:
                pass
        return []
    else:
        data = request.json or []
        preset_path.parent.mkdir(parents=True, exist_ok=True)
        with open(preset_path, "w", encoding="utf-8") as f:
            _json.dump(data, f, ensure_ascii=False)
        return {"success": True}


@app.route("/cultivate-fetch")
def cultivate_fetch():
    from arknights_mower.solvers.cultivate_depot import cultivate

    try:
        cultivate().start()
        return {"success": True, "message": "数据拉取成功"}
    except Exception as e:
        return {"success": False, "message": str(e)}


@app.route("/weekly-plans", methods=["GET"])
@require_token
def get_weekly_plans():
    from arknights_mower.utils.config.weekly_plan_loader import get_weekly_plan_manager

    manager = get_weekly_plan_manager()
    return {"plans": manager.get_plans()}


@app.route("/weekly-plans/active", methods=["POST"])
@require_token
def update_active_weekly_plan():
    from arknights_mower.utils.config.weekly_plan_loader import get_weekly_plan_manager

    try:
        req = request.json or {}
        manager = get_weekly_plan_manager()

        active_key = str(req.get("active", "")).strip()
        if not active_key:
            return {"error": "Plan key cannot be empty"}, 400

        plan_data = req.get("plan")

        if plan_data is not None:
            if not manager.create_or_update_plan(active_key, plan_data):
                return {"error": f"Failed to create or update plan '{active_key}'"}, 400
        else:
            if not manager.set_active_plan(active_key):
                return {"error": f"Plan '{active_key}' not found"}, 404

        new_plan = manager.get_plan(active_key) or []
        return {
            "active": active_key,
            "plan": new_plan,
        }
    except Exception as e:
        logger.exception(f"Failed to update weekly plan: {e}")
        return {"error": str(e)}, 500


@app.route("/weekly-plans/<key>", methods=["DELETE"])
@require_token
def delete_weekly_plan(key):
    from arknights_mower.utils.config.weekly_plan_loader import get_weekly_plan_manager

    try:
        manager = get_weekly_plan_manager()

        if not manager.delete_plan(key):
            return {
                "error": f"Cannot delete plan '{key}' (must keep at least one)"
            }, 400

        active_key = manager.get_active_plan_key()
        plan_data = manager.get_plan(active_key)

        return {
            "active": active_key,
            "plan": plan_data,
        }
    except Exception as e:
        logger.exception(f"Failed to delete weekly plan: {e}")
        return {"error": str(e)}, 500


@app.route("/submit_feedback", methods=["POST"])
@require_token
def submit_feedback():
    req = request.json
    logger.debug(f"收到反馈务请求：{req}")

    def ts_to_str(ts):
        if isinstance(ts, (int, float)):
            return datetime.datetime.fromtimestamp(ts / 1000).strftime(
                "%Y-%m-%d %H:%M:%S"
            )
        return ts

    start_time = ts_to_str(req.get("startTime"))
    end_time = ts_to_str(req.get("endTime"))

    from arknights_mower.agent.tools.submit_issue import submit_issue

    return submit_issue(
        req.get("description", ""), req.get("type", ""), start_time, end_time
    )


@sock.route("/ws/chat")
def ws_chat(ws):
    context = []
    while True:
        data = ws.receive()
        if not data:
            break
        try:
            req = json.loads(data)
            last_reply = None
            if "message" in req:
                user_input = req["message"]
                context.append({"role": "user", "content": user_input})
                logger.debug(f"收到llm请求：{user_input}")
                # 用流式生成器
                from arknights_mower.agent.agent import ask_llm

                for reply in ask_llm(
                    user_input, context=context, api_key=config.conf.resolved_ai_key
                ):
                    ws.send(json.dumps({"reply": reply}))
                    last_reply = reply
                if last_reply:
                    context.append({"role": "assistant", "content": reply})
        except Exception as e:
            logger.exception(f"WebSocket处理错误：{str(e)}")
            ws.send(json.dumps({"error": str(e)}))


app.register_blueprint(mastery_bp)
app.register_blueprint(task_bp)
app.register_blueprint(db_admin_bp)
