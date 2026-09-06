import datetime
import hashlib
import hmac
import json
import time
from urllib import parse

import requests

from arknights_mower.utils.config import atomic_write
from arknights_mower.utils.log import logger
from arknights_mower.utils.path import get_path
from arknights_mower.utils.SecuritySm import get_d_id

app_code = "4ca99fa6b56cc2ba"

# Global session cache - persists for entire program runtime
skland_cache = {}

# 签到url
sign_url = "https://zonai.skland.com/api/v1/game/attendance"
# 终末地签到url
sign_endfield_url = "https://zonai.skland.com/web/v1/game/endfield/attendance"
# 绑定的角色url
binding_url = "https://zonai.skland.com/api/v1/game/player/binding"
player_info_url = "https://zonai.skland.com/api/v1/game/player/info"
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
SKLAND_VERSION = "1.62.0"
SKLAND_BUILD = "106200040"
SKLAND_ANDROID = "36"
# UA 由上面三值拼出，避免版本号/构建号/系统版本在多处重复、漏改漂移
SKLAND_UA = (
    f"Skland/{SKLAND_VERSION} (com.hypergryph.skland; build:{SKLAND_BUILD}; "
    f"Android {SKLAND_ANDROID}; ) Okhttp/4.11.0"
)
header = {
    "cred": "",
    "User-Agent": SKLAND_UA,
    "Accept-Encoding": "gzip",
    "Connection": "close",
}
header_login = {
    "User-Agent": SKLAND_UA,
    "Accept-Encoding": "gzip",
    "Connection": "close",
    "dId": "",
}
# 签名携带的四个参数：platform 固定为 1（Android），vName 与 UA 版本号一致，
# dId 在 generate_signature 中惰性填充（与登录请求共用 _ensure_device_id 缓存）。
# 请求头发送的字段与签名输入保持自洽，避免服务器未来对字段做非空校验时被拒
header_for_sign = {"platform": "1", "timestamp": "", "dId": "", "vName": SKLAND_VERSION}

# 模块级状态：设备指纹与服务器时钟偏移，均由下列函数惰性维护。
# 设备指纹导入时不联网（fp-it 服务不可达也不会导致导入崩溃），首次登录前取，
# 重试几次仍失败才降级为空串，随后本程序运行期间不再重试（_device_id_failed 短路），
# 避免反复捶打不可达服务、重复刷警告；
# 时钟偏移由 _sync_server_time 从每次响应校准，签名时间戳用它落在服务器时间上。
_device_id = ""
_device_id_failed = False
server_time_offset = 0

# 设备指纹（dId）落盘文件：dId 是数美（fp-it）签发的设备身份，设备级且长期稳定。
# 复用上次签发的结果能扛住指纹服务临时不可达/被阻断（正是「设备信息无效」的根因），
# 不必每次运行都重新联网去要。
_DEVICE_ID_FILE = get_path("@app/config/skland_device_id.json", space="")
# 指纹服务偶发超时：取不到时重试几次再放弃，避免一次瞬时故障就让整个运行期的森空岛认证落空。
_DEVICE_ID_RETRIES = 3


def _read_persisted_did() -> str:
    """读上次落盘的 dId；文件缺失或内容非法时返回空串。"""
    try:
        data = json.loads(_DEVICE_ID_FILE.read_text("utf-8"))
        did = data.get("dId", "")
        return did if isinstance(did, str) else ""
    except Exception:
        return ""


def _write_persisted_did(did: str) -> None:
    """幂等写落盘 dId；写入失败不影响本次运行（仅下次无法复用）。"""
    try:
        atomic_write(_DEVICE_ID_FILE, lambda f: json.dump({"dId": did}, f))
    except Exception:
        pass


def _invalidate_device_id() -> None:
    """认证因设备指纹被拒（设备信息无效）时清掉内存与落盘 dId，下次重新取。"""
    global _device_id, _device_id_failed
    _device_id = ""
    _device_id_failed = False
    try:
        _DEVICE_ID_FILE.unlink()
    except Exception:
        pass


def _ensure_device_id() -> str:
    """取森空岛设备指纹；服务不可达时降级为空串，不抛异常。

    优先用上次落盘的 dId（不再联网）；没有才去 fp-it 取，重试几次仍失败才放弃，
    并在本次运行期间不再尝试（_device_id_failed 短路）。
    """
    global _device_id, _device_id_failed
    if _device_id_failed:
        return _device_id
    if not _device_id:
        _device_id = _read_persisted_did()
    if not _device_id:
        for attempt in range(_DEVICE_ID_RETRIES):
            try:
                _device_id = get_d_id()
                _write_persisted_did(_device_id)
                break
            except Exception:
                if attempt == _DEVICE_ID_RETRIES - 1:
                    _device_id_failed = True
                    logger.warning(
                        "设备指纹获取失败（设备信息服务不可达），设备校验可能被拒"
                    )
                else:
                    time.sleep(1)
    return _device_id


