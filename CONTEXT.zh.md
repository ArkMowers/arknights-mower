# Arknights Mower 领域词汇表 (SSOT)

[English](CONTEXT.md) | [中文](CONTEXT.zh.md)

Arknights Mower 权威领域术语、代码映射与不变式规范。所有技术笔记、系统规格书、源码注释与 Agent 交互必须严格遵守本定义。

---

## 1. 设备控制与传输域 (Device & Transport Domain)

### 设备配置 (`Device Profile`)
- **定义**：用户显式配置并持久化的设备连接参数集合（模拟器预设、路径、特征码标识与截图/触控后端），仅保存用户确定意图，与运行时瞬态状态严格隔离。
- **代码映射**：[`DeviceProfile`](arknights_mower/utils/config/device_profile.py), [`Conf.device`](arknights_mower/utils/config/device_profile.py)
- **_Avoid_**: `Device runtime state`, `Discovery candidate`, `Active connection`

### 模拟器实例绑定 (`Instance Binding`)
- **定义**：与特定模拟器多开实例建立的不可变身份关联。在连接断开或重启时严格保持目标唯一性，严禁自动漂移或静默回退到主机其他在线设备。
- **代码映射**：[`DeviceSession.bind()`](arknights_mower/utils/device/session.py), [`DeviceSession.target_serial`](arknights_mower/utils/device/session.py)
- **_Avoid_**: `Dynamic device selection`, `Floating target`, `Auto fallback`

### 设备连接检查结果 (`Readiness Verdict`)
- **定义**：对模拟器及 ADB 传输链路各就绪阶段进行的结构化分类评估结果（`absent`、`offline`、`booting`、`ready`），携带明确的状态码与修复指引。
- **代码映射**：[`ReadinessResult`](arknights_mower/utils/device/session.py), [`DeviceSession.readiness`](arknights_mower/utils/device/session.py)
- **_Avoid_**: `Raw exception`, `Unformatted error string`

### 重连恢复上限 (`Recovery Budget`)
- **定义**：为设备重连、等待启动就绪或重启实例设定的单调递增有限总超时时间、最大重试次数与单次等待间隔预算，杜绝无界重试与阻塞死循环。
- **代码映射**：[`RecoveryPolicy`](arknights_mower/utils/device/session.py), `recovery_timeout`, `recovery_attempts`
- **_Avoid_**: `Infinite retry`, `Unconstrained loop`, `Background sleep`

### 多开实例特征码 (`Topology Fingerprint`)
- **定义**：由模拟器配置文件或多开管理工具提取的机器唯一拓扑哈希特征码，用于在端口漂移或索引变动时稳定识别多开 VM 实例。
- **代码映射**：`topology_fingerprint`, `instance_name`
- **_Avoid_**: `Vague identifier`, `Simulator metadata`, `Transient serial`

### 实体设备临时分辨率适配 (`Temporary Preparation`)
- **定义**：仅在实体 Android 设备单次会话运行期间动态应用的 1920×1080 临时分辨率与密度适配，且在会话退出或异常时提供严格的原状恢复补偿保证。
- **代码映射**：[`PreparationSession`](arknights_mower/utils/device/preparation.py), `restore_screen_resolution`
- **_Avoid_**: `Permanent configuration`, `Unmanaged resolution change`

### 标准画面帧 (`Capture Frame`)
- **定义**：跨 ADB、DroidCast 及 MuMu IPC 后端统一解码输出的标准 1920×1080 纯画布 RGB 画面矩阵，不包含黑边或未解码压缩字节。
- **代码映射**：`CanvasFrame`, `FrameBuffer`
- **_Avoid_**: `Scaled preview`, `Raw stream byte`

### ADB 服务共享管理 (`Shared ADB Guard`)
- **定义**：通过 Socket 协议级握手预先探测共享 ADB 服务端状态、严格禁止隐式执行 `kill-server` 从而保障与其他多开或调试工具共存的服务治理机制。
- **代码映射**：[`guard_adb`](arknights_mower/utils/device/adb_client/server.py), [`probe_adb_server`](arknights_mower/utils/device/adb_client/server.py)
- **_Avoid_**: `Direct kill-server`, `Unguarded CLI call`

