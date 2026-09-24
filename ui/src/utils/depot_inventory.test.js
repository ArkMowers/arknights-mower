import { describe, expect, it } from 'vitest'

import {
  alignSnapshotsToRange,
  BASELINE_MODES,
  BASELINE_PRESETS,
  BASELINE_STORAGE_KEY,
  DEFAULT_BASELINE_CONFIG,
  buildBaselineEndOptions,
  buildBaselineStartOptions,
  buildDeltaDetail,
  buildDeltaMap,
  computePresetRange,
  buildDepotExportFilename,
  buildFavoriteHighlights,
  buildHighlights,
  buildItemHistory,
  computeDrawCount,
  countByTier,
  FAVORITES_STORAGE_KEY,
  filterItems,
  flattenItems,
  formatCompact,
  formatDelta,
  formatNumber,
  formatRelative,
  formatTimestamp,
  groupItemsByTier,
  isDerivedItem,
  isTokenItem,
  isValidBaselineRange,
  isValidSnapshotKey,
  itemIconUrl,
  loadBaselineConfig,
  loadFavorites,
  matchesNumericQuery,
  matchesPinyin,
  parseDepotResponse,
  RELATIVE_PRESET_KEYS,
  resolveCopyText,
  resolveSnapshot,
  saveBaselineConfig,
  saveFavorites,
  sortItems,
  summarizeItemHistory,
  tierOf,
  usableSnapshots
} from './depot_inventory'

function item(number, sort = 1, icon = 'x') {
  return { number, sort, icon }
}

function categoriesOf(entries) {
  // entries: { 分类名: { 物品名: 数量 } }
  // 后端为每件物品都写了唯一的 sort（key_mapping 里的资源序号），这里按写入顺序
  // 递增模拟，避免所有条目 sort 相同而让排序退化到按名称比较。
  const result = {}
  let sort = 1
  for (const [category, items] of Object.entries(entries)) {
    result[category] = {}
    for (const [name, number] of Object.entries(items)) {
      result[category][name] = item(number, sort++)
    }
  }
  return result
}

describe('parseDepotResponse', () => {
  it('reads the current wrapped shape', () => {
    const parsed = parseDepotResponse({
      depot: [{ A常用: { 合成玉: item(600) } }, '{"合成玉":600}', '2026-09-24 10:00:00'],
      cultivate_ok: true,
      cultivate_msg: '2026-09-24 09:00:00'
    })

    expect(parsed.ok).toBe(true)
    expect(parsed.copyText).toBe('{"合成玉":600}')
    expect(parsed.scannedAt).toBe('2026-09-24 10:00:00')
    expect(parsed.cultivateOk).toBe(true)
  })

  it('reads the legacy bare-tuple shape', () => {
    const parsed = parseDepotResponse([{ A常用: { 合成玉: item(1) } }, 'txt', 'time'])

    expect(parsed.ok).toBe(true)
    expect(parsed.copyText).toBe('txt')
  })

  it('reports failure instead of silently yielding undefined fields', () => {
    // 旧页面在 resp.depot 缺失时把整个对象当元组用，data[0] 是 undefined，页面全空白却不报错。
    const parsed = parseDepotResponse({ cultivate_ok: false, cultivate_msg: '未同步' })

    expect(parsed.ok).toBe(false)
    expect(parsed.categories).toEqual({})
    expect(parsed.scannedAt).toBe('')
    expect(parsed.cultivateMsg).toBe('未同步')
  })

  it('rejects an array standing in for the category dict', () => {
    expect(parseDepotResponse({ depot: [[], 'txt', 'time'] }).ok).toBe(false)
  })

  it('tolerates null and primitive inputs', () => {
    expect(parseDepotResponse(null).ok).toBe(false)
    expect(parseDepotResponse(undefined).ok).toBe(false)
    expect(parseDepotResponse('nope').ok).toBe(false)
  })

  it('normalizes a non-string copy text and missing scan time', () => {
    const parsed = parseDepotResponse({ depot: [{ A常用: {} }, 12345, null] })

    expect(parsed.copyText).toBe('')
    expect(parsed.scannedAt).toBe('')
  })
})

describe('tierOf', () => {
  it('maps a category prefix to its tier metadata', () => {
    expect(tierOf('A常用')).toMatchObject({ key: 'A', short: '常用', badge: '常用', rarity: 5 })
    expect(tierOf('C稀有度5')).toMatchObject({ key: 'C', badge: '5★', rarity: 5 })
    expect(tierOf('K未分类')).toMatchObject({ key: 'K', badge: '其他', rarity: 0 })
  })

  it('falls back neutrally for unknown or missing prefixes', () => {
    // 旧页面用 slice(1) 硬切首字符，任何不以拉丁字母开头的分类都会被吃掉一个真字。
    expect(tierOf('奇怪分类')).toMatchObject({ key: '奇', rarity: 0 })
    expect(tierOf('奇怪分类').name).toBe('奇怪分类')
    expect(tierOf(undefined).key).toBe('?')
  })
})

