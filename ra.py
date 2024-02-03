from arknights_mower.solvers.reclamation_algorithm import ReclamationAlgorithm
from arknights_mower.utils import config

config.ADB_CONTROL_CLIENT == "scrcpy"
config.ADB_DEVICE = ["127.0.0.1:5556"]
config.TAP_TO_LAUNCH = {"enable": False, "x": 0, "y": 0}

solver = ReclamationAlgorithm()
solver.run()