def _offset_from_server_epoch(server_epoch) -> int | None:
    """服务器 epoch 与本机时间的偏移（秒）；epoch 非法时返回 None。"""
    try:
        return int(server_epoch) - int(time.time())
    except (TypeError, ValueError):
        return None


def _sync_server_time(resp):
    """从响应刷新服务器时间偏移：优先 HTTP Date 头，其次错误响应 body 的 timestamp 字段。"""
    global server_time_offset
    date = resp.headers.get("Date")
    if date:
        try:
            srv = datetime.datetime.strptime(date, "%a, %d %b %Y %H:%M:%S GMT").replace(
                tzinfo=datetime.timezone.utc
            )
            server_time_offset = _offset_from_server_epoch(srv.timestamp())
            return
        except ValueError:
            pass
    try:
        body = resp.json()
    except Exception:
        return
    ts = body.get("timestamp") if isinstance(body, dict) else None
    if ts:
        offset = _offset_from_server_epoch(ts)
        if offset is not None:
            server_time_offset = offset


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
    # 服务器对本机时钟偏差敏感：签名时间戳用服务器时间校准（_sync_server_time
    # 算出的偏移），再减 2 秒落在过去窗口内，避免「请勿修改设备本地时间」

    t = str(int(time.time()) + server_time_offset - 2)
    token = token.encode("utf-8")
    header_ca = json.loads(json.dumps(header_for_sign))
    header_ca["timestamp"] = t
    if not header_ca["dId"]:
        # dId 惰性取：与 header_login 共用 _device_id 缓存，保证登录与签名自洽
        header_ca["dId"] = _ensure_device_id()
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
        raise Exception(f"获得认证代码失败：{resp['msg']}")
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
        # 「设备信息无效」是 dId 失效/丢失的信号：清掉内存与落盘缓存，
        # 让下次认证重新取一个新的，避免连续复用同一个失效 dId
        if resp.get("message") == "设备信息无效":
            _invalidate_device_id()
        raise Exception(f"获得cred失败：{resp['message']}")

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
        timeout=30,
    )
    _sync_server_time(resp)
    body = resp.json()

    if body["code"] != 0:
        logger.info(f"请求角色列表出现问题：{body['message']}")
        if body.get("message") == "用户未登录":
            logger.warning("用户登录可能失效了，请重新运行此程序！")
        return []
    for i in body["data"]["list"]:
        if i.get("appCode") not in ("arknights", "endfield"):
            continue
        v.extend(i.get("bindingList"))
    return v


def get_cred_by_token(token):
    return get_cred(get_grant_code(token))


def log(account):
    header_login["dId"] = _ensure_device_id()
    if not header_login["dId"]:
        # 取不到 dId 时不应以空串继续请求：森空岛后端在换 cred 时会把空 dId 视为无效设备，
        # 误报「设备信息无效」。提前中止，明确报指纹服务不可达。
        raise Exception("设备指纹服务不可达，无法认证森空岛")
    resp = requests.post(
        token_password_url,
        json={"phone": account.account, "password": account.password},
        headers=header_login,
        timeout=30,
    )
    _sync_server_time(resp)
    r = resp.json()
    if r.get("status") != 0:
        raise Exception(f"获得token失败：{r['msg']}")
    logger.info("森空岛登陆成功")
    return r["data"]["token"]


def restore_cached_session(account: str) -> dict | None:
    """
    Restore a cached session if it exists.

    Args:
        account: Account identifier

    Returns:
        dict with 'sign_token' and 'cred' keys, or None if not found
    """
    session = skland_cache.get(account)
    if not session:
        return None
    return session


def refresh_session(item):
    """
    Refresh a session by getting new credentials.

    Args:
        item: Account item with account attribute

    Returns:
        dict with 'cred', 'sign_token', and 'updated_at' keys
    """
    cred_resp = get_cred_by_token(log(item))
    session_data = {
        "cred": cred_resp["cred"],
        "sign_token": cred_resp["token"],
        "updated_at": datetime.datetime.now(datetime.timezone.utc),
    }
    skland_cache[item.account] = session_data
    return session_data
