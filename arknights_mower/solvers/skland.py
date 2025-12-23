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
    get_d_id,
    get_sign_header,
    header,
    header_login,
    log,
    sign_url,
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
            if self.has_record(item.account):
                continue
            self.all_recorded = False
            self.save_param(get_cred_by_token(log(item)))
            for i in get_binding_list(self.sign_token):
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
                        {"nickName": item.account, "reward": resp.get("message")}
                    )
                    logger.info(f"{i.get('nickName')}：{resp.get('message')}")
                    continue
                awards = resp["data"]["awards"]
                for j in awards:
                    res = j["resource"]
                    self.reward.append(
                        {
                            "nickName": item.account,
                            "reward": "{}×{}".format(res["name"], j.get("count") or 1),
                        }
                    )
                    logger.info(
                        f"{i.get('nickName')}获得了{res['name']}×{j.get('count') or 1}"
                    )
        if len(self.reward) > 0:
            return self.record_log()
        if self.all_recorded:
            return True
        return False

    def save_param(self, cred_resp):
        header["cred"] = cred_resp["cred"]
        self.sign_token = cred_resp["token"]

    def _load_record_dataframe(self):
        encodings = ("utf-8", "utf-8-sig", "gbk", "gb18030")
        last_error = None
        for idx, encoding in enumerate(encodings):
            try:
                if idx:
                    logger.debug(f"尝试使用编码 {encoding} 读取 skland.csv")
                return pd.read_csv(
                    self.record_path, header=None, encoding=encoding, on_bad_lines="skip"
                )
            except UnicodeDecodeError as exc:
                last_error = exc
                if idx == 0:
                    logger.warning(
                        "用 UTF-8 读取 skland.csv 失败，将尝试其它编码：%s", exc
                    )
                else:
                    logger.debug("编码 %s 读取 skland.csv 失败：%s", encoding, exc)
        if last_error:
            logger.error("skland.csv 编码异常，无法读取：%s", last_error)
        return None

    def log(self, account):
        headers = header_login.copy()
        headers["dId"] = get_d_id()
        r = requests.post(
            token_password_url,
            json={"phone": account.account, "password": account.password},
            headers=headers,
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
                res_df.to_csv(self.record_path, mode="a", header=False, encoding="utf-8")
        except Exception as e:
            logger.exception(e)

        return True

    def has_record(self, phone: str):
        try:
            if os.path.exists(self.record_path) is False:
                logger.debug("无森空岛记录")
                return False
            df = self._load_record_dataframe()
            if df is None:
                return False
            for item in df.iloc:
                if item[0] == datetime.datetime.now().strftime("%Y/%m/%d"):
                    if item[1].astype(str) == phone:
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
            if item.isCheck:
                try:
                    self.save_param(get_cred_by_token(log(item)))
                    for i in get_binding_list(self.sign_token):
                        if i["uid"]:
                            res.append(
                                "{}连接成功".format(
                                    i["nickName"] + "({})".format(i["channelName"])
                                )
                            )
                except Exception as e:
                    msg = "{}无法连接-{}".format(item.account, e)
                    logger.exception(msg)
                    res.append(msg)
        return res
