// PROTOTYPE：任务编排原型的假数据，选定方案后删除。
// 结构参照当前调度：基建任务按时间排队；距下一项基建任务 ≥ 9 分钟时，
// 依次执行日常 → MAA 日常 → 长任务，最后执行空闲动作并休眠。
import { reactive } from 'vue'

export const sections = {
  base: { title: '基建环线', short: '基', color: '#16a34a', note: '按任务时间排队，跑单优先' },
  daily: { title: '日常线', short: '日', color: '#2563eb', note: '空闲 ≥ 9 分钟时依次执行' },
  maa: {
    title: 'MAA 线',
    short: 'M',
    color: '#9333ea',
    note: '每隔 MAA 间隔发车，基建任务前 5 分钟收车'
  },
  long: {
    title: '长任务线',
    short: '长',
    color: '#ea580c',
    note: '停运时段外执行，基建任务前 30 秒收车'
  }
}

const sw = (key, label, value, help) => ({ key, label, type: 'switch', value, help })
const num = (key, label, value, unit, min, max, step = 1) => ({
  key,
  label,
  type: 'number',
  value,
  unit,
  min,
  max,
  step
})
const sel = (key, label, value, options) => ({ key, label, type: 'select', value, options })
const txt = (key, label, value) => ({ key, label, type: 'text', value })
const slider = (key, label, value, min = 0, max = 100) => ({
  key,
  label,
  type: 'slider',
  value,
  min,
  max
})