describe('flattenItems', () => {
  it('flattens categories and sorts by the backend sort key', () => {
    const categories = {
      A常用: {
        合成玉: { number: 3630, sort: 10002, icon: '合成玉' },
        '玉+卷': { number: 22.1, sort: 9999999, icon: '寻访凭证' }
      },
      G稀有度1: { 源岩: { number: 120, sort: 100010, icon: '源岩' } }
    }

    const rows = flattenItems(categories)

    expect(rows.map((row) => row.name)).toEqual(['合成玉', '源岩', '玉+卷'])
    expect(rows[0]).toMatchObject({ tier: 'A', tierShort: '常用', derived: false })
    expect(rows[1]).toMatchObject({ tier: 'G', rarity: 1 })
    expect(rows[2].derived).toBe(true)
  })

  it('reads numbers defensively and keeps the icon fallback', () => {
    const rows = flattenItems({ A常用: { 缺字段: {}, 字符串: { number: '12' } } })
    const byName = Object.fromEntries(rows.map((row) => [row.name, row]))

    expect(byName['缺字段'].number).toBe(0)
    expect(byName['缺字段'].icon).toBe('缺字段')
    expect(byName['字符串'].number).toBe(12)
  })

  it('drops duplicate names so grid keys stay unique', () => {
    const rows = flattenItems({ A常用: { 合成玉: item(1) }, K未分类: { 合成玉: item(2) } })

    expect(rows).toHaveLength(1)
    expect(rows[0].tier).toBe('A')
  })

  it('filters out token items from display', () => {
    const categories = {
      A常用: { 合成玉: item(600, 1) },
      K未分类: { 阿米娅的信物: item(1, 3), 先锋皇家信物: item(4, 4), 纯金: item(50, 2) }
    }
    const rows = flattenItems(categories)
    expect(rows.map((row) => row.name)).toEqual(['合成玉', '纯金'])
  })

  it('skips malformed buckets without throwing', () => {
    expect(flattenItems({ A常用: null, B经验卡: 'nope' })).toEqual([])
    expect(flattenItems(null)).toEqual([])
  })
})

describe('buildBaselineStartOptions / buildBaselineEndOptions and two-point selection', () => {
  const snapshots = [
    { at: 100, items: { 龙门币: 1000 } },
    { at: 200, items: { 龙门币: 1200 } },
    { at: 300, items: { 龙门币: 1500 } }
  ]

  it('generates start options and end options accurately', () => {
    const startOpts = buildBaselineStartOptions(snapshots)
    const endOpts = buildBaselineEndOptions(snapshots)

    expect(startOpts.map((o) => o.value)).toContain('previous')
    expect(startOpts.map((o) => o.value)).toContain('first')
    expect(startOpts.map((o) => o.value)).toContain('200')

    expect(endOpts.map((o) => o.value)).toContain('latest')
    expect(endOpts.map((o) => o.value)).toContain('300')
  })

  it('returns empty list for less than 2 snapshots', () => {
    expect(buildBaselineStartOptions([])).toEqual([])
    expect(buildBaselineEndOptions([{ at: 100, items: {} }])).toEqual([])
  })

  it('drops rows without a numeric timestamp or an item dict', () => {
    // 两个构建器共用 usableSnapshots，残行不该把下拉框带崩。
    const mixed = [{ at: 100, items: {} }, { at: 'nope', items: {} }, null, { at: 300 }]

    expect(usableSnapshots(mixed)).toEqual([{ at: 100, items: {} }])
    expect(buildBaselineStartOptions(mixed)).toEqual([])
  })

  it('resolves previous / first / latest / timestamp keys to one snapshot', () => {
    const usable = usableSnapshots(snapshots)

    expect(resolveSnapshot(usable, 'latest')).toBe(usable[2])
    expect(resolveSnapshot(usable, 'previous')).toBe(usable[1])
    expect(resolveSnapshot(usable, 'first')).toBe(usable[0])
    expect(resolveSnapshot(usable, '200')).toBe(usable[1])
    expect(resolveSnapshot(usable, usable[1])).toBe(usable[1])
    // 未知键退回 fallbackIndex，负数从尾部数。
    expect(resolveSnapshot(usable, 'nope', -1)).toBe(usable[2])
    expect(resolveSnapshot(usable, 'nope', 0)).toBe(usable[0])
    expect(resolveSnapshot([], 'latest')).toBeNull()
  })
})

