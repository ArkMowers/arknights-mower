import { pinyin } from 'pinyin-pro'

/**
 * 仓库页的数据模型层：把后端那个位置元组 + 分类字典整理成页面直接可渲染的视图模型。
 *
 * 后端 /depot/readdepot 返回的是 `{ depot: [分类字典, 复制文本, 扫描时间], ... }`，
 * 位置索引没有名字、字段名又是中文，页面里散着写 `reportData[0]` / `data['number']`
 * 这种代码很快就会失去可维护性。这里把"读什么"和"怎么显示"分开：
 * 本文件只负责前者（纯净、可测），渲染交给 depot.vue。
 */

/** 分类前缀 → 展示名与配色。前缀本身是人工维护的档位序（A 常用 … K 未分类）。 */
export const DEPOT_TIERS = [
  { key: 'A', name: '常用资源', short: '常用', badge: '常用', color: '#d4a017', rarity: 5 },
  { key: 'B', name: '作战记录', short: '经验', badge: '经验', color: '#b07d3b', rarity: 3 },
  { key: 'C', name: '5星材料', short: '5星', badge: '5★', color: '#e0a800', rarity: 5 },
  { key: 'D', name: '4星材料', short: '4星', badge: '4★', color: '#b8860b', rarity: 4 },
  { key: 'E', name: '3星材料', short: '3星', badge: '3★', color: '#8a8a8a', rarity: 3 },
  { key: 'F', name: '2星材料', short: '2星', badge: '2★', color: '#6f7d5a', rarity: 2 },
  { key: 'G', name: '1星材料', short: '1星', badge: '1★', color: '#5a6b78', rarity: 1 },
  { key: 'H', name: '模组材料', short: '模组', badge: '模组', color: '#4a7fb5', rarity: 4 },
  { key: 'I', name: '技巧概要', short: '技能书', badge: '技能', color: '#5c8a8a', rarity: 3 },
  { key: 'J', name: '芯片与凭证', short: '芯片', badge: '芯片', color: '#7a6ba5', rarity: 4 },
  { key: 'K', name: '未分类', short: '未分类', badge: '其他', color: '#8a8a8a', rarity: 0 }
]

/** 抽卡资源换算：1 抽 = 600 合成玉；1 源石 = 180 合成玉；1 源石碎片 = 20 合成玉（两个碎片换一抽）。 */
export const DRAW_TIERS = [
  {
    key: '玉+卷',
    name: '基础 (玉+券)',
    short: '玉+券',
    label: '合成玉 + 寻访凭证',
    hint: '合成玉与寻访凭证现货',
    detail: '合成玉÷600 + 寻访凭证（单抽及十连）'
  },
  {
    key: '玉+卷+石',
    name: '+ 至纯源石',
    short: '+ 源石',
    label: '并入至纯源石',
    hint: '源石按 180 合成玉折算',
    detail: '在玉+券基础上，至纯源石按 180 合成玉 (0.3 抽) 折算并入'
  },
  {
    key: '额外+碎片',
    name: '+ 源石碎片',
    short: '+ 碎片',
    label: '并入源石碎片',
    hint: '碎片按两片换一抽',
    detail: '在上述基础之上，源石碎片按 2 片换 20 合成玉折算并入'
  },
  {
    key: '额外+碎片+土',
    name: '+ 固源岩',
    short: '+ 固源岩',
    label: '并入固源岩搓玉',
    hint: '固源岩按搓玉折算',
    detail: '在上述基础之上，固源岩按 2 块合成 1 碎片并折算抽数后并入'
  }
]

/** 哪些条目是后端算出来的、并不真实存在于仓库中的派生值。 */
export const DERIVED_ITEM_NAMES = new Set([
  ...DRAW_TIERS.map((tier) => tier.key),
  '全部经验（计算）'
])

export function isDerivedItem(name) {
  return DERIVED_ITEM_NAMES.has(name)
}

/** 用分类前缀找档位信息；找不到时给一个中性兜底，避免页面上出现 undefined。 */
export function tierOf(categoryName) {
  const prefix = String(categoryName || '')
    .trim()
    .charAt(0)
    .toUpperCase()
  return (
    DEPOT_TIERS.find((tier) => tier.key === prefix) || {
      key: prefix || '?',
      name: categoryName || '未分类',
      short: categoryName || '未分类',
      badge: prefix || '?',
      color: '#8a8a8a',
      rarity: 0
    }
  )
}

/**
 * 后端历史上存在两种返回形状：`{ depot: [...] }`（当前）与直接的元组 `[...]`（旧版本）。
 * 早期版本在 `resp.depot` 缺失时会把整个对象赋给 reportData，于是 `data[0]` 是 undefined，
 * 页面静默地渲染出一堆空白而不报错。这里显式区分"拿到了"和"没拿到"。
 */
