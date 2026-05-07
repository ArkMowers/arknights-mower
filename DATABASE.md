# arknights-mower 数据库层设计

## 现状问题 (`solvers/record.py`)

| 问题 | 表现 |
|---|---|
| Raw SQL 分散 | 每个函数自己 `CREATE TABLE IF NOT EXISTS` |
| 连接管理混乱 | `sqlite3.connect` 到处开/关, 无连接池 |
| 装饰器耦合 | `save_state` 里 `from arknights_mower.__main__ import base_scheduler` 循环引用 |
| 无迁移 | 改表结构要手动写 ALTER TABLE |
| 路径硬编码 | `get_path("@app/tmp/data.db")` 写死 |
| 混合职责 | 存储 + 查询 + 统计聚合全在一个文件 |
| 非跨平台 | raw `sqlite3` 没有 ORM 层, 手机端换数据库要全改 |

---

## 目标设计

### 分层

```
scheduler/database/              ← 新建, 纯 Python, 跨平台
├── __init__.py
├── core.py                      # DatabaseEngine (连接管理)
├── errors.py                    # 数据库异常
├── migration.py                 # 迁移管理
│
├── repositories/                # 数据访问层 (单表 CRUD)
│   ├── __init__.py
│   ├── base.py                  # BaseRepository (通用)
│   ├── agent_action.py          # 干员行为记录
│   ├── saved_state.py           # 调度器状态持久化
│   ├── trading_history.py       # 贸易记录
│   ├── inventory.py             # 仓库物品
│   ├── operation.py             # 作战记录
│   └── log.py                   # 日志
│
└── migrations/                  # SQL 迁移文件
    ├── 001_create_agent_action.sql
    ├── 002_create_trading_history.sql
    ├── 003_create_inventory.sql
    └── ...
```

### DatabaseEngine (core.py)

```python
class DatabaseEngine:
    """
    连接管理, 单例.

    桌面端: SQLite
    手机端: 可换成 Room (SQLite 包装) 或直接复用 SQLite
    """

    _instance = None

    def __init__(self, path: str | None = None):
        self.path = path or get_path("@app/tmp/data.db")
        self._conn: sqlite3.Connection | None = None

    @classmethod
    def get(cls) -> "DatabaseEngine":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    @property
    def conn(self) -> sqlite3.Connection:
        if self._conn is None:
            self._conn = sqlite3.connect(self.path)
            self._conn.row_factory = sqlite3.Row
            self._conn.execute("PRAGMA journal_mode=WAL")
            self._conn.execute("PRAGMA foreign_keys=ON")
        return self._conn

    def close(self):
        if self._conn:
            self._conn.close()
            self._conn = None

    def execute(self, sql: str, params=()) -> sqlite3.Cursor:
        return self.conn.execute(sql, params)

    def executemany(self, sql: str, params_seq) -> sqlite3.Cursor:
        return self.conn.executemany(sql, params_seq)

    def fetchone(self, sql: str, params=()) -> sqlite3.Row | None:
        return self.execute(sql, params).fetchone()

    def fetchall(self, sql: str, params=()) -> list[sqlite3.Row]:
        return self.execute(sql, params).fetchall()

    def commit(self):
        self.conn.commit()

    # 手机端兼容: 如果换成 Android Room, 只需替换这个类
    # 接口不变, repositories 不用改

    def save_snapshot(self, key: str, data: dict) -> None:
        """通用 key-value 持久化 (替代 pickle.dumps)"""
        self.execute(
            "INSERT OR REPLACE INTO snapshots (key, value, updated_at) VALUES (?, ?, ?)",
            (key, json.dumps(data), datetime.now().isoformat()),
        )
        self.commit()

    def load_snapshot(self, key: str) -> dict | None:
        row = self.fetchone("SELECT value FROM snapshots WHERE key = ?", (key,))
        if row:
            return json.loads(row["value"])
        return None
```

### 迁移系统 (migration.py)

