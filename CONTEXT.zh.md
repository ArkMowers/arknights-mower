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
- **定义**：跨 ADB、DroidCast、MuMu IPC 及 LD 截图增强后端统一解码输出的标准 1920×1080 纯画布 RGB 画面矩阵，不包含黑边或未解码压缩字节。
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
- 维护副表在公告停服大更新前的配置时刻生效，先完成现有停服前无人机加速跑单任务，再执行动态换班；其生效主班包含跑单干员时，暂停全部贸易站跑单。
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
- **定义**：干员进驻宿舍恢复心情的过程。按宿舍分床优先级分配床位，建立并保留单回位置；离宿依据回班、不养闲人和个人上限规则分别处理。
- 不养闲人的规划与选人共用候选和预约规则，区分未知读数与已核验心情；保留已回满的原住客前，通过游戏心情升序列表核验未知心情。主班恢复的床位预约优先于普通空床补位，普通补位不获得集中恢复批次保护。加工在宿舍安排完成后作为独立任务执行。
- **救急恢复**：原生救急沿用平均心情判断与普通轮休规则。自动救急默认关闭，在初始化实测与排班核对后，仅于至少两个不同休息组的主班心情低于各自救急线，优先使用实测，缺失时使用有效卡牌预估、仍有主班等待下班且当前原生轮休无法安排这些主班休息时启动；启动判断不依赖历史消耗速率或未来心情预测。卡牌预估仅用于初始化准入及原生轮休可行性预演，不写入实测记录，不作为恢复完成或退出救急的依据。排班绑定组按组计数，未绑组主班分别计数，仍低于救急线的在休组计入休息竞争。加工站和训练室仍执行原有专项任务。救急驻员与正常主班重名时，启动时提示名单，仍按救急排班运行。恢复期间冻结正常排班的副表。临时上岗要求卡牌心情不低于个人正常下班线加 1 点，本轮恢复主班在统一退出前不上临时工作岗位。期间暂停副表与普通工作站换班，心情复查时收取普通订单和制造产物，并保留符合正常条件的跑单与专项临时换人。恢复目标使用适用历史，历史不足时采用正常下班线加 1 点。 救急排班允许已知 0 心情驻员上岗，并沿用正常排班的绑组、下班阈值及完整替班匹配规则；组内非零心情工作干员低于下班线时，取得完整替班后集体离岗；属于正常主班的干员纳入恢复需求并可预约宿舍，其余干员待命，不预约宿舍。救急表的零心情工作名单和宿舍黑名单按副表规则追加，显式宿舍优先级顺序覆盖此前设置。未知心情、预约冲突及加工和专精任务自身的心情检查继续生效。
- 自动救急使用独立的救急主表和副表配置工作驻员、跑单人选、宿管以及菲亚梅塔的位置和充能对象，未配置的专项任务不沿用正常排班配置。Free 床位优先恢复正常主班，同组优先一起休息；剩余空位可按正常排班优先级安排替班或其他空闲未满心情干员。宿管按恢复需求让床，需求减少后每间先补回一名群回宿管，有空位再补回一名单回宿管。正常排班能够覆盖仍需休息的组并继续周转时即可退出救急，无需所有组都达到恢复目标；未恢复的组继续休息，其余岗位恢复正常排班。
- 救急排班中的加工站和训练室驻员参与排班部署；加工和专精继续使用原有任务流程，训练室换人遵守现有的训练位及协助位保护规则。
- 自动救急开关及救急排班入口位于 Mower 设置的基建设置，不随正常排班表导入导出。进入自动救急前，先按当前条件确定正常排班和救急排班各自生效的副表，再比较最终工作站的设施类型、等级及产物；任一不一致时提示具体设施和差异，并保持正常调度。无法确定副表运行条件的静态验证不据主表差异直接判定不匹配，最终准入以初始化实测后的生效排班为准。
- **代码映射**：[`dorm_recovery.py`](arknights_mower/utils/dorm_recovery.py), [`resting_tier`](arknights_mower/utils/resting_priority.py)
- **_Avoid_**: `Sleep queue`, `Rest list`

### 心情消耗速率 (`Depletion Rate`)
- **定义**：干员进驻工作设施时每小时消耗的心情点数。基础消耗为 1 点/小时，实际速度受干员、设施及技能等因素影响。Mower 根据有效的工作心情读数估算实际速度，用于预测心情和下班时间；肥鸭充能造成的心情突变不计入工作消耗。
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

### 完整换班收敛 (`Complete Shift Convergence`)
- **定义**: 执行换人前，根据已有信息一起计算上下班、副表切换、宿舍重排和补床，直到副表条件与人员安排不再变化，再提交一份最终安排。实际读屏获得新信息后仍可重新规划。
- **代码映射**: [`BaseSchedulerSolver._prepare_shift_cycle`](arknights_mower/solvers/base_schedule.py)