// cadence: event = 由排班/订单产生；every = 每 N 小时；daily = 每天一次（4:00 刷新）
const taskList = [
  {
    id: 'shift',
    section: 'base',
    name: '换班',
    cadence: { kind: 'event' },
    trigger: '按心情与排班表产生',
    fields: [
      slider('resting_threshold', '休息心情阈值 %', 50),
      sw('automatic_rescue_enable', '自动救急排班', true)
    ]
  },
  {
    id: 'runorder',
    section: 'base',
    name: '跑单',
    cadence: { kind: 'event' },
    trigger: '订单完成前提前进站',
    fields: [
      num('run_order_delay', '提前进站', 3, '分钟', 0, 30),
      sw('grandet', '葛朗台跑单', true),
      num('buffer_time', '葛朗台缓冲', 25, '秒', 0, 120),
      sw('back_to_index', '跑单后返回首页', true)
    ]
  },
  {
    id: 'drone',
    section: 'base',
    name: '无人机',
    cadence: { kind: 'every', hours: 4 },
    trigger: '每 4 小时',
    fields: [
      sel('drone_room', '加速房间', 'B101 贸易站', [
        '任意贸易站',
        'B101 贸易站',
        'B201 贸易站',
        'B102 制造站'
      ]),
      num('drone_interval', '间隔', 4, '小时', 1, 24),
      num('drone_count_limit', '保留无人机', 92, '架', 0, 200)
    ]
  },
  {
    id: 'clue',
    section: 'base',
    name: '线索',
    cadence: { kind: 'every', hours: 1 },
    trigger: '每小时至多一次',
    fields: [
      sw('enable_party', '线索交流', true),
      sw('leifeng_mode', '雷锋模式', false, '把多余线索送给好友')
    ]
  },
  {
    id: 'workshop',
    section: 'base',
    name: '加工站',
    cadence: { kind: 'event' },
    trigger: '材料不足或预设触发',
    fields: [
      sel('workshop_preset', '加工预设', '技巧概要', ['技巧概要', '芯片组', '碳素', '不使用'])
    ]
  },
  {
    id: 'reload',
    section: 'base',
    name: '搓玉补货',
    cadence: { kind: 'every', hours: 3 },
    trigger: '随 MAA 间隔',
    fields: []
  },
  {
    id: 'fia',
    section: 'base',
    name: '菲亚梅塔',
    cadence: { kind: 'event' },
    trigger: '目标心情低于阈值',
    fields: [slider('fia_threshold', '触发心情 %', 90), sw('fia_fool', '防呆检查', true)]
  },
  {
    id: 'trust',
    section: 'daily',
    name: '信赖轮换',
    cadence: { kind: 'every', hours: 8 },
    trigger: '每 8 小时',
    fields: [
      sw('trust_rotation_prefer_low', '优先低信赖', true),
      num('trust_rotation_threshold', '信赖上限', 200, '%', 0, 200),
      num('trust_rotation_interval', '间隔', 8, '小时', 1, 48)
    ]
  },
  {
    id: 'visit',
    section: 'daily',
    name: '访友',
    cadence: { kind: 'daily' },
    trigger: '每天一次',
    fields: [sel('visit_friend_mode', '执行方', 'Mower', ['Mower', 'MAA'])]
  },
  {
    id: 'report',
    section: 'daily',
    name: '基报',
    cadence: { kind: 'daily' },
    trigger: '每天一次',
    fields: []
  },
  {
    id: 'skland',
    section: 'daily',
    name: '森空岛签到',
    cadence: { kind: 'daily' },
    trigger: '每天一次',
    fields: [txt('skland_account', '账号', '1**********')]
  },
  {
    id: 'mail',
    section: 'daily',
    name: '邮件',
    cadence: { kind: 'daily' },
    trigger: '每天一次',
    fields: []
  },
  {
    id: 'recruit',
    section: 'daily',
    name: '公开招募',
    cadence: { kind: 'every', hours: 9 },
    trigger: '每 9 小时',
    fields: [
      num('recruit_gap', '间隔', 9, '小时', 1, 24),
      num('recruitment_permit', '三星招募阈值', 30, '张', 0, 999),
      sel('recruit_auto_5', '五星策略', '自动选择', ['自动选择', '手动', '仅五星']),
      sw('recruit_robot', '保留支援机械标签', true)
    ]
  },
  {
    id: 'depot',
    section: 'daily',
    name: '仓库扫描',
    cadence: { kind: 'every', hours: 3 },
    trigger: '随 MAA 间隔',
    fields: []
  },
  {
    id: 'stage',
    section: 'daily',
    name: '刷理智',
    cadence: { kind: 'every', hours: 3 },
    trigger: '随 MAA 间隔',
    fields: [
      sel('stage_plan_runner', '执行方', 'MAA', ['Mower', 'MAA']),
      txt('stage_today', '今日关卡', '1-7, CE-6'),
      num('medicine', '理智药', 0, '瓶', 0, 99)
    ]
  },
  {
    id: 'maa-fight',
    section: 'maa',
    name: '作战',
    cadence: { kind: 'every', hours: 3 },
    trigger: '每趟发车',
    fields: [
      sw('maa_eat_stone', '吃源石', false),
      num('medicine_expire_days', '使用临期药', 2, '天内', 0, 7)
    ]
  },
  {
    id: 'maa-mall',
    section: 'maa',
    name: '信用商店',
    cadence: { kind: 'every', hours: 3 },
    trigger: '每趟发车',
    fields: [
      txt('maa_mall_buy', '优先购买', '招聘许可, 龙门币'),
      txt('maa_mall_blacklist', '黑名单', '碳, 家具零件'),
      sw('maa_mall_only_discount', '只买打折', false),
      sw('maa_credit_fight', '借助战刷信用', true)
    ]
  },
  {
    id: 'maa-award',
    section: 'maa',
    name: '领取奖励',
    cadence: { kind: 'every', hours: 3 },
    trigger: '每趟发车',
    fields: [
      sw('maa_mail', '邮件', true),
      sw('maa_orundum', '合成玉', true),
      sw('maa_mining', '赤金矿', false),
      sw('maa_specialaccess', '月卡', true)
    ]
  },
  {
    id: 'rogue',
    section: 'long',
    name: '集成战略',
    cadence: { kind: 'window' },
    trigger: '停运时段外',
    fields: [
      sel('maa_rg_theme', '主题', '萨卡兹', ['傀影', '水月', '萨米', '萨卡兹', '界园']),
      sel('squad', '开局分队', '指挥分队', ['指挥分队', '后勤分队', '蓝图测绘分队']),
      sel('mode', '模式', '刷蜡烛', ['刷蜡烛', '刷源石锭', '投资'])
    ]
  }
]

