#!/usr/bin/env python3
import requests

from arknights_mower.solvers import record
from arknights_mower.utils.conf import load_conf, save_conf, load_plan, write_plan
from arknights_mower.utils import depot
from arknights_mower.__main__ import main

from flask import Flask, send_from_directory, request, abort
from flask_cors import CORS
from flask_sock import Sock

from simple_websocket import ConnectionClosed

import webview

import os
import multiprocessing
from threading import Thread
import json
import time
import sys
import mimetypes

import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

from functools import wraps

import pathlib

mimetypes.add_type("text/html", ".html")
mimetypes.add_type("text/css", ".css")
mimetypes.add_type("application/javascript", ".js")

app = Flask(__name__, static_folder="dist", static_url_path="")
sock = Sock(app)
CORS(app)

conf = {}
plan = {}
mower_process = None
read = None
operators = {}
log_lines = []
ws_connections = []


def require_token(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if hasattr(app, "token") and request.headers.get("token", "") != app.token:
            abort(403)
        return f(*args, **kwargs)

    return decorated_function


@app.route("/")
def serve_index():
    return send_from_directory("dist", "index.html")


@app.errorhandler(404)
def not_found(e):
    return send_from_directory("dist", "index.html")


@app.route("/conf", methods=["GET", "POST"])
@require_token
def load_config():
    global conf

    if request.method == "GET":
        conf = load_conf()
        return conf
    else:
        conf.update(request.json)
        save_conf(conf)
        return f"New config saved!"


@app.route("/plan", methods=["GET", "POST"])
@require_token
def load_plan_from_json():
    global plan

    if request.method == "GET":
        global conf
        plan = load_plan(conf["planFile"])
        return plan
    else:
        plan = request.json
        write_plan(plan, conf["planFile"])
        return f"New plan saved at {conf['planFile']}"


@app.route("/operator")
def operator_list():
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        with open(
            os.path.join(
                sys._MEIPASS,
                "arknights_mower",
                "__init__",
                "data",
                "agent.json",
            ),
            "r",
            encoding="utf8",
        ) as f:
            return json.load(f)
    else:
        with open(
            os.path.join(
                os.getcwd(),
                "arknights_mower",
                "data",
                "agent.json",
            ),
            "r",
            encoding="utf8",
        ) as f:
            return json.load(f)


@app.route("/shop")
def shop_list():
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        with open(
            os.path.join(
                sys._MEIPASS,
                "arknights_mower",
                "__init__",
                "data",
                "shop.json",
            ),
            "r",
            encoding="utf8",
        ) as f:
            return json.load(f)
    else:
        with open(
            os.path.join(
                os.getcwd(),
                "arknights_mower",
                "data",
                "shop.json",
            ),
            "r",
            encoding="utf8",
        ) as f:
            return json.load(f)


def read_log(conn):
    global operators
    global mower_process
    global log_lines
    global ws_connections

    try:
        while True:
            msg = conn.recv()
            if msg["type"] == "log":
                new_line = time.strftime("%m-%d %H:%M:%S ") + msg["data"]
                log_lines.append(new_line)
                log_lines = log_lines[-500:]
                for ws in ws_connections:
                    ws.send(new_line)
            elif msg["type"] == "operators":
                operators = msg["data"]
            elif msg["type"] == "update_conf":
                global conf
                conn.send(conf)
    except EOFError:
        conn.close()


@app.route("/depot/readdepot")
def read_depot():
    return depot.read_and_compare_depots()


@app.route("/running")
def running():
    global mower_process
    return "false" if mower_process is None else "true"


@app.route("/start")
@require_token
def start():
    global conf
    global plan
    global mower_process
    global operators
    global log_lines

    if mower_process is not None:
        return "Mower is already running."

    read, write = multiprocessing.Pipe()
    mower_process = multiprocessing.Process(
        target=main,
        args=(
            conf,
            plan,
            operators,
            write,
        ),
        daemon=False,
    )
    mower_process.start()

    Thread(target=read_log, args=(read,)).start()

    log_lines = []

    return "Mower started."


@app.route("/stop")
@require_token
def stop():
    global mower_process

    if mower_process is None:
        return "Mower is not running."

    mower_process.terminate()
    mower_process = None

    return "Mower stopped."


@sock.route("/log")
def log(ws):
    global ws_connections
    global log_lines

    ws.send("\n".join(log_lines))
    ws_connections.append(ws)

    try:
        while True:
            ws.receive()
    except ConnectionClosed:
        ws_connections.remove(ws)


@app.route("/dialog/file")
@require_token
def open_file_dialog():
    window = webview.active_window()
    file_path = window.create_file_dialog(dialog_type=webview.OPEN_DIALOG)
    if file_path:
        return file_path[0]
    else:
        return ""


@app.route("/dialog/folder")
@require_token
def open_folder_dialog():
    window = webview.active_window()
    folder_path = window.create_file_dialog(dialog_type=webview.FOLDER_DIALOG)
    if folder_path:
        return folder_path[0]
    else:
        return ""


@app.route("/check-maa")
@require_token
def get_maa_adb_version():
    try:
        asst_path = os.path.dirname(pathlib.Path(conf["maa_path"]) / "Python" / "asst")
        if asst_path not in sys.path:
            sys.path.append(asst_path)
        from asst.asst import Asst

        Asst.load(conf["maa_path"])
        asst = Asst()
        version = asst.get_version()
        asst.set_instance_option(2, conf["maa_touch_option"])
        if asst.connect(conf["maa_adb_path"], conf["adb"]):
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
            os.path.join(conf["maa_path"], "resource", "config.json"),
            "r",
            encoding="utf-8",
        ) as f:
            presets = [i["configName"] for i in json.load(f)["connection"]]
    except:
        presets = []
    return presets


@app.route("/record/getMoodRatios")
def get_mood_ratios():
    return record.get_mood_ratios()


@app.route("/test-email")
@require_token
def test_email():
    msg = MIMEMultipart()
    msg.attach(MIMEText("arknights-mower测试邮件", "plain"))
    msg["Subject"] = conf["mail_subject"] + "测试邮件"
    msg["From"] = conf["account"]
    try:
        s = smtplib.SMTP_SSL("smtp.qq.com", 465, timeout=10.0)
        s.login(conf["account"], conf["pass_code"])
        s.sendmail(conf["account"], conf["account"], msg.as_string())
    except Exception as e:
        return "邮件发送失败！\n" + str(e)
    return "邮件发送成功！"


@app.route("/check-skland")
@require_token
def test_skland():
    skland_info = []
    skland_info = conf["skland_info"]

    request_header = {
        "user-agent": "Skland/1.0.1 (com.hypergryph.skland; build:100001014; Android 33; ) Okhttp/4.11.0",
        "cred": "",
        "vName": "1.0.1",
        "vCode": "100001014",
        "Accept-Encoding": "gzip",
        "Connection": "close",
        "dId": "de9759a5afaa634f",
        "platform": "1",
    }
    res = []
    for item in skland_info:
        data = {"phone": item["account"], "password": item["password"]}
        response = requests.post(
            headers=request_header,
            url="https://as.hypergryph.com/user/auth/v1/token_by_phone_password",
            data=data,
        )
        response_json = json.loads(response.text)
        temp_res = {"account": item["account"], "msg": response_json["msg"]}
        res.append(temp_res)

    return res
