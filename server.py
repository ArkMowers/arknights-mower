#!/usr/bin/env python3
import datetime
import json
import mimetypes
import os
import pathlib
import sys
import time
from functools import wraps
from queue import Queue
from threading import Event, Thread

import pytz
from flask import Flask, abort, request, send_from_directory
from flask_cors import CORS
from flask_sock import Sock
from tzlocal import get_localzone
from werkzeug.exceptions import NotFound

from arknights_mower import __system__
from arknights_mower.model import Config
from arknights_mower.utils import config
from arknights_mower.utils.conf import load_conf, load_plan, save_conf, write_plan
from arknights_mower.utils.log import logger
from arknights_mower.utils.path import get_path

mimetypes.add_type("text/html", ".html")
mimetypes.add_type("text/css", ".css")
mimetypes.add_type("application/javascript", ".js")

app = Flask(__name__, static_folder="dist", static_url_path="")
sock = Sock(app)
CORS(app)

plan = {}
operators = {}
config.stop_mower = Event()
config.log_queue = Queue()
config.wh = None

mower_thread = None
log_lines = []
ws_connections = []


def read_log():
    global log_lines
    global ws_connections

    while True:
        msg = config.log_queue.get()
        new_line = time.strftime("%m-%d %H:%M:%S ") + msg
        log_lines.append(new_line)
        log_lines = log_lines[-500:]
        for ws in ws_connections:
            ws.send(new_line)


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
    return send_from_directory("dist", path)


@app.errorhandler(404)
def not_found(e):
    if (path := request.path).startswith("/docs"):
        try:
            return send_from_directory("dist" + path, "index.html")
        except NotFound:
            return "<h1>404 Not Found</h1>", 404
    return send_from_directory("dist", "index.html")


@app.route("/conf", methods=["GET", "POST"])
@require_token
def load_config():
    if request.method == "GET":
        config.conf = Config.load_conf()
        return config.conf.model_dump_json()
    else:
        config.conf = config.conf.my_copy(request.json)
        print(config.conf.mower.adb)
        config.conf.save_conf("./conf.yml", old=True)
        config.conf.save_conf("./conf.upgraded.yml", old=False)

        return "New config saved!"


@app.route("/plan", methods=["GET", "POST"])
@require_token
def load_plan_from_json():
    global plan

    if request.method == "GET":
        try:
            plan = load_plan(config.conf["planFile"])
        except Exception as e:
            logger.error(f"plan.json路径错误{e}，重置为plan.json")
            plan = load_plan()
        return plan
    else:
        plan = request.json
        write_plan(plan, config.conf["planFile"])
        return f"New plan saved at {config.conf['planFile']}"


@app.route("/operator")
def operator_list():
    from arknights_mower.data import agent_list

    return agent_list


@app.route("/shop")
def shop_list():
    from arknights_mower.data import shop_items

    return list(shop_items.keys())


@app.route("/depot/readdepot")
def read_depot():
    from arknights_mower.utils import depot

    return depot.读取仓库()


@app.route("/running")
def running():
    return "true" if mower_thread and mower_thread.is_alive() else "false"


@app.route("/start")
@require_token
def start():
    global mower_thread
    global log_lines

    if mower_thread and mower_thread.is_alive():
        return "false"

    # 创建 tmp 文件夹
    tmp_dir = get_path("@app/tmp")
    tmp_dir.mkdir(exist_ok=True)

    from arknights_mower.__main__ import main

    config.stop_mower.clear()
    config.plan = plan
    config.operators = {}
    mower_thread = Thread(target=main, daemon=True)
    mower_thread.start()

    log_lines = []

    return "true"


@app.route("/stop")
@require_token
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


@sock.route("/log")
def log(ws):
    global ws_connections
    global log_lines

    ws.send("\n".join(log_lines))
    ws_connections.append(ws)

    from simple_websocket import ConnectionClosed

    try:
        while True:
            ws.receive()
    except ConnectionClosed:
        ws_connections.remove(ws)


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


@app.route("/import")
@require_token
def import_from_image():
    img_path = conn_send("file")

    if not img_path:
        return "No file selected."

    from PIL import Image

    from arknights_mower.utils import qrcode

    img = Image.open(img_path)
    global plan
    plan = qrcode.decode(img)
    if plan:
        write_plan(plan, config.conf["planFile"])
        return "排班已加载"
    return "排班表导入失败！"


@app.route("/dialog/save/img", methods=["POST"])
@require_token
def save_file_dialog():
    img = request.files["img"]
    if not img:
        return "图片未上传"

    from PIL import Image

    from arknights_mower.utils import qrcode

    upper = Image.open(img)

    global plan
    img = qrcode.export(plan, upper, config.conf["theme"])

    img_path = conn_send("save")
    if img_path == "":
        return "保存已取消"
    else:
        img.save(img_path)
        return f"图片已导出至{img_path}"


@app.route("/check-maa")
@require_token
def get_maa_adb_version():
    try:
        asst_path = os.path.dirname(
            pathlib.Path(config.conf["maa_path"]) / "Python" / "asst"
        )
        if asst_path not in sys.path:
            sys.path.append(asst_path)
        from asst.asst import Asst

        Asst.load(config.conf["maa_path"])
        asst = Asst()
        version = asst.get_version()
        asst.set_instance_option(2, config.conf["maa_touch_option"])
        if asst.connect(config.conf["maa_adb_path"], config.conf["adb"]):
            maa_msg = f"Maa {version} 加载成功"
        else:
            maa_msg = "连接失败，请检查Maa日志！"
    except Exception as e:
        maa_msg = "Maa加载失败：" + str(e)
    return maa_msg