### 实际驻员／预演驻员 (`Actual and Projected Occupancy`)
- **定义**: 实际驻员是最近一次确认的干员位置；预演驻员是假设任务执行后的位置，仅用于计算。预演不移动游戏中的干员，也不提前覆盖实际位置缓存。
- **代码映射**: [`Operators.project_arrangements`](arknights_mower/utils/operators.py)

### 宿舍分床优先级 (`Dormitory Bed Priority`)
- **定义**: 决定谁优先获得休息位、单回位，以及谁可以接管较低优先级的床位。同级比较距各自心情上限还差多少点，差得越多越优先；已入住者换位仍须遵守保位规则。
- **代码映射**: [`resting_key`](arknights_mower/utils/resting_priority.py)

### 下班候选顺序 (`Off-Shift Candidate Order`)
- **定义**: 按当前心情减去有效下限，从小到大尝试安排休息，再检查替班、床位、编组和用尽等条件。宿舍分床优先级不直接让某人提前下班。
- **代码映射**: [`BaseSchedulerSolver.resting`](arknights_mower/solvers/base_schedule.py)

### 单回宿管／单回目标 (`Single-Target Recovery Manager and Target`)
- **定义**: 单回宿管是宿舍第 1 或第 2 位具有指定单人心情恢复技能的干员；单回目标是安排接受加成的休息干员。目标直接占住最终位置；前方非宿管位置保留已满心情的原住者，否则用最高心情的可用空闲干员垫位，确认后恢复其余入住者。相关宿管与目标均未移动或替换时保留配置；目标回满后，游戏可自动转移加成。
- **代码映射**: [`recovery_order_plan`](arknights_mower/utils/dorm_recovery.py)

### 回满目标／强制离宿上限 (`Recovery Target and Mandatory Release Limit`)
- **定义**: 回满目标是排班认定休息完成的有效心情值，不一定为 24。强制离宿上限是达到后须安排离宿的个人限制，包括个人设置和令夕规则。全局上限用于确定回满目标，不要求因此将宿舍留空。
- **代码映射**: [`Operators.has_rest_mood_limit`](arknights_mower/utils/operators.py)

### 不养闲人清退／上限强制离宿 (`Idle Dormitory Release and Mood-Limit Release`)
- **定义**: 不养闲人清退为其他人腾出休息位，受开关、排除名单和满员兜底规则约束。上限强制离宿遵守个人心情限制，不受不养闲人开关和排除名单豁免。离宿不等于安排上班；执行前须核验原住者仍在对应床位。
- **代码映射**: [`BaseSchedulerSolver.prepare_release_dorm`](arknights_mower/solvers/base_schedule.py)

### 动态 Free 位／实际空床 (`Dynamic Free Slot and Vacant Bed`)
- **定义**: 排班表中的 Free 位是不固定主班、可动态安排休息者的位置；任务中的 Free 表示由选人流程确定入住者。实际空床是位置缓存确认无人占用的床位，补人还须检查任务预约。
- **代码映射**: [`vacant_dorm_slots`](arknights_mower/utils/dorm_candidates.py)

### 有效心情缓存／默认心情 (`Valid Mood Cache and Default Mood`)
- **定义**: 有效心情缓存包含实读数值、读取时间及可用的推算结果。缺少有效缓存时，候选筛选、排序和主班轮休选择使用有效期一小时的选人卡牌预估：绿色笑脸为 24，红色为 0，黄色按心情条长度粗估且严格介于 0 与 24 之间。读不清的卡牌保持未知。预估不构成实读回满、采样时间、心情掉率、恢复截止时间或达到个人强制上限的依据。
- **代码映射**: [`has_resting_mood`](arknights_mower/utils/resting_priority.py)

### 初始化心情观测 (`Initial Mood Observation`)
- **定义**: 启动先读取实际房间驻员，再在普通设施选人页预估缺少的心情，随后进行副表判断和缓存纠偏。观测不选择干员、不确认安排。有界扫描保留部分预估，卡牌读不清时仍继续启动；正常巡检校准实读心情和恢复时间。
- **代码映射**: [`BaseSchedulerSolver._read_initial_card_mood`](arknights_mower/solvers/base_schedule.py)

### 肥鸭充能 (`Fiammetta Charging`)
- **定义**: 利用菲亚梅塔技能为指定干员恢复心情的特殊任务，包含临时换位、充能和后续安排。充能流程暂停副表切换；更新心情和读取时间，保留工作心情消耗速度，之后由正常工作读数继续校准。
- 初始化实测完成后，已满心情且已配置充能对象的菲亚梅塔优先完成充能及原班恢复，再继续初始化后的普通调度和自动救急判断；个人心情上限离宿及已到期的关键任务仍遵守原有保护规则。
- **代码映射**: [`BaseSchedulerSolver.plan_fia`](arknights_mower/solvers/base_schedule.py)

- 自动救急期间，已配置的菲亚梅塔充能目标均满心情时，可从未配置特殊心情上限的正常主班中，按心情从低到高选择符合现有充能条件且无预约冲突的目标。