// 还没有放进线路的任务，可以插入
const spareList = [
  {
    id: 'sss',
    section: 'long',
    name: '保全派驻',
    cadence: { kind: 'window' },
    trigger: '停运时段外',
    fields: [sel('sss_type', '关卡', '多索雷斯', ['多索雷斯', '洛伦'])]
  },
  {
    id: 'rcl',
    section: 'long',
    name: '生息演算',
    cadence: { kind: 'window' },
    trigger: '停运时段外',
    fields: [sel('maa_rcl_theme', '主题', '沙洲遗闻', ['沙洲遗闻', '不知名的岛'])]
  },
  {
    id: 'sf',
    section: 'long',
    name: '隐秘战线',
    cadence: { kind: 'window' },
    trigger: '停运时段外',
    fields: [sel('sf_target', '目标', '结局 A', ['结局 A', '结局 B'])]
  },
  {
    id: 'mastery',
    section: 'daily',
    name: '技能专精',
    cadence: { kind: 'event' },
    trigger: '仓库扫描后发现可专精',
    fields: []
  },
  {
    id: 'maa-recruit',
    section: 'maa',
    name: 'MAA 公招',
    cadence: { kind: 'every', hours: 3 },
    trigger: '每趟发车',
    fields: []
  }
]
// 全局设置融入隐喻：设备 = 列车/乐器/表芯；截图与等待 = 节奏；空闲动作 = 终点/休止
export const globals = {
  device: {
    name: 'MuMu 12 · 实例 0',
    adb: '127.0.0.1:16384',
    status: '已连接',
    cpu: '8 核',
    ram: '16 GB',
    fields: [
      sel('screenshot', '截图后端', 'DroidCast', ['DroidCast', 'MuMu 截图', 'ADB']),
      sel('touch', '触控后端', 'scrcpy 1.21', ['scrcpy 1.21', 'MaaTouch', 'ADB']),
      sel('performance_mode', '性能适配', '自动', ['自动', '极高', '高', '中', '低']),
      sel('launch', '启动游戏', 'adb 命令', ['adb 命令', '点击屏幕', '自定义命令'])
    ]
  },
  pace: {
    fields: [
      num('screenshot_interval', '截图最短间隔', 500, '毫秒', 0, 2000, 50),
      num('selection_poll_interval', '选择轮询', 200, '毫秒', 50, 1000, 50),
      num('selection_transition_timeout', '场景切换超时', 8, '秒', 1, 30),
      num('waiting_loading', '加载界面最长等待', 6, '秒', 1, 60)
    ]
  },
  idle: {
    value: 'home',
    options: [
      ['idle', '原地待命'],
      ['home', '返回首页'],
      ['exit', '退出游戏'],
      ['close', '关闭模拟器']
    ]
  },
  maaGap: 3,
  longPause: [0, 8]
}

const clone = (task) => ({ ...task, fields: task.fields.map((f) => ({ ...f })) })

export function createState() {
  return reactive({
    tasks: taskList.map((task) => ({ ...clone(task), enabled: task.id !== 'reload' })),
    spare: spareList.map((task) => ({ ...clone(task), enabled: true })),
    globals: JSON.parse(JSON.stringify(globals)),
    // 选中项：任务 id，或 'device' / 'pace' / 'idle' / 'gap'
    selected: null,
    // 原型里模拟的当前时刻（小时，0-24）
    now: 14.4
  })
}

export function insertTask(state, id, section, index) {
  const at = state.spare.findIndex((task) => task.id === id)
  if (at < 0 || state.spare[at].section !== section) return
  const [task] = state.spare.splice(at, 1)
  const inSection = state.tasks.filter((t) => t.section === section)
  // 日常序列的顺序写死在 simulate() 里：按固定位置插入，忽略 index
  if (section === 'daily') index = inSection.filter((t) => dailyRank(t) < dailyRank(task)).length
  const anchor = inSection[index ?? inSection.length]
  const sectionOrder = ['base', 'daily', 'maa', 'long']
  const following = state.tasks.findIndex(
    (t) => sectionOrder.indexOf(t.section) > sectionOrder.indexOf(section)
  )
  const position = anchor
    ? state.tasks.indexOf(anchor)
    : inSection.length
      ? state.tasks.indexOf(inSection.at(-1)) + 1
      : following < 0
        ? state.tasks.length
        : following
  state.tasks.splice(position, 0, task)
  state.selected = task.id
}

export function removeTask(state, id) {
  const at = state.tasks.findIndex((task) => task.id === id)
  if (at < 0) return
  const [task] = state.tasks.splice(at, 1)
  state.spare.push(task)
  if (state.selected === id) state.selected = null
}

