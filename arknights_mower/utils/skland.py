import hashlib
import hmac
import json
import time
from urllib import parse

import requests

from arknights_mower.utils.log import logger
from arknights_mower.utils.SecuritySm import get_d_id

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
cred_code_url = "https://zonai.skland.com/web/v1/user/auth/generate_cred_by_code"
header = {
    "cred": "",
    "User-Agent": "Skland/1.0.1 (com.hypergryph.skland; build:100001014; Android 31; ) Okhttp/4.11.0",
    "Accept-Encoding": "gzip",
    "Connection": "close",
}
header_login = {
    "User-Agent": "Skland/1.0.1 (com.hypergryph.skland; build:100001014; Android 31; ) Okhttp/4.11.0",
    "Accept-Encoding": "gzip",
    "Connection": "close",
    "dId": get_d_id(),
}
header_for_sign = {"platform": "", "timestamp": "", "dId": "", "vName": ""}


def generate_signature(token: str, path, body_or_query):
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
    header_ca = json.loads(json.dumps(header_for_sign))
    header_ca["timestamp"] = t
    header_ca_str = json.dumps(header_ca, separators=(",", ":"))
    s = path + body_or_query + t + header_ca_str
    hex_s = hmac.new(token, s.encode("utf-8"), hashlib.sha256).hexdigest()
    md5 = hashlib.md5(hex_s.encode("utf-8")).hexdigest().encode("utf-8").decode("utf-8")
    return md5, header_ca


def get_sign_header(url: str, method, body, sign_token, old_header=header):
    h = json.loads(json.dumps(old_header))
    p = parse.urlparse(url)
    if method.lower() == "get":
        h["sign"], header_ca = generate_signature(sign_token, p.path, p.query)
    else:
        h["sign"], header_ca = generate_signature(sign_token, p.path, json.dumps(body))
    for i in header_ca:
        h[i] = header_ca[i]
    return h


def get_grant_code(token):
    response = requests.post(
        grant_code_url,
        json={"appCode": app_code, "token": token, "type": 0},
        headers=header_login,
    )
    resp = response.json()
    if response.status_code != 200:
        raise Exception(f"获得认证代码失败：{resp}")
    if resp.get("status") != 0:
        raise Exception(f'获得认证代码失败：{resp["msg"]}')
    return resp["data"]["code"]


def get_cred(grant):
    """
    获取cred
    :param cred_code_url: 获取cred的URL
    :param grant: 授权代码
    :param header_login: 登录请求头
    :return: cred
    """
    resp = requests.post(
        cred_code_url, json={"code": grant, "kind": 1}, headers=header_login
    ).json()

    if resp["code"] != 0:
        raise Exception(f'获得cred失败：{resp["message"]}')

    return resp["data"]


def get_binding_list(sign_token):
    v = []
    resp = requests.get(
        binding_url,
        headers=get_sign_header(
            binding_url,
            "get",
            None,
            sign_token,
        ),
    ).json()

    if resp["code"] != 0:
        logger.info(f"请求角色列表出现问题：{resp['message']}")
        if resp.get("message") == "用户未登录":
            logger.warning("用户登录可能失效了，请重新运行此程序！")
            return []
    for i in resp["data"]["list"]:
        if i.get("appCode") != "arknights":
            continue
        v.extend(i.get("bindingList"))
    return v


def get_cred_by_token(token):
    return get_cred(get_grant_code(token))


def log(account):
    r = requests.post(
        token_password_url,
        json={"phone": account.account, "password": account.password},
        headers=header_login,
    ).json()
    if r.get("status") != 0:
        raise Exception(f'获得token失败：{r["msg"]}')
    logger.info("森空岛登陆成功")
    return r["data"]["token"]