export function parseDepotResponse(response) {
  const tuple = Array.isArray(response) ? response : response?.depot
  const report = Array.isArray(tuple) ? tuple : null
  const categories = report?.[0]

  if (!categories || typeof categories !== 'object' || Array.isArray(categories)) {
    return {
      ok: false,
      categories: {},
      copyText: '',
      scannedAt: '',
      cultivateOk: Boolean(response?.cultivate_ok),
      cultivateMsg: response?.cultivate_msg || ''
    }
  }

  return {
    ok: true,
    categories,
    copyText: typeof report[1] === 'string' ? report[1] : '',
    scannedAt: report[2] == null ? '' : String(report[2]),
    cultivateOk: Boolean(response?.cultivate_ok),
    cultivateMsg: response?.cultivate_msg || ''
  }
}

export function isTokenItem(name) {
  return typeof name === 'string' && name.includes('信物')
}

/** 一个分类字典 → 条目数组，带档位、派生标记，并按后端给的 sort 升序。 */
export function flattenItems(categories) {
  const rows = []
  const used = new Map()
  for (const [categoryName, items] of Object.entries(categories || {})) {
    if (!items || typeof items !== 'object') continue
    const tier = tierOf(categoryName)
    for (const [name, data] of Object.entries(items)) {
      // 过滤信物类物品，不予在仓库中展示
      if (isTokenItem(name)) continue
      // 同名条目理论上归属唯一分类；真出现重复时保留首个，避免 grid key 冲突。
      if (used.has(name)) continue
      used.set(name, true)
      rows.push({
        name,
        number: Number(data?.number ?? 0),
        sort: Number(data?.sort ?? Number.MAX_SAFE_INTEGER),
        icon: data?.icon || name,
        category: categoryName,
        tier: tier.key,
        tierName: tier.name,
        tierShort: tier.short,
        tierBadge: tier.badge,
        color: tier.color,
        rarity: tier.rarity,
        derived: isDerivedItem(name)
      })
    }
  }
  return rows.sort((a, b) => a.sort - b.sort || a.name.localeCompare(b.name, 'zh-CN'))
}

/** 前端兜底折算用的档位键；派生值一律以后端为准。 */
const DRAW_TIER_KEYS = ['玉+卷', '玉+卷+石', '额外+碎片', '额外+碎片+土']

/** 参与折算的原始物料；一个都没有时说明这条快照根本没有抽数，不该补 0。 */
const DRAW_SOURCE_KEYS = ['合成玉', '寻访凭证', '十连寻访凭证', '至纯源石', '源石碎片', '固源岩']

/**
 * 单条快照的抽数：优先读后端写入的派生项。
 *
 * 后端 读取仓库 与 读取仓库历史 都按同一份公式（depot.py 折算抽数）填好这四个键，
 * 前端只负责取值。只有旧快照缺派生项时才走 fallbackDrawCount —— 浮点舍入上 Python
 * 的 round() 与 JS 的 Math.round() 并不等价，同一份仓库能差 0.1 抽，所以兜底值只
 * 用来补缺，不能盖过后端结果。
 */
export function computeDrawCount(items = {}, drawTierKey = '玉+卷') {
  const derived = Number(items?.[drawTierKey])
  if (Number.isFinite(derived)) return derived
  return fallbackDrawCount(items, drawTierKey)
}

/** 按 depot.py 折算抽数的口径在本地重算，仅用于派生项缺失的快照。 */
function fallbackDrawCount(items = {}, drawTierKey = '玉+卷') {
  // 六个来源键全缺时返回 NaN：让 buildDrawHistory 把它过滤掉，
  // 而不是画出一个"抽数 0"的假点。
  if (!DRAW_SOURCE_KEYS.some((key) => Number.isFinite(Number(items?.[key])))) return NaN

  const jade = Number(items['合成玉'] ?? 0)
  const tickets = Number(items['寻访凭证'] ?? 0) + Number(items['十连寻访凭证'] ?? 0) * 10
  const opOriginium = Number(items['至纯源石'] ?? 0)
  const shards = Number(items['源石碎片'] ?? 0)
  const rock = Number(items['固源岩'] ?? 0)
  const base = jade + opOriginium * 180
  const rockShards = Math.floor(rock / 2)

  switch (drawTierKey) {
    case '玉+卷+石':
      return Math.round((base / 600 + tickets) * 10) / 10
    case '额外+碎片':
      return Math.round(((base + Math.floor(shards / 2) * 20) / 600 + tickets) * 10) / 10
    case '额外+碎片+土':
      return (
        Math.round(((base + Math.floor((shards + rockShards) / 2) * 20) / 600 + tickets) * 10) / 10
      )
    case '玉+卷':
    default:
      return Math.round((jade / 600 + tickets) * 10) / 10
  }
}

