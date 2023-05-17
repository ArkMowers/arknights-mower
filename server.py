#!/usr/bin/env python3

from arknights_mower.utils.conf import load_conf, save_conf, load_plan, write_plan
from arknights_mower.__main__ import main

from flask import Flask
from flask_cors import CORS
from flask_sock import Sock

import os
import multiprocessing
from threading import Thread
import json
import queue


app = Flask(__name__)
sock = Sock(app)
CORS(app)


conf = {}
plan = {}
mower_process = None
read = None
queue = queue.SimpleQueue()
operators = {}


@app.route("/conf")
def load_config():
    global conf
    conf = load_conf()
    return conf


@app.route("/plan")
def load_plan_from_json():
    global conf
    global plan
    plan = load_plan(conf["planFile"])
    return plan


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
                queue.put(msg["data"])
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
