from collections import Counter
from dataclasses import dataclass
from email.utils import parsedate_to_datetime
from threading import Lock
from uuid import uuid4

import requests

from arknights_mower.utils import config
from arknights_mower.utils.csleep import MowerExit
from arknights_mower.utils.csv_utils import append_dict_rows
from arknights_mower.utils.log import logger
from arknights_mower.utils.path import get_path
from arknights_mower.utils.skland import (
    get_binding_list,
    get_cred_by_token,
    get_sign_header,
    header,
    log,
    sign_endfield_url,
    sign_url,
)
from arknights_mower.utils.skland_log import (
    redact_signing_text,
    sign_role_key,
    skland_day,
)
from arknights_mower.utils.skland_statistics import (
    ACCOUNT_FAILED,
    ACCOUNT_RECOVERED,
    EVENT_COMMITTED,
    SIGNED_OUTCOMES,
    classify_outcome,
    read_sign_in_state,
)

_SIGN_LOCK = Lock()
_SIGN_TIMEOUT = 10
_SIGN_CHANNELS = (
    (1, "官服", "arknights_isCheck", "sign_in_official"),
    (1, "bilibili服", "arknights_isCheck", "sign_in_bilibili"),
    (3, "官服", "endfield_isCheck", "sign_in_endfield_official"),
    (3, "bilibili服", "endfield_isCheck", "sign_in_endfield_bilibili"),
)


@dataclass(frozen=True)
class _SignTarget:
    game: str
    role_key: str
    url: str
    body: dict
    endfield_header: str | None = None


def _enabled_sign_in_channels(account):
    return {
        (game_id, channel)
        for game_id, channel, game_flag, channel_flag in _SIGN_CHANNELS
        if getattr(account, game_flag) and getattr(account, channel_flag, False)
    }


def enabled_sign_in_accounts():
    return [
        account
        for account in config.conf.skland_info
        if _enabled_sign_in_channels(account)
    ]


def _response_day(http_date):
    if isinstance(http_date, str):
        try:
            response_time = parsedate_to_datetime(http_date)
            if response_time.tzinfo is not None:
                return skland_day(response_time.timestamp())
        except (ValueError, OverflowError, OSError):
            pass
    return skland_day()


