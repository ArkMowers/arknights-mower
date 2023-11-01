import json
import csv
import datetime
import requests

from arknights_mower.utils.log import logger


class SKLand:
    def __init__(self, skland_info):
        self.account = []
        try:
            for item in skland_info:
                if item["isCheck"] is False:
                    continue
                if item['account'] != "" and item['password'] != "":
                    self.account.append({
                        "name": "",
                        "phone": item['account'],
                        "password": item['password'],
                        "uid": "",
                        "cred": ""
                    })
        except:
            raise RuntimeError("森空岛信息初始化失败")

        self.url = {
            "get_cred": "https://zonai.skland.com/api/v1/user/auth/generate_cred_by_code",
            "token_by_phone_password": "https://as.hypergryph.com/user/auth/v1/token_by_phone_password",
            "check_cred_url": "https://zonai.skland.com/api/v1/user/check",
            "OAuth2": "https://as.hypergryph.com/user/oauth2/v2/grant",
            "get_cred_url": "https://zonai.skland.com/api/v1/user/auth/generate_cred_by_code",
            "attendance": "https://zonai.skland.com/api/v1/game/attendance",
            "get_binding_player": "https://zonai.skland.com/api/v1/game/player/binding"
        }

        self.request_header = {
            "user-agent": "Skland/1.0.1 (com.hypergryph.skland; build:100001014; Android 33; ) Okhttp/4.11.0",
            "cred": '',
            "vName": "1.0.1",
            "vCode": "100001014",
            'Accept-Encoding': 'gzip',
            'Connection': 'close',
            "dId": "de9759a5afaa634f",
            "platform": "1"
        }

        self.get_award = {}
        self.record_path = "skland_record.csv"

    def respone_to_json(self, responese):
        try:
            responese_json = json.loads(responese.text)
            return responese_json
        except:
            raise RuntimeError("返回信息获取失败")

    """登录获取cred"""
    def sign_by_phone(self, account):
        data = {"phone": account['phone'], "password": account['password']}
        response = requests.post(headers=self.request_header, url=self.url.get("token_by_phone_password"), data=data)

        response_json = self.respone_to_json(response)
        if response_json.get("status") == 0:
            return response_json.get("data").get("token")
        else:
            raise RuntimeError("token获取失败")

    def check_cred(self, account):
        if account['cred'] == "":
            return False
        headers = self.request_header
        headers["cred"] = account['cred']
        response = requests.get(headers=headers, url=self.url.get("check_cred_url"))
        response_json = self.respone_to_json(response)

        if response_json.get("code") == 0:
            logger.debug("验证cred未过期")
        else:
            raise RuntimeError("验证cred过期")

    def get_binding_player(self, account):
        if account['cred'] == "":
            raise RuntimeError("获取绑定信息失败")
        headers = self.request_header
        headers["cred"] = account['cred']

        response = requests.get(headers=headers, url=self.url.get("get_binding_player"))
        response_json = self.respone_to_json(response)

        if response_json.get("code") == 0:
            logger.info("获取玩家信息成功")
            player_info = response_json.get('data').get('list')[0].get('bindingList')[0]
            account['name'] = player_info.get('nickName')
            account['uid'] = player_info.get('uid')
        else:
            raise RuntimeError("验证cred过期")

    def get_OAuth2_token(self, account):
        token = self.sign_by_phone(account)
        if token == "":
            raise RuntimeError("token获取失败")

        data = {
            "token": token,
            "appCode": "4ca99fa6b56cc2ba",
            "type": 0
        }
        response = requests.post(headers=self.request_header, url=self.url.get("OAuth2"), data=data)
        response_json = self.respone_to_json(response)
        if response_json.get("status") == 0:
            logger.debug("OAuth2授权代码获取成功")
            return response_json.get("data").get("code")

        return ""

    def get_cred(self, account):
        code = self.get_OAuth2_token(account)

        if code == "":
            raise RuntimeError("OAuth2授权代码获取失败")
        data = {
            "kind": 1,
            "code": code
        }
        response = requests.post(headers=self.request_header, url=self.url.get("get_cred_url"), data=data)
        response_json = self.respone_to_json(response)

        if response_json.get("code") == 0:
            account['cred'] = response_json.get("data").get("cred")

    def attendance(self):
        for account in self.account:
            if self.get_record(account['phone']):
                logger.info(f"{account['phone']} 今日已经签到过了")
                continue

            if self.check_cred(account) is False:
                self.get_cred(account)

            self.get_binding_player(account)
            logger.debug(account)
            data = {
                "uid": account["uid"],
                "gameId": 1
            }
            headers = self.request_header
            headers["cred"] = account['cred']
            response = requests.post(headers=headers, url=self.url.get("attendance"), data=data)

            response_json = self.respone_to_json(response)
            award = []
            if response_json["code"] == 0:

                for item in response_json.get("data").get("awards"):
                    temp_str = str(item["count"]) + str(item["resource"]["name"])
                    award.append(temp_str)
            elif response_json["code"] == 10001 and response_json["message"] == "请勿重复签到！":
                logger.info(f"{account['name']} 请勿重复签到！")
                award.append("请勿重复签到！")
            self.get_award[account['phone']] = award
            self.record_attendance(account['phone'], self.get_award[account['phone']])
        if self.get_award:
            logger.info(self.get_award)
        return self.get_award

    def record_attendance(self, account, data):

        data_row = [account, data, datetime.date.today()]
        with open(self.record_path, 'a+') as f:
            csv_write = csv.writer(f)
            csv_write.writerow(data_row)

    def get_record(self, account):

        try:
            with open(self.record_path, 'r+') as f:
                csv_reader = csv.reader(f)
                for line in csv_reader:
                    if line:
                        if line[0] == account and line[2] == str(datetime.date.today()):
                            return True
        except:
            with open(self.record_path, 'a+') as f:
                return False

        return False

    def test_connect(self):
        res = []
        for item in self.account:
            data = {"phone": item['phone'], "password": item['password']}
            response = requests.post(headers=self.request_header, url=self.url.get("token_by_phone_password"),
                                     data=data)

            response_json = self.respone_to_json(response)
            temp_res = {
                "account": item['phone'],
                'msg': response_json['msg']
            }
            res.append(temp_res)

        logger.info(res)

