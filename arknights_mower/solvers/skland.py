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
    sign_url,
    sign_endfield_url,
    token_password_url,
)


class SKLand:
    def __init__(self):
        self.record_path = get_path("@app/tmp/skland.csv")

        self.reward = []

        self.sign_token = ""
        self.all_recorded = True

    def start(self):
        for item in config.conf.skland_info:
            if not(item.account) or not(item.password):
                logger.warning(f"有未输入的账号或密码，请检查")
                continue
            if not(item.isCheck or item.endfield_isCheck):
                logger.info(f"账号：{item.account}未勾选，跳过签到")
                continue
            if self.has_record(item.account):
                continue
            self.all_recorded = False
            self.save_param(get_cred_by_token(log(item)))
            # 明日方舟森空岛签到
            for i in get_binding_list(self.sign_token):
                if i["gameId"] == 1 and item.isCheck:
                    if not(item.sign_in_bilibili) and i["channelName"] == "bilibili服":
                        logger.info(f"账号：{item.account}的b服未勾选，跳过签到")
                        continue
                    if not(item.sign_in_official) and i["channelName"] == "官服":
                        logger.info(f"账号：{item.account}的官服未勾选，跳过签到")
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
                            {"nickName": item.account, "game": "明日方舟", "reward": resp.get("message")}
                        )
                        logger.info(f"{i.get('nickName')}：{resp.get('message')}")
                        continue
                    awards = resp["data"]["awards"]
                    for j in awards:
                        res = j["resource"]
                        self.reward.append(
                            {
                                "nickName": item.account,
                                "game": "明日方舟",
                                "reward": "{}×{}".format(res["name"], j.get("count") or 1),
                            }
                        )
                        logger.info(
                            f"{i.get('nickName')}获得了{res['name']}×{j.get('count') or 1}"
                        )
                # 终末地森空岛签到
                if i["gameId"] == 3 and item.endfield_isCheck:
                    for j in i["roles"]:
                        if not(item.sign_in_endfield_bilibili) and i["channelName"] == "bilibili服":
                            logger.info(f"账号：{item.account}的终末地b服未勾选，跳过签到")
                            continue
                        if not(item.sign_in_endfield_official) and i["channelName"] == "官服":
                            logger.info(f"账号：{item.account}的终末地官服未勾选，跳过签到")
                            continue
                        body_endfield = {"gameId": 3, "roleId": j.get("roleId"), "serverId": j.get("serverId")}
                        headers_endfield = get_sign_header(sign_endfield_url, "post", body_endfield, self.sign_token, header)
                        headers_endfield["Content-Type"] = "application/json"
                        headers_endfield["sk-game-role"] = f"3_{j.get('roleId')}_{j.get('serverId')}"
                        headers_endfield["referer"] = "https://game.skland.com/"
                        headers_endfield["origin"] = "https://game.skland.com/"

                        resp = requests.post(
                            sign_endfield_url,
                            headers=headers_endfield,
                            json=body_endfield,
                        ).json()
                        if resp["code"] != 0:
                            self.reward.append(
                                {"nickname": item.account, "game": "终末地", "reward": resp.get("message")}
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
                                    "game": "终末地",
                                    "reward": "{}×{}".format(res["name"], res.get("count") or 1),
                                }
                            )
                            logger.info(
                                f"{j.get('nickname')}获得了{res['name']}×{res.get('count') or 1}"
                            )
        if len(self.reward) > 0:
            return self.record_log()
        if self.all_recorded:
            if len(self.reward) == 0:
                logger.warning(f"没有设置需要签到的账号！")
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
        date_str = datetime.datetime.now().strftime("%Y/%m/%d")
        logger.info(f"存入{date_str}的数据{self.reward}")
        try:
            for item in self.reward:
                res_df = pd.DataFrame(item, index=[date_str])
                res_df.to_csv(self.record_path, mode="a", header=False, encoding="gbk")
        except Exception as e:
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

            sign_arknights = False
            sign_endfield = False

            for item in df.iloc:
                if item[0] == datetime.datetime.now().strftime("%Y/%m/%d"):
                    if item[1].astype(str) == phone and item[2] == "明日方舟":
                        sign_arknights = True
                    if item[1].astype(str) == phone and item[2] == "终末地":
                        sign_endfield = True
                    if sign_arknights and sign_endfield:
                        logger.info(f"{phone}今天签到过了")
                        return True
            return False
        except PermissionError:
            logger.info("skland.csv正在被占用")
        except pd.errors.EmptyDataError:
            return False

    def test_connect(self):
        res = []
        for item in config.conf.skland_info:
            if item.isCheck or item.endfield_isCheck:
                try:
                    self.save_param(get_cred_by_token(log(item)))
                    for i in get_binding_list(self.sign_token):
                        if i["uid"] and i["gameId"] == 1:
                            res.append(
                                "{}连接成功".format(
                                    i["nickName"] + "({})".format(i["channelName"])
                                )
                            )
                        # 从roles列表中获取终末地角色信息
                        if i["roles"] and i["gameId"] == 3:
                            for j in i["roles"]:
                                res.append(
                                    "{}连接成功".format(
                                        j["nickname"] + "(终末地{})".format(i["channelName"])
                                    )
                                )
                except Exception as e:
                    msg = "{}无法连接-{}".format(item.account, e)
                    logger.exception(msg)
                    res.append(msg)
        return res
