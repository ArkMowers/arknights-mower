import json
from pathlib import Path
import yaml
from yaml import Loader, Dumper
from flatten_dict import flatten, unflatten
from .. import __rootdir__
from .path import app_dir


def __get_temp_conf():
    with Path(f"{__rootdir__}/templates/conf.yml").open("r", encoding="utf8") as f:
        return yaml.load(f, Loader=Loader)


def save_conf(conf, path="./conf.yml"):
    path = app_dir / path
    with path.open("w", encoding="utf8") as f:
        yaml.dump(
            conf,
            f,
            Dumper=Dumper,
            encoding="utf-8",
            default_flow_style=False,
            allow_unicode=True,
        )


def load_conf(path="./conf.yml"):
    temp_conf = __get_temp_conf()
    path = app_dir / path
    if not path.is_file():
        path.parent.mkdir(exist_ok=True)
        open(path, "w")  # 创建空配置文件
        save_conf(temp_conf, path)
        return temp_conf
    else:
        with path.open("r", encoding="utf8") as c:
            conf = yaml.load(c, Loader=Loader)
            if conf is None:
                conf = {}
            flat_temp = flatten(temp_conf)
            flat_conf = flatten(conf)
            flat_temp.update(flat_conf)
            temp_conf = unflatten(flat_temp)
            return temp_conf


def __get_temp_plan():
    with open(f"{__rootdir__}/templates/plan.json", "r") as f:
        return json.loads(f.read())


def load_plan(path="./plan.json"):
    temp_plan = __get_temp_plan()
    path = app_dir / path
    if not path.is_file():
        path.parent.mkdir(exist_ok=True)
        with open(path, "w") as f:
            json.dump(temp_plan, f)  # 创建空json文件
        return temp_plan
    with open(path, "r", encoding="utf8") as fp:
        plan = json.loads(fp.read())
        if "conf" not in plan.keys():  # 兼容旧版本
            temp_plan["plan1"] = plan
            return temp_plan
        # 获取新版本的
        tmp = temp_plan["conf"]
        tmp.update(plan["conf"])
        plan["conf"] = tmp
        return plan


def write_plan(plan, path="./plan.json"):
    path = app_dir / path
    with path.open("w", encoding="utf8") as c:
        json.dump(plan, c, ensure_ascii=False)