describe('alignSnapshotsToRange and baseline presets', () => {
  const snapshots = [
    { at: 1000, items: { 龙门币: 100 } },
    { at: 2000, items: { 龙门币: 200 } },
    { at: 3000, items: { 龙门币: 300 } },
    { at: 4000, items: { 龙门币: 400 } }
  ]

  it('aligns to previous two snapshots by default', () => {
    const res = alignSnapshotsToRange(snapshots, { preset: 'previous' })
    expect(res.matchedCount).toBe(2)
    expect(res.startSnapshot.at).toBe(3000)
    expect(res.endSnapshot.at).toBe(4000)
  })

  it('aligns to first and latest for all preset', () => {
    const res = alignSnapshotsToRange(snapshots, { preset: 'all' })
    expect(res.matchedCount).toBe(4)
    expect(res.startSnapshot.at).toBe(1000)
    expect(res.endSnapshot.at).toBe(4000)
  })

  it('aligns to range timestamps in custom mode', () => {
    const res = alignSnapshotsToRange(snapshots, {
      preset: 'custom',
      range: [1500 * 1000, 3500 * 1000],
      followLatest: false
    })
    expect(res.matchedCount).toBe(2)
    expect(res.startSnapshot.at).toBe(2000)
    expect(res.endSnapshot.at).toBe(3000)
  })

  it('handles followLatest by overriding end time with latest snapshot', () => {
    const res = alignSnapshotsToRange(snapshots, {
      preset: 'custom',
      range: [1500 * 1000, 2500 * 1000],
      followLatest: true
    })
    expect(res.matchedCount).toBe(3)
    expect(res.startSnapshot.at).toBe(2000)
    expect(res.endSnapshot.at).toBe(4000)
  })

  it('handles zero matches gracefully', () => {
    const res = alignSnapshotsToRange(snapshots, {
      preset: 'custom',
      range: [5000 * 1000, 6000 * 1000],
      followLatest: false
    })
    expect(res.matchedCount).toBe(0)
    expect(res.startSnapshot).toBeNull()
    expect(res.endSnapshot).toBeNull()
  })

  it('recomputes relative presets from now instead of the stored window', () => {
    // "近 7 天"在点选时会算出绝对窗口并随配置落盘。第二天打开页面若照用它，标签写的
    // 是"近 7 天"、比较的却是当初那 7 天，所以相对预设必须按 now 重算。
    const stale = [0, 100 * 1000] // 上次点选时存下来的窗口，只覆盖 at:100 之前

    // now 必须落在最后一条快照之后：关掉 followLatest 时窗口右端就是 now，取在
    // at:4000 前面会把那条挡在窗口外，断言就变成在测右端而不是"按 now 重算"。
    const res = alignSnapshotsToRange(
      snapshots,
      { preset: '7d', range: stale, followLatest: false },
      5000 * 1000
    )

    // 按 now 重算后窗口是 [-7d, now]，四条快照全落在里面。
    expect(res.matchedCount).toBe(4)
    expect(res.startSnapshot.at).toBe(1000)
  })

  it('keeps honouring the stored window for custom ranges', () => {
    const res = alignSnapshotsToRange(
      snapshots,
      { preset: 'custom', range: [1500 * 1000, 3500 * 1000], followLatest: false },
      9_000_000_000
    )

    expect(res.matchedCount).toBe(2)
    expect(res.startSnapshot.at).toBe(2000)
  })

  it('exposes which presets are relative and which ranges are usable', () => {
    expect(RELATIVE_PRESET_KEYS.has('7d')).toBe(true)
    expect(RELATIVE_PRESET_KEYS.has('previous')).toBe(false)
    expect(BASELINE_PRESETS.map((preset) => preset.key)).toContain('custom')

    expect(isValidBaselineRange([1000, 2000])).toBe(true)
    expect(isValidBaselineRange([2000, 1000])).toBe(false)
    expect(isValidBaselineRange([1000, null])).toBe(false)
    expect(isValidBaselineRange([null, null])).toBe(false)
    expect(isValidBaselineRange(['1000', '2000'])).toBe(false)
    expect(isValidBaselineRange('1000-2000')).toBe(false)
  })

  it('aligns to an explicit pair of snapshots in snapshot mode', () => {
    // 按快照模式不看时间范围，直接指定起止那两次扫描。
    const res = alignSnapshotsToRange(snapshots, {
      mode: 'snapshot',
      startKey: '2000',
      endKey: '4000'
    })

    expect(res.matchedCount).toBe(3)
    expect(res.startSnapshot.at).toBe(2000)
    expect(res.endSnapshot.at).toBe(4000)
    expect(res.matchedSnapshots.map((snap) => snap.at)).toEqual([2000, 3000, 4000])
  })

  it('normalises a reversed snapshot pair and validates stored keys', () => {
    const reversed = alignSnapshotsToRange(snapshots, {
      mode: 'snapshot',
      startKey: '4000',
      endKey: '2000'
    })
    expect(reversed.matchedCount).toBe(3)
    expect(reversed.startSnapshot.at).toBe(2000)
    expect(reversed.endSnapshot.at).toBe(4000)

    expect(BASELINE_MODES.map((mode) => mode.value)).toEqual(['time', 'snapshot'])
    expect(isValidSnapshotKey('previous')).toBe(true)
    expect(isValidSnapshotKey('latest')).toBe(true)
    expect(isValidSnapshotKey('2000')).toBe(true)
    expect(isValidSnapshotKey('nope')).toBe(false)
    expect(isValidSnapshotKey('')).toBe(false)
    expect(isValidSnapshotKey(null)).toBe(false)
  })

  it('computes preset ranges accurately', () => {
    const fixedNow = 1700000000000
    const r7d = computePresetRange('7d', fixedNow)
    expect(r7d[1]).toBe(fixedNow)
    expect(r7d[0]).toBe(fixedNow - 7 * 86400 * 1000)

    const r30d = computePresetRange('30d', fixedNow)
    expect(r30d[0]).toBe(fixedNow - 30 * 86400 * 1000)

    const rAll = computePresetRange('all', fixedNow)
    expect(rAll[0]).toBe(0)
    expect(rAll[1]).toBe(fixedNow)
  })
})