/** 该快照是否带齐了后端派生档位；缺一个就整体按兜底公式处理。 */
export function hasDerivedDrawTiers(items) {
  return DRAW_TIER_KEYS.every((key) => Number.isFinite(Number(items?.[key])))
}

/** 抽数历史快照序列计算 */
export function buildDrawHistory(snapshots, drawTierKey = '玉+卷') {
  return usableSnapshots(snapshots)
    .map((entry) => ({
      at: entry.at,
      value: computeDrawCount(entry.items || {}, drawTierKey)
    }))
    .filter((point) => Number.isFinite(point.value))
}

/**
 * 快照序列里"能用来对比"的条目：必须有秒级时间戳和物品字典。
 *
 * 后端 读取仓库历史 已经保证这个形状，但这里是前端唯一入口，独立校验一遍才不会
 * 让一条残行把整条曲线或整个下拉框带崩。
 */
export function usableSnapshots(snapshots) {
  const list = Array.isArray(snapshots) ? snapshots : []
  return list.filter(
    (entry) =>
      entry && typeof entry.at === 'number' && entry.items && typeof entry.items === 'object'
  )
}

/** 快照 → 下拉选项，历史条目按时间反序罗列并带上相对时间。 */
function snapshotOption(snap) {
  const rel = formatRelative(snap.at)
  return {
    value: String(snap.at),
    label: `${formatTimestamp(snap.at)} ${rel ? `(${rel})` : ''}`,
    at: snap.at
  }
}

/** 同值的选项只保留第一个，避免同一时间戳在"较最早记录"和具体条目上重复出现。 */
function dedupeOptions(options) {
  const seen = new Set()
  return options.filter((opt) => {
    if (seen.has(opt.value)) return false
    seen.add(opt.value)
    return true
  })
}

/**
 * 扫描快照序列 → 生成对比起始点下拉选项。
 */
export function buildBaselineStartOptions(snapshots) {
  const usable = usableSnapshots(snapshots)
  if (usable.length < 2) return []

  const previous = usable[usable.length - 2]
  const first = usable[0]

  const options = [
    {
      value: 'previous',
      label: `较上次扫描 (${formatTimestamp(previous.at)})`,
      at: previous.at
    }
  ]

  if (usable.length > 2) {
    options.push({
      value: 'first',
      label: `较最早记录 (${formatTimestamp(first.at)})`,
      at: first.at
    })
  }

  // 历史所有快照反序罗列（不含最新一条，最新默认作为结束点）
  for (let i = usable.length - 2; i >= 0; i--) {
    options.push(snapshotOption(usable[i]))
  }

  return dedupeOptions(options)
}

/**
 * 扫描快照序列 → 生成对比结束点下拉选项。
 */
export function buildBaselineEndOptions(snapshots) {
  const usable = usableSnapshots(snapshots)
  if (usable.length < 2) return []

  const latest = usable[usable.length - 1]

  const options = [
    {
      value: 'latest',
      label: `当前最新 (${formatTimestamp(latest.at)})`,
      at: latest.at
    }
  ]

  // 历史快照反序罗列
  for (let i = usable.length - 1; i >= 0; i--) {
    options.push(snapshotOption(usable[i]))
  }

  return dedupeOptions(options)
}

export const BASELINE_PRESETS = [
  { key: 'previous', label: '单次环比', shortLabel: '单次' },
  { key: 'today', label: '当天', shortLabel: '当天' },
  { key: '7d', label: '近 7 天', shortLabel: '7d' },
  { key: '14d', label: '近 14 天', shortLabel: '14d' },
  { key: '30d', label: '近 30 天', shortLabel: '30d' },
  { key: 'all', label: '全部历史', shortLabel: '全部' }
]

export function computePresetRange(presetKey, nowMs = Date.now()) {
  const now = new Date(nowMs)
  const endOfDay = nowMs

  switch (presetKey) {
    case 'today': {
      const startOfDay = new Date(
        now.getFullYear(),
        now.getMonth(),
        now.getDate(),
        0,
        0,
        0,
        0
      ).getTime()
      return [startOfDay, endOfDay]
    }
    case '7d': {
      return [nowMs - 7 * 24 * 60 * 60 * 1000, endOfDay]
    }
    case '14d': {
      return [nowMs - 14 * 24 * 60 * 60 * 1000, endOfDay]
    }
    case '30d': {
      return [nowMs - 30 * 24 * 60 * 60 * 1000, endOfDay]
    }
    case 'all': {
      return [0, endOfDay]
    }
    default:
      return null
  }
}

