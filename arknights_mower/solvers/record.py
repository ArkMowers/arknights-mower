# 用于记录Mower操作行为
import collections
import pickle
import sqlite3
from datetime import datetime, timedelta

import pytz
from tzlocal import get_localzone

from arknights_mower.utils import config
from arknights_mower.utils.log import logger
from arknights_mower.utils.path import get_path


# 记录干员进出站以及心情数据，将记录信息存入agent_action表里
def save_action_to_sqlite_decorator(func):
    def wrapper(self, name, mood, current_room, current_index, update_time=False):
        agent = self.operators[name]  # 干员

        agent_current_room = agent.current_room  # 干员所在房间
        agent_is_high = agent.is_high()  # 是否高优先级

        # 调用原函数
        result = func(self, name, mood, current_room, current_index, update_time)
        if not update_time:
            return
        # 保存到数据库
        current_time = datetime.now()
        database_path = get_path("@app/tmp/data.db")

        try:
            # Create 'tmp' directory if it doesn't exist
            get_path("@app/tmp").mkdir(exist_ok=True)

            connection = sqlite3.connect(database_path)
            cursor = connection.cursor()

            # Create a table if it doesn't exist
            cursor.execute(
                "CREATE TABLE IF NOT EXISTS agent_action ("
                "name TEXT,"
                "agent_current_room TEXT,"
                "current_room TEXT,"
                "is_high INTEGER,"
                "agent_group TEXT,"
                "mood REAL,"
                "current_time TEXT"
                ")"
            )

            # Insert data
            cursor.execute(
                "INSERT INTO agent_action VALUES (?, ?, ?, ?, ?, ?, ?)",
                (
                    name,
                    agent_current_room,
                    current_room,
                    int(agent_is_high),
                    agent.group,
                    mood,
                    str(current_time),
                ),
            )

            connection.commit()
            connection.close()

            # Log the action
            logger.debug(
                f"Saved action to SQLite: Name: {name}, Agent's Room: {agent_current_room}, Agent's group: {agent.group}, "
                f"Current Room: {current_room}, Is High: {agent_is_high}, Current Time: {current_time}"
            )

        except sqlite3.Error as e:
            logger.error(f"SQLite error: {e}")

        return result

    return wrapper


def save_state(func):
    def save_wrapper(*args, **kwargs):
        from arknights_mower.__main__ import base_scheduler

        saved_state = {
            "dorm": base_scheduler.op_data.dorm,
            "tasks": base_scheduler.tasks,
            "party_time": base_scheduler.op_data.party_time,
            "operators": base_scheduler.op_data.operators,
            "daily_visit_friend": base_scheduler.daily_visit_friend,
            "daily_report": base_scheduler.daily_report,
            "daily_skland": base_scheduler.daily_skland,
            "daily_mail": base_scheduler.daily_mail,
            "task_count": base_scheduler.task_count,
            "skill_upgrade_supports": base_scheduler.op_data.skill_upgrade_supports,
        }

        # Call the original function
        result = func(*args, **kwargs)

        # Save saved_state to database
        current_time = datetime.now()
        database_path = get_path("@app/tmp/data.db")

        try:
            # Create 'tmp' directory if it doesn't exist
            get_path("@app/tmp").mkdir(exist_ok=True)

            connection = sqlite3.connect(database_path)
            cursor = connection.cursor()

            # Create a table if it doesn't exist
            cursor.execute(
                "CREATE TABLE IF NOT EXISTS saved_state (time TEXT,state BLOB)"
            )

            # Delete the previous saved state
            cursor.execute("DELETE FROM saved_state")

            # Insert data
            cursor.execute(
                "INSERT INTO saved_state VALUES (?, ?)",
                (
                    str(current_time),
                    sqlite3.Binary(pickle.dumps(saved_state)),  # Serialize saved_state
                ),
            )

            connection.commit()
            connection.close()

            logger.info(f"储存缓存数据至数据库 {current_time}")

        except sqlite3.Error as e:
            logger.error(f"SQLite error: {e}")

        return result

    return save_wrapper


def load_state():
    # Initialize an empty variable to hold the loaded state
    loaded_state = None
    database_path = get_path("@app/tmp/data.db")

    try:
        connection = sqlite3.connect(database_path)
        cursor = connection.cursor()

        # Query the last saved state
        cursor.execute("SELECT state FROM saved_state ORDER BY time DESC LIMIT 1")
        row = cursor.fetchone()

        if row is not None:
            loaded_state = pickle.loads(row[0])  # Deserialize the state
        else:
            logger.debug("No saved state found in the database")

        connection.close()

    except sqlite3.Error as e:
        logger.error(f"SQLite error: {e}")

    return loaded_state


def clear_data(date_time):
    database_path = get_path("@app/tmp/data.db")
    try:
        connection = sqlite3.connect(database_path)
        cursor = connection.cursor()

        # Ensure date_time is in the correct format
        if isinstance(date_time, datetime):
            date_time_str = date_time.strftime("%Y-%m-%d %H:%M:%S")
        else:
            date_time_str = date_time

        # Execute the DELETE statement with parameterized query
        cursor.execute(
            "DELETE FROM agent_action WHERE `current_time` < ?", (date_time_str,)
        )

        connection.commit()
        connection.close()
        logger.info(f"已删除 早于 {date_time_str} 的干员心情记录")

    except sqlite3.Error as e:
        logger.error(f"SQLite error: {e}")


