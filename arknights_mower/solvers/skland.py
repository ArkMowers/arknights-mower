import datetime
import os

import pandas as pd
import requests

from arknights_mower.utils import config
from arknights_mower.utils.log import logger
from arknights_mower.utils.path import get_path
from arknights_mower.utils.skland import (
    get_binding_list,
    get_cred_by_token,
    get_sign_header,
    header,
    header_login,
    log,
    sign_endfield_url,
    sign_url,
    token_password_url,
)


class SKLand:
    def __init__(self):
        self.record_path = get_path("@app/tmp/skland.csv")

        self.reward = []

        self.sign_token = ""
        self.all_recorded = True

        self.test_writecsv = True

    def start(self):

        for item in config.conf.skland_info:
            if not (item.arknights_isCheck or item.endfield_isCheck):
                continue
            if self.has_record(item.account):
                continue

            self.all_recorded = False
            self.save_param(get_cred_by_token(log(item)))

            # 明日方舟森空岛签到
            for i in get_binding_list(self.sign_token):
                if i["gameId"] == 1 and item.arknights_isCheck:
                    if not i.get("uid"):
                        continue
                    if not (item.sign_in_bilibili) and i["channelName"] == "bilibili服":
                        continue
                    if not (item.sign_in_official) and i["channelName"] == "官服":
                        continue
                    body = {"gameId": 1, "uid": i.get("uid")}
                    resp = requests.post(
                        sign_url,
                        headers=get_sign_header(
                            sign_url, "post", body, self.sign_token, header
                        ),
                        json=body,
                    ).json()
                    if resp["code"] != 0:
                        self.reward.append(
                            {
                                "nickName": item.account,
                                "game": "明日方舟{}".format(i.get("channelName")),
                                "reward": resp.get("message"),
                            }
                        )
                        logger.info(f"{i.get('nickName')}：{resp.get('message')}")
                        continue
                    awards = resp["data"]["awards"]
                    for j in awards:
                        res = j["resource"]
                        self.reward.append(
                            {
                                "nickName": item.account,
                                "game": "明日方舟{}".format(i.get("channelName")),
                                "reward": "{}×{}".format(
                                    res["name"], j.get("count") or 1
                                ),
                            }
                        )
                        logger.info(
                            f"{i.get('nickName')}的明日方舟{i.get('channelName')}获得了{res['name']}×{j.get('count') or 1}"
                        )
                # 终末地森空岛签到
                if i["gameId"] == 3 and item.endfield_isCheck:
                    for j in i.get("roles"):
                        if not j.get("roleId"):
                            continue
                        if (
                            not (item.sign_in_endfield_bilibili)
                            and i["channelName"] == "bilibili服"
                        ):
                            continue
                        if (
                            not (item.sign_in_endfield_official)
                            and i["channelName"] == "官服"
                        ):
                            continue
                        body_endfield = {
                            "gameId": 3,
                            "roleId": j.get("roleId"),
                            "serverId": j.get("serverId"),
                        }
                        headers_endfield = get_sign_header(
                            sign_endfield_url,
                            "post",
                            body_endfield,
                            self.sign_token,
                            header,
                        )
                        headers_endfield["Content-Type"] = "application/json"
                        headers_endfield["sk-game-role"] = (
                            f"3_{j.get('roleId')}_{j.get('serverId')}"
                        )
                        headers_endfield["referer"] = "https://game.skland.com/"
                        headers_endfield["origin"] = "https://game.skland.com/"

                        resp = requests.post(
                            sign_endfield_url,
                            headers=headers_endfield,
                            json=body_endfield,
                        ).json()
                        if resp["code"] != 0:
                            self.reward.append(
                                {
                                    "nickname": item.account,
                                    "game": "终末地{}".format(i.get("channelName")),
                                    "reward": resp.get("message"),
                                }
                            )
                            logger.info(f"{j.get('nickname')}：{resp.get('message')}")
                            continue
                        awards = resp["data"]["awardIds"]
                        resource = resp["data"]["resourceInfoMap"]
                        for award in awards:
                            awardid = award.get("id")
                            res = resource[awardid]
                            self.reward.append(
                                {
                                    "nickname": item.account,
                                    "game": "终末地{}".format(i.get("channelName")),
                                    "reward": "{}×{}".format(
                                        res["name"], res.get("count") or 1
                                    ),
                                }
                            )
                            logger.info(
                                f"{j.get('nickname')}的终末地{i.get('channelName')}获得了{res['name']}×{res.get('count') or 1}"
                            )
        if len(self.reward) > 0:
            return self.record_log()
        if self.all_recorded:
            if len(self.reward) == 0:
                return False
            return True
        return False

    def save_param(self, cred_resp):
        header["cred"] = cred_resp["cred"]
        self.sign_token = cred_resp["token"]

    def log(self, account):
        r = requests.post(
            token_password_url,
            json={"phone": account.account, "password": account.password},
            headers=header_login,
        ).json()
        if r.get("status") != 0:
            raise Exception(f"获得token失败：{r['msg']}")
        return r["data"]["token"]

    def record_log(self):
        self.test_writecsv = True
        date_str = datetime.datetime.now().strftime("%Y/%m/%d")
        logger.info(f"存入{date_str}的数据{self.reward}")
        try:
            for item in self.reward:
                res_df = pd.DataFrame(item, index=[date_str])
                res_df.to_csv(self.record_path, mode="a", header=False, encoding="gbk")
        except Exception as e:
            self.test_writecsv = False
            logger.exception(e)
        return True

    def has_record(self, phone: str):
        try:
            if os.path.exists(self.record_path) is False:
                logger.debug("无森空岛记录")
                return False
            df = pd.read_csv(
                self.record_path, header=None, encoding="gbk", on_bad_lines="skip"
            )

            sign_arknights_official = False
            sign_arknights_bilbili = False
            sign_endfield_official = False
            sign_endfield_bilibili = False

            for item in df.iloc:
                if (item[0] == datetime.datetime.now().strftime("%Y/%m/%d")) and (
                    item[1].astype(str) == phone
                ):
                    for game in config.conf.skland_info:
                        if (phone == game.account) and not game.sign_in_official:
                            sign_arknights_official = True
                        if (phone == game.account) and not game.sign_in_bilibili:
                            sign_arknights_bilbili = True
                        if (
                            phone == game.account
                        ) and not game.sign_in_endfield_official:
                            sign_endfield_official = True
                        if (
                            phone == game.account
                        ) and not game.sign_in_endfield_bilibili:
                            sign_endfield_bilibili = True
                    if item[2] == "明日方舟官服":
                        sign_arknights_official = True
                    if item[2] == "明日方舟bilibili服":
                        sign_arknights_bilbili = True
                    if item[2] == "终末地官服":
                        sign_endfield_official = True
                    if item[2] == "终末地bilibili服":
                        sign_endfield_bilibili = True
                    if (
                        sign_arknights_official
                        and sign_arknights_bilbili
                        and sign_endfield_official
                        and sign_endfield_bilibili
                    ):
                        logger.info(f"{phone}今天签到过了")
                        return True
            return False
        except PermissionError:
            logger.info("skland.csv正在被占用")
        except pd.errors.EmptyDataError:
            return False

    # 用于测试连接
    def test_connect(self):
        res = []
        for item in config.conf.skland_info:
            try:
                self.save_param(get_cred_by_token(log(item)))
                res.append(f"账号 {item.account}：")
                for i in get_binding_list(self.sign_token):
                    # 明日方舟角色/区服信息
                    if i["uid"] and i["gameId"] == 1:
                        res.append(
                            " - {}连接成功".format(
                                i["nickName"] + "(明日方舟{})".format(i["channelName"])
                            )
                        )
                    # 终末地角色/区服信息
                    if i["roles"] and i["gameId"] == 3:
                        for j in i["roles"]:
                            res.append(
                                " - {}连接成功".format(
                                    j["nickname"]
                                    + "(终末地{})".format(i["channelName"])
                                )
                            )

            except Exception as e:
                msg = "{}无法连接-{}".format(item.account, e)
                logger.exception(msg)
                res.append(msg)
        return res

    # 用于测试签到
    def test_sign(self):
        res = []

        try:
            if bool(self.start()):
                for info in self.reward:
                    res.append(
                        "{}{}签到成功".format(
                            info.get("nickname") or info.get("nickName"),
                            info.get("game"),
                        )
                    )
                if not self.test_writecsv:
                    res.append("签到数据写入失败")
                    self.test_writecsv = True
                return res
        except Exception as e:
            msg = "测试出错-{}".format(e)
            logger.exception(msg)
            res.append(msg)
        res.append("勾选的账号今天均已签到~")
        return res