describe('buildDeltaMap', () => {
  it('compares the two most recent snapshots by default', () => {
    const delta = buildDeltaMap([
      { at: 100, items: { 龙门币: 1000, 合成玉: 600 } },
      { at: 200, items: { 龙门币: 1600, 合成玉: 600 } }
    ])

    expect(delta.get('龙门币')).toBe(600)
    expect(delta.has('合成玉')).toBe(false)
  })

  it('can compare against the earliest snapshot or a custom timestamp', () => {
    const snapshots = [
      { at: 100, items: { 龙门币: 1000, 合成玉: 100 } },
      { at: 200, items: { 龙门币: 1200, 合成玉: 200 } },
      { at: 300, items: { 龙门币: 1600, 合成玉: 200 } }
    ]

    const deltaFirst = buildDeltaMap(snapshots, 'first')
    expect(deltaFirst.get('龙门币')).toBe(600) // 1600 - 1000
    expect(deltaFirst.get('合成玉')).toBe(100) // 200 - 100

    const deltaAt200 = buildDeltaMap(snapshots, '200')
    expect(deltaAt200.get('龙门币')).toBe(400) // 1600 - 1200
    expect(deltaAt200.has('合成玉')).toBe(false)
  })

  it('supports comparing two arbitrary historical timestamps (startKey -> endKey)', () => {
    const snapshots = [
      { at: 100, items: { 龙门币: 1000, 合成玉: 100 } },
      { at: 200, items: { 龙门币: 1200, 合成玉: 300 } },
      { at: 300, items: { 龙门币: 1800, 合成玉: 250 } }
    ]

    // 对比 100 到 200 的变化
    const delta100to200 = buildDeltaMap(snapshots, '100', '200')
    expect(delta100to200.get('龙门币')).toBe(200) // 1200 - 1000
    expect(delta100to200.get('合成玉')).toBe(200) // 300 - 100

    // 对比 200 到 300 的变化
    const delta200to300 = buildDeltaMap(snapshots, '200', '300')
    expect(delta200to300.get('龙门币')).toBe(600) // 1800 - 1200
    expect(delta200to300.get('合成玉')).toBe(-50) // 250 - 300
  })

  it('does not generate fake delta for items unobserved in one of the snapshots', () => {
    const delta = buildDeltaMap([
      { at: 100, items: { 龙门币: 1 } },
      { at: 200, items: { 龙门币: 1, 至纯源石: 5 } }
    ])

    // 至纯源石在 at: 100 快照中未观测，不能得出 +5 的虚假增量
    expect(delta.has('至纯源石')).toBe(false)
    expect(delta.has('龙门币')).toBe(false)
  })

  it('returns an empty map rather than fake zeros with fewer than two snapshots', () => {
    // 只有它自己对比自己会得到全 0，而"全 0 变化"和"没有数据"在界面上必须区分开。
    expect(buildDeltaMap([]).size).toBe(0)
    expect(buildDeltaMap([{ at: 100, items: { 龙门币: 1 } }]).size).toBe(0)
    expect(buildDeltaMap(null).size).toBe(0)
  })

  it('reports items that stopped being observed instead of silently dropping them', () => {
    // 起始有、结束没有 = 大概率耗尽；不折算成 −N，但也绝不能当没发生（否则
    // "仅减少"永远看不到刚用完的物资）。只在结束出现的名字是首次观测，两份都不进。
    const detail = buildDeltaDetail([
      { at: 100, items: { 龙门币: 1000, 固源岩: 40, 至纯源石: 3 } },
      { at: 200, items: { 龙门币: 1600, 至纯源石: 3, 芯片助剂: 2 } }
    ])

    expect(detail.deltas.get('龙门币')).toBe(600)
    expect(detail.deltas.has('固源岩')).toBe(false)
    expect([...detail.unobserved]).toEqual(['固源岩'])
    expect(detail.deltas.has('芯片助剂')).toBe(false)
    expect(detail.unobserved.has('芯片助剂')).toBe(false)
  })

  it('treats a missing name as zero when the snapshot is a complete inventory', () => {
    // 完整库存快照（后端记的整份库存）没列出来就是 0：物品用完了要算成真实减少，
    // 而不是像扫描快照那样标"未扫描"。
    const detail = buildDeltaDetail([
      { at: 100, items: { 固源岩: 40, 龙门币: 1000 }, complete: true },
      { at: 200, items: { 龙门币: 1600 }, complete: true }
    ])

    expect(detail.deltas.get('固源岩')).toBe(-40)
    expect(detail.deltas.get('龙门币')).toBe(600)
    expect(detail.unobserved.size).toBe(0)
  })

  it('counts a newly observed item when the baseline snapshot is complete', () => {
    const detail = buildDeltaDetail([
      { at: 100, items: { 龙门币: 1000 }, complete: true },
      { at: 200, items: { 龙门币: 1000, D32钢: 5 }, complete: true }
    ])

    expect(detail.deltas.get('D32钢')).toBe(5)
    expect(detail.unobserved.size).toBe(0)
  })
})

describe('buildItemHistory', () => {
  it('emits an ascending series and skips missing scans instead of injecting fake zero', () => {
    const points = buildItemHistory(
      [
        { at: 100, items: { 龙门币: 10 } },
        { at: 200, items: { 合成玉: 1 } },
        { at: 300, items: { 龙门币: 30 } }
      ],
      '龙门币'
    )

    expect(points).toEqual([
      { at: 100, value: 10 },
      { at: 300, value: 30 }
    ])
  })

  it('skips snapshots without a usable timestamp', () => {
    expect(
      buildItemHistory([{ items: { 龙门币: 5 } }, { at: 1, items: { 龙门币: 5 } }], '龙门币')
    ).toHaveLength(1)
  })

  it('emits a real zero point for complete snapshots that omit the item', () => {
    // 完整库存快照没列出来就是 0：不补这个点，物品耗尽后曲线会停在最后一个非零值上。
    const points = buildItemHistory(
      [
        { at: 100, items: { 固源岩: 40 }, complete: true },
        { at: 200, items: { 龙门币: 1000 }, complete: true },
        { at: 300, items: { 固源岩: 10 } }
      ],
      '固源岩'
    )

    expect(points).toEqual([
      { at: 100, value: 40 },
      { at: 200, value: 0 },
      { at: 300, value: 10 }
    ])
  })
})

describe('summarizeItemHistory', () => {
  it('reports the net change over the window', () => {
    expect(
      summarizeItemHistory([
        { at: 1, value: 10 },
        { at: 2, value: 40 }
      ])
    ).toEqual({
      change: 30,
      first: 10,
      last: 40,
      points: 2
    })
  })

  it('handles empty and single-point series', () => {
    expect(summarizeItemHistory([])).toMatchObject({ change: 0, points: 0 })
    expect(summarizeItemHistory([{ at: 1, value: 7 }])).toMatchObject({
      change: 0,
      first: 7,
      last: 7
    })
  })
})