/**
 * 将时间范围或快捷预设对齐到快照序列中的起止快照。
 */
export function alignSnapshotsToRange(snapshots, options = {}, nowMs = Date.now()) {
  const usable = usableSnapshots(snapshots)
  const preset = options.preset || 'previous'
  const followLatest = options.followLatest !== false

  if (usable.length < 2) {
    return {
      matchedCount: usable.length,
      startSnapshot: usable[0] || null,
      endSnapshot: usable[0] || null,
      effectiveRange: usable[0] ? [usable[0].at * 1000, usable[0].at * 1000] : null,
      matchedSnapshots: usable
    }
  }

  if (preset === 'previous') {
    const startSnapshot = usable[usable.length - 2]
    const endSnapshot = usable[usable.length - 1]
    return {
      matchedCount: 2,
      startSnapshot,
      endSnapshot,
      effectiveRange: [startSnapshot.at * 1000, endSnapshot.at * 1000],
      matchedSnapshots: [startSnapshot, endSnapshot]
    }
  }

  if (preset === 'all') {
    const startSnapshot = usable[0]
    const endSnapshot = usable[usable.length - 1]
    return {
      matchedCount: usable.length,
      startSnapshot,
      endSnapshot,
      effectiveRange: [startSnapshot.at * 1000, endSnapshot.at * 1000],
      matchedSnapshots: usable
    }
  }

  let range = options.range
  if (!range || !Array.isArray(range) || range.length < 2) {
    range = computePresetRange(preset, nowMs)
  }

  if (!range || !range[0] || !range[1]) {
    const startSnapshot = usable[0]
    const endSnapshot = usable[usable.length - 1]
    return {
      matchedCount: usable.length,
      startSnapshot,
      endSnapshot,
      effectiveRange: [startSnapshot.at * 1000, endSnapshot.at * 1000],
      matchedSnapshots: usable
    }
  }

  const startSec = Math.floor(range[0] / 1000)
  const endSec = followLatest ? usable[usable.length - 1].at : Math.ceil(range[1] / 1000)

  const matched = usable.filter((s) => s.at >= startSec && s.at <= endSec)

  if (matched.length === 0) {
    return {
      matchedCount: 0,
      startSnapshot: null,
      endSnapshot: null,
      effectiveRange: null,
      matchedSnapshots: []
    }
  }

  if (matched.length === 1) {
    return {
      matchedCount: 1,
      startSnapshot: matched[0],
      endSnapshot: matched[0],
      effectiveRange: [matched[0].at * 1000, matched[0].at * 1000],
      matchedSnapshots: matched
    }
  }

  const startSnapshot = matched[0]
  const endSnapshot = matched[matched.length - 1]

  return {
    matchedCount: matched.length,
    startSnapshot,
    endSnapshot,
    effectiveRange: [startSnapshot.at * 1000, endSnapshot.at * 1000],
    matchedSnapshots: matched
  }
}

/**
 * 对比起点/结束点下拉的取值：把 'previous' / 'first' / 'latest' / 秒级时间戳 / 快照对象
 * 统一解析成一条快照。depot.vue 的趋势标签与 deltaMap 都走这里，避免页面里再抄一份
 * 同样的分支级联。
 */
export function resolveSnapshot(usable, key, fallbackIndex) {
  if (!usable || !usable.length) return null
  if (typeof key === 'object' && key !== null && typeof key.at === 'number') return key
  if (key === 'latest') return usable[usable.length - 1]
  if (key === 'previous') return usable[Math.max(0, usable.length - 2)]
  if (key === 'first') return usable[0]

  const targetAt = Number(key)
  if (Number.isFinite(targetAt)) {
    const found = usable.find((s) => s.at === targetAt)
    if (found) return found
  }

  if (typeof fallbackIndex === 'number') {
    const idx = fallbackIndex < 0 ? usable.length + fallbackIndex : fallbackIndex
    return usable[idx] ?? null
  }
  return null
}

/**
 * 扫描快照序列 → 任意两个快照点之间的物品差额。
 *
 * 仅对比两端快照中均观测到的物品；快照中缺失的物品代表本次扫描未覆盖（而非确认为 0），
 * 不在此区间生成虚假的增减差额。
 *
 * startKey: 'previous' | 'first' | 时间戳
 * endKey: 'latest' | 时间戳
 */
