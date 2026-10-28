export const incomeMessages = {
  'zh-CN': {
    overview: '干员时间总览',
    overviewScroll: '干员时间总览横向滚动',
    sampling:
      '仅统计采样期 {hours} 小时，不含预热。工作、休息、空闲和心情涣散驻岗分别统计，主班和替班工时不含心情涣散驻岗。',
    ratioHelp: '工作占比 = 工作时长 / 采样时长；工休比 = 工作时长 / 休息时长，无休息时显示 —。',
    operator: '干员',
    workFraction: '工作占比',
    workRest: '工休比',
    work: '工作（小时）',
    primary: '主班（小时）',
    substitute: '替班（小时）',
    rest: '休息（小时）',
    idle: '空闲（小时）',
    exhausted: '心情涣散（小时）',
    finalMorale: '期末心情',
    currentTask: '当前任务',
    taskLabel: '{kind}：{label}',
    pendingTask: '最近待执行任务',
    due: '计划时刻 T+{hours} 小时',
    morale: '心情 {value} / {limit}',
    noStaff: '未驻员',
    noGroup: '未绑组',
    recent: '近期活动：{events}',
    occurrences: '{label} {count} 次',
    noDetails: '当前观测没有具体干员或任务信息。',
    observedOnly: '以上为已观测记录，不能仅凭活动频次认定原因；历史校验记录不表示当前仍未解决。',
    dayRange: '{period}天数必须为 {min}–{max} 的整数',
    warmup: '预热',
    sample: '统计',
    seedRange: '随机种子必须为 0–4294967295 的整数',
    missingDrone: '无人机目标不在本次排班中',
    noOperatorCache: '没有可用的森空岛练度缓存，请先同步或选择其他练度来源',
    emptyOperatorCache: '森空岛缓存中没有已拥有干员',
    enterOperators: '请填写干员和练度',
    invalidOperatorMode: '干员练度选项无效',
    noWeights: 'Mower 收益算法尚未读取，请重试或选择本次自定义权重',
    invalidWeights: '产出权重来源无效',
    experience: '经验',
    goldEquivalent: '赤金等价龙门币',
    tradeLmd: '贸易龙门币',
    lmdCost: '龙门币消耗',
    netLmd: '龙门币净增',
    fragments: '源石碎片',
    orundum: '合成玉',
    recycle: '回收站产出',
    recruitment: '公招刷新',
    clues: '会客室线索',
    expUnit: '经验值',
    lmdUnit: '龙门币',
    itemUnit: '个',
    countUnit: '次',
    dorm: '宿舍{number}',
    baseSkills: '基建技能',
    owned: '已拥有',
    unowned: '未拥有',
    active: '已解锁',
    locked: '未解锁',
    replaced: '已替换',
    initialMorale: '初始心情 24（受个人上限约束）',
    initialFiammettaMorale: '菲亚梅塔初始心情 {value}；其他干员从个人心情上限开始（未设置时为 24）',
    sourceImage: '原图：{label}；二维码包含完整主副表和高级设置，可在 Mower「导入排班」中读取。',
    sampleSummary:
      '预热 {warmup} 天，不计入收益；统计 {sample} 天，共 {total} 天；随机种子 {seed}。',
    droneInventorySummary: '无人机：{target}；{inventory}',
    finiteInventorySummary: '有限库存：无外源收入，连续记账；{shortage}',
    potentialInventorySummary: '潜在产出：不受初始库存限制，不能视为可交付收入。',
    initialInventorySummary: '初始库存（{source}）：{inventory}。初始数量不计入收益。',
    cachedInventorySource: '森空岛缓存，可手动补充修改',
    allZero: '全部为 0',
    goldBalanceSummary:
      '赤金余额：初始 {initial}；统计开始 {opening}；期末 {closing}。负数表示赤金缺口，不代表实物库存。',
    cacheDateSummary: '缓存库存同步时间：{date}；缓存不代表当前游戏即时状态。',
    noCacheDate: '缓存未提供时间',
    operatorAssumptions: '干员：{source}；{initialMorale}；孑精零 {jaye}。',
    cachedOperatorsSource: '森空岛缓存的实际拥有和练度',
    manualOperatorsSource: '按本次填写的拥有和练度',
    maximumOperatorsSource: '全部干员满配假设',
    enabled: '开启',
    disabled: '关闭',
    noTrainingAssumption:
      '本次演算固定为无未完成训练计划且未在训练，不模拟训练进度或计划完成时刻。',
    historicalTrainingAssumption:
      '历史演算的未完成训练计划：{present}，整段演算保持此条件，不模拟训练完成。',
    goldEquivalentAssumption:
      '赤金等价龙门币为制造赤金 × 500 加特殊订单溢价，不扣除交付消耗的赤金；该项不是实际龙门币入账。',
    weightAssumptions: '收益权重（{source}）：{weights}。加权产出不是龙门币结算额。',
    modelAssumptions:
      '模型假设：理想跑单；部分读房与调度耗时已建模，其余点击识别耗时忽略；宿舍氛围按等级上限。',
    thresholdStrategyAssumption:
      '轮班策略 {version}；实时心情计算调控{enabled}。两种模式均模拟心情变化，按正常下班阈值轮休，不为避免替班断档而提前下班；普通救急召回须能坚持到对应主班回满。',
    strategyAssumption: '轮班策略 {version}；实时心情计算调控{enabled}。两种模式均模拟心情变化。',
    noStrategyAssumption: '这份历史记录未保存轮班策略版本，重新演算后可比较当前策略。',
    facilityLevelsAssumption: '本次设施等级（优先使用排班保存值，未设置时推断）：{levels}。',
    provenanceAssumption:
      '计算器基线 {base}，选择性同步 {sync}（含本地适配）；调度基线 Mower alpha {mowerBase}，本轮核对 {mowerChecked}，后续本体逻辑不自动同步。',
    legacyProvenanceAssumption:
      '计算器 {calculator}（含本地完成时刻精度、赤金透支、制造成本观察、公招与线索观察适配）；调度参考 Mower alpha {mower}，后续本体逻辑不自动同步。',
    recruitmentAssumption:
      '公招刷新按办公室驻员、心情与已解锁技能计算联络产出；初始进度为零，预热进度延续但预热完成次数不计。假设及时使用刷新次数，不模拟存满 3 次停工，不计入加权收益。',
    noClueAssumption: '这份历史记录未统计会客室线索，重新演算后可查看。',
    clueAssumption:
      '会客室线索仅统计驻员搜集完成的个数，初始进度为零，预热进度延续但预热完成数不计；假设及时领取及清理库存，不模拟满库停工、每日赠送和好友赠送，不计算信用点或加权收益。',
    clueExchangeAssumption:
      '线索产量按全程开启交流计算，计入已解锁且非涣散驻员的交流加速技能；不模拟集齐线索或交流开关，调度侧 Party Time 仍为空。',
    legacyClueExchangeAssumption:
      '这份历史记录按线索交流关闭计算；重新演算后按全程开启交流计算线索产量。',
    recyclingAssumption:
      '回收站仅统计产出次数，不推算随机材料，不增加材料库存，也不计材料收益价值。',
    offlineAssumption:
      '这是离线模型估算，不是实测收益或实际排班可执行性的证明。图片导入不恢复本次计算参数和结果。',
    sampleAnnotation: '{algorithm} · {days} 天采样',
    dailyWeightedIncome: '日均加权收益',
    orderDistribution: '订单分布 · 原始档位',
    totalOrders: '共 {count} 单',
    noStatistics: '暂无统计',
    orderGold: '{count} 赤金',
    otherOrders: '其他 {count} 单 · {percent}%',
    noSavedOrders: '该记录未保存订单统计',
    imageFailed: '收益图片生成失败',
    imageAuthor: '作者：{author}',
    imageRemarks: '备注：{remarks}',
    custom: '自定义',
    imageWeights: '经验 {experience} · 赤金 {gold} · 订单 {orders}',
    imageFragmentWeights: '源石碎片 {fragments} · 合成玉 {orundum}',
    imageFilename: '{name}_日均收益{score}_{days}天.jpg',
    display: {
      progress: '{period} {elapsed} / {total} 小时',
      preparing: '正在准备排班数据',
      preparingCalculation: '正在准备计算…',
      workerFailed: '后台演算失败',
      transferFailed: '演算结果传输失败',
      stopped: '演算已停止，可修改参数后重试',
      archiveTimeout: '收益记录存储等待超时',
      archiveBlocked: '收益记录存储被其他窗口占用',
      archiveAborted: '收益记录存储已中止',
      archiveIncompatible: '已保存的收益记录格式不兼容',
      inventorySource: '库存来源无效',
      noInventoryCache: '没有可用的森空岛库存缓存，请先同步或选择手动设定',
      unknownOperator: '第 {line} 行：未知干员',
      duplicateInventoryOperator: '第 {line} 行：{operator} 重复录入',
      invalidRow: '第 {line} 行：请填写“干员代号,精英阶段,等级”',
      invalidStage: '第 {line} 行：{operator}：无效精英阶段或等级',
      missingSkills: '第 {line} 行：{operator}：缺少完整技能槽数据',
      invalidInventory: '干员库必须为数组',
      unsupportedOfficeSkill: '尚未支持的办公室技能：{skill}（{id}）',
      unsupportedReceptionSkill: '尚未支持的会客室技能：{skill}（{id}）',
      missingReceptionDevelopment: '缺少会客室干员练度：{operator}',
      duplicatePrimary: '干员 {operator} 在 {room1} 和 {room2} 同时在岗，不可重复指派主力。',
      powerDeficit: '基建总耗电量 ({consumption}) 超过总发电量 ({generation})，存在电力赤字。',
      unbuiltFacility: '{room} 未建造，不能配置干员、休息床位或替补。',
      outputFacilityType: '{room} 为产出设施，类型必须为制造站、贸易站或发电站，当前为 {type}。',
      outputFacilityLevel: '{room} 等级必须为 1~3 级，当前为 {level}。',
      invalidFactoryProduct:
        '制造站 {room} 产物配置无效：{product}，必须为赤金、作战记录或源石碎片。',
      invalidTradeProduct: '贸易站 {room} 产物配置无效：{product}，必须为龙门币或源石订单。',
      controlLevel: '控制中枢等级必须为 1~5 级，当前等级 {level}，类型 {type}。',
      dormLevel: '宿舍 {room} 等级必须为 1~5 级，当前等级 {level}，类型 {type}。',
      functionalLevel: '功能设施 {room} 等级必须为 1~3 级，当前等级 {level}。',
      activityRoomUnsupported: '活动室 ({room}) 暂不支持收益计算与电力模拟，已从电力总计中忽略。',
      capacity: '{room} 的在岗人数 ({count}) 超过了设施等级容量 ({capacity})。',
      placeholder: '{room} 席位使用 {kind} 占位，在收益模拟中将视为空席。',
      noReplacement: '{room} 席位干员 ({operator}) 未配置替补。',
      freeDormOnly: 'Free 只能安排在宿舍。',
      freeNoGroup: 'Free 不能配置绑组。',
      fiammettaNoGroup: '菲亚梅塔不能参与绑组换班。',
      uniqueBindings: '多绑组的组名不能重复，空组名最多一列。',
      dormNoPersonalBinding: '宿舍多绑组不能配置个人空组名列；个人轮休仅适用于非宿舍工作主班。',
      replacementEachBinding: '多绑组的每一列均需配置替班。',
      duplicateReplacement: '替补列表中存在重复干员：{operator}。',
      freeReplacement: 'Free 替补仅用于非菲亚梅塔的宿舍绑组席位。',
      replacementConflict: '替补干员 {operator} 必须为同一非空组内的其他主力或未在岗的替补。',
      groupAnchor:
        '{group} 缺少决定上下班的工作主班：需要非宿舍、非零心情工作、非多绑组且非候补的主班。',
      groupReplacements: '{group} 分组无法排班：替班名单不能覆盖所有成员。',
      groupBeds: '{group} 分组无法排班：有效宿舍床位不足。',
      backupIssue: '副表 {label}：{message}',
      backupOnlyIssue: '副表 {label} 单独生效时：{message} 实际组合将在切表前校验。',
      activityRunning: '演算正在推进。',
      activitySlow:
        '演算推进较慢。以下是最近涉及的干员与任务，仅供排查，尚不能确定是哪位干员或配置导致。',
      shiftOff: '下班',
      shiftOn: '上班',
      fiammetta: '菲亚充能',
      backupSwitch: '副表切换',
      backupTask: '副表安排',
      releaseDorm: '宿舍清退',
      bedTakeover: '床位接替',
      exhaustSupport: '耗尽协助',
      runOrder: '跑单',
      switchProduct: '切换产物/订单',
      exhaustOff: '用尽下班',
      correction: '纠错',
      clueExchange: '趴体',
      dormOrder: '宿舍排序',
      releaseDormSlot: '释放宿舍空位',
      reported: '演算曾报告：{message}',
      shortSlow: '演算推进较慢。',
      droneCapacity: '无人机上限须为0或以上的安全整数',
      finiteModel:
        '使用预设初始库存；从预热开始连续扣料、收取和交付，采样时不重置。无外源收入或自动补货；缺料停止相应生产或交付。回收站随机材料未计入物品库存。',
      goldDebtModel: '{message} 本次允许赤金透支，赤金不足不阻止交付；其他材料仍受库存约束。',
      compatibilityModel: '使用 Mower 默认兼容换班策略；按六阶段评估副表，保留完整任务保护',
      alphaModel: '使用 Mower alpha 排班模型（80c97ee60 增量适配）：副表收敛、共享绑组与宿舍隔离',
      unsupportedStage: '当前动态模拟使用已校对的最高基建技能；较低精英阶段尚未编译',
      operationDuration: '当前模拟仅支持忽略换人操作耗时',
      orderLifecycle: '保留跑单配置；本报告统计日常班组效率，尚未模拟每单插入干员、收单与资源结算',
      integration:
        '使用{mode}暖机，最大步长 {step} h；复制取整等非线性效率采用区间中点数值积分，可缩小步长检查敏感性',
      wholeHours: '整小时',
      continuous: '连续',
      singleRecovery:
        '单回始终排除自身和菲亚梅塔；单回技能持有者仅在唯一待恢复候选时合格，不主动锁单回；后续入住可使其资格失效，确认或显式指定不能绕过资格。普通有效目标保持至回满、离宿或宿管变化，重选按最低心情，同心情按槽位顺序',
      ioClock:
        'Mower 每房返回 0.5 秒及无临近任务时的通知检查 1 秒已纳入时间线；识别与其他点击耗时按 0 处理。已完成 run 后仍有同刻任务时，外层单调时钟推进 1 微秒；该适配步长不改任务时刻。',
      continuousMorale:
        '本地心情及读取值使用连续数值，未复现游戏心情条像素与识别误差。关闭菲亚梅塔防呆时，接近满心情的微小缺额可能产生密集充能；模拟保留该策略，不添加额外冷却。',
      tradeQuality:
        '裁缝类订单概率采用线性近似：α／β分别在原工位连续工作 3／5 小时达到峰值；移动工位或离岗后重新计时。同类效果不叠加，取当前四赤金概率最高者；中间曲线和叠加机制未经实测核验。',
      passiveOccupancy:
        '{room} / {operator}：本次只模拟闲置进驻，不执行加工或训练任务，心情消耗 0/h',
      unmodeledTaskMorale:
        '{room} / {operator}：尚未建模该设施的任务心情消耗；当前按未执行任务的 0/h',
      backupCycle: '副表同刻任务链循环',
      clueModel: '线索产量按交流固定开启计算；调度侧 Party Time 仍为空，不执行线索待办及交流任务。',
      legacyClueModel: '线索交流固定关闭，Party Time 为空，不执行线索待办及交流任务。',
      orderModel:
        '理想跑单在新单开始时锁定佩佩/可露希尔模式，在普通订单完成时转换但书/龙舌兰收益；保留 Mower 订单读取、任务排序与唤醒，不执行临时换人；常规换班、收取及无人机任务仍按 Mower 时间线执行。',
      eventLimit: '达到 {count} 个积分区间，结果未完成',
      sameTimeAction: '同刻调度未能稳定，结果未完成',
      stalled: '无法确定下一个正长度区间',
      pendingFailure:
        '统计结束仍有未恢复的{task}任务（{rooms}）：{message}；保留原任务和时间，本次收益演算未完整完成',
      recoveredDelay: '{message}; {count} 次延后均已由后续完整分组下班事件确认恢复',
      blockingPlan: '排班存在阻断错误，无法进行收益计算',
      incompleteReport: '未取得完整生产报告',
      missingInventoryOperator: '{operator}：参与排班或联动，但未录入干员库',
      fillDorm: '宿舍补位',
      refreshTaskTimes: '强制刷新任务时间',
      swapSupport: '换协助位',
      potentialModel:
        '直观产出模式：忽略材料库存不足，设施容量与收取按 Mower 排班执行，完成即计产出；账本为测算辅助，不代表实际到账。无人机仍按所选策略及实际生成量使用。',
      idealRunOrders:
        '理想跑单按已解锁的佩佩/可露希尔候选决定新单模式，在普通订单完成时应用 U-Official/但书/龙舌兰效果；保留 Mower 任务读取、排序与唤醒，不临时换人、不等待、不消耗跑单干员心情或无人机。常规排班和无人机目标策略仍执行。',
      dronePolicy:
        '无人机由 Mower 的任务阶段使用：每 {hours} 小时待办检查、{count} 架判断门槛；按所选设施加速，不额外消耗跑单无人机。',
      incomplete: '演算未完成',
      finding: '曾报告{finding}：{message}。此记录不表示当前仍未解决。',
      groupBlocked: '可用替班或床位不足，原在岗安排保留',
      forcedBedWait: '强制宿舍任务等待有效恢复床位',
      backupPreviewCycle: '副表预演循环',
      backupDeferred: '副表切换暂缓',
      taskException: '任务异常',
      planException: '排班规划异常',
      planningException: '调度规划异常',
      groupOperators: '绑组 {group}；当前关联干员：{operators}',
      slotOperators: '岗位 {slot}；当前关联干员：{operators}',
      groupDetail: '绑组 {group}',
      slotDetail: '岗位 {slot}',
      activitySpan: '，模拟时间跨度 {minutes} 分钟',
      repeatedShifts:
        '近期记录 {operator} 上班 {on} 次、下班 {off} 次{span}；仅描述活动，原因未确定。',
      repeatedBackups: '近期记录 {label} 切换 {count} 次{span}；仅描述活动，原因未确定。',
      repeatedRecharges: '近期记录菲亚充能 {count} 次{span}；仅描述活动，原因未确定。',
      smallRecharge:
        '近期 {count} 次菲亚充能的目标心情增量不超过 1；最近一次 {operator}：{before} → {after}，增加 {gain}。此数值不表示充能无效或解释演算变慢。',
      orderCompleted: '订单完成',
      orderDelivered: '交付订单',
      productSwitch: '切换产物',
      productSwitchDrone: '切产物使用无人机',
      tradeDrone: '贸易加速',
      manufactureDrone: '制造加速',
      recycleCollected: '回收站收取'
    },
    present: '有',
    absent: '无',
    dailyOutput: '日均产出'
  },
  'en-US': {
    overview: 'Operator Time Overview',
    overviewScroll: 'Scroll operator time overview horizontally',
    sampling:
      'Only the {hours}-hour sampling period is counted; warmup is excluded. Work, rest, idle time and exhausted staffing are counted separately. Primary and substitute work hours exclude exhausted staffing.',
    ratioHelp:
      'Work share = work hours / sample hours. Work/rest ratio = work hours / rest hours; — is shown when there is no rest time.',
    operator: 'Operator',
    workFraction: 'Work Share',
    workRest: 'Work/Rest Ratio',
    work: 'Work (h)',
    primary: 'Primary (h)',
    substitute: 'Substitute (h)',
    rest: 'Rest (h)',
    idle: 'Idle (h)',
    exhausted: 'Exhausted (h)',
    finalMorale: 'Final Morale',
    currentTask: 'Current task',
    taskLabel: '{kind}: {label}',
    pendingTask: 'Next pending task',
    due: 'Scheduled for T+{hours} h',
    morale: 'Morale {value} / {limit}',
    noStaff: 'Unstaffed',
    noGroup: 'No group binding',
    recent: 'Recent activity: {events}',
    occurrences: '{label}: {count} times',
    noDetails: 'This observation contains no specific operator or task information.',
    observedOnly:
      'These are recorded observations. Frequency alone does not establish a cause; historical verification records do not mean a problem is still unresolved.',
    dayRange: '{period} days must be an integer from {min} to {max}',
    warmup: 'Warmup',
    sample: 'Sample',
    seedRange: 'The random seed must be an integer from 0 to 4294967295',
    missingDrone: 'The drone target is not in this scheduling plan',
    noOperatorCache:
      'No SKLand progression cache is available. Sync it first or choose another progression source.',
    emptyOperatorCache: 'The SKLand cache contains no owned operators',
    enterOperators: 'Enter operators and their progression',
    invalidOperatorMode: 'Invalid operator progression source',
    noWeights:
      'Mower income weights have not loaded. Retry or choose custom weights for this calculation.',
    invalidWeights: 'Invalid production weight source',
    experience: 'EXP',
    goldEquivalent: 'Pure Gold LMD Equivalent',
    tradeLmd: 'Trading LMD',
    lmdCost: 'LMD Spent',
    netLmd: 'Net LMD',
    fragments: 'Originium Shards',
    orundum: 'Orundum',
    recycle: 'Recycling Output',
    recruitment: 'Recruitment Refreshes',
    clues: 'Reception Room Clues',
    expUnit: 'EXP',
    lmdUnit: 'LMD',
    itemUnit: 'items',
    countUnit: 'count',
    dorm: 'Dormitory {number}',
    baseSkills: 'Base Skills',
    owned: 'Owned',
    unowned: 'Not owned',
    active: 'Unlocked',
    locked: 'Locked',
    replaced: 'Replaced',
    initialMorale: 'Initial Morale 24 (subject to personal limits)',
    initialFiammettaMorale:
      'Fiammetta starts at {value} Morale; other operators start at their personal upper limit (24 when unset)',
    sourceImage:
      "Source image: {label}. Its QR code includes all primary and backup plans and advanced settings, and can be read with Mower's Import Plan.",
    sampleSummary:
      'Warmup: {warmup} days, excluded from income; sample: {sample} days; total: {total} days; seed: {seed}.',
    droneInventorySummary: 'Drones: {target}; {inventory}',
    finiteInventorySummary:
      'Finite inventory: no external income; balances carry forward. {shortage}',
    potentialInventorySummary:
      'Potential output: unconstrained by initial inventory; it does not represent deliverable income.',
    initialInventorySummary:
      'Initial inventory ({source}): {inventory}. Initial quantities are excluded from income.',
    cachedInventorySource: 'SKLand cache, with manual adjustments allowed',
    allZero: 'all zero',
    goldBalanceSummary:
      'Pure Gold balance: initial {initial}; sample opening {opening}; closing {closing}. Negative values indicate a shortage, not physical stock.',
    cacheDateSummary:
      'Cached inventory synced: {date}. The cache does not represent the live game state.',
    noCacheDate: 'cache timestamp unavailable',
    operatorAssumptions: 'Operators: {source}; {initialMorale}; Elite 0 Jaye: {jaye}.',
    cachedOperatorsSource: 'actual ownership and progression from the SKLand cache',
    manualOperatorsSource: 'ownership and progression entered for this run',
    maximumOperatorsSource: 'all operators assumed fully developed',
    enabled: 'enabled',
    disabled: 'disabled',
    noTrainingAssumption:
      'This run assumes no unfinished training plans and no active training. Training progress and completion times are not simulated.',
    historicalTrainingAssumption:
      'Unfinished training plans in the historical run: {present}. This condition stays fixed throughout; training completion is not simulated.',
    goldEquivalentAssumption:
      'Pure Gold LMD equivalent is manufactured Pure Gold × 500 plus special order premiums, without subtracting Pure Gold used for deliveries. It is not actual LMD received.',
    weightAssumptions: 'Output weights ({source}): {weights}. Weighted output is not settled LMD.',
    modelAssumptions:
      'Model assumptions: ideal order completion; some room reads and scheduling delays are modeled, while other click and recognition delays are omitted; dorm ambiance is at the level cap.',
    thresholdStrategyAssumption:
      'Shift strategy {version}; calculated Morale control: {enabled}. Both modes simulate Morale and use normal rest thresholds, without early rest to avoid substitute gaps. An ordinary emergency recall must last until the corresponding primary operators fully recover.',
    strategyAssumption:
      'Shift strategy {version}; calculated Morale control: {enabled}. Both modes simulate Morale changes.',
    noStrategyAssumption:
      'This historical record has no saved shift strategy version. Rerun to compare it with the current strategy.',
    facilityLevelsAssumption:
      'Facility levels (saved plan values take priority; otherwise inferred): {levels}.',
    provenanceAssumption:
      'Calculator baseline {base}, selected updates from {sync} with local adaptations; scheduling baseline Mower alpha {mowerBase}, checked against {mowerChecked}. Later Mower logic is not synchronized automatically.',
    legacyProvenanceAssumption:
      'Calculator {calculator}, including local completion timing, Pure Gold debt, manufacturing cost, recruitment and clue observation adaptations; scheduling reference Mower alpha {mower}. Later Mower logic is not synchronized automatically.',
    recruitmentAssumption:
      'Recruitment refreshes use Office staffing, Morale and unlocked skills. Initial progress is zero; warmup progress carries over but completions are excluded. Refreshes are assumed to be used promptly; stopping at the 3-refresh cap is not modeled. No weighted income is assigned.',
    noClueAssumption:
      'This historical record has no Reception Room clue totals. Rerun to view them.',
    clueAssumption:
      'Reception Room clues count only completed searches by assigned operators. Progress starts at zero and carries over from warmup, whose completions are excluded. Prompt collection and inventory clearing are assumed; full-stock stoppages, daily gifts and friend gifts are not modeled. Credits and weighted income are excluded.',
    clueExchangeAssumption:
      'Clue output assumes exchange is active throughout and includes unlocked exchange speed skills of operators who are not exhausted. Collecting all clues and toggling exchange are not modeled; scheduling Party Time stays empty.',
    legacyClueExchangeAssumption:
      'This historical record assumed clue exchange was off. A new run calculates clue output with exchange active throughout.',
    recyclingAssumption:
      'Recycling counts output events only. Random materials, inventory gains and material value are not calculated.',
    offlineAssumption:
      'This is an offline model estimate, not measured income or proof that the plan is executable. Importing the image does not restore these calculation parameters or results.',
    sampleAnnotation: '{algorithm} · {days} sample days',
    dailyWeightedIncome: 'Daily Weighted Income',
    orderDistribution: 'Orders · Original Tiers',
    totalOrders: '{count} orders',
    noStatistics: 'No statistics',
    orderGold: '{count} Pure Gold',
    otherOrders: 'Other {count} orders · {percent}%',
    noSavedOrders: 'No order statistics saved',
    imageFailed: 'Could not create the income image',
    imageAuthor: 'Author: {author}',
    imageRemarks: 'Remarks: {remarks}',
    custom: 'Custom',
    imageWeights: 'EXP {experience} · Pure Gold {gold} · Orders {orders}',
    imageFragmentWeights: 'Originium Shards {fragments} · Orundum {orundum}',
    imageFilename: '{name}_daily-income{score}_{days}days.jpg',
    display: {
      progress: '{period} {elapsed} / {total} h',
      preparing: 'Preparing scheduling data',
      preparingCalculation: 'Preparing calculation…',
      workerFailed: 'Background calculation failed',
      transferFailed: 'Could not transfer the calculation result',
      stopped: 'Calculation stopped. Adjust the parameters and retry.',
      archiveTimeout: 'Timed out waiting for income storage',
      archiveBlocked: 'Income storage is occupied by another window',
      archiveAborted: 'Income storage operation aborted',
      archiveIncompatible: 'The saved income record format is incompatible',
      inventorySource: 'Invalid inventory source',
      noInventoryCache:
        'No SKLand inventory cache is available. Sync it first or use manual inventory.',
      unknownOperator: 'Line {line}: unknown operator',
      duplicateInventoryOperator: 'Line {line}: duplicate entry for {operator}',
      invalidRow: 'Line {line}: enter operator ID or original Chinese name,promotion,level',
      invalidStage: 'Line {line}: {operator}: invalid promotion or level',
      missingSkills: 'Line {line}: {operator}: complete skill-slot data is missing',
      invalidInventory: 'The operator inventory must be an array',
      unsupportedOfficeSkill: 'Unsupported Office skill: {skill} ({id})',
      unsupportedReceptionSkill: 'Unsupported Reception Room skill: {skill} ({id})',
      missingReceptionDevelopment: 'Missing progression for Reception Room operator: {operator}',
      duplicatePrimary:
        '{operator} is assigned to both {room1} and {room2}. A primary operator cannot be assigned twice.',
      powerDeficit:
        'Total base power consumption ({consumption}) exceeds generation ({generation}).',
      unbuiltFacility:
        '{room} is unbuilt and cannot have operators, rest beds or replacements configured.',
      outputFacilityType:
        '{room} is an output facility and must be a Factory, Trading Post or Power Plant. Current type: {type}.',
      outputFacilityLevel: '{room} must be level 1–3. Current level: {level}.',
      invalidFactoryProduct:
        'Factory {room} has invalid product {product}; choose Pure Gold, Battle Records or Originium Shards.',
      invalidTradeProduct:
        'Trading Post {room} has invalid product {product}; choose LMD or Originium orders.',
      controlLevel: 'The Control Center must be level 1–5. Current level: {level}; type: {type}.',
      dormLevel: 'Dormitory {room} must be level 1–5. Current level: {level}; type: {type}.',
      functionalLevel: 'Auxiliary facility {room} must be level 1–3. Current level: {level}.',
      activityRoomUnsupported:
        'Activity Room ({room}) does not yet support income or power simulation and is excluded from power totals.',
      capacity: '{room} has {count} occupants, exceeding the level capacity of {capacity}.',
      placeholder:
        '{room} uses a {kind} placeholder; it is treated as an empty slot in income simulation.',
      noReplacement: '{room} operator ({operator}) has no replacement configured.',
      freeDormOnly: 'Free can only be assigned to a Dormitory.',
      freeNoGroup: 'Free cannot have group bindings.',
      fiammettaNoGroup: 'Fiammetta cannot participate in group shifts.',
      uniqueBindings:
        'Multiple bindings cannot repeat group names and may have at most one unnamed column.',
      dormNoPersonalBinding:
        'Dormitory multi-bindings cannot include a personal unnamed column; individual rest only applies to non-dormitory primaries.',
      replacementEachBinding: 'Each binding column needs replacements.',
      duplicateReplacement: 'Duplicate operator in the replacement list: {operator}.',
      freeReplacement:
        "Free replacements are only allowed for grouped Dormitory slots other than Fiammetta's.",
      replacementConflict:
        'Replacement {operator} must be another primary in the same named group or an off-duty substitute.',
      groupAnchor:
        '{group} has no primary to determine shifts: a non-dormitory primary who is not a zero-Morale worker, multiply bound or on standby is required.',
      groupReplacements:
        'Group {group} cannot be scheduled: replacements do not cover all members.',
      groupBeds: 'Group {group} cannot be scheduled: not enough usable Dormitory beds.',
      backupIssue: 'Backup {label}: {message}',
      backupOnlyIssue:
        'When backup {label} is applied alone: {message} The actual combination is checked before switching.',
      activityRunning: 'Calculation is progressing.',
      activitySlow:
        'Calculation is progressing slowly. The recent operators and tasks below are observations for investigation; they do not establish the cause.',
      shiftOff: 'Shift off',
      shiftOn: 'Shift on',
      fiammetta: 'Fiammetta recharge',
      backupSwitch: 'Backup switch',
      backupTask: 'Backup assignment',
      releaseDorm: 'Dormitory release',
      bedTakeover: 'Bed takeover',
      exhaustSupport: 'Exhaustion support',
      runOrder: 'Complete trading orders',
      switchProduct: 'Switch product/order',
      exhaustOff: 'Shift off at exhaustion',
      correction: 'Correct staffing',
      clueExchange: 'Clue exchange',
      dormOrder: 'Reorder Dormitories',
      releaseDormSlot: 'Release Dormitory slots',
      reported: 'Previously reported: {message}',
      shortSlow: 'Calculation is progressing slowly.',
      droneCapacity: 'Drone capacity must be a safe integer of 0 or greater',
      finiteModel:
        'Uses preset initial inventory, with continuous consumption, collection and delivery from warmup onward; no reset at sampling. There is no external income or automatic restocking. Shortages stop the affected production or delivery. Random Recycling materials are excluded from inventory.',
      goldDebtModel:
        '{message} This run allows Pure Gold debt: shortages do not block delivery. Other materials remain inventory-constrained.',
      compatibilityModel:
        "Uses Mower's default compatible shift policy; evaluates backups in six stages and retains full task protection",
      alphaModel:
        'Uses the Mower alpha scheduling model (incremental adaptation of 80c97ee60): backup convergence, shared groups and Dormitory separation',
      unsupportedStage:
        'Dynamic simulation currently uses verified maximum Base Skills; lower promotion stages are not yet compiled',
      operationDuration: 'This simulation currently requires staffing-operation time to be ignored',
      orderLifecycle:
        'Trading-run settings are retained. This report measures ordinary team efficiency; per-order staffing, collection and resource settlement are not simulated.',
      integration:
        'Uses {mode} warmup with a maximum step of {step} h. Nonlinear effects such as rounded copying use midpoint integration; reduce the step to check sensitivity.',
      wholeHours: 'whole-hour',
      continuous: 'continuous',
      singleRecovery:
        'Single-target recovery always excludes self and Fiammetta. Operators with single-target recovery skills qualify only as the sole recovery candidate and do not lock the target; later arrivals can invalidate eligibility, which confirmation or explicit selection cannot bypass. Valid ordinary targets stay until full recovery, departure or a dorm-keeper change; reselection uses lowest Morale, then slot order.',
      ioClock:
        "The timeline includes Mower's 0.5-second room return and 1-second notification check when no task is imminent. Recognition and other clicks cost zero time. If same-time tasks remain after a completed run, the outer monotonic clock advances 1 microsecond without changing task times.",
      continuousMorale:
        'Local Morale and readings use continuous values; game-bar pixels and recognition errors are not reproduced. With Fiammetta protection off, tiny deficits near full Morale can produce dense recharges. The simulation preserves that strategy without adding a cooldown.',
      tradeQuality:
        'Tailoring order probability uses a linear approximation: α/β peak after 3/5 continuous hours in the same slot; moving slots or leaving resets the timer. Similar effects do not stack; the highest current four-gold probability applies. Intermediate curves and stacking have not been verified in-game.',
      passiveOccupancy:
        '{room} / {operator}: idle staffing only; no Workshop or Training tasks are run, so Morale consumption is 0/h',
      unmodeledTaskMorale:
        '{room} / {operator}: task Morale consumption for this facility is not modeled; treated as no active task, at 0/h',
      backupCycle: 'Same-time backup task chain cycle',
      clueModel:
        'Clue output assumes exchange is always on. Scheduling Party Time stays empty; clue checklist and exchange tasks are not executed.',
      legacyClueModel:
        'Clue exchange stays off and Party Time is empty; clue checklist and exchange tasks are not executed.',
      orderModel:
        'Ideal trading locks Pepe/Closure mode when an order starts and converts Proviso/Tequila income when an ordinary order completes. Mower order reads, task order and wakeups are retained, without temporary staffing; normal shifts, collection and drone tasks follow the Mower timeline.',
      eventLimit: 'Reached {count} integration intervals; the result is incomplete',
      sameTimeAction: 'Same-time scheduling did not stabilize; the result is incomplete',
      stalled: 'Could not determine the next positive-length interval',
      pendingFailure:
        'At sample end, a {task} task ({rooms}) still had an unresolved failure: {message}. The original task and time are retained; this income calculation is incomplete.',
      recoveredDelay:
        '{message}; all {count} deferrals were confirmed recovered by later full-group shift-off events',
      blockingPlan: 'The plan has blocking errors; income cannot be calculated',
      incompleteReport: 'No complete production report was obtained',
      missingInventoryOperator:
        '{operator}: used in the plan or a linked effect, but absent from the operator inventory',
      fillDorm: 'Fill Dormitory slots',
      refreshTaskTimes: 'Refresh task times',
      swapSupport: 'Change training support',
      potentialModel:
        'Potential-output mode ignores material shortages; facility capacity and collection follow Mower scheduling, with output counted at completion. The ledger aids estimation and does not represent actual receipts. Drones still follow the selected policy and actual generation.',
      idealRunOrders:
        'Ideal trading selects new-order mode from unlocked Pepe/Closure candidates and applies U-Official/Proviso/Tequila effects when ordinary orders complete. Mower task reads, order and wakeups are retained; no temporary staffing, waiting, trader Morale or trading-run drones are used. Normal staffing and drone-target policies still apply.',
      dronePolicy:
        "Drones are used in Mower's task phase: a checklist check every {hours} hours and a {count}-drone decision threshold. The selected facility is accelerated; no additional trading-run drones are consumed.",
      incomplete: 'Calculation incomplete',
      finding:
        'Previously reported {finding}: {message}. This record does not mean the condition is still unresolved.',
      groupBlocked: 'insufficient available replacements or beds; original staffing retained',
      forcedBedWait: 'forced Dormitory task waiting for usable recovery beds',
      backupPreviewCycle: 'backup preview cycle',
      backupDeferred: 'backup switch deferred',
      taskException: 'task exception',
      planException: 'staffing-plan exception',
      planningException: 'scheduling exception',
      groupOperators: 'Group {group}; currently associated operators: {operators}',
      slotOperators: 'Slot {slot}; currently associated operators: {operators}',
      groupDetail: 'Group {group}',
      slotDetail: 'Slot {slot}',
      activitySpan: ', spanning {minutes} simulated minutes',
      repeatedShifts:
        'Recent records: {operator} shifted on {on} times and off {off} times{span}. This describes activity only; the cause is undetermined.',
      repeatedBackups:
        'Recent records: {label} switched {count} times{span}. This describes activity only; the cause is undetermined.',
      repeatedRecharges:
        'Recent records: {count} Fiammetta recharges{span}. This describes activity only; the cause is undetermined.',
      smallRecharge:
        "The target's Morale gain was at most 1 in {count} recent Fiammetta recharges. Latest: {operator}, {before} → {after}, gain {gain}. This does not prove recharging was ineffective or explain slow calculation.",
      orderCompleted: 'Order completed',
      orderDelivered: 'Deliver order',
      productSwitch: 'Switch product',
      productSwitchDrone: 'Use drones to switch product',
      tradeDrone: 'Accelerate trade',
      manufactureDrone: 'Accelerate manufacturing',
      recycleCollected: 'Collect Recycling output'
    },
    present: 'present',
    absent: 'none',
    dailyOutput: 'Daily Output'
  }
}