describe('computeDrawCount', () => {
  const derived = {
    '玉+卷': 20,
    '玉+卷+石': 23,
    '额外+碎片': 23.3,
    '额外+碎片+土': 23.7
  }
  const rawItems = {
    合成玉: 3600,
    寻访凭证: 4,
    十连寻访凭证: 1,
    至纯源石: 10,
    源石碎片: 20,
    固源岩: 40
  }

  it('prefers the backend derived tiers over any local recomputation', () => {
    // 后端按 depot.py 折算抽数 写入的派生值就是唯一口径，前端不再重算。
    const items = { ...rawItems, ...derived }
    expect(computeDrawCount(items, '玉+卷')).toBe(20)
    expect(computeDrawCount(items, '玉+卷+石')).toBe(23)
    expect(computeDrawCount(items, '额外+碎片')).toBe(23.3)
    expect(computeDrawCount(items, '额外+碎片+土')).toBe(23.7)
  })

  it('takes the backend value even when the local formula would differ', () => {
    // Python 的 round() 是银行家舍入、JS 的 Math.round() 遇 .5 进位：同一份物料
    // 两边会差 0.1。这里钉住"后端为准"，兜底值不许盖过它。
    const items = { ...rawItems, ...derived, '玉+卷': 0.1 }
    expect(computeDrawCount(items, '玉+卷')).toBe(0.1)
  })

  it('falls back to the local formula only for snapshots missing derived tiers', () => {
    // tickets = 4 + 10 = 14
    // 玉+卷: 3600 / 600 + 14 = 20.0
    expect(computeDrawCount(rawItems, '玉+卷')).toBe(20)
    // 玉+卷+石: (3600 + 10 * 180) / 600 + 14 = 5400 / 600 + 14 = 23.0
    expect(computeDrawCount(rawItems, '玉+卷+石')).toBe(23)
    // 额外+碎片: (3600 + 1800 + 10 * 20) / 600 + 14 = 5600 / 600 + 14 = 23.3
    expect(computeDrawCount(rawItems, '额外+碎片')).toBe(23.3)
    // 额外+碎片+土: (3600 + 1800 + floor((20 + 20) / 2) * 20) / 600 + 14 = (5400 + 400) / 600 + 14 = 23.7
    expect(computeDrawCount(rawItems, '额外+碎片+土')).toBe(23.7)
  })

  it('reports a snapshot with no draw-bearing materials as non-finite', () => {
    // 六个来源键一个都没有时不能补 0，否则会画出一个"抽数 0"的假点。
    // 后端 读取仓库历史 现在也不回填这种快照的派生档位，两边约定一致。
    expect(Number.isFinite(computeDrawCount({ 龙门币: 12 }, '玉+卷'))).toBe(false)
    expect(Number.isFinite(computeDrawCount({ 龙门币: 12, '玉+卷': undefined }, '玉+卷'))).toBe(
      false
    )
  })
})

describe('filterItems', () => {
  const rows = flattenItems(
    categoriesOf({
      A常用: { 合成玉: 3630, '玉+卷': 22 },
      C稀有度5: { D32钢: 5 },
      H模组: { 模组数据块: 3, 数据增补仪: 10 },
      G稀有度1: { 源岩: 0 }
    })
  )

  it('returns everything for an empty query', () => {
    expect(filterItems(rows)).toHaveLength(6)
  })

  it('matches substrings in the item name', () => {
    expect(filterItems(rows, { query: '源岩' }).map((row) => row.name)).toEqual(['源岩'])
  })

  it('treats a numeric query as a minimum count', () => {
    expect(filterItems(rows, { query: '1000' }).map((row) => row.name)).toEqual(['合成玉'])
  })

  it('can hide derived entries', () => {
    const visible = filterItems(rows, { showDerived: false })
    expect(visible.map((row) => row.name)).not.toContain('玉+卷')
  })

  it('can hide empty stacks', () => {
    const visible = filterItems(rows, { stockFilter: 'owned' })
    expect(visible.map((row) => row.name)).not.toContain('源岩')
  })

  it('keeps only empty stacks when stockFilter is empty', () => {
    // empty 以前是页面在 filterItems 外面自己补的一遍过滤，现在归 filterItems 管。
    const visible = filterItems(rows, { stockFilter: 'empty' })
    expect(visible.map((row) => row.name)).toEqual(['源岩'])
  })

  it('still honours the legacy ownedOnly flag', () => {
    const visible = filterItems(rows, { ownedOnly: true })
    expect(visible.map((row) => row.name)).not.toContain('源岩')
  })

  it('handles a null item list', () => {
    expect(filterItems(null)).toEqual([])
  })

  it('routes latin queries through the pinyin index (initials & full pinyin)', () => {
    const sample = flattenItems(categoriesOf({ A常用: { 龙门币: 12, 合成玉: 3630 } }))
    expect(filterItems(sample, { query: 'lmb' }).map((row) => row.name)).toEqual(['龙门币'])
    expect(filterItems(sample, { query: 'longmenbi' }).map((row) => row.name)).toEqual(['龙门币'])
    expect(filterItems(sample, { query: 'longmen' }).map((row) => row.name)).toEqual(['龙门币'])
    expect(filterItems(sample, { query: 'hm' })).toEqual([])
  })

  it('matches category names and star ratings', () => {
    expect(filterItems(rows, { query: '模组' }).map((row) => row.name)).toEqual([
      '模组数据块',
      '数据增补仪'
    ])
    expect(filterItems(rows, { query: '5星' }).map((row) => row.name)).toEqual(['D32钢'])
    expect(filterItems(rows, { query: '五星' }).map((row) => row.name)).toEqual(['D32钢'])
  })

  it('filters by delta status (increased, decreased, changed)', () => {
    const deltaMap = new Map([
      ['合成玉', 600],
      ['D32钢', -2],
      ['模组数据块', 0]
    ])
    const unobserved = new Set(['数据增补仪'])

    expect(filterItems(rows, { deltaFilter: 'increased', deltaMap }).map((r) => r.name)).toEqual([
      '合成玉'
    ])
    expect(
      filterItems(rows, { deltaFilter: 'decreased', deltaMap, unobserved }).map((r) => r.name)
    ).toEqual(['D32钢', '数据增补仪'])
    expect(
      filterItems(rows, { deltaFilter: 'changed', deltaMap, unobserved }).map((r) => r.name)
    ).toEqual(['合成玉', 'D32钢', '数据增补仪'])
    // 未扫描不算"没有变化"：它已经从起始快照里消失，不能混进 unchanged。
    expect(
      filterItems(rows, { deltaFilter: 'unchanged', deltaMap, unobserved }).map((r) => r.name)
    ).toEqual(['玉+卷', '模组数据块', '源岩'])
  })

  it('filters by comparison operators (<, <=, >, >=, =, !=, range)', () => {
    // rows numbers: 合成玉: 3630, 玉+卷: 22, D32钢: 5, 模组数据块: 3, 数据增补仪: 10, 源岩: 0
    expect(filterItems(rows, { query: '<5' }).map((r) => r.name)).toEqual(['模组数据块', '源岩'])
    expect(filterItems(rows, { query: '<=5' }).map((r) => r.name)).toEqual([
      'D32钢',
      '模组数据块',
      '源岩'
    ])
    expect(filterItems(rows, { query: '>20' }).map((r) => r.name)).toEqual(['合成玉', '玉+卷'])
    expect(filterItems(rows, { query: '>=10' }).map((r) => r.name)).toEqual([
      '合成玉',
      '玉+卷',
      '数据增补仪'
    ])
    expect(filterItems(rows, { query: '=5' }).map((r) => r.name)).toEqual(['D32钢'])
    expect(filterItems(rows, { query: '!=0' }).map((r) => r.name)).not.toContain('源岩')
    expect(filterItems(rows, { query: '5~25' }).map((r) => r.name)).toEqual([
      '玉+卷',
      'D32钢',
      '数据增补仪'
    ])
    expect(filterItems(rows, { query: '小于5' }).map((r) => r.name)).toEqual(['模组数据块', '源岩'])
    expect(filterItems(rows, { query: '不超过5' }).map((r) => r.name)).toEqual([
      'D32钢',
      '模组数据块',
      '源岩'
    ])
    expect(filterItems(rows, { query: '至少10' }).map((r) => r.name)).toEqual([
      '合成玉',
      '玉+卷',
      '数据增补仪'
    ])
  })

  it('filters by favorites list when favoriteOnly is true', () => {
    expect(
      filterItems(rows, { favoriteOnly: true, favorites: ['D32钢', '源岩'] }).map((r) => r.name)
    ).toEqual(['D32钢', '源岩'])
  })
})