export function buildDeltaMap(snapshots, startKey = 'previous', endKey = 'latest') {
  const list = Array.isArray(snapshots) ? snapshots : []
  const usable = usableSnapshots(list)
  if (usable.length < 2) return new Map()

  const startSnapshot = resolveSnapshot(usable, startKey, usable.length - 2)
  const endSnapshot = resolveSnapshot(usable, endKey, usable.length - 1)

  if (!startSnapshot || !endSnapshot || startSnapshot === endSnapshot) return new Map()

  const delta = new Map()
  const startItems = startSnapshot.items || {}
  const endItems = endSnapshot.items || {}

  for (const [name, endValRaw] of Object.entries(endItems)) {
    if (Object.prototype.hasOwnProperty.call(startItems, name)) {
      const before = Number(startItems[name])
      const after = Number(endValRaw)
      if (Number.isFinite(before) && Number.isFinite(after)) {
        const change = after - before
        if (change !== 0) delta.set(name, change)
      }
    }
  }
  return delta
}

/** 单个物品的历史曲线点，按时间升序。仅记录实际被扫描观测到的数据点，未扫描的快照直接跳过，避免将未观测物料误记为 0 导致曲线虚假下跌。 */
export function buildItemHistory(snapshots, itemName) {
  return usableSnapshots(snapshots)
    .filter(
      (entry) =>
        entry.items &&
        Object.prototype.hasOwnProperty.call(entry.items, itemName) &&
        Number.isFinite(Number(entry.items[itemName]))
    )
    .map((entry) => ({
      at: entry.at,
      value: Number(entry.items[itemName])
    }))
}

/** 该物品历史中的净增减，用于详情页"这段时间攒了多少"。 */
export function summarizeItemHistory(points) {
  if (!Array.isArray(points) || points.length < 2) {
    return {
      change: 0,
      first: points?.[0]?.value ?? 0,
      last: points?.[0]?.value ?? 0,
      points: points?.length ?? 0
    }
  }
  const first = points[0].value
  const last = points[points.length - 1].value
  return { change: last - first, first, last, points: points.length }
}

/**
 * 中文/拼音/英文/分类/星级/变动/关注混合搜索与过滤。
 *
 * stockFilter 是"库存状态"这个概念的完整取值：all / owned / empty。之前页面只把
 * owned 传进来、再在外面自己滤一遍 empty，同一个概念被拆成两处判断。
 */
export function filterItems(
  items,
  {
    query = '',
    stockFilter = 'all',
    ownedOnly = false,
    showDerived = true,
    deltaFilter = 'all',
    deltaMap = new Map(),
    favoriteOnly = false,
    favorites = []
  } = {}
) {
  const text = String(query || '').trim()
  const favSet = new Set(Array.isArray(favorites) ? favorites : [])
  // ownedOnly 是 stockFilter 出现前的旧参数，保留以免调用方漏改后静默失去过滤。
  const stock = stockFilter === 'all' && ownedOnly ? 'owned' : stockFilter
  return (items || []).filter((item) => {
    if (!showDerived && item.derived) return false
    if (stock === 'owned' && !(item.number > 0)) return false
    if (stock === 'empty' && item.number > 0) return false
    if (favoriteOnly && !favSet.has(item.name)) return false

    if (deltaFilter === 'increased') {
      const diff = deltaMap.get(item.name) ?? 0
      if (!(diff > 0)) return false
    } else if (deltaFilter === 'decreased') {
      const diff = deltaMap.get(item.name) ?? 0
      if (!(diff < 0)) return false
    } else if (deltaFilter === 'changed') {
      const diff = deltaMap.get(item.name) ?? 0
      if (diff === 0) return false
    } else if (deltaFilter === 'unchanged') {
      const diff = deltaMap.get(item.name) ?? 0
      if (diff !== 0) return false
    }

    if (!text) return true
    return matchesQuery(item, text)
  })
}

const STAR_TIER_MAP = {
  '5星': 'C',
  五星: 'C',
  '5*': 'C',
  '4星': 'D',
  四星: 'D',
  '4*': 'D',
  '3星': 'E',
  三星: 'E',
  '3*': 'E',
  '2星': 'F',
  二星: 'F',
  '2*': 'F',
  '1星': 'G',
  一星: 'G',
  '1*': 'G'
}

function matchesCategoryOrTier(item, text) {
  const t = text.toLowerCase()
  if (STAR_TIER_MAP[t] !== undefined) {
    return item.tier === STAR_TIER_MAP[t]
  }
  if (item.category && item.category.toLowerCase().includes(t)) return true
  if (item.tierName && item.tierName.toLowerCase().includes(t)) return true
  if (item.tierShort && item.tierShort.toLowerCase().includes(t)) return true
  return false
}

/**
 * 数值与区间条件过滤：
 * - 比较运算符：<, <=, >, >=, =, != 以及中文全角/词汇（如 小于50, 不超过100, 至少20）
 * - 区间匹配：10-50, 10~50, 10..50, 10到50
 * - 纯数字：默认按 >= 匹配
 */