```python
from arknights_mower.utils.log import logger

MIGRATIONS = [
    ("001_agent_action", """
        CREATE TABLE IF NOT EXISTS agent_action (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            agent_current_room TEXT,
            current_room TEXT,
            is_high INTEGER,
            agent_group TEXT,
            mood REAL,
            current_time TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_agent_action_name_time
            ON agent_action(name, current_time);
    """),
    ("002_trading_history", """
        CREATE TABLE IF NOT EXISTS trading_history (
            time INTEGER PRIMARY KEY,
            server_date TEXT,
            type TEXT,
            price INTEGER
        );
    """),
    ("003_inventory", """
        CREATE TABLE IF NOT EXISTS inventory (
            item_name TEXT PRIMARY KEY,
            count INTEGER NOT NULL
        );
    """),
    ("004_operation_history", """
        CREATE TABLE IF NOT EXISTS operation_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            stage_id TEXT,
            run_count INTEGER,
            ap_cost INTEGER,
            started_at TEXT,
            finished_at TEXT,
            duration_seconds REAL,
            status TEXT,
            drop_json TEXT,
            created_at TEXT
        );
    """),
    ("005_snapshots", """
        CREATE TABLE IF NOT EXISTS snapshots (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );
    """),
    ("006_resources", """
        CREATE TABLE IF NOT EXISTS resources (
            name TEXT NOT NULL,
            locale TEXT NOT NULL DEFAULT 'CN',
            png_blob BLOB,
            version INTEGER NOT NULL DEFAULT 0,
            PRIMARY KEY (name, locale)
        );
    """),
    ("007_log", """
        CREATE TABLE IF NOT EXISTS logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            time INTEGER NOT NULL,
            task TEXT,
            level TEXT,
            message TEXT
        );
    """),
]

def run_migrations():
    db = DatabaseEngine.get()
    db.execute("""
        CREATE TABLE IF NOT EXISTS schema_migrations (
            name TEXT PRIMARY KEY,
            applied_at TEXT NOT NULL
        )
    """)
    applied = {r["name"] for r in db.fetchall("SELECT name FROM schema_migrations")}

    for name, sql in MIGRATIONS:
        if name not in applied:
            logger.info(f"Running migration: {name}")
            db.execute(sql)
            db.execute(
                "INSERT INTO schema_migrations (name, applied_at) VALUES (?, ?)",
                (name, datetime.now().isoformat()),
            )
            db.commit()

    return len(MIGRATIONS) - len(applied)  # 返回本次运行的迁移数
```

### Repository 模式

```python
# repositories/base.py
class BaseRepository:
    def __init__(self, db: DatabaseEngine | None = None):
        self._db = db or DatabaseEngine.get()

    @property
    def db(self) -> DatabaseEngine:
        return self._db


# repositories/agent_action.py
class AgentActionRepository(BaseRepository):
    def insert(self, name: str, current_room: str, target_room: str,
               is_high: bool, group: str, mood: float) -> None:
        self.db.execute(
            "INSERT INTO agent_action (name, agent_current_room, current_room, "
            "is_high, agent_group, mood, current_time) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (name, current_room, target_room, int(is_high), group, mood, str(datetime.now())),
        )
        self.db.commit()

    def get_recent_by_names(self, names: list[str], days: int = 7) -> list[sqlite3.Row]:
        placeholders = ",".join("?" * len(names))
        return self.db.fetchall(
            f"SELECT * FROM agent_action WHERE name IN ({placeholders}) "
            f"AND DATE(current_time) >= DATE('now', '-{days} day', 'localtime') "
            f"ORDER BY current_time",
            names,
        )

    def clean_before(self, cutoff: datetime) -> int:
        self.db.execute("DELETE FROM agent_action WHERE current_time < ?", (str(cutoff),))
        self.db.commit()
        return self.db.conn.total_changes


# repositories/inventory.py
class InventoryRepository(BaseRepository):
    def upsert(self, items: dict[str, int]) -> None:
        self.db.executemany(
            "INSERT INTO inventory (item_name, count) VALUES (?, ?) "
            "ON CONFLICT(item_name) DO UPDATE SET count = excluded.count",
            list(items.items()),
        )
        self.db.commit()

    def get_all(self) -> dict[str, int]:
        return dict(self.db.fetchall("SELECT item_name, count FROM inventory"))

    def get_by_names(self, names: list[str]) -> dict[str, int]:
        placeholders = ",".join("?" * len(names))
        return dict(
            self.db.fetchall(
                f"SELECT item_name, count FROM inventory WHERE item_name IN ({placeholders})",
                names,
            )
        )
```

### 手机端复用的关键

所有 `repository` 只依赖 `DatabaseEngine`:

```python
# PC: 直接 SQLite
db = DatabaseEngine(path="app/tmp/data.db")
repo = AgentActionRepository(db)

# Android: DatabaseEngine 实现可以换成 Room
# 只需要重写 DatabaseEngine 一个类, repositories 不动
```

### 旧代码迁移策略

旧 `solvers/record.py` 保留不动 (向后兼容)。新代码全部走新 `scheduler/database/`。

迁移步骤:

1. **Phase A**: 写 `scheduler/database/` 全新, 旧 `record.py` 不动
2. **Phase B**: 逐个改 consumer (`record_operation_batch` → `OperationRepository`, 等等)
3. **Phase C**: 全部 consumer 改完后, 删除 `record.py` 中对应函数
