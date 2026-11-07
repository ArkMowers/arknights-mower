// PROTOTYPE：仅供交互预览；所有示例配置只保存在页面内存中。
// 字段对应现有配置，示例房间、账号、配方和周计划不代表当前用户的数据。
const number = (key, label, value, unit, min, max, extra = {}) => ({
  key,
  label,
  type: 'number',
  value,
  unit,
  min,
  max,
  ...extra
})
const select = (key, label, value, options, extra = {}) => ({
  key,
  label,
  type: 'select',
  value,
  options,
  ...extra
})
const toggle = (key, label, value, extra = {}) => ({
  key,
  label,
  type: 'switch',
  value,
  ...extra
})
const text = (key, label, value, extra = {}) => ({
  key,
  label,
  type: 'text',
  value,
  ...extra
})
const time = (key, label, value, extra = {}) => ({
  key,
  label,
  type: 'time',
  value,
  ...extra
})
const runners = [
  { label: 'Mower', value: 'mower' },
  { label: 'MAA', value: 'maa' }
]

export const taskGroups = [
  { id: 'base', label: '基建任务', description: '按排班和基建状态安排，优先处理到期任务。' },
  { id: 'daily', label: '日常任务', description: '利用基建任务之间的空档执行。' },
  { id: 'combat', label: '作战与空闲', description: '刷理智和长任务各自配置，基建任务优先。' }
]

export const connectionDefinition = {
  id: 'connection',
  title: '连接与启动',
  description: '选择设备、游戏服务器和启动方式；这里只编辑原型示例，不检测或连接设备。',
  condition: '开始托管前连接已选择的设备；各项任务共用这个设备。',
  effect: '原型修改仅保存在页面内存中。',
  fields: [
    select('preset_id', '设备类型', 'windows.mumu12', [
      { label: 'MuMu 12 · Windows', value: 'windows.mumu12' },
      { label: '雷电 9 · Windows', value: 'windows.ldplayer9' },
      { label: 'Android AVD · Linux', value: 'linux.avd' },
      { label: 'Android AVD · macOS', value: 'macos.avd' },
      { label: '其他模拟器 · 手动连接', value: 'manual.other' },
      { label: '实体 Android 设备', value: 'manual.physical' }
    ]),
    text('instance_id', '实例标识', '0', {
      help: '示例实例序号；实际使用时通过检测选择并核验所需的实例身份信息。'
    }),
    text('last_serial', '连接地址', '127.0.0.1:16384'),
    select('game_package', '游戏服务器', 'com.hypergryph.arknights', [
      { label: '官服', value: 'com.hypergryph.arknights' },
      { label: 'B 服', value: 'com.hypergryph.arknights.bilibili' }
    ]),
    select('screenshot_backend', '截图后端', 'droidcast', [
      { label: 'DroidCast', value: 'droidcast' },
      { label: 'ADB gzip', value: 'adb_gzip' }
    ]),
    select('touch_backend', '触控后端', 'scrcpy', [
      { label: 'scrcpy', value: 'scrcpy' },
      { label: 'MaaTouch', value: 'maatouch' }
    ]),
    select('tap_to_launch_game.mode', '启动游戏方式', 'adb', [
      { label: 'ADB 命令', value: 'adb' },
      { label: '点击屏幕', value: 'tap' },
      { label: '自定义命令', value: 'custom' }
    ]),
    number('tap_to_launch_game.x', '启动点击横坐标', 100, 'px', 0, 1919, {
      visibleWhen: { key: 'tap_to_launch_game.mode', value: 'tap' }
    }),
    number('tap_to_launch_game.y', '启动点击纵坐标', 100, 'px', 0, 1079, {
      visibleWhen: { key: 'tap_to_launch_game.mode', value: 'tap' }
    }),
    text(
      'tap_to_launch_game.command',
      '启动命令',
      'input keyevent KEYCODE_WAKEUP; wm dismiss-keyguard; am start -n {package}/{activity}',
      { visibleWhen: { key: 'tap_to_launch_game.mode', value: 'custom' } }
    ),
    toggle('start_automatically', '启动后自动托管', false, {
      help: '启动 Mower 后自动开始托管任务，不是单独的自动启动模拟器开关。'
    }),
    select(
      'idleAction',
      '任务空档时',
      'home',
      [
        { label: '无操作', value: 'idle' },
        { label: '返回设备桌面', value: 'home' },
        { label: '退出游戏', value: 'exit' },
        { label: '关闭模拟器', value: 'close' }
      ],
      {
        source: 'shared',
        help: '等待下一项任务时执行；退出游戏和关闭模拟器要求空档超过 5 分钟，关闭模拟器还需实例支持启停。'
      }
    )
  ]
}