export function matchesNumericQuery(num, queryText) {
  const t = String(queryText || '').trim()
  if (!t) return false
  const val = Number(num ?? 0)
  if (!Number.isFinite(val)) return false

  // 1. 区间: 10-50, 10~50, 10..50, 10到50, 10至50
  const rangeMatch = t.match(/^(\d+)\s*(?:[-~～]|到|至|\.\.)\s*(\d+)$/)
  if (rangeMatch) {
    const min = Number(rangeMatch[1])
    const max = Number(rangeMatch[2])
    return val >= Math.min(min, max) && val <= Math.max(min, max)
  }

  // 2. <=, ≤, 小于等于, 不超过, 至多
  const lteMatch = t.match(/^(?:<=|≤|小于等于|不超过|至多)\s*(\d+)$/)
  if (lteMatch) return val <= Number(lteMatch[1])

  // 3. >=, ≥, 大于等于, 至少
  const gteMatch = t.match(/^(?:>=|≥|大于等于|至少)\s*(\d+)$/)
  if (gteMatch) return val >= Number(gteMatch[1])

  // 4. <, ＜, 小于
  const ltMatch = t.match(/^(?:<|＜|小于)\s*(\d+)$/)
  if (ltMatch) return val < Number(ltMatch[1])

  // 5. >, ＞, 大于
  const gtMatch = t.match(/^(?:>|＞|大于)\s*(\d+)$/)
  if (gtMatch) return val > Number(gtMatch[1])

  // 6. !=, ≠, 不等于
  const neMatch = t.match(/^(?:!=|≠|不等于)\s*(\d+)$/)
  if (neMatch) return val !== Number(neMatch[1])

  // 7. =, ==, ＝, 等于
  const eqMatch = t.match(/^(?:={1,2}|＝|等于)\s*(\d+)$/)
  if (eqMatch) return val === Number(eqMatch[1])

  // 8. 纯数字: 默认为 >= target
  if (/^\d+$/.test(t)) return val >= Number(t)

  return false
}

export function matchesQuery(item, text) {
  const t = String(text || '').trim()
  if (!t) return true
  if (item.name.includes(t)) return true
  if (item.name.toLowerCase().includes(t.toLowerCase())) return true
  // 拼音首字母或全拼匹配
  if (matchesPinyin(item.name, t)) return true
  // 分类/档位/星级标签匹配
  if (matchesCategoryOrTier(item, t)) return true
  // 数值条件过滤（支持 <, <=, >, >=, =, !=, 区间等）
  if (matchesNumericQuery(item.number, t)) return true
  return false
}

/**
 * 中文物品名的拼音搜索：支持首字母缩写（lmb / zzxp）与全拼（longmenbi）。
 */
const pinyinCache = new Map()

function getPinyinData(name) {
  if (pinyinCache.has(name)) return pinyinCache.get(name)
  let initials = ''
  let full = ''
  try {
    initials = pinyin(name, { pattern: 'first', toneType: 'none', type: 'array' })
      .join('')
      .toLowerCase()
    full = pinyin(name, { toneType: 'none', separator: '' }).toLowerCase()
  } catch {
    initials = ''
    full = ''
  }
  const data = { initials, full }
  pinyinCache.set(name, data)
  return data
}

export function matchesPinyin(name, query) {
  const text = String(query || '')
    .trim()
    .toLowerCase()
  if (!text) return false
  if (!/^[a-z0-9·]+$/.test(text)) return false

  const { initials, full } = getPinyinData(name)
  if (!initials && !full) return false

  // 1. 全拼子串（如 longmenbi / longmen / bi）
  if (full && full.includes(text)) return true

  // 2. 首字母连续子串（如 lmb / lm）
  if (initials && initials.includes(text)) return true

  // 3. 首字母子序列（如 zzxp 匹配 zzsxp）
  if (initials) {
    let cursor = 0
    let matched = true
    for (const char of text) {
      cursor = initials.indexOf(char, cursor)
      if (cursor === -1) {
        matched = false
        break
      }
      cursor += 1
    }
    if (matched) return true
  }

  return false
}

export const SORT_MODES = [
  { value: 'tier', label: '档位优先' },
  { value: 'delta-desc', label: '变动增量从多到少 (增长优先)' },
  { value: 'delta-asc', label: '变动增量从少到多 (消耗优先)' },
  { value: 'count-desc', label: '库存数量从多到少' },
  { value: 'count-asc', label: '库存数量从少到多' },
  { value: 'name', label: '按物品名称' }
]

