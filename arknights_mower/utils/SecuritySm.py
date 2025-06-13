# from https://gitee.com/FancyCabbage/skyland-auto-sign

import base64
import gzip
import hashlib

# 数美加密方法类
import json
import time
import uuid

import requests
from cryptography.hazmat.decrepit.ciphers.algorithms import TripleDES
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import padding
from cryptography.hazmat.primitives.ciphers.algorithms import AES
from cryptography.hazmat.primitives.ciphers.base import Cipher
from cryptography.hazmat.primitives.ciphers.modes import CBC, ECB

# 查询dId请求头
devices_info_url = "https://fp-it.portal101.cn/deviceprofile/v4"

# 数美配置
SM_CONFIG = {
    "organization": "UWXspnCCJN4sfYlNfqps",
    "appId": "default",
    "publicKey": "MIGfMA0GCSqGSIb3DQEBAQUAA4GNADCBiQKBgQCmxMNr7n8ZeT0tE1R9j/mPixoinPkeM+k4VGIn/s0k7N5rJAfnZ0eMER+QhwFvshzo0LNmeUkpR8uIlU/GEVr8mN28sKmwd2gpygqj0ePnBmOW4v0ZVwbSYK+izkhVFk2V/doLoMbWy6b+UnA8mkjvg0iYWRByfRsK2gdl7llqCwIDAQAB",
    "protocol": "https",
    "apiHost": "fp-it.portal101.cn",
}

PK = serialization.load_der_public_key(base64.b64decode(SM_CONFIG["publicKey"]))

DES_RULE = {
    "appId": {
        "cipher": "DES",
        "is_encrypt": 1,
        "key": "uy7mzc4h",
        "obfuscated_name": "xx",
    },
    "box": {"is_encrypt": 0, "obfuscated_name": "jf"},
    "canvas": {
        "cipher": "DES",
        "is_encrypt": 1,
        "key": "snrn887t",
        "obfuscated_name": "yk",
    },
    "clientSize": {
        "cipher": "DES",
        "is_encrypt": 1,
        "key": "cpmjjgsu",
        "obfuscated_name": "zx",
    },
    "organization": {
        "cipher": "DES",
        "is_encrypt": 1,
        "key": "78moqjfc",
        "obfuscated_name": "dp",
    },
    "os": {
        "cipher": "DES",
        "is_encrypt": 1,
        "key": "je6vk6t4",
        "obfuscated_name": "pj",
    },
    "platform": {
        "cipher": "DES",
        "is_encrypt": 1,
        "key": "pakxhcd2",
        "obfuscated_name": "gm",
    },
    "plugins": {
        "cipher": "DES",
        "is_encrypt": 1,
        "key": "v51m3pzl",
        "obfuscated_name": "kq",
    },
    "pmf": {
        "cipher": "DES",
        "is_encrypt": 1,
        "key": "2mdeslu3",
        "obfuscated_name": "vw",
    },
    "protocol": {"is_encrypt": 0, "obfuscated_name": "protocol"},
    "referer": {
        "cipher": "DES",
        "is_encrypt": 1,
        "key": "y7bmrjlc",
        "obfuscated_name": "ab",
    },
    "res": {
        "cipher": "DES",
        "is_encrypt": 1,
        "key": "whxqm2a7",
        "obfuscated_name": "hf",
    },
    "rtype": {
        "cipher": "DES",
        "is_encrypt": 1,
        "key": "x8o2h2bl",
        "obfuscated_name": "lo",
    },
    "sdkver": {
        "cipher": "DES",
        "is_encrypt": 1,
        "key": "9q3dcxp2",
        "obfuscated_name": "sc",
    },
    "status": {
        "cipher": "DES",
        "is_encrypt": 1,
        "key": "2jbrxxw4",
        "obfuscated_name": "an",
    },
    "subVersion": {
        "cipher": "DES",
        "is_encrypt": 1,
        "key": "eo3i2puh",
        "obfuscated_name": "ns",
    },
    "svm": {
        "cipher": "DES",
        "is_encrypt": 1,
        "key": "fzj3kaeh",
        "obfuscated_name": "qr",
    },
    "time": {
        "cipher": "DES",
        "is_encrypt": 1,
        "key": "q2t3odsk",
        "obfuscated_name": "nb",
    },
    "timezone": {
        "cipher": "DES",
        "is_encrypt": 1,
        "key": "1uv05lj5",
        "obfuscated_name": "as",
    },
    "tn": {
        "cipher": "DES",
        "is_encrypt": 1,
        "key": "x9nzj1bp",
        "obfuscated_name": "py",
    },
    "trees": {
        "cipher": "DES",
        "is_encrypt": 1,
        "key": "acfs0xo4",
        "obfuscated_name": "pi",
    },
    "ua": {
        "cipher": "DES",
        "is_encrypt": 1,
        "key": "k92crp1t",
        "obfuscated_name": "bj",
    },
    "url": {
        "cipher": "DES",
        "is_encrypt": 1,
        "key": "y95hjkoo",
        "obfuscated_name": "cf",
    },
    "version": {"is_encrypt": 0, "obfuscated_name": "version"},
    "vpw": {
        "cipher": "DES",
        "is_encrypt": 1,
        "key": "r9924ab5",
        "obfuscated_name": "ca",
    },
}

