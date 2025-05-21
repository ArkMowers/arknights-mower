#!/usr/bin/env python3
import datetime
import json
import mimetypes
import os
import pathlib
import sys
import time
from functools import wraps
from io import BytesIO
from threading import Thread

import pytz
from flask import Flask, abort, request, send_file, send_from_directory
from flask_cors import CORS
from flask_sock import Sock
from tzlocal import get_localzone
from werkzeug.exceptions import NotFound

from arknights_mower import __system__, __version__
from arknights_mower.solvers.record import clear_data, load_state, save_state
from arknights_mower.utils import config
from arknights_mower.utils.datetime import get_server_time
from arknights_mower.utils.log import get_log_by_time, logger
from arknights_mower.utils.path import get_path

mimetypes.add_type("text/html", ".html")
mimetypes.add_type("text/css", ".css")
mimetypes.add_type("application/javascript", ".js")

app = Flask(__name__, static_folder="ui/dist", static_url_path="")
sock = Sock(app)
CORS(app)

mower_thread = None
log_lines = []
ws_connections = []


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
        return config.conf.model_dump()
    else:
        config.conf = config.Conf(**request.json)
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
    from arknights_mower.utils import depot

    return depot.读取仓库()


@app.route("/running")
def running():
    response = {
        "running": bool(mower_thread and mower_thread.is_alive()),
        "plan_condition": [],
    }
    if response["running"]:
        from arknights_mower.__main__ import base_scheduler

        if base_scheduler and mower_thread.is_alive():
            response["plan_condition"] = list(base_scheduler.op_data.plan_condition)
            for idx, plan in enumerate(base_scheduler.op_data.backup_plans):
                if response["plan_condition"][idx]:
                    response["plan_condition"][idx] = plan.name
            response["plan_condition"] = [
                name for name in response["plan_condition"] if name
            ]
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
    from arknights_mower.__main__ import main

    mower_thread = Thread(target=main, args=(saved_state,), daemon=True)
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


@app.route("/check-maa")
@require_token
def get_maa_adb_version():
    try:
        asst_path = os.path.dirname(
            pathlib.Path(config.conf.maa_path) / "Python" / "asst"
        )
        if asst_path not in sys.path:
            sys.path.append(asst_path)
        from asst.asst import Asst

        Asst.load(config.conf.maa_path)
        asst = Asst()
        version = asst.get_version()
        asst.set_instance_option(2, config.conf.maa_touch_option)
        if asst.connect(config.conf.maa_adb_path, config.conf.adb):
            maa_msg = f"Maa {version} 加载成功"
        else:
            maa_msg = "连接失败，请检查Maa日志！"
    except Exception as e:
        maa_msg = "Maa加载失败：" + str(e)
        logger.exception(maa_msg)
    return maa_msg


