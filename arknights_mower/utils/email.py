from jinja2 import Environment, FileSystemLoader, select_autoescape
import os
import sys


if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
    template_dir = os.path.join(
        sys._MEIPASS,
        "arknights_mower",
        "__init__",
        "templates",
        "email",
    )
else:
    template_dir = os.path.join(
        os.getcwd(),
        "arknights_mower",
        "templates",
        "email",
    )

env = Environment(
    loader=FileSystemLoader(template_dir),
    autoescape=select_autoescape(),
)

task_template = env.get_template("task.html")