describe('matchesNumericQuery', () => {
  it('correctly handles all operators and ranges', () => {
    expect(matchesNumericQuery(5, '<10')).toBe(true)
    expect(matchesNumericQuery(10, '<10')).toBe(false)
    expect(matchesNumericQuery(10, '<=10')).toBe(true)
    expect(matchesNumericQuery(10, '>5')).toBe(true)
    expect(matchesNumericQuery(10, '>=10')).toBe(true)
    expect(matchesNumericQuery(10, '=10')).toBe(true)
    expect(matchesNumericQuery(10, '!=10')).toBe(false)
    expect(matchesNumericQuery(15, '10-20')).toBe(true)
    expect(matchesNumericQuery(25, '10~20')).toBe(false)
    expect(matchesNumericQuery(100, '50')).toBe(true) // pure number >= 50
    expect(matchesNumericQuery(40, '50')).toBe(false)
  })
})

describe('favorites persistence and highlights', () => {
  const fakeStorage = () => {
    let store = {}
    return {
      getItem: (k) => store[k] ?? null,
      setItem: (k, v) => {
        store[k] = String(v)
      },
      clear: () => {
        store = {}
      }
    }
  }

  it('loads empty favorites on missing/corrupt storage', () => {
    const storage = fakeStorage()
    expect(loadFavorites(storage)).toEqual([])
    storage.setItem(FAVORITES_STORAGE_KEY, 'invalid-json')
    expect(loadFavorites(storage)).toEqual([])
  })

  it('saves and loads favorites correctly', () => {
    const storage = fakeStorage()
    saveFavorites(['固源岩', '高级作战记录', '固源岩'], storage)
    expect(loadFavorites(storage)).toEqual(['固源岩', '高级作战记录'])
  })

  it('saves and loads baseline config correctly with fallback', () => {
    const storage = fakeStorage()
    expect(loadBaselineConfig(storage)).toEqual(DEFAULT_BASELINE_CONFIG)

    storage.setItem(BASELINE_STORAGE_KEY, 'corrupt-json')
    expect(loadBaselineConfig(storage)).toEqual(DEFAULT_BASELINE_CONFIG)

    saveBaselineConfig({ preset: '7d', range: [1000, 2000], followLatest: false }, storage)
    expect(loadBaselineConfig(storage)).toEqual({
      mode: 'time',
      preset: '7d',
      range: [1000, 2000],
      followLatest: false,
      startKey: 'previous',
      endKey: 'latest'
    })

    // 按快照模式：时间范围清掉，起止两次扫描跟着走。
    saveBaselineConfig(
      { mode: 'snapshot', preset: 'previous', startKey: '100', endKey: '300', range: [1, 2] },
      storage
    )
    expect(loadBaselineConfig(storage)).toEqual({
      mode: 'snapshot',
      preset: 'previous',
      range: null,
      followLatest: true,
      startKey: '100',
      endKey: '300'
    })
  })

  it('refuses baseline configs it cannot act on', () => {
    const storage = fakeStorage()

    // 不认识的 preset 会让对齐一路落到"整段历史"，用户看到的是一个从没选过的区间。
    storage.setItem(
      BASELINE_STORAGE_KEY,
      JSON.stringify({ preset: '上个版本', range: [1000, 2000], followLatest: true })
    )
    expect(loadBaselineConfig(storage)).toEqual(DEFAULT_BASELINE_CONFIG)

    // 半截/颠倒的 range 一律当没配，而不是算出一个 NaN 边界。
    storage.setItem(
      BASELINE_STORAGE_KEY,
      JSON.stringify({ preset: 'custom', range: [2000, 1000], followLatest: true })
    )
    expect(loadBaselineConfig(storage)).toEqual({
      mode: 'time',
      preset: 'custom',
      range: null,
      followLatest: true,
      startKey: 'previous',
      endKey: 'latest'
    })

    // 按快照模式的时间范围一律丢掉：比的是哪两次扫描，留一对时间只会在切回
    // "按时间"时冒出一个从没选过的区间。
    storage.setItem(
      BASELINE_STORAGE_KEY,
      JSON.stringify({
        mode: 'snapshot',
        preset: 'previous',
        range: [1000, 2000],
        startKey: '100'
      })
    )
    expect(loadBaselineConfig(storage)).toEqual({
      mode: 'snapshot',
      preset: 'previous',
      range: null,
      followLatest: true,
      startKey: '100',
      endKey: 'latest'
    })

    saveBaselineConfig({ preset: '上个版本', range: [2000, 1000] }, storage)
    expect(loadBaselineConfig(storage)).toEqual(DEFAULT_BASELINE_CONFIG)
  })

  it('builds favorite highlights with deltas and compact formatting', () => {
    const allItems = [
      { name: '固源岩', number: 1250, icon: '固源岩' },
      { name: '高级作战记录', number: 20000, icon: '高级作战记录' },
      { name: 'D32钢', number: 5, icon: 'D32钢' }
    ]
    const deltaMap = new Map([
      ['固源岩', 50],
      ['高级作战记录', -200]
    ])

    const highlights = buildFavoriteHighlights(
      allItems,
      ['固源岩', '高级作战记录', '不存在物品'],
      deltaMap
    )
    expect(highlights).toHaveLength(2)
    expect(highlights[0]).toMatchObject({
      name: '固源岩',
      number: 1250,
      compact: '1,250',
      delta: 50
    })
    expect(highlights[1]).toMatchObject({
      name: '高级作战记录',
      number: 20000,
      compact: '2 万',
      delta: -200
    })
  })
})