@app.route("/maa-conn-preset")
@require_token
def get_maa_conn_presets():
    try:
        with open(
            os.path.join(config.conf.maa_path, "resource", "config.json"),
            "r",
            encoding="utf-8",
        ) as f:
            presets = [i["configName"] for i in json.load(f)["connection"]]
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
    import pandas as pd

    record_path = get_path("@app/tmp/report.csv")
    try:
        format_data = []
        if os.path.exists(record_path) is False:
            logger.debug("基报不存在")
            return False
        df = pd.read_csv(record_path, encoding="gbk")
        data = df.to_dict("records")
        earliest_date = str2date(data[0]["Unnamed: 0"])

        for item in data:
            format_data.append(
                {
                    "日期": date2str(
                        str2date(item["Unnamed: 0"]) - datetime.timedelta(days=1)
                    ),
                    "作战录像": item["作战录像"],
                    "赤金": item["赤金"],
                    "制造总数": int(item["赤金"] + item["作战录像"]),
                    "龙门币订单": item["龙门币订单"],
                    "反向作战录像": -item["作战录像"],
                    "龙门币订单数": item["龙门币订单数"],
                    "每单获取龙门币": int(item["龙门币订单"] / item["龙门币订单数"]),
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
    import pandas as pd

    record_path = get_path("@app/tmp/report.csv")
    try:
        format_data = []
        if os.path.exists(record_path) is False:
            logger.debug("基报不存在")
            return False
        df = pd.read_csv(record_path, encoding="gbk")
        data = df.to_dict("records")
        earliest_date = datetime.datetime.now()

        begin_make_orundum = (earliest_date + datetime.timedelta(days=1)).date()
        print(begin_make_orundum)
        if len(data) >= 15:
            for i in range(len(data) - 1, -1, -1):
                if 0 < i < len(data) - 15:
                    data.pop(i)
                else:
                    logger.debug("合成玉{}".format(data[i]["合成玉"]))
                    if data[i]["合成玉"] > 0:
                        begin_make_orundum = str2date(data[i]["Unnamed: 0"])
        else:
            for item in data:
                if item["合成玉"] > 0:
                    begin_make_orundum = str2date(item["Unnamed: 0"])
        if begin_make_orundum > earliest_date.date():
            return format_data
        total_orundum = 0
        for item in data:
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
    from arknights_mower.solvers.skland import SKLand

    return SKLand().test_connect()


@app.route("/task", methods=["GET", "POST"])
def get_count():
    from arknights_mower.__main__ import base_scheduler
    from arknights_mower.data import agent_list
    from arknights_mower.utils.operators import SkillUpgradeSupport
    from arknights_mower.utils.scheduler_task import SchedulerTask, TaskTypes

    if request.method == "POST":
        try:
            req = request.json
            task = req["task"]
            logger.debug(f"收到新增任务请求：{req}")
            if base_scheduler and mower_thread.is_alive():
                # if not base_scheduler.sleeping:
                #     raise Exception("只能在休息时间添加")
                if task:
                    utc_time = datetime.datetime.strptime(
                        task["time"], "%Y-%m-%dT%H:%M:%S.%f%z"
                    )
                    task_time = (
                        utc_time.replace(tzinfo=pytz.utc)
                        .astimezone(get_localzone())
                        .replace(tzinfo=None)
                    )
                    new_task = SchedulerTask(
                        time=task_time,
                        task_plan=task["plan"],
                        task_type=task["task_type"],
                        meta_data=task["meta_data"],
                    )
                    if base_scheduler.find_next_task(
                        compare_time=task_time, compare_type="="
                    ):
                        raise Exception("找到同时间任务请勿重复添加")
                    if new_task.type == TaskTypes.SKILL_UPGRADE:
                        supports = []
                        for s in req["upgrade_support"]:
                            if (
                                s["name"] not in agent_list
                                or s["swap_name"] not in agent_list
                            ):
                                raise Exception("干员名不正确")
                            sup = SkillUpgradeSupport(
                                name=s["name"],
                                skill_level=s["skill_level"],
                                efficiency=s["efficiency"],
                                match=s["match"],
                                swap_name=s["swap_name"],
                            )
                            sup.half_off = s["half_off"]
                            supports.append(sup)
                        if len(supports) == 0:
                            raise Exception("请添加专精工具人")
                        base_scheduler.op_data.skill_upgrade_supports = supports
                        logger.info("更新专精工具人完毕")
                    base_scheduler.tasks.append(new_task)
                    logger.debug(f"成功：{str(new_task)}")
                    return "添加任务成功！"
            raise Exception("添加任务失败！！")
        except Exception as e:
            logger.exception(f"添加任务失败：{str(e)}")
            return str(e)
    else:
        if base_scheduler and mower_thread and mower_thread.is_alive():
            from jsonpickle import encode

            return [
                json.loads(
                    encode(
                        i,
                        unpicklable=False,
                    )
                )
                for i in base_scheduler.tasks
            ]
        else:
            return []


@app.route("/submit_feedback", methods=["POST"])
@require_token
def submit_feedback():
    from arknights_mower.utils.email import Email

    req = request.json
    logger.debug(f"收到反馈务请求：{req}")
    try:
        log_files = []
        logger.debug(__version__)
        from arknights_mower.__main__ import base_scheduler

        if base_scheduler and mower_thread.is_alive():
            for k, v in base_scheduler.op_data.plan.items():
                logger.debug(str(v))
        if req["type"] == "Bug":
            dt = datetime.datetime.fromtimestamp(req["endTime"] / 1000.0)
            logger.info(dt)
            log_files = get_log_by_time(dt)
            logger.info("log 文件发送中，请等待")
            if not log_files:
                raise ValueError("对应时间log 文件无法找到")
            body = f"<p>Bug 发生时间区间:{datetime.datetime.fromtimestamp(req['startTime'] / 1000.0)}--{dt}</p><br><p>{req['description']}</p>"
        else:
            body = req["description"]
        email = Email(
            body,
            "Mower " + req["type"],
            None,
            attach_files=None if req["type"] != "Bug" else log_files,
        )
        email.send(["354013233@qq.com"])
    except ValueError as v:
        logger.exception(v)
        return str(v)
    except Exception as e:
        msg = "反馈发送失败，请确保邮箱功能正常使用\n" + str(e)
        logger.exception(msg)
        return msg
    return "邮件发送成功！"