export function moveTask(state, id, step) {
  const task = state.tasks.find((t) => t.id === id)
  if (!task || !reorderable(task.section)) return
  const inSection = state.tasks.filter((t) => t.section === task.section)
  const swap = inSection[inSection.indexOf(task) + step]
  if (!swap) return
  const a = state.tasks.indexOf(task)
  const b = state.tasks.indexOf(swap)
  state.tasks[a] = swap
  state.tasks[b] = task
}

const usesMaaGap = (t) => t.section === 'maa' || ['stage', 'depot', 'reload'].includes(t.id)
const intervalFields = {
  drone: 'drone_interval',
  trust: 'trust_rotation_interval',
  recruit: 'recruit_gap'
}

export function taskInterval(state, task) {
  if (usesMaaGap(task)) return state.globals.maaGap
  const field = task.fields.find((f) => f.key === intervalFields[task.id])
  return field ? field.value : task.cadence.hours
}

// 模拟一天的发车：[{ id, section, hour, span? }]，供表盘和乐谱使用
export function simulateDay(state) {
  const runs = []
  const on = (id) => state.tasks.some((t) => t.id === id && t.enabled)
  if (on('shift'))
    for (const h of [1.5, 5, 9.5, 13, 17.5, 21])
      runs.push({ id: 'shift', section: 'base', hour: h })
  if (on('runorder'))
    for (let h = 0.7; h < 24; h += 2.6) runs.push({ id: 'runorder', section: 'base', hour: h })
  for (const t of state.tasks.filter((t) => t.enabled && t.cadence.kind === 'every')) {
    const gap = taskInterval(state, t)
    // 数字输入编辑中可以暂时为空；不为未填好的间隔生成预览。
    if (!Number.isFinite(gap) || gap < 1) continue
    for (let h = 4.3; h < 28; h += gap) runs.push({ id: t.id, section: t.section, hour: h % 24 })
  }
  for (const t of state.tasks.filter((t) => t.enabled && t.cadence.kind === 'daily')) {
    runs.push({ id: t.id, section: t.section, hour: 4.2 })
  }
  const [a, b] = state.globals.longPause
  if (Number.isFinite(a) && Number.isFinite(b)) {
    const pauseHours = b >= a ? b - a : 24 - a + b
    const span = 24 - pauseHours - 1
    if (span > 0) {
      for (const t of state.tasks.filter((t) => t.enabled && t.cadence.kind === 'window')) {
        runs.push({ id: t.id, section: t.section, hour: (b + 0.5) % 24, span })
      }
    }
  }
  return runs.sort((x, y) => x.hour - y.hour)
}

export function nextRun(state, id) {
  const runs = simulateDay(state).filter((r) => r.id === id)
  const next = runs.find((r) => r.hour > state.now) ?? runs[0]
  return next ? fmt(next.hour) : '—'
}

export function fmt(hour) {
  const total = Math.round(hour * 60) % (24 * 60)
  return `${String(Math.floor(total / 60)).padStart(2, '0')}:${String(total % 60).padStart(2, '0')}`
}

// simulate() 中日常任务的固定顺序
export const DAILY_ORDER = [
  'trust',
  'visit',
  'report',
  'skland',
  'mail',
  'recruit',
  'depot',
  'mastery',
  'stage'
]
const dailyRank = (t) => DAILY_ORDER.indexOf(t.id)

// 基建队列按时间排序、日常顺序固定；MAA 子任务和长任务原型里允许调整
export const reorderable = (section) => section === 'maa' || section === 'long'

// 闲时序列的进入门槛与收车余量（后端常量）
export const IDLE_GATE_MIN = 9
export const MAA_MARGIN = '5 分钟'
export const LONG_MARGIN = '30 秒'

// 距下一项基建任务的分钟数，以及它是哪一项
export function nextBase(state) {
  const runs = simulateDay(state).filter((r) => r.section === 'base')
  const next = runs.find((r) => r.hour > state.now) ?? runs[0]
  if (!next) return null
  const gap = Math.round(((next.hour - state.now + 24) % 24) * 60)
  const task = state.tasks.find((t) => t.id === next.id)
  return { id: next.id, name: task?.name, at: fmt(next.hour), gap, open: gap >= IDLE_GATE_MIN }
}

export const findTask = (state, id) =>
  state.tasks.find((t) => t.id === id) ?? state.spare.find((t) => t.id === id)