---

## 2. 基建设施与排班域 (Facility & Scheduling Domain)

### 排班表 (`Scheduling Plan`)
- **定义**：配置基建各房间主班干员、主班干员绑组、替班干员、生产产物以及换班规则的声明式方案。包含基准主排班（`plan1`）与条件触发的备用排班（`backup_plans`）。
- **代码映射**：[`PlanModel`](arknights_mower/utils/config/plan.py), [`Plan1`](arknights_mower/utils/config/plan.py), [`BackupPlan`](arknights_mower/utils/config/plan.py)
- **_Avoid_**: `Task script`, `Macro`, `Work plan`

### 干员心情 (`Operator Mood`)
- **定义**：衡量干员在基建中工作与休息状态的数值（上限为 24 点）。进驻工作设施持续消耗，进驻宿舍恢复。降至 0 点注意力涣散后技能失效。
- **代码映射**：[`Operator.mood`](arknights_mower/utils/operators.py), [`Operator.current_mood()`](arknights_mower/utils/operators.py)
- **_Avoid_**: `Physical energy`, `Fatigue level`

### 基建设施 (`Base Facility`)
- **定义**：罗德岛基建中具备独立功能与进驻槽位的各类房间。划分为工作设施（中枢、制造、贸易、发电、办公、会客、训练、加工）与休息设施（1~4 号宿舍）。
- **代码映射**：[`Facility`](arknights_mower/utils/config/plan.py), [`base_room_list`](arknights_mower/data/__init__.py)
- **_Avoid_**: `Building slot`, `Isolated room`

### 宿舍心情恢复 (`Dormitory Recovery`)
- **定义**：干员进驻宿舍恢复心情的过程。结合房间顺序与干员优先级梯度分配床位，依入驻顺序保障定向宿管加成，并在心情回满后自动腾退床位。
- **代码映射**：[`dorm_recovery.py`](arknights_mower/utils/dorm_recovery.py), [`resting_tier`](arknights_mower/utils/resting_priority.py)
- **_Avoid_**: `Sleep queue`, `Rest list`

### 心情消耗速率 (`Depletion Rate`)
- **定义**：干员进驻工作设施时每小时消耗的心情点数。基准值为 1.0 点/小时，由两次进驻信息读取差值实测动态算出，用于推算余量与预测耗尽时间。
- **代码映射**：[`Operator.depletion_rate`](arknights_mower/utils/operators.py)
- **_Avoid_**: `Drain speed`, `Depletion cost`

### 动态换班 (`Dynamic Shift Transition`)
- **定义**：根据干员实时心情、排班表与触发条件，在工作设施与宿舍之间执行的人员轮换机制。包括低心情入宿、替班补位、回满出宿以及跑单或充能等事件驱动切换。
- **代码映射**：[`TaskTypes.SHIFT_OFF`](arknights_mower/utils/scheduler_task.py), [`BaseSchedulerSolver.plan_solver`](arknights_mower/solvers/base_schedule.py)
- **_Avoid_**: `Fixed timetable swap`, `Static worker cycle`

### 线索搜集与交流 (`Clue Collection & Exchange`)
- **定义**：进驻会客室搜集 1~7 号线索、接收与赠送线索，以及集齐后开启 24 小时线索交流（派对）获取信用点的过程。
- **代码映射**：[`Operators.clues`](arknights_mower/utils/operators.py), [`CreditSolver`](arknights_mower/solvers/credit.py)
- **_Avoid_**: `Party mode`, `Clue trade`

### 无人机加速 (`Drone Acceleration`)
- **定义**：消耗发电站充能恢复的基建无人机（每架抵扣 3 分钟），为指定制造站或贸易站加速生产与订单获取的机制。
- **代码映射**：[`drone_plan`](arknights_mower/utils/manufacture_product.py), [`DRONE_SECONDS`](arknights_mower/utils/manufacture_product.py)
- **_Avoid_**: `Speed up`, `Drone boost`