@app.route("/maa-conn-preset")
@require_token
def get_maa_conn_presets():
    try:
        with open(
            os.path.join(config.conf["maa_path"], "resource", "config.json"),
            "r",
            encoding="utf-8",
        ) as f:
            presets = [i["configName"] for i in json.load(f)["connection"]]
    except Exception:
        presets = []
    return presets


@app.route("/record/getMoodRatios")
def get_mood_ratios():
    from arknights_mower.solvers import record

    return record.get_mood_ratios()


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
    import smtplib
    from email.mime.multipart import MIMEMultipart
    from email.mime.text import MIMEText

    msg = MIMEMultipart()
    msg.attach(MIMEText("arknights-mower测试邮件", "plain"))
    msg["Subject"] = config.conf["mail_subject"] + "测试邮件"
    recipients = config.conf["recipient"] or [config.conf["account"]]
    msg["To"] = ", ".join(recipients)
    msg["From"] = config.conf["account"]
    # 根据conf字典中的custom_smtp_server设置SMTP服务器和端口
    smtp_server = config.conf["custom_smtp_server"]["server"]
    ssl_port = config.conf["custom_smtp_server"]["ssl_port"]
    use_qq_mail = not config.conf["custom_smtp_server"]["enable"]
    # 根据encryption键的值选择加密方法
    encryption = config.conf["custom_smtp_server"]["encryption"]
    try:
        if use_qq_mail:
            # 如果不用自定义用qq邮箱就使用TLS加密
            s = smtplib.SMTP_SSL("smtp.qq.com", 465, timeout=10.0)
        elif encryption == "starttls":
            # 使用STARTTLS加密
            s = smtplib.SMTP(smtp_server, ssl_port, timeout=10.0)
            s.starttls()
        else:
            # 如果encryption键的值不是starttls，则使用默认的TLS加密
            s = smtplib.SMTP_SSL(smtp_server, ssl_port, timeout=10.0)
        # 登录SMTP服务器
        s.login(config.conf["account"], config.conf["pass_code"])
        # 发送邮件
        s.sendmail(config.conf["account"], recipients, msg.as_string())
        s.close()
    except Exception as e:
        return "邮件发送失败！\n" + str(e)
    return "邮件发送成功！"


@app.route("/test-custom-screenshot")
@require_token
def test_custom_screenshot():
    import base64
    import subprocess

    import cv2
    import numpy as np

    command = config.conf["custom_screenshot"]["command"]

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


@app.route("/test-serverJang-push")
@require_token
def test_serverJang_push():
    import requests

    try:
        response = requests.get(
            f"https://sctapi.ftqq.com/{config.conf['sendKey']}.send",
            params={
                "title": "arknights-mower推送测试",
                "desp": "arknights-mower推送测试",
            },
        )

        if response.status_code == 200 and response.json().get("code") == 0:
            return "发送成功"
        else:
            return "发送失败 : " + response.json().get("message", "")
    except Exception as e:
        return "发送失败 : " + str(e)


@app.route("/test-pushplus-push")
@require_token
def test_pushplus_push():
    import requests

    try:
        response = requests.post(
            r"http://www.pushplus.plus/send",
            params={
                "token": config.conf["pushplus"]["token"],
                "title": "arknights-mower推送测试",
                "content": "arknights-mower推送测试",
            },
        )

        if response.status_code == 200 and response.json().get("code") == 200:
            return "发送成功"
        else:
            return "发送失败 : " + response.json().get("message", "")
    except Exception as e:
        print(type(e))
        return "发送失败 : " + str(e)


@app.route("/check-skland")
@require_token
def test_skland():
    from arknights_mower.solvers.skland import SKLand

    return SKLand(config.conf["skland_info"]).test_connect()


@app.route("/task", methods=["GET", "POST"])
def get_count():
    from arknights_mower.__main__ import base_scheduler
    from arknights_mower.data import agent_list
    from arknights_mower.utils.operators import SkillUpgradeSupport
    from arknights_mower.utils.scheduler_task import (
        SchedulerTask,
        TaskTypes,
        find_next_task,
    )

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
                    next_task = find_next_task(
                        base_scheduler.tasks, compare_time=task_time, compare_type="="
                    )
                    if next_task is not None:
                        raise Exception("找到同时间任务请勿重复添加")
                    if new_task.type == TaskTypes.SKILL_UPGRADE:
                        supports = []
                        for s in req["upgrade_support"]:
                            if (
                                s["name"] not in agent_list
                                or s["swap_name"] not in agent_list
                            ):
                                raise Exception("干员名不正确")
                            supports.append(
                                SkillUpgradeSupport(
                                    name=s["name"],
                                    skill_level=s["skill_level"],
                                    efficiency=s["efficiency"],
                                    match=s["match"],
                                    swap_name=s["swap_name"],
                                )
                            )
                        if len(supports) == 0:
                            raise Exception("请添加专精工具人")
                        base_scheduler.op_data.skill_upgrade_supports = supports
                        logger.error("更新专精工具人完毕")
                    base_scheduler.tasks.append(new_task)
                    logger.debug(f"成功：{str(new_task)}")
                    return "添加任务成功！"
            raise Exception("添加任务失败！！")
        except Exception as e:
            logger.error(f"添加任务失败：{str(e)}")
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