def get_work_rest_ratios():
    # TODO 整理数据计算工休比
    database_path = get_path("@app/tmp/data.db")
    favorite = [] if config.conf.favorite == '' else config.conf.favorite.split(',')
    sel = ''
    for name in favorite:
        sel = sel + """
                UNION
                SELECT '{}' AS name
            """.format(name)
    try:
        # 连接到数据库
        conn = sqlite3.connect(database_path)
        # conn = sqlite3.connect('../../tmp/data.db')
        cursor = conn.cursor()
        # 查询数据
        cursor.execute("""
                        SELECT a.*
                        FROM agent_action a
                        JOIN (
                            SELECT DISTINCT b.name
                            FROM agent_action b
                            WHERE DATE(b.current_time) >= DATE('now', '-7 day', 'localtime')
                            AND b.is_high = 1 AND b.current_room NOT LIKE 'dormitory%'
                            UNION
                            SELECT '菲亚梅塔' AS name
                       """+ sel +
                        """
                        ) AS subquery ON a.name = subquery.name
                        WHERE DATE(a.current_time) >= DATE('now', '-1 month', 'localtime')
                        ORDER BY a.current_time;
                       """)
        data = cursor.fetchall()
        # 关闭数据库连接
        conn.close()
    except sqlite3.Error:
        data = []
    processed_data = {}
    grouped_data = {}
    for row in data:
        name = row[0]
        current_room = row[2]
        current_time = row[6]  # Assuming index 6 is the current_time column
        agent = grouped_data.get(
            name,
            {
                "agent_data": [
                    {"current_time": current_time, "current_room": current_room}
                ],
                "difference": [],
            },
        )
        difference = {
            "time_diff": calculate_time_difference(
                agent["agent_data"][-1]["current_time"], current_time
            ),
            "current_room": agent["agent_data"][-1]["current_room"],
        }
        agent["agent_data"].append(
            {"current_time": current_time, "current_room": current_room}
        )
        agent["difference"].append(difference)
        grouped_data[name] = agent
    for name in grouped_data:
        work_time = 0
        rest_time = 0
        for difference in grouped_data[name]["difference"]:
            if difference["current_room"].startswith("dormitory"):
                rest_time += difference["time_diff"]
            else:
                work_time += difference["time_diff"]
        processed_data[name] = {
            "labels": ["休息时间", "工作时间"],
            "datasets": [{"data": [rest_time, work_time]}],
        }

    return processed_data


# 整理心情曲线
def get_mood_ratios():
    database_path = get_path("@app/tmp/data.db")
    favorite = [] if config.conf.favorite == '' else config.conf.favorite.split(',')
    sel = ''
    for name in favorite:
        sel = sel + """
                UNION
                SELECT '{}' AS name
            """.format(name)
    try:
        # 连接到数据库
        conn = sqlite3.connect(database_path)
        cursor = conn.cursor()
        # 查询数据（筛掉宿管和替班组的数据）
        cursor.execute("""
                       SELECT a.*
                        FROM agent_action a
                        JOIN (
                            SELECT DISTINCT b.name
                            FROM agent_action b
                            WHERE DATE(b.current_time) >= DATE('now', '-7 day', 'localtime')
                            AND b.is_high = 1 AND b.current_room NOT LIKE 'dormitory%'
                            UNION
                            SELECT '菲亚梅塔' AS name
                       """+ sel +
                        """
                        ) AS subquery ON a.name = subquery.name
                        WHERE DATE(a.current_time) >= DATE('now', '-7 day', 'localtime')
                        ORDER BY a.agent_group DESC, a.current_time;

        """)
        data = cursor.fetchall()
        # 关闭数据库连接
        conn.close()
    except sqlite3.Error:
        data = []

    work_rest_data_ratios = get_work_rest_ratios()
    grouped_data = {}
    grouped_work_rest_data = {}
    for row in data:
        group_name = row[4]  # Assuming 'agent_group' is at index 4
        if not group_name:
            group_name = row[0]
        mood_data = grouped_data.get(group_name, {"labels": [], "datasets": []})
        work_rest_data = grouped_work_rest_data.get(
            group_name, work_rest_data_ratios[row[0]]
        )
        grouped_work_rest_data[group_name] = work_rest_data

        timestamp_datetime = datetime.strptime(
            row[6], "%Y-%m-%d %H:%M:%S.%f"
        )  # Assuming 'current_time' is at index 6
        # 创建 Luxon 格式的字符串
        current_time = f"{timestamp_datetime.year:04d}-{timestamp_datetime.month:02d}-{timestamp_datetime.day:02d}T{timestamp_datetime.hour:02d}:{timestamp_datetime.minute:02d}:{timestamp_datetime.second:02d}.{timestamp_datetime.microsecond:06d}+08:00"

        mood_label = row[0]  # Assuming 'name' is at index 0
        mood_value = row[5]  # Assuming 'mood' is at index 5

        if mood_label in [dataset["label"] for dataset in mood_data["datasets"]]:
            # if mood_label == mood_data['datasets'][0]['label']:
            mood_data["labels"].append(current_time)
            # If mood label already exists, find the corresponding dataset
            for dataset in mood_data["datasets"]:
                if dataset["label"] == mood_label:
                    dataset["data"].append({"x": current_time, "y": mood_value})
                    break
        else:
            # If mood label doesn't exist, create a new dataset
            mood_data["labels"].append(current_time)
            mood_data["datasets"].append(
                {"label": mood_label, "data": [{"x": current_time, "y": mood_value}]}
            )

        grouped_data[group_name] = mood_data
    print(grouped_work_rest_data)
    # 将数据格式整理为数组
    formatted_data = []
    for group_name, mood_data in grouped_data.items():
        formatted_data.append(
            {
                "groupName": group_name,
                "moodData": mood_data,
                "workRestData": grouped_work_rest_data[group_name],
            }
        )
    return formatted_data


