#!/usr/bin/env python3

from arknights_mower.utils.conf import load_conf, save_conf, load_plan, write_plan
from arknights_mower.__main__ import main

from flask import Flask, send_from_directory, request
from flask_cors import CORS
from flask_sock import Sock

import os
import multiprocessing
from threading import Thread
import json
import queue
import time


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
    if request.method == "GET":
        global conf
        conf = load_conf()
        return conf
    else:
        save_conf(request.json)
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
    with open(
        os.path.join(
            os.getcwd(),
            "arknights_mower",
            "data",
            "agent.json",
        ),
        "r",
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