export function sortItems(items, mode = 'tier', deltaMap = new Map()) {
  const list = [...(items || [])]
  switch (mode) {
    case 'delta-desc':
      return list.sort(
        (a, b) =>
          (deltaMap.get(b.name) ?? 0) - (deltaMap.get(a.name) ?? 0) ||
          b.number - a.number ||
          a.sort - b.sort
      )
    case 'delta-asc':
      return list.sort(
        (a, b) =>
          (deltaMap.get(a.name) ?? 0) - (deltaMap.get(b.name) ?? 0) ||
          a.number - b.number ||
          a.sort - b.sort
      )
    case 'count-desc':
      return list.sort((a, b) => b.number - a.number || a.sort - b.sort)
    case 'count-asc':
      return list.sort((a, b) => a.number - b.number || a.sort - b.sort)
    case 'name':
      return list.sort((a, b) => a.name.localeCompare(b.name, 'zh-CN'))
    case 'tier':
    default:
      // 档位优先时，派生条目沉到所属分类末尾（后端给了 9999999 的 sort），保持原语义。
      return list.sort((a, b) => a.sort - b.sort || a.name.localeCompare(b.name, 'zh-CN'))
  }
}

/** 按固定档位字典分组，确保无论如何排序，A~K 分组结构与导航顺序恒定稳定 */
export function groupItemsByTier(items, tierCounts = {}) {
  const map = new Map()
  for (const item of items || []) {
    if (!map.has(item.tier)) {
      map.set(item.tier, [])
    }
    map.get(item.tier).push(item)
  }

  const groups = []
  for (const tierDef of DEPOT_TIERS) {
    if (map.has(tierDef.key)) {
      const rows = map.get(tierDef.key)
      groups.push({
        key: tierDef.key,
        name: tierDef.name,
        short: rows[0]?.tierShort || tierDef.short,
        badge: rows[0]?.tierBadge || tierDef.badge || tierDef.key,
        color: tierDef.color,
        rows,
        total: tierCounts[tierDef.key]?.total ?? rows.length,
        shown: rows.length
      })
    }
  }

  // 兜底处理未在 DEPOT_TIERS 中注册的未知前缀
  for (const [tierKey, rows] of map.entries()) {
    if (!DEPOT_TIERS.some((t) => t.key === tierKey)) {
      const fallback = tierOf(tierKey)
      groups.push({
        key: tierKey,
        name: fallback.name,
        short: rows[0]?.tierShort || fallback.short,
        badge: rows[0]?.tierBadge || fallback.badge || tierKey,
        color: fallback.color,
        rows,
        total: tierCounts[tierKey]?.total ?? rows.length,
        shown: rows.length
      })
    }
  }
  return groups
}

/** 每个档位下的条目数与"有货"数，用于档位导航上的角标。 */
export function countByTier(items) {
  const counts = {}
  for (const item of items || []) {
    const bucket = counts[item.tier] || (counts[item.tier] = { total: 0, owned: 0 })
    bucket.total += 1
    if (item.number > 0) bucket.owned += 1
  }
  return counts
}

/**
 * Hero 区要展示的四个数字。抽卡数直接取后端算好的派生项，而不是在前端重算：
 * 换算公式（600 玉一抽、源石 180、碎片两片一抽）只在 depot.py 里维护一份，
 * 前端重算迟早会和后端漂移。
 */
export function buildHighlights(categories) {
  const items = flattenItems(categories)
  const find = (name) => items.find((item) => item.name === name)
  const draws = DRAW_TIERS.map((tier) => {
    const item = find(tier.key)
    return { ...tier, value: item ? item.number : null, icon: item?.icon || '寻访凭证' }
  }).filter((tier) => tier.value !== null)

  return {
    draws,
    currencies: ['龙门币', '至纯源石', '合成玉', '高级凭证', '资质凭证', '招聘许可']
      .map((name) => find(name))
      .filter(Boolean)
      .map((item) => ({ ...item, compact: formatCompact(item.number) })),
    exp: (() => {
      const item = find('全部经验（计算）')
      // icon 直接用后端给的 EXP（depot.py 里写死为资源包中的 EXP.webp）；
      // 不再覆盖成「高级作战记录」，那是 B经验卡 分类下真实物料的图。
      return item ? { ...item, compact: formatCompact(item.number) } : null
    })()
  }
}

export const FAVORITES_STORAGE_KEY = 'mower_depot_favorites'

export function loadFavorites(storage = typeof localStorage !== 'undefined' ? localStorage : null) {
  if (!storage) return []
  try {
    const raw = storage.getItem(FAVORITES_STORAGE_KEY)
    if (!raw) return []
    const parsed = JSON.parse(raw)
    return Array.isArray(parsed) ? parsed.filter((x) => typeof x === 'string') : []
  } catch {
    return []
  }
}