def calculate_time_difference(start_time, end_time):
    time_format = "%Y-%m-%d %H:%M:%S.%f"
    start_datetime = datetime.strptime(start_time, time_format)
    end_datetime = datetime.strptime(end_time, time_format)
    time_difference = end_datetime - start_datetime
    return time_difference.total_seconds()


def save_trading_info(func):
    def wrapper(*args, **kwargs):
        database_path = get_path("@app/tmp/data.db")
        try:
            result = None
            get_path("@app/tmp").mkdir(exist_ok=True)
            connection = sqlite3.connect(database_path)
            cursor = connection.cursor()
            cursor.execute(
                "CREATE TABLE IF NOT EXISTS trading_history ("
                "time INTEGER PRIMARY KEY,"
                "server_date TEXT,"
                "type TEXT,"
                "price INTEGER"
                ")"
            )
            if len(args) > 2:
                dt = args[2]
                cursor.execute(
                    "SELECT COUNT(*) FROM trading_history WHERE time = ?",
                    (int(dt.timestamp()),),
                )
                exists = cursor.fetchone()[0] > 0
                if exists:
                    logger.debug("当前订单信息已经存在数据库，跳过.")
                    return
            result = func(*args, **kwargs)

            if result:
                dubai_tz = pytz.timezone("Asia/Dubai")
                cursor.execute(
                    "INSERT INTO trading_history VALUES (?, ?, ?, ?)",
                    (
                        int(result.time.timestamp()),
                        result.time.astimezone(dubai_tz).date(),
                        result.buff,
                        result.price,
                    ),
                )
                logger.info(f"当前为 {result.buff} 订单, 订单价值为: {result.price}")
                logger.info(f"储存订单信息至数据库 {datetime.now()}")
                connection.commit()
        except sqlite3.Error as e:
            logger.error(f"SQLite error: {e}")
        finally:
            connection.close()
        return result

    return wrapper


def get_trading_history(start_date: str, end_date: str):
    if start_date == "" or end_date == "":
        pass
    dubai_tz = pytz.timezone("Asia/Dubai")
    dubai_start = dubai_tz.localize(datetime.strptime(start_date, "%Y-%m-%d"))
    dubai_end = (
        dubai_tz.localize(datetime.strptime(end_date, "%Y-%m-%d"))
        + timedelta(days=1)
        - timedelta(seconds=1)
    )
    local_tz = get_localzone()

    start_dt = dubai_start.astimezone(local_tz)
    end_dt = dubai_end.astimezone(local_tz)

    database_path = get_path("@app/tmp/data.db")
    start_timestamp = int(start_dt.timestamp())
    end_timestamp = int(end_dt.timestamp())

    result_dict = collections.defaultdict(list)
    logger.debug(f"分析数据从{start_dt}")
    logger.debug(f"分析数据至{end_dt}")

    try:
        connection = sqlite3.connect(database_path)
        cursor = connection.cursor()
        cursor.execute(
            "CREATE TABLE IF NOT EXISTS trading_history ("
            "time INTEGER PRIMARY KEY,"
            "server_date TEXT,"
            "type TEXT,"
            "price INTEGER"
            ")"
        )
        cursor.execute(
            """
            SELECT server_date, type, price, COUNT(*)
            FROM trading_history
            WHERE time BETWEEN ? AND ?
            GROUP BY server_date, type, price
            """,
            (start_timestamp, end_timestamp),
        )
        for row in cursor.fetchall():
            trade_date, trade_type, price, count = row
            # 构建每个记录的统计信息
            key = (
                trade_type
                if trade_type in ["佩佩", "龙舌兰"]
                else f"{trade_type}_{price}"
            )
            result_dict[trade_date].append({key: count})

    except sqlite3.Error as e:
        logger.exception(e)
    finally:
        if connection:
            connection.close()
    result_list = [
        {"日期": date, **{k: v for stat in stats for k, v in stat.items()}}
        for date, stats in result_dict.items()
    ]
    return result_list