BROWSER_ENV = {
    "plugins": "MicrosoftEdgePDFPluginPortableDocumentFormatinternal-pdf-viewer1,MicrosoftEdgePDFViewermhjfbmdgcfjbbpaeojofohoefgiehjai1",
    "ua": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/129.0.0.0 Safari/537.36 Edg/129.0.0.0",
    "canvas": "259ffe69",  # 基于浏览器的canvas获得的值，不知道复用行不行
    "timezone": -480,  # 时区，应该是固定值吧
    "platform": "Win32",
    "url": "https://www.skland.com/",  # 固定值
    "referer": "",
    "res": "1920_1080_24_1.25",  # 屏幕宽度_高度_色深_window.devicePixelRatio
    "clientSize": "0_0_1080_1920_1920_1080_1920_1080",
    "status": "0011",  # 不知道在干啥
}


# // 将浏览器环境对象的key全部排序，然后对其所有的值及其子对象的值加入数字并字符串相加。若值为数字，则乘以10000(0x2710)再将其转成字符串存入数组,最后再做md5,存入tn变量（tn变量要做加密）
# //把这个对象用加密规则进行加密，然后对结果做GZIP压缩（结果是对象，应该有序列化），最后做AES加密（加密细节目前不清除），密钥为变量priId
# //加密规则：新对象的key使用相对应加解密规则的obfuscated_name值，value为字符串化后进行进行DES加密，再进行btoa加密


# 通过测试
def _DES(o: dict):
    result = {}
    for i in o.keys():
        if i in DES_RULE.keys():
            rule = DES_RULE[i]
            res = o[i]
            if rule["is_encrypt"] == 1:
                c = Cipher(TripleDES(rule["key"].encode("utf-8")), ECB())
                data = str(res).encode("utf-8")
                # 补足字节
                data += b"\x00" * 8
                res = base64.b64encode(c.encryptor().update(data)).decode("utf-8")
            result[rule["obfuscated_name"]] = res
        else:
            result[i] = o[i]
    return result


# 通过测试
def _AES(v: bytes, k: bytes):
    iv = "0102030405060708"
    key = AES(k)
    c = Cipher(key, CBC(iv.encode("utf-8")))
    c.encryptor()
    # 填充明文
    v += b"\x00"
    while len(v) % 16 != 0:
        v += b"\x00"
    return c.encryptor().update(v).hex()


def GZIP(o: dict):
    # 这个压缩结果似乎和前台不太一样,不清楚是否会影响
    json_str = json.dumps(o, ensure_ascii=False)
    stream = gzip.compress(json_str.encode("utf-8"), 2, mtime=0)
    return base64.b64encode(stream)


# 获得tn的值,后续做DES加密用
# 通过测试
def get_tn(o: dict):
    sorted_keys = sorted(o.keys())

    result_list = []

    for i in sorted_keys:
        v = o[i]
        if isinstance(v, (int, float)):
            v = str(v * 10000)
        elif isinstance(v, dict):
            v = get_tn(v)
        result_list.append(v)
    return "".join(result_list)


def get_smid():
    t = time.localtime()
    _time = "{}{:0>2d}{:0>2d}{:0>2d}{:0>2d}{:0>2d}".format(
        t.tm_year, t.tm_mon, t.tm_mday, t.tm_hour, t.tm_min, t.tm_sec
    )
    uid = str(uuid.uuid4())
    v = _time + hashlib.md5(uid.encode("utf-8")).hexdigest() + "00"
    smsk_web = hashlib.md5(("smsk_web_" + v).encode("utf-8")).hexdigest()[0:14]
    return v + smsk_web + "0"


def get_d_id():
    # storageName = '.thumbcache_' + md5(SM_CONFIG['organization']) // 用于从本地存储获得值
    # uid = uuid()
    # priId=md5(uid)[0:16]
    # ep=rsa(uid,publicKey)
    # SMID = localStorage.get(storageName);// 获得本地存储存的值
    # _0x30b2eb为递归md5

    uid = str(uuid.uuid4()).encode("utf-8")
    priId = hashlib.md5(uid).hexdigest()[0:16]
    # ep不一定对，先走走看
    ep = PK.encrypt(uid, padding.PKCS1v15())
    ep = base64.b64encode(ep).decode("utf-8")

    browser = BROWSER_ENV.copy()
    current_time = int(time.time() * 1000)
    browser.update(
        {
            "vpw": str(uuid.uuid4()),
            "svm": current_time,
            "trees": str(uuid.uuid4()),
            "pmf": current_time,
        }
    )

    des_target = {
        **browser,
        "protocol": 102,
        "organization": SM_CONFIG["organization"],
        "appId": SM_CONFIG["appId"],
        "os": "web",
        "version": "3.0.0",
        "sdkver": "3.0.0",
        "box": "",  # 似乎是个SMID，但是第一次的时候是空,不过不影响结果
        "rtype": "all",
        "smid": get_smid(),
        "subVersion": "1.0.0",
        "time": 0,
    }
    des_target["tn"] = hashlib.md5(get_tn(des_target).encode()).hexdigest()

    des_result = _AES(GZIP(_DES(des_target)), priId.encode("utf-8"))

    response = requests.post(
        devices_info_url,
        json={
            "appId": "default",
            "compress": 2,
            "data": des_result,
            "encode": 5,
            "ep": ep,
            "organization": SM_CONFIG["organization"],
            "os": "web",  # 固定值
        },
    )

    resp = response.json()
    if resp["code"] != 1100:
        raise Exception("did计算失败，请联系作者")
    # 开头必须是B
    return "B" + resp["detail"]["deviceId"]