class SKLand:
    def __init__(self):
        self.record_path = get_path("@app/tmp/skland.csv")

        self.reward = []

        self.sign_token = ""
        self._headers = header.copy()
        self._record_encoding = "gbk"

        self.test_writecsv = True
        self._log_secrets = set()
        self._account_errors = []

    def start(self):
        with _SIGN_LOCK:
            return self._start()

    def _start(self):
        self.reward.clear()
        self._account_errors.clear()
        self.test_writecsv = True
        accounts = enabled_sign_in_accounts()
        if not accounts:
            logger.warning("森空岛签到未执行，未启用任何账号的游戏签到")
            return None

        logger.debug("开始森空岛签到")
        try:
            completed, account_failures, self._record_encoding = read_sign_in_state(
                self.record_path
            )
        except OSError:
            completed = set()
            account_failures = set()
            logger.warning("读取森空岛签到记录失败")

        all_complete = True
        for account in accounts:
            self._log_secrets.add(account.account)
            failure = "森空岛登录失败，请检查账号设置或网络连接"
            try:
                login_token = log(account)
                self._log_secrets.add(login_token)
                self.save_param(get_cred_by_token(login_token))
                failure = "读取森空岛签到角色失败，请检查网络连接后重试"
                targets = self._sign_targets(account)
            except MowerExit:
                raise
            except Exception as error:
                logger.warning(
                    "森空岛签到准备失败（%s）：%s",
                    type(error).__name__,
                    redact_signing_text(error, *self._log_secrets),
                )
                targets = []
            else:
                failure = "没有可签到的已启用角色，请检查账号的游戏和区服设置"

            day = skland_day()
            account_day = (day, account.account.strip())
            if not targets:
                account_name = redact_signing_text(account.account, account.account)
                message = f"森空岛账号 {account_name}：{failure}"
                logger.warning("%s", message)
                self._account_errors.append(message)
                if self._record_account_event(
                    account.account, day, ACCOUNT_FAILED, failure
                ):
                    account_failures.add(account_day)
                all_complete = False
                continue
            if account_day in account_failures:
                if self._record_account_event(
                    account.account, day, ACCOUNT_RECOVERED, ""
                ):
                    account_failures.discard(account_day)
                else:
                    all_complete = False
            for target in targets:
                day = skland_day()
                role = (day, account.account.strip(), target.game, target.role_key)
                if role in completed:
                    continue

                day, entries = self._sign(account.account, target)
                self.reward.extend(entries)
                saved = self.record_log(entries, day)
                outcome = classify_outcome(entries[0]["status"], entries[0]["reward"])
                if saved and outcome in SIGNED_OUTCOMES:
                    completed.add(
                        (day, account.account.strip(), target.game, target.role_key)
                    )
                else:
                    all_complete = False
        return all_complete

    def _sign_targets(self, account):
        enabled = _enabled_sign_in_channels(account)
        targets = {}
        for binding in get_binding_list(self.sign_token, old_header=self._headers):
            channel = binding["channelName"]
            game_id = binding["gameId"]
            if (game_id, channel) not in enabled:
                continue
            if game_id == 1:
                uid = binding.get("uid")
                if not uid:
                    continue
                self._log_secrets.update((uid, binding.get("nickName")))
                game = f"明日方舟{channel}"
                key = sign_role_key(account.account, game, uid)
                targets[key] = _SignTarget(
                    game, key, sign_url, {"gameId": 1, "uid": uid}
                )
            else:
                game = f"终末地{channel}"
                for role in binding.get("roles") or ():
                    role_id = role.get("roleId")
                    server_id = role.get("serverId")
                    if not role_id or server_id is None:
                        continue
                    self._log_secrets.update((role_id, role.get("nickname")))
                    key = sign_role_key(account.account, game, role_id, server_id)
                    body = {"gameId": 3, "roleId": role_id, "serverId": server_id}
                    targets[key] = _SignTarget(
                        game, key, sign_endfield_url, body, f"3_{role_id}_{server_id}"
                    )
        return list(targets.values())

    def _sign(self, account, target):
        headers = get_sign_header(
            target.url, "post", target.body, self.sign_token, self._headers
        )
        if target.endfield_header:
            headers.update(
                {
                    "Content-Type": "application/json",
                    "sk-game-role": target.endfield_header,
                    "referer": "https://game.skland.com/",
                    "origin": "https://game.skland.com",
                }
            )
        try:
            response = requests.post(
                target.url, headers=headers, json=target.body, timeout=_SIGN_TIMEOUT
            )
        except requests.RequestException:
            return skland_day(), self._entries(
                account, target, ["签到请求失败，请检查网络连接"], "failure", None
            )
        day = _response_day(response.headers.get("Date"))
        try:
            result = response.json()
            code = result["code"]
        except (KeyError, TypeError, ValueError):
            return day, self._entries(
                account, target, ["森空岛签到响应格式错误"], "failure", None
            )
        if code != 0:
            message = redact_signing_text(
                result.get("message") or "", *self._log_secrets
            )
            logger.info(
                "%s签到结果（状态码：%s）：%s",
                target.game,
                code if isinstance(code, int) else "未知",
                message,
            )
            rewards = [message]
            status = "failure"
        else:
            try:
                rewards = self._response_rewards(result["data"], target.endfield_header)
            except (AttributeError, KeyError, TypeError, ValueError):
                rewards = ["签到成功"]
                logger.warning("%s签到成功，奖励明细无法解析", target.game)
            status = "success"

        return day, self._entries(account, target, rewards, status, code)

    @staticmethod
    def _entries(account, target, rewards, status, code):
        event_id = uuid4().hex
        return [
            {
                "nickName": account,
                "game": target.game,
                "reward": reward,
                "status": status,
                "code": code,
                "role_key": target.role_key,
                "event_id": event_id,
            }
            for reward in rewards
        ]

    @staticmethod
    def _response_rewards(data, endfield_header):
        counts = Counter()
        if endfield_header:
            for award in data["awardIds"]:
                resource = data["resourceInfoMap"][award.get("id")]
                counts[resource["name"]] += int(resource.get("count") or 1)
        else:
            for award in data["awards"]:
                resource = award["resource"]
                counts[resource["name"]] += int(award.get("count") or 1)
        return [f"{item}×{count}" for item, count in counts.items()] or ["签到成功"]

    def save_param(self, cred_resp):
        self._headers["cred"] = cred_resp["cred"]
        self.sign_token = cred_resp["token"]
        self._log_secrets.update((cred_resp["cred"], cred_resp["token"]))

    def log(self, account):
        return log(account)

    def _record_account_event(self, account, day, status, message):
        return self._append_entries(
            [
                {
                    "nickName": account,
                    "reward": message,
                    "status": status,
                    "event_id": uuid4().hex,
                }
            ],
            day.strftime("%Y/%m/%d"),
        )

    def _append_entries(self, entries, date_str):
        rows = [
            {
                "date": date_str,
                "account": entry.get("nickname") or entry.get("nickName"),
                "game": entry.get("game"),
                "reward": entry.get("reward"),
                "status": entry.get("status"),
                "code": entry.get("code"),
                "role_key": entry.get("role_key"),
                "event_id": entry.get("event_id"),
            }
            for entry in entries
        ]
        event_ids = [entry.get("event_id") for entry in entries]
        output = []
        for index, row in enumerate(rows):
            output.append(row)
            event_id = event_ids[index]
            if event_id and event_id not in event_ids[index + 1 :]:
                # 同一个事件的记录行之后追加完成标记；读取时缺少标记即视为未写完。
                output.append(
                    {
                        "date": date_str,
                        "account": row["account"],
                        "game": "",
                        "reward": "",
                        "status": EVENT_COMMITTED,
                        "code": "",
                        "role_key": "",
                        "event_id": event_id,
                    }
                )
        try:
            for row in output:
                for value in row.values():
                    str(value).encode(self._record_encoding)
            append_dict_rows(
                self.record_path,
                output,
                header=False,
                encoding=self._record_encoding,
            )
        except (OSError, UnicodeError) as error:
            self.test_writecsv = False
            logger.error("森空岛签到记录写入失败（%s）", type(error).__name__)
            return False
        return True

    def record_log(self, entries=None, day=None):
        entries = self.reward if entries is None else entries
        day = skland_day() if day is None else day
        date_str = day.strftime("%Y/%m/%d")
        secrets = self._log_secrets | {
            entry.get("nickname") or entry.get("nickName") for entry in entries
        }
        safe_reward = [
            {
                key: value
                if key == "code" and isinstance(value, int)
                else redact_signing_text(value, *secrets)
                for key, value in entry.items()
            }
            for entry in entries
        ]
        logger.debug("%s的森空岛签到结果：%s", date_str, safe_reward)
        saved = self._append_entries(entries, date_str)
        lines = [
            f"已保存 {date_str} 的森空岛签到记录，共 {len(entries)} 条："
            if saved
            else f"{date_str} 的森空岛签到记录保存失败，本次签到结果如下："
        ]
        accounts = {}
        for original, safe in zip(entries, safe_reward):
            account = original.get("nickname") or original.get("nickName")
            accounts.setdefault(account, []).append(safe)
        for results in accounts.values():
            account = results[0].get("nickname") or results[0].get("nickName")
            lines.append(f"    账号 {account or '未标明账号'}：")
            for result in results:
                game = result.get("game", "未标明游戏")
                reward = result.get("reward") or "未返回结果"
                if result.get("status") == "success" and result.get("code") == 0:
                    outcome = f"签到成功，{reward}"
                elif classify_outcome(result.get("status"), reward) == "repeated":
                    outcome = f"已签到，{reward}"
                elif result.get("status") == "failure":
                    outcome = f"签到失败，{reward}"
                else:
                    outcome = f"签到结果，{reward}"
                lines.append(f"        {game}：{outcome}")
        logger.info("%s", "\n".join(lines))
        return saved

    # 用于测试连接
    def test_connect(self):
        res = []
        for item in config.conf.skland_info:
            try:
                login_token = log(item)
                self._log_secrets.update((item.account, login_token))
                self.save_param(get_cred_by_token(login_token))
                res.append(f"账号 {item.account}：")
                for i in get_binding_list(self.sign_token, old_header=self._headers):
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
            completed = self.start()
            if self.reward:
                seen = set()
                for info in self.reward:
                    event = info["event_id"]
                    if event in seen:
                        continue
                    seen.add(event)
                    outcome = classify_outcome(info["status"], info["reward"])
                    result = {
                        "signed": "签到成功",
                        "repeated": "已签到",
                        "failed": f"签到失败，{info['reward']}",
                    }[outcome]
                    res.append(
                        "{}{}{}".format(
                            info.get("nickname") or info.get("nickName"),
                            info.get("game"),
                            result,
                        )
                    )
            elif completed:
                res.append("勾选的账号今天均已签到~")
            elif not self._account_errors:
                res.append("签到未完成，请检查账号配置或网络")
            res.extend(self._account_errors)
            if not self.test_writecsv:
                res.append("签到数据写入失败")
                self.test_writecsv = True
        except Exception as e:
            msg = "测试出错-{}".format(e)
            logger.error(
                "森空岛测试签到失败（%s）：%s",
                type(e).__name__,
                redact_signing_text(e, *self._log_secrets),
            )
            res.append(msg)
        return res
