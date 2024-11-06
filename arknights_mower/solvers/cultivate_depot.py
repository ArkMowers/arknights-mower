import json

import requests

from arknights_mower.utils import config
from arknights_mower.utils.path import get_path
from arknights_mower.utils.skland import (
    get_binding_list,
    get_cred_by_token,
    get_sign_header,
    header,
    log,
)


class cultivate:
    def __init__(self):
        self.record_path = get_path("@app/tmp/cultivate.json")
        self.reward = []
        self.sign_token = ""
        self.all_recorded = True

    def start(self):
        for item in config.conf.skland_info:
            if item.isCheck:
                self.save_param(get_cred_by_token(log(item)))
                for i in get_binding_list(self.sign_token):
                    if item.cultivate_select == i.get("isOfficial"):
                        body = {"gameId": 1, "uid": i.get("uid")}
                        ingame = f"https://zonai.skland.com/api/v1/game/cultivate/player?uid={i.get('uid')}"
                        resp = requests.get(
                            ingame,
                            headers=get_sign_header(
                                ingame, "get", body, self.sign_token
                            ),
                        ).json()
                        with open(self.record_path, "w", encoding="utf-8") as file:
                            json.dump(resp, file, ensure_ascii=False, indent=4)

    def save_param(self, cred_resp):
        header["cred"] = cred_resp["cred"]
        self.sign_token = cred_resp["token"]