export function saveFavorites(
  favorites,
  storage = typeof localStorage !== 'undefined' ? localStorage : null
) {
  if (!storage) return
  try {
    const list = Array.isArray(favorites) ? Array.from(new Set(favorites.filter(Boolean))) : []
    storage.setItem(FAVORITES_STORAGE_KEY, JSON.stringify(list))
  } catch {
    // ignore
  }
}

/** 关注物品高亮看板数据（含最新存量及基准差额） */
export function buildFavoriteHighlights(allItems, favoriteNames = [], deltaMap = new Map()) {
  if (!Array.isArray(favoriteNames) || !favoriteNames.length) return []
  const itemMap = new Map((allItems || []).map((item) => [item.name, item]))
  return favoriteNames
    .map((name) => {
      const item = itemMap.get(name)
      if (!item) return null
      const delta = deltaMap.get(name) ?? 0
      return {
        ...item,
        compact: formatCompact(item.number),
        delta
      }
    })
    .filter(Boolean)
}

/** 数量格式化：万以上折成"万"，保留两位小数，去掉无意义的尾巴零。 */
export function formatCompact(value) {
  const number = Number(value)
  if (!Number.isFinite(number)) return '—'
  const abs = Math.abs(number)
  if (abs >= 100000000) return `${trimZero(number / 100000000)} 亿`
  if (abs >= 10000) return `${trimZero(number / 10000)} 万`
  return formatNumber(number)
}

function trimZero(value) {
  return value.toFixed(2).replace(/\.?0+$/, '')
}

export function formatNumber(value) {
  const number = Number(value)
  if (!Number.isFinite(number)) return '—'
  return new Intl.NumberFormat('zh-CN', { maximumFractionDigits: 2 }).format(number)
}

/** 带符号的变化量，用于环比徽标。 */
export function formatDelta(value) {
  const number = Number(value)
  if (!Number.isFinite(number) || number === 0) return ''
  return `${number > 0 ? '+' : '−'}${formatCompact(Math.abs(number))}`
}

export function formatTimestamp(at) {
  if (at == null || at === '') return '—'
  const date =
    typeof at === 'number' ? new Date(at * 1000) : new Date(String(at).replace(/-/g, '/'))
  if (Number.isNaN(date.getTime())) return String(at)
  return new Intl.DateTimeFormat('zh-CN', {
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit'
  }).format(date)
}

/** 相对时间，用于"上次扫描：3 小时前"。 */
export function formatRelative(at, now = Date.now()) {
  const seconds = typeof at === 'number' ? at : null
  if (seconds == null) return ''
  const diff = Math.floor(now / 1000) - seconds
  if (diff < 0) return '刚刚'
  if (diff < 60) return `${diff} 秒前`
  if (diff < 3600) return `${Math.floor(diff / 60)} 分钟前`
  if (diff < 86400) return `${Math.floor(diff / 3600)} 小时前`
  if (diff < 2592000) return `${Math.floor(diff / 86400)} 天前`
  return formatTimestamp(seconds)
}

/** 图标地址：后端按 depot/ 前缀从资源包提供，缺失时页面走 fallback。 */
export function itemIconUrl(icon) {
  if (!icon) return ''
  return `/depot/${encodeURIComponent(icon)}.webp`
}

/**
 * 复制到明日方舟工具箱用的文本。后端给的是它自己序列化的 json 字符串，
 * 直接用它即可；为空时给一个明确的提示而不是复制空串。
 */
export function resolveCopyText(parsed) {
  return typeof parsed?.copyText === 'string' ? parsed.copyText.trim() : ''
}

/**
 * 格式化仓库库存图片导出的文件名。
 */
export function buildDepotExportFilename(scannedAt, scope = 'all', now = new Date()) {
  let timePart = ''
  if (scannedAt && typeof scannedAt === 'string') {
    const digits = scannedAt.replace(/\D+/g, '')
    if (digits.length >= 8) {
      timePart = digits.length >= 14 ? `${digits.slice(0, 8)}_${digits.slice(8, 14)}` : digits
    }
  }
  if (!timePart) {
    const d = now instanceof Date && !Number.isNaN(now.getTime()) ? now : new Date()
    const pad = (n) => String(n).padStart(2, '0')
    const yyyy = d.getFullYear()
    const mm = pad(d.getMonth() + 1)
    const dd = pad(d.getDate())
    const hh = pad(d.getHours())
    const mi = pad(d.getMinutes())
    const ss = pad(d.getSeconds())
    timePart = `${yyyy}${mm}${dd}_${hh}${mi}${ss}`
  }

  const prefix = scope === 'filtered' ? 'mower-depot-filtered' : 'mower-depot'
  return `${prefix}-${timePart}.png`
}