describe('matchesPinyin', () => {
  it('matches full pinyin strings', () => {
    expect(matchesPinyin('龙门币', 'longmenbi')).toBe(true)
    expect(matchesPinyin('龙门币', 'longmen')).toBe(true)
    expect(matchesPinyin('合成玉', 'hechengyu')).toBe(true)
  })

  it('matches the natural initialism of a long name', () => {
    expect(matchesPinyin('重装双芯片', 'zzxp')).toBe(true)
    expect(matchesPinyin('重装双芯片', 'zzsxp')).toBe(true)
  })

  it('matches plain two- and three-character initialisms', () => {
    expect(matchesPinyin('龙门币', 'lmb')).toBe(true)
    expect(matchesPinyin('龙门币', 'lm')).toBe(true)
    expect(matchesPinyin('至纯源石', 'zcy')).toBe(true)
  })

  it('does not invent matches for wrong letters', () => {
    expect(matchesPinyin('合成玉', 'hm')).toBe(false)
    expect(matchesPinyin('龙门币', 'abc')).toBe(false)
  })

  it('ignores Chinese, numeric and empty queries', () => {
    expect(matchesPinyin('龙门币', '龙门')).toBe(false)
    expect(matchesPinyin('龙门币', '100')).toBe(false)
    expect(matchesPinyin('龙门币', '')).toBe(false)
  })

  it('caches the pinyin index per name', () => {
    const first = matchesPinyin('模组数据块', 'mzsjk')
    const second = matchesPinyin('模组数据块', 'mzsjk')
    expect(first).toBe(true)
    expect(second).toBe(true)
  })
})

describe('groupItemsByTier', () => {
  it('preserves canonical DEPOT_TIERS order regardless of input sorting', () => {
    const rows = flattenItems(
      categoriesOf({
        G稀有度1: { 源岩: 10000 },
        A常用: { 合成玉: 600 },
        C稀有度5: { D32钢: 2 }
      })
    )
    // Sorted descending by quantity: 源岩 (10000), 合成玉 (600), D32钢 (2)
    const sorted = sortItems(rows, 'count-desc')
    const groups = groupItemsByTier(sorted)

    // Groups must follow canonical order: A -> C -> G
    expect(groups.map((g) => g.key)).toEqual(['A', 'C', 'G'])
    // Inside each group, sorted order is preserved
    expect(groups.find((g) => g.key === 'G').rows[0].name).toBe('源岩')
  })
})

describe('sortItems', () => {
  const rows = flattenItems(
    categoriesOf({ A常用: { 合成玉: 3630 }, G稀有度1: { 源岩: 12, 双酮: 900 } })
  )

  it('leaves the tier ordering intact by default', () => {
    expect(sortItems(rows).map((row) => row.name)).toEqual(['合成玉', '源岩', '双酮'])
  })

  it('sorts by count in both directions', () => {
    expect(sortItems(rows, 'count-desc').map((row) => row.number)).toEqual([3630, 900, 12])
    expect(sortItems(rows, 'count-asc').map((row) => row.number)).toEqual([12, 900, 3630])
  })

  it('sorts by delta in both directions', () => {
    const deltaMap = new Map([
      ['合成玉', -100],
      ['源岩', 500],
      ['双酮', 0]
    ])
    expect(sortItems(rows, 'delta-desc', deltaMap).map((row) => row.name)).toEqual([
      '源岩',
      '双酮',
      '合成玉'
    ])
    expect(sortItems(rows, 'delta-asc', deltaMap).map((row) => row.name)).toEqual([
      '合成玉',
      '双酮',
      '源岩'
    ])
  })

  it('does not mutate the input', () => {
    const before = rows.map((row) => row.name)
    sortItems(rows, 'count-desc')
    expect(rows.map((row) => row.name)).toEqual(before)
  })
})

describe('countByTier', () => {
  it('counts totals and owned stacks per tier', () => {
    const rows = flattenItems(
      categoriesOf({ A常用: { 合成玉: 1 }, G稀有度1: { 源岩: 0, 双酮: 5 } })
    )

    expect(countByTier(rows)).toEqual({
      A: { total: 1, owned: 1 },
      G: { total: 2, owned: 1 }
    })
  })
})

