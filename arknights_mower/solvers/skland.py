import datetime
import os

import requests

from arknights_mower.utils import config
from arknights_mower.utils.csv_utils import EmptyDataError, read_csv_rows
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
from arknights_mower.utils.skland_log import redact_signing_text


class SKLand:
    def __init__(self):
        self.record_path = get_path("@app/tmp/skland.csv")

        self.reward = []

        self.sign_token = ""
        self.all_recorded = True

        self.test_writecsv = True
        self._log_secrets = set()

    def start(self):

        for item in config.conf.skland_info:
            if not (item.arknights_isCheck or item.endfield_isCheck):
                continue
            self._log_secrets.add(item.account)
            if self.has_record(item.account):
                continue

            self.all_recorded = False
            login_token = log(item)
            self._log_secrets.add(login_token)
            self.save_param(get_cred_by_token(login_token))

            # 明日方舟森空岛签到
            for i in get_binding_list(self.sign_token):
                if i["gameId"] == 1 and item.arknights_isCheck:
                    if not i.get("uid"):
                        continue
                    if nickname := i.get("nickName"):
                        self._log_secrets.add(nickname)
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
                        logger.info(
                            "明日方舟签到失败（状态码：%s）：%s",
                            resp["code"] if isinstance(resp["code"], int) else "未知",
                            redact_signing_text(
                                resp.get("message", ""),
                                self.sign_token,
                                *self._log_secrets,
                            ),
                        )
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
                            f"明日方舟{i.get('channelName')}签到获得了{res['name']}×{j.get('count') or 1}"
                        )
                # 终末地森空岛签到
                if i["gameId"] == 3 and item.endfield_isCheck:
                    for j in i.get("roles"):
                        if not j.get("roleId"):
                            continue
                        if nickname := j.get("nickname"):
                            self._log_secrets.add(nickname)
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
                            logger.info(
                                "终末地签到失败（状态码：%s）：%s",
                                resp["code"]
                                if isinstance(resp["code"], int)
                                else "未知",
                                redact_signing_text(
                                    resp.get("message", ""),
                                    self.sign_token,
                                    *self._log_secrets,
                                ),
                            )
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
                                f"终末地{i.get('channelName')}签到获得了{res['name']}×{res.get('count') or 1}"
                            )
        if len(self.reward) > 0:
            return self.record_log()
        if self.all_recorded:
            return True
        return False

    def save_param(self, cred_resp):
        header["cred"] = cred_resp["cred"]
        self.sign_token = cred_resp["token"]
        self._log_secrets.update((cred_resp["cred"], cred_resp["token"]))

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
        secrets = self._log_secrets | {
            entry.get("nickname") or entry.get("nickName") for entry in self.reward
        }
        safe_reward = [
            {key: redact_signing_text(value, *secrets) for key, value in entry.items()}
            for entry in self.reward
        ]
        logger.info("存入%s的森空岛签到数据%s", date_str, safe_reward)
        try:
            from arknights_mower.utils.csv_utils import append_dated_row

            for item in self.reward:
                append_dated_row(
                    self.record_path,
                    date_str,
                    item,
                    header=False,
                    encoding="gbk",
                )
        except Exception as e:
            self.test_writecsv = False
            logger.error("森空岛签到记录写入失败（%s）", type(e).__name__)
        return True

    def has_record(self, phone: str):
        try:
            if os.path.exists(self.record_path) is False:
                logger.debug("无森空岛记录")
                return False
            rows = read_csv_rows(self.record_path, header=False, encoding="gbk")

            sign_arknights_official = False
            sign_arknights_bilbili = False
            sign_endfield_official = False
            sign_endfield_bilibili = False

            for line_no, item in enumerate(rows, start=1):
                if len(item) < 3:
                    logger.warning(
                        "跳过不完整的森空岛签到记录：第%s行，仅%s列",
                        line_no,
                        len(item),
                    )
                    continue
                if (item[0] == datetime.datetime.now().strftime("%Y/%m/%d")) and (
                    str(item[1]) == phone
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
                        logger.info("森空岛账号今天已签到")
                        return True
            return False
        except PermissionError:
            logger.info("skland.csv正在被占用")
        except EmptyDataError:
            return False

    # 用于测试连接
    def test_connect(self):
        res = []
        for item in config.conf.skland_info:
            try:
                login_token = log(item)
                self._log_secrets.update((item.account, login_token))
                self.save_param(get_cred_by_token(login_token))
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
                logger.error(
                    "森空岛账号连接失败（%s）：%s",
                    type(e).__name__,
                    redact_signing_text(e, *self._log_secrets),
                )
                res.append(msg)
        return res

    # 用于测试签到
    def test_sign(self):
        res = []

        try:
            if bool(self.start()):
                if self.reward:
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
                else:
                    res.append("勾选的账号今天均已签到~")
                return res
            else:
                res.append("签到未完成，请检查账号配置或网络")
                return res
        except Exception as e:
            msg = "测试出错-{}".format(e)
            logger.error(
                "森空岛测试签到失败（%s）：%s",
                type(e).__name__,
                redact_signing_text(e, *self._log_secrets),
            )
            res.append(msg)
        return res