export const categoryFieldBindings = {
  base: [{ source: 'task', taskId: 'drone', key: 'drone_interval', label: '无人机加速间隔' }],
  daily: [
    {
      source: 'shared',
      key: 'dailyGap',
      label: '日常任务间隔',
      help: '与“作战与空闲”共用，用于 MAA 日常、刷理智、仓库扫描和制造站补货。邮件等每日任务按游戏日检查；公招和信赖使用各自间隔。'
    },
    { source: 'task', taskId: 'recruit', key: 'recruit_gap', label: '公开招募启动间隔' },
    {
      source: 'task',
      taskId: 'trust',
      key: 'trust_rotation_interval',
      label: '自动切换信赖检查间隔'
    }
  ],
  combat: [
    {
      source: 'shared',
      key: 'dailyGap',
      label: '日常任务间隔',
      help: '与“日常任务”共用，用于 MAA 日常、刷理智、仓库扫描和制造站补货；长任务另按允许时段和基建空档安排。'
    }
  ]
}

export const taskDefinitions = [
  {
    id: 'shift',
    group: 'base',
    title: '基建排班',
    subtitle: '按心情和排班表安排换班',
    enabled: true,
    engine: 'Mower',
    mode: 'automatic',
    automaticLabel: '随排班',
    description:
      '基建轮休是 Mower 持续托管的主要工作；跑单、菲亚梅塔充能和人员安排仍在排班编辑中配置。',
    condition: '根据生效排班、实际心情和任务依赖产生安排。',
    effect: '排班和初始化设置在下次启动时载入。',
    fields: [
      toggle('automatic_rescue_enable', '自动救急', false, {
        help: '初始化确认普通轮休无法周转时使用独立救急排班，需先完成救急排班配置。'
      })
    ],
    links: [
      { label: '排班编辑', to: '/plan-editor' },
      { label: '救急排班', to: '/rescue-plan-editor' }
    ]
  },
  {
    id: 'drone',
    group: 'base',
    title: '无人机加速',
    subtitle: '为指定设施加速生产或订单',
    enabled: true,
    engine: 'Mower',
    mode: 'automatic',
    automaticLabel: '按参数',
    description: '周期加速由房间、间隔和无人机阈值控制；跑单中的无人机操作继续遵循排班规则。',
    condition: '指定房间达到加速间隔，且基建调度有足够操作时间。',
    effect: '房间在下次启动时载入，间隔和阈值在后续加速时读取。',
    fields: [
      select(
        'drone_room',
        '加速房间',
        'room_1_1',
        [
          { label: 'B101 贸易站（示例）', value: 'room_1_1' },
          { label: 'B102 制造站（示例）', value: 'room_1_2' },
          { label: '不指定周期加速房间', value: '' }
        ],
        { help: '房间列表为原型示例；未指定房间时不进行该项周期加速。' }
      ),
      number('drone_interval', '加速间隔', 3, '小时', 0, 168),
      number('drone_count_limit', '无人机使用阈值', 100, '架', 0, 200, {
        help: '数量不足时跳过；普通制造站加速保留该数量，贸易站按订单逐次检查。'
      })
    ]
  },
  {
    id: 'clue',
    group: 'base',
    title: '线索搜集与交流',
    subtitle: '收取、赠送线索并开启交流',
    enabled: true,
    engine: 'Mower',
    description: '处理会客室线索及交流；Mower 信用购物接在线索流程之后，购物策略另行配置。',
    condition: '定期检查线索，交流结束后由相应任务处理。',
    effect: '线索开关和雷锋模式在下次启动时载入。',
    fields: [
      toggle('leifeng_mode', '雷锋模式', true, {
        help: '按现有赠送规则把可赠送线索送给好友。'
      })
    ]
  },
  {
    id: 'workshop',
    group: 'base',
    title: '加工站合成',
    subtitle: '按配方和库存安排加工',
    enabled: true,
    engine: 'Mower',
    mode: 'automatic',
    automaticLabel: '按配方',
    description: '此处演示一条手动加工配方；实际功能支持多条配方，自动专精备料由养成规划管理。',
    condition: '按已启用配方、材料库存、干员心情和基建时间预算安排。',
    effect: '后续加工规划使用配置；自动专精备料期间的手动修改在备料结束后生效。',
    fields: [
      text('workshop_settings.0.operator', '加工干员', '九色鹿', { help: '示例干员。' }),
      text('workshop_settings.0.items.0.item_names', '合成材料', '碳素组', {
        help: '示例配方；完整编辑器使用材料列表。'
      }),
      number('workshop_settings.0.items.0.self_upper_limit', '成品库存上限', 30, '个', 0, 999999),
      number(
        'workshop_settings.0.items.0.children_lower_limit',
        '子材料保留数量',
        20,
        '个',
        0,
        999999
      ),
      toggle('workshop_settings.0.enabled', '启用这条配方', true, { advanced: true })
    ],
    links: [{ label: '养成规划', to: '/mastery-recommendation' }]
  },
  {
    id: 'trust',
    group: 'daily',
    title: '自动切换信赖',
    subtitle: '检查基建副手和活动室使用者',
    enabled: true,
    engine: 'Mower',
    description:
      '默认保留现任至 200% 信赖；开启低信赖优先后，存在合格候选时可提前更换，不改变干员原工作或休息安排。',
    condition: '日常空档达到检查间隔时检查副手与已建造活动室。',
    effect: '下次信赖检查使用新的设置。',
    fields: [
      number('trust_rotation_interval', '检查间隔', 24, '小时', 1, 168),
      toggle('trust_rotation_prefer_low', '优先低信赖干员', false),
      number('trust_rotation_threshold', '优先信赖阈值', 100, '%', 1, 200, {
        visibleWhen: { key: 'trust_rotation_prefer_low', value: true },
        help: '现任达到阈值且有低于阈值的同类候选时更换，否则保留至 200%。'
      })
    ]
  },
  {
    id: 'skland',
    group: 'daily',
    title: '森空岛签到',
    subtitle: '为已选择的账号和区服签到',
    enabled: false,
    engine: 'Mower',
    description: '使用森空岛账号签到，与游戏内活动签到分开；此原型未连接账号。',
    condition: '日常流程检查当日签到状态后，为已勾选区服签到。',
    effect: '下一次签到检查使用已保存的账号与区服选择。',
    fields: [
      text('skland_info.0.account', '森空岛账号', '演示账号（未连接）'),
      toggle('skland_info.0.sign_in_official', '明日方舟官服', true),
      toggle('skland_info.0.sign_in_bilibili', '明日方舟 B 服', false),
      toggle('skland_info.0.sign_in_endfield_official', '终末地官服', false, { advanced: true }),
      toggle('skland_info.0.sign_in_endfield_bilibili', '终末地 B 服', false, { advanced: true })
    ]
  },
  {
    id: 'mail',
    group: 'daily',
    title: '领取邮件',
    subtitle: '收取游戏内邮件奖励',
    enabled: true,
    engine: 'Mower',
    description:
      '开启后由 Mower 领取游戏内邮件，没有额外参数；发送运行通知的邮箱在通知设置中配置。',
    condition: '基建任务之间有足够日常操作时间时检查当日邮件。',
    effect: '下次日常检查读取此开关。',
    fields: []
  },
  {
    id: 'report',
    group: 'daily',
    title: '读取基报',
    subtitle: '读取基建生产报告',
    enabled: true,
    engine: 'Mower',
    description: '开启后在日常流程读取基建生产报告，这项功能没有独立时间表或额外参数。',
    condition: '基建任务之间有足够日常操作时间时检查基报。',
    effect: '下次日常检查读取此开关。',
    fields: []
  },
  {
    id: 'recruit',
    group: 'daily',
    title: '公开招募',
    subtitle: '按标签和许可数量安排招募',
    enabled: true,
    engine: 'Mower',
    description: '识别公开招募标签并按策略选择；三星招募阈值决定许可充足时是否招募三星干员。',
    condition: '日常空档达到公招启动间隔时检查。',
    effect: '下一次公招检查使用新的间隔和选择策略。',
    fields: [
      number('recruit_gap', '启动间隔', 9, '小时', 0, 168, {
        help: '公招使用自己的间隔，可填小数。'
      }),
      number('recruitment_permit', '三星招募阈值', 30, '张', 0, 9999, {
        help: '剩余公招券大于此阈值时招募三星干员。'
      }),
      select('recruit_auto_5', '五星招募策略', 1, [
        { label: '自动选择', value: 1 },
        { label: '手动选择', value: 2 }
      ]),
      toggle('recruit_robot', '保留支援机械标签', true, { advanced: true }),
      toggle('recruit_auto_only5', '五星词条组合唯一时自动选择', false, {
        advanced: true,
        visibleWhen: { key: 'recruit_auto_5', value: 2 }
      })
    ]
  },
  {
    id: 'depot',
    group: 'daily',
    title: '仓库物品混合读取',
    subtitle: '同步森空岛并补充读取游戏仓库',
    enabled: false,
    engine: 'Mower',
    description:
      '先同步第一个森空岛账号的指定服务器，再读取游戏仓库；确认后的材料数据也供养成与专精使用。',
    condition: '日常空档达到共享日常间隔后，尝试同步并扫描。',
    effect: '下一次扫描使用账号选择，历史条数按相应读取与保存流程处理。',
    fields: [
      select('skland_info.0.cultivate_select', '第一个账号的服务器', true, [
        { label: '官服（演示账号）', value: true },
        { label: 'B 服（演示账号）', value: false }
      ]),
      number('depot_history_limit', '历史分析条数', 3000, '次', 1, 999999, {
        help: '趋势、环比和快照对比最多读取的扫描记录数。'
      }),
      number('depot_history_keep', '历史保留条数', 0, '次', 0, 999999, {
        advanced: true,
        help: '0 表示一直保留；超出数量时从最早记录开始删除。'
      })
    ]
  },
  {
    id: 'visit',
    group: 'daily',
    title: '访问好友',
    subtitle: '拜访好友并收取信用',
    enabled: true,
    engine: 'Mower / MAA',
    description:
      '访问好友可单独选择执行方式，信用购物另外启用；Mower 的按需领取信用与按性价比购物都要求开启 Mower 访友。',
    condition: 'Mower 在日常空档检查，MAA 在共享日常轮次中执行。',
    effect: '下次相应日常调度读取执行方式，正在运行的 MAA 轮次保持原参数。',
    fields: [select('visit_friend_mode', '执行方式', 'mower', runners)]
  },
  {
    id: 'credit',
    group: 'daily',
    title: '信用作战',
    subtitle: '借助战完成 OF-1 获取信用',
    enabled: false,
    engine: 'MAA',
    description: '由 MAA 在信用流程中使用指定编队借助战作战，和访友、购物分别控制。',
    condition: '共享日常轮次检查当日信用作战状态，并要求周计划已指定关卡。',
    effect: '下一轮 MAA 任务使用新的开关和编队。',
    fields: [
      select('credit_fight.squad', '使用编队', 1, [
        { label: '第一编队', value: 1 },
        { label: '第二编队', value: 2 },
        { label: '第三编队', value: 3 },
        { label: '第四编队', value: 4 }
      ])
    ]
  },
  {
    id: 'shop',
    group: 'daily',
    title: '信用商店购物',
    subtitle: '按优先名单和购买策略消费信用',
    enabled: true,
    engine: 'Mower / MAA',
    description:
      'MAA 在日常轮次购物，Mower 在线索流程完成后购物；按性价比购物仅在 Mower 访友与购物同时启用时适用。',
    condition: '依所选执行方式进入信用流程，并遵守相应购物条件。',
    effect: 'Mower 下次购物读取设置，MAA 下一轮任务使用新的参数。',
    fields: [
      select('maa_mall_mode', '执行方式', 'mower', runners),
      text('maa_mall_buy', '优先购买', '招聘许可,技巧概要·卷2'),
      text('maa_mall_blacklist', '购物黑名单', '加急许可,碳,碳素,家具零件'),
      toggle('credit_shop_by_value', '按性价比购物', false, {
        advanced: true,
        visibleWhen: { key: 'maa_mall_mode', value: 'mower' },
        help: '还需开启 Mower 访问好友；未满足条件时不会按性价比购物。'
      }),
      toggle('maa_mall_only_buy_discount', '只购买折扣物品', false, {
        advanced: true,
        visibleWhen: { key: 'maa_mall_mode', value: 'maa' },
        help: '仅作用于 MAA 的第二轮购买。'
      })
    ]
  },
  {
    id: 'stage',
    group: 'combat',
    title: '刷理智',
    subtitle: '按照周计划执行关卡',
    enabled: true,
    engine: 'Mower / MAA',
    description:
      '根据游戏日的周计划选择关卡、理智药数量和保留理智；此处只演示周一一行，实际功能保留七天周计划。',
    condition: '达到共享日常间隔，并满足所选执行方式的基建时间预算。',
    effect: '下一轮作战读取周计划，正在执行的 MAA 轮次保持原参数。',
    fields: [
      select('stage_plan_runner', '执行方式', 'maa', runners),
      text('maa_weekly_plan.0.stage', '周一关卡', '1-7', {
        help: '原型示例；实际周计划支持每天配置多个关卡。'
      }),
      number('maa_weekly_plan.0.medicine', '周一理智药上限', 0, '瓶', 0, 999),
      number('medicine_expire_days', '临期理智药阈值', 0, '天', 0, 999, {
        advanced: true,
        help: '0 表示不使用临期药；MAA 接收剩余天数阈值，Mower 在大于 0 时启用临期药识别。'
      }),
      toggle('maa_eat_stone', '允许无限使用源石', false, {
        advanced: true,
        visibleWhen: { key: 'stage_plan_runner', value: 'maa' }
      })
    ]
  },
  {
    id: 'reward',
    group: 'daily',
    title: 'MAA 领取奖励',
    subtitle: '选择由 MAA 领取的奖励内容',
    enabled: false,
    engine: 'MAA',
    mode: 'automatic',
    automaticLabel: '按内容',
    description: '这组功能按具体奖励分别勾选，没有独立总开关；活动奖励仅在游戏有对应活动时有效。',
    condition: '在共享 MAA 日常轮次执行已选择的奖励内容。',
    effect: '下一轮 MAA 任务使用所选奖励内容。',
    fields: [
      toggle('maa_mail', '领取所有邮件奖励', false, {
        help: '与 Mower 的领取邮件分开控制，通常选择一种方式即可。'
      }),
      toggle('maa_recruit', '限定池每日免费单抽', false),
      toggle('maa_orundum', '幸运墙每日合成玉', false),
      toggle('maa_mining', '限时开采每日合成玉', false, { advanced: true }),
      toggle('maa_specialaccess', '五周年赠送月卡奖励', false, {
        advanced: true,
        help: '现有历史活动选项，仅在对应活动可领取时适用。'
      })
    ]
  },
  {
    id: 'long',
    group: 'combat',
    title: '空闲长任务',
    subtitle: '基建空档运行一种长任务',
    enabled: false,
    engine: 'Mower / MAA',
    description:
      '一次选择一种模式；集成战略、保全派驻和 MAA 生息演算使用 MAA，原生生息演算与隐秘战线使用 Mower。',
    condition: '在允许时段且基建任务之间有可用时间时运行。',
    effect: '下一次长任务调度使用所选模式与时段，已启动任务遵循原来的停止规则。',
    fields: [
      select('maa_long_task_type', '任务模式', 'rogue', [
        { label: '集成战略 · MAA', value: 'rogue' },
        { label: '保全派驻 · MAA', value: 'sss' },
        { label: '生息演算 · MAA', value: 'rcl' },
        { label: '生息演算 · Mower', value: 'ra' },
        { label: '隐秘战线 · Mower', value: 'sf' }
      ]),
      time('maa_rg_sleep_max', '允许开始时间', '00:00', {
        help: '与停止时间相同表示全天允许；到达时刻仍需等待可用的基建空档。'
      }),
      time('maa_rg_sleep_min', '允许停止时间', '00:00'),
      select(
        'maa_rg_theme',
        '集成战略主题',
        'Mizuki',
        [
          { label: '水月与深蓝之树', value: 'Mizuki' },
          { label: '探索者的银凇止境', value: 'Sami' }
        ],
        {
          advanced: true,
          visibleWhen: { key: 'maa_long_task_type', value: 'rogue' },
          help: '原型仅展示部分已有主题，实际可用主题依 MAA 资源而定。'
        }
      ),
      select(
        'maa_rcl_theme',
        'MAA 生息演算主题',
        'Tales',
        [
          { label: '沙洲遗闻', value: 'Tales' },
          { label: '重启锚点', value: 'RelaunchAnchor' }
        ],
        { advanced: true, visibleWhen: { key: 'maa_long_task_type', value: 'rcl' } }
      )
    ]
  }
]

export function createTaskSwitchesState() {
  return JSON.parse(
    JSON.stringify({
      enabled: Object.fromEntries(taskDefinitions.map((task) => [task.id, task.enabled])),
      values: Object.fromEntries(
        taskDefinitions.map((task) => [
          task.id,
          Object.fromEntries(task.fields.map((field) => [field.key, field.value]))
        ])
      ),
      connection: Object.fromEntries(
        connectionDefinition.fields
          .filter((field) => field.source !== 'shared')
          .map((field) => [field.key, field.value])
      ),
      shared: { dailyGap: 3, idleAction: 'home' }
    })
  )
}