describe('buildHighlights', () => {
  const categories = {
    A常用: {
      合成玉: item(3630),
      寻访凭证: item(12),
      至纯源石: item(30),
      龙门币: item(2450000),
      '玉+卷': item(18.1),
      '玉+卷+石': item(27.1)
    },
    B经验卡: {
      基础作战记录: item(100),
      '全部经验（计算）': item(20000)
    },
    K未分类: { 源石碎片: item(40) }
  }

  it('takes draw counts from the backend derived values instead of recomputing', () => {
    // 换算公式（600 玉一抽、源石 180、碎片两片一抽）只在 depot.py 维护一份；
    // 前端若重算，这里就会和 18.1 / 27.1 漂移。
    const highlights = buildHighlights(categories)
    const byKey = Object.fromEntries(highlights.draws.map((tier) => [tier.key, tier.value]))

    expect(byKey['玉+卷']).toBe(18.1)
    expect(byKey['玉+卷+石']).toBe(27.1)
  })

  it('omits draw tiers the backend did not send', () => {
    const highlights = buildHighlights({ A常用: { 合成玉: item(600) } })

    expect(highlights.draws.map((tier) => tier.key)).toEqual([])
  })

  it('collects currencies with compact formatting', () => {
    const highlights = buildHighlights(categories)
    const gold = highlights.currencies.find((row) => row.name === '龙门币')

    expect(gold.compact).toBe('245 万')
    expect(highlights.currencies.map((row) => row.name)).toContain('至纯源石')
    // 未出现的货币不应凭空补 0，否则会误导成"确实拥有 0 个"。
    expect(highlights.currencies.map((row) => row.name)).not.toContain('资质凭证')
  })

  it('exposes the computed EXP total', () => {
    // icon 直接沿用后端给的 EXP（depot.py 里指向资源包的 EXP.webp），
    // 前端不再覆盖成「高级作战记录」。
    const withIcon = { B经验卡: { '全部经验（计算）': item(20000, 1, 'EXP') } }

    expect(buildHighlights(withIcon).exp).toMatchObject({
      number: 20000,
      compact: '2 万',
      icon: 'EXP'
    })
    expect(buildHighlights(categories).exp).toMatchObject({ number: 20000, compact: '2 万' })
    expect(buildHighlights({}).exp).toBeNull()
  })
})

describe('formatting helpers', () => {
  it('formats compact magnitudes', () => {
    expect(formatCompact(0)).toBe('0')
    expect(formatCompact(9999)).toBe('9,999')
    expect(formatCompact(10000)).toBe('1 万')
    expect(formatCompact(2450000)).toBe('245 万')
    expect(formatCompact(12345)).toBe('1.23 万')
    expect(formatCompact(200000000)).toBe('2 亿')
  })

  it('degrades to a dash instead of NaN', () => {
    expect(formatCompact(undefined)).toBe('—')
    expect(formatCompact('abc')).toBe('—')
    expect(formatNumber(null)).toBe('0')
  })

  it('signs deltas and uses a real minus glyph', () => {
    expect(formatDelta(600)).toBe('+600')
    expect(formatDelta(-2450000)).toBe('−245 万')
    expect(formatDelta(0)).toBe('')
    expect(formatDelta(NaN)).toBe('')
  })

  it('renders timestamps and relative ages', () => {
    const at = 1789895956
    expect(formatTimestamp(at)).toMatch(/\d{4}/)
    expect(formatTimestamp('nonsense')).toBe('nonsense')
    expect(formatTimestamp('')).toBe('—')

    const now = (at + 7200) * 1000
    expect(formatRelative(at, now)).toBe('2 小时前')
    expect(formatRelative(at, (at + 30) * 1000)).toBe('30 秒前')
    expect(formatRelative(null)).toBe('')
  })

  it('builds icon urls with escaping', () => {
    expect(itemIconUrl('至纯源石')).toBe('/depot/%E8%87%B3%E7%BA%AF%E6%BA%90%E7%9F%B3.webp')
    expect(itemIconUrl('')).toBe('')
  })

  it('resolves the copy text only when it is a real string', () => {
    expect(resolveCopyText({ copyText: '  {"a":1}  ' })).toBe('{"a":1}')
    expect(resolveCopyText({ copyText: '' })).toBe('')
    expect(resolveCopyText(null)).toBe('')
  })

  it('knows which names are derived', () => {
    expect(isDerivedItem('玉+卷')).toBe(true)
    expect(isDerivedItem('额外+碎片+土')).toBe(true)
    expect(isDerivedItem('全部经验（计算）')).toBe(true)
    expect(isDerivedItem('合成玉')).toBe(false)
  })

  it('identifies token items', () => {
    expect(isTokenItem('阿米娅的信物')).toBe(true)
    expect(isTokenItem('先锋皇家信物')).toBe(true)
    expect(isTokenItem('合成玉')).toBe(false)
    expect(isTokenItem(null)).toBe(false)
    expect(isTokenItem(123)).toBe(false)
  })

  it('builds depot export filenames cleanly', () => {
    expect(buildDepotExportFilename('2026-09-24 10:00:00', 'all')).toBe(
      'mower-depot-20260924_100000.png'
    )
    expect(buildDepotExportFilename('2026-09-24 10:00:00', 'filtered')).toBe(
      'mower-depot-filtered-20260924_100000.png'
    )
    expect(buildDepotExportFilename('2026-09-24', 'all')).toBe('mower-depot-20260924.png')
    const fixedNow = new Date('2026-09-24T17:30:00')
    expect(buildDepotExportFilename('', 'all', fixedNow)).toBe('mower-depot-20260924_173000.png')
    expect(buildDepotExportFilename(null, 'filtered', fixedNow)).toBe(
      'mower-depot-filtered-20260924_173000.png'
    )
  })
})
