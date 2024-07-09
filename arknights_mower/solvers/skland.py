import hashlib
import hmac
import json
import datetime
import os
import time
from urllib import parse

import pandas as pd
import requests

from arknights_mower.utils.log import logger
from arknights_mower.utils.path import get_path

app_code = "4ca99fa6b56cc2ba"

# 签到url
sign_url = "https://zonai.skland.com/api/v1/game/attendance"
# 绑定的角色url
binding_url = "https://zonai.skland.com/api/v1/game/player/binding"
# 验证码url
login_code_url = "https://as.hypergryph.com/general/v1/send_phone_code"
# 验证码登录
token_phone_code_url = "https://as.hypergryph.com/user/auth/v2/token_by_phone_code"
# 密码登录
token_password_url = "https://as.hypergryph.com/user/auth/v1/token_by_phone_password"
# 使用token获得认证代码
grant_code_url = "https://as.hypergryph.com/user/oauth2/v2/grant"
# 使用认证代码获得cred
cred_code_url = "https://zonai.skland.com/api/v1/user/auth/generate_cred_by_code"


class SKLand:
    def __init__(self, skland_info):
        self.record_path = get_path("@app/tmp/skland.csv")
        self.account_list = []
        for item in skland_info:
            self.account_list.append(
                {
                    "account": item["account"],
                    "isCheck": item["isCheck"],
                    "password": item["password"],
                    "sign_in_official": item["sign_in_official"],
                    "sign_in_bilibili": item["sign_in_bilibili"],
                    "cultivate_select": item["cultivate_select"],
                }
            )

        self.header = {
            "cred": "",
            "User-Agent": "Skland/1.0.1 (com.hypergryph.skland; build:100001014; Android 31; ) Okhttp/4.11.0",
            "Accept-Encoding": "gzip",
            "Connection": "close",
        }
        self.header_login = {
            "User-Agent": "Skland/1.0.1 (com.hypergryph.skland; build:100001014; Android 31; ) Okhttp/4.11.0",
            "Accept-Encoding": "gzip",
            "Connection": "close",
        }

        self.reward = []
        # 签名请求头一定要这个顺序，否则失败
        # timestamp是必填的,其它三个随便填,不要为none即可
        self.header_for_sign = {"platform": "", "timestamp": "", "dId": "", "vName": ""}
        self.sign_token = ""
        self.all_recorded = True

    def start(self):
        for item in self.account_list:
            if item["isCheck"]:
                if self.has_record(item["account"]):
                    continue
                self.all_recorded = False
                self.save_param(self.get_cred_by_token(self.log(item)))
                for i in self.get_binding_list():
                    body = {"gameId": 1, "uid": i.get("uid")}
                    # list_awards(1, i.get('uid'))
                    resp = requests.post(
                        sign_url,
                        headers=self.get_sign_header(
                            sign_url, "post", body, self.header
                        ),
                        json=body,
                    ).json()
                    if resp["code"] != 0:
                        self.reward.append(
                            {"nickName": item["account"], "reward": resp.get("message")}
                        )
                        logger.info(f'{i.get("nickName")}：{resp.get("message")}')
                        continue
                    awards = resp["data"]["awards"]
                    for j in awards:
                        res = j["resource"]
                        self.reward.append(
                            {
                                "nickName": item["account"],
                                "reward": "{}×{}".format(
                                    res["name"], j.get("count") or 1
                                ),
                            }
                        )
                        logger.info(
                            f'{i.get("nickName")}获得了{res["name"]}×{j.get("count") or 1}'
                        )
        if len(self.reward) > 0:
            return self.record_log()
        if self.all_recorded:
            return True
        return False

    def save_param(self, cred_resp):
        self.header["cred"] = cred_resp["cred"]
        self.sign_token = cred_resp["token"]

    def log(self, account):
        r = requests.post(
            token_password_url,
            json={"phone": account["account"], "password": account["password"]},
            headers=self.header_login,
        ).json()
        if r.get("status") != 0:
            raise Exception(f'获得token失败：{r["msg"]}')
        return r["data"]["token"]

    def get_cred_by_token(self, token):
        return self.get_cred(self.get_grant_code(token))

    def get_grant_code(self, token):
        response = requests.post(
            grant_code_url,
            json={"appCode": app_code, "token": token, "type": 0},
            headers=self.header_login,
        )
        resp = response.json()
        if response.status_code != 200:
            raise Exception(f"获得认证代码失败：{resp}")
        if resp.get("status") != 0:
            raise Exception(f'获得认证代码失败：{resp["msg"]}')
        return resp["data"]["code"]

    def get_cred(self, grant):
        resp = requests.post(
            cred_code_url, json={"code": grant, "kind": 1}, headers=self.header_login
        ).json()
        if resp["code"] != 0:
            raise Exception(f'获得cred失败：{resp["message"]}')
        return resp["data"]

    def get_binding_list(self):
        v = []
        resp = requests.get(
            binding_url,
            headers=self.get_sign_header(binding_url, "get", None, self.header),
        ).json()

        if resp["code"] != 0:
            print(f"请求角色列表出现问题：{resp['message']}")
            if resp.get("message") == "用户未登录":
                print("用户登录可能失效了，请重新运行此程序！")
                return []
        for i in resp["data"]["list"]:
            if i.get("appCode") != "arknights":
                continue
            v.extend(i.get("bindingList"))
        return v

    def get_sign_header(self, url: str, method, body, old_header):
        h = json.loads(json.dumps(old_header))
        p = parse.urlparse(url)
        if method.lower() == "get":
            h["sign"], header_ca = self.generate_signature(
                self.sign_token, p.path, p.query
            )
        else:
            h["sign"], header_ca = self.generate_signature(
                self.sign_token, p.path, json.dumps(body)
            )
        for i in header_ca:
            h[i] = header_ca[i]
        return h

    def generate_signature(self, token: str, path, body_or_query):
        """
        获得签名头
        接口地址+方法为Get请求？用query否则用body+时间戳+ 请求头的四个重要参数（dId，platform，timestamp，vName）.toJSON()
        将此字符串做HMAC加密，算法为SHA-256，密钥token为请求cred接口会返回的一个token值
        再将加密后的字符串做MD5即得到sign
        :param token: 拿cred时候的token
        :param path: 请求路径（不包括网址）
        :param body_or_query: 如果是GET，则是它的query。POST则为它的body
        :return: 计算完毕的sign
        """
        # 总是说请勿修改设备时间，怕不是yj你的服务器有问题吧，所以这里特地-2

        t = str(int(time.time()) - 2)
        token = token.encode("utf-8")
        header_ca = json.loads(json.dumps(self.header_for_sign))
        header_ca["timestamp"] = t
        header_ca_str = json.dumps(header_ca, separators=(",", ":"))
        s = path + body_or_query + t + header_ca_str
        hex_s = hmac.new(token, s.encode("utf-8"), hashlib.sha256).hexdigest()
        md5 = (
            hashlib.md5(hex_s.encode("utf-8"))
            .hexdigest()
            .encode("utf-8")
            .decode("utf-8")
        )
        return md5, header_ca

    def record_log(self):
        date_str = datetime.datetime.now().strftime("%Y/%m/%d")
        logger.info(f"存入{date_str}的数据{self.reward}")
        try:
            for item in self.reward:
                res_df = pd.DataFrame(item, index=[date_str])
                res_df.to_csv(self.record_path, mode="a", header=False, encoding="gbk")
        except Exception:
            pass

        return True

    def has_record(self, phone: str):
        try:
            if os.path.exists(self.record_path) is False:
                logger.debug("无森空岛记录")
                return False
            df = pd.read_csv(
                self.record_path, header=None, encoding="gbk", on_bad_lines="skip"
            )
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
        for item in self.account_list:
            if item["isCheck"]:
                try:
                    self.save_param(self.get_cred_by_token(self.log(item)))
                    for i in self.get_binding_list():
                        if i["uid"]:
                            res.append(
                                "{}连接成功".format(
                                    i["nickName"] + "({})".format(i["channelName"])
                                )
                            )
                except Exception as e:
                    res.append("{}无法连接-{}".format(item["account"], e))

        return res
