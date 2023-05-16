#!/usr/bin/env python3

from arknights_mower.utils.conf import load_conf, save_conf, load_plan, write_plan
from arknights_mower.__main__ import main

from fastapi import FastAPI, WebSocket, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse

import asyncio_pipe

import os
import asyncio
import multiprocessing
import time

app = FastAPI()

origins = [
    "http://127.0.0.1:5173",
    "http://127.0.0.1:4173",
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

conf = {}
plan = {}


@app.get("/conf")
def load_config():
    global conf
    conf = load_conf()
    return conf


@app.get("/plan")
def load_plan_from_json():
    global conf
    global plan
    plan = load_plan(conf["planFile"])
    return plan


@app.get("/operator")
async def operator_list():
    return FileResponse(
        os.path.join(
            os.getcwd(),
            "arknights_mower",
            "data",
            "agent.json",
        )
    )


mower_process = None
read = None
queue = asyncio.Queue()
operators = {}


async def read_log(read):
    global queue
    global operators

    connection = asyncio_pipe.Connection(read)
    while True:
        try:
            log_line = await connection.recv()
            if log_line["type"] == "log":
                await queue.put(
                    f"{time.strftime('%m-%d %H:%M:%S')} {log_line['data']}".strip()
                )
            elif log_line["type"] == "operators":
                operators = log_line["data"]
        except:
            print("Connection closed!")
            break
    connection.close()


@app.get("/start")
async def start(background_tasks: BackgroundTasks):
    global conf
    global plan

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
    background_tasks.add_task(read_log, read)
    return "OK"


@app.get("/stop")
async def stop():
    return "OK"


@app.websocket("/log")
async def log(ws: WebSocket):
    global queue

    await ws.accept()
    while True:
        log_line = await queue.get()
        await ws.send_text(log_line)
