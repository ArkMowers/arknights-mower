#!/usr/bin/env python3

from arknights_mower.utils.conf import load_conf, save_conf, load_plan, write_plan
from arknights_mower.__main__ import main

from flask import Flask, send_from_directory, request
from flask_cors import CORS
from flask_sock import Sock

import webview

import os
import multiprocessing
from threading import Thread
import json
import queue
import time
import sys
import mimetypes


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
queue = queue.SimpleQueue()
operators = {}


@app.route("/")
def serve_index():
    return send_from_directory("dist", "index.html")


@app.route("/conf", methods=["GET", "POST"])
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
def load_plan_from_json():
    if request.method == "GET":
        global conf
        global plan
        plan = load_plan(conf["planFile"])
        return plan
    else:
        write_plan(request.json, conf["planFile"])
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


def read_log(read):
    global queue
    global operators
    global mower_process

    try:
        while True:
            msg = read.recv()
            if msg["type"] == "log":
                queue.put(time.strftime("%m-%d %H:%M:%S ") + msg["data"])
            elif msg["type"] == "operators":
                operators = msg["data"]
    except EOFError:
        read.close()


@app.route("/running")
def running():
    global mower_process
    return "false" if mower_process is None else "true"


@app.route("/start")
def start():
    global conf
    global plan
    global mower_process
    global operators

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
        daemon=True,
    )
    mower_process.start()

    Thread(target=read_log, args=(read,)).start()

    return "Mower started."


@app.route("/stop")
def stop():
    global mower_process

    if mower_process is None:
        return "Mower is not running."

    mower_process.terminate()
    mower_process = None

    return "Mower stopped."


@sock.route("/log")
def log(ws):
    global queue
    while True:
        data = queue.get()
        ws.send(data)


@app.route("/dialog/file")
def open_file_dialog():
    window = webview.active_window()
    file_path = window.create_file_dialog(dialog_type=webview.OPEN_DIALOG)
    if file_path:
        return file_path[0]
    else:
        return ""


@app.route("/dialog/folder")
def open_folder_dialog():
    window = webview.active_window()
    folder_path = window.create_file_dialog(dialog_type=webview.FOLDER_DIALOG)
    if folder_path:
        return folder_path[0]
    else:
        return ""
