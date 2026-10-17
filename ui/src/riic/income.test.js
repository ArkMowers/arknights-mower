import { describe, expect, it } from 'vitest'
import { createDefaultWorkspace } from './vendor/workbench/defaults'
import { compileRosterSchedule } from './vendor/scheduler/compileRosterSchedule'
import { compiledScheduleToRuntimeConfig } from './vendor/scheduler/scheduleAdapter'
import { createRosterRuntime } from './vendor/scheduler/rosterRuntime'
import { getMowerSourceRuntime } from './vendor/scheduler/mowerSourceRuntime'
import { simulateSchedule } from './vendor/simulator/scheduleSimulation'
import { resolveOperatorCharId } from './vendor/domain/operatorIdentifiers'
import {
  defaultIncomeSettings,
  incomeRequest,
  incomeMetrics,
  incomeImageMetrics,
  incomeGoldEquivalentLmd,
  inventoryRequired
} from './income'
const modelSettings = () => ({
  ...defaultIncomeSettings(),
  operatorMode: 'maximum',
  inventorySource: 'manual',
  finiteInventory: false,
  weightMode: 'custom',
  allowGoldDebt: false
})
import { calculateIncome } from './incomeWorker'
import { runCalculationBridge } from './vendor/workbench/calculationBridge'
import { incomeReportLines } from './incomeImage'
import { buildTimelineData } from './vendor/workbench/timeline/timelineModel'
const plan = () => ({
  default: 'plan1',
  conf: {},
  backup_plans: [],
  plan1: {
    room_1_1: { name: '制造站', product: 'gold', plans: [] },
    room_1_3: { name: '发电站', plans: [] }
  }
})
describe('income export calculation', () => {
  it('converts the default horizon and isolates inputs', () => {
    const source = plan(),
      settings = modelSettings()
    source.advanced_settings = {
      resting_threshold: 0.7,
      fia_fool: false,
      group_rest_in_full_on_mood_gap: true,
      group_mood_gap_max_extra_wait_hours: 0.5,
      group_mood_gap_exclusions: ['主表组', '副表组']
    }
    const original = structuredClone(source),
      request = incomeRequest(source, settings)
    expect(request.options.simulationOptions).toMatchObject({
      warmupHours: 72,
      sampleHours: 672,
      recordSegments: true
    })
    expect(request.options.simulationAssumptions).toMatchObject({
      restingThreshold: 0.7,
      fiammettaFool: false,
      groupRestInFullOnMoodGap: true,
      groupMoodGapMaxExtraWaitHours: 0.5,
      groupMoodGapExclusions: ['主表组', '副表组']
    })
    const compiled = compileRosterSchedule(request.workspace, request.options.simulationAssumptions)
    const runtimeConfig = compiledScheduleToRuntimeConfig(compiled)
    const runtime = createRosterRuntime(runtimeConfig)
    expect(getMowerSourceRuntime(runtime).data.groupMoodGapThresholdMinutes).toBe(60)
    expect(getMowerSourceRuntime(runtime).data.groupMoodGapExclusions).toEqual(['主表组', '副表组'])
    runtimeConfig.mowerPolicy.groupMoodGapExclusions.push('额外组')
    expect(compiled.assumptions.groupMoodGapExclusions).toEqual(['主表组', '副表组'])
    request.workspace.mainPlan.facilities.room_1_1.product = 'exp'
    expect(source).toEqual(original)
    expect(modelSettings()).toEqual(settings)
  })
  it.each([
    ['warmupDays', -1],
    ['warmupDays', 31],
    ['sampleDays', 0],
    ['sampleDays', null],
    ['sampleDays', 1.5],
    ['seed', NaN]
  ])('rejects invalid %s=%s', (field, value) => {
    expect(() => incomeRequest(plan(), { ...modelSettings(), [field]: value })).toThrow()
  })
  it('requires finite stock for inventory conditions with explicit zero', () => {
    const source = plan()
    source.backup_plans = [
      { name: '库存', trigger: "op_data.inventory_count('赤金') < 1", plan: {} }
    ]
    expect(inventoryRequired(source)).toBe(true)
    expect(
      incomeRequest(source, modelSettings()).options.simulationOptions.production
    ).toMatchObject({
      outputMode: 'settled',
      inventoryMode: 'finite',
      initialResources: { gold: 0, fragment: 0, exp: 0, lmd: 0, device: 0, orirock: 0 }
    })
    expect(() =>
      incomeRequest(source, { ...modelSettings(), initialInventory: { gold: -1 } })
    ).toThrow()
  })
  it('validates the target and explicit operator growth', () => {
    expect(() => incomeRequest(plan(), { ...modelSettings(), droneRoom: 'room_3_3' })).toThrow()
    expect(() =>
      incomeRequest(plan(), {
        ...modelSettings(),
        operatorMode: 'custom',
        operatorText: ''
      })
    ).toThrow()
    expect(
      incomeRequest(plan(), {
        ...modelSettings(),
        operatorMode: 'custom',
        operatorText: '阿米娅,2,80'
      }).options.simulationOptions.operatorInventory
    ).toEqual([{ operator: '阿米娅', elitePhase: 2, level: 80 }])
  })
  it('calculates all 3 + 28 days against known unstaffed factory output', () => {
    const source = plan(),
      original = structuredClone(source),
      settings = modelSettings(),
      progress = []
    const result = calculateIncome(source, settings, (p) => progress.push(p))
    expect(result.success, result.error).toBe(true)
    expect(result.observedHours).toBeCloseTo(672, 8)
    // Unstaffed gold factory: 72 minutes per bar, twenty bars daily.
    expect(result.summary.goldCount).toBeCloseTo(20, 8)
    expect(result.summary.totalScore82).toBeCloseTo(8000, 7)
    expect(result.orderDistribution).toMatchObject({ total: 0, other: 0 })
    expect(
      incomeMetrics(result.summary, 28).find((row) => row.label === '赤金等价龙门币').total
    ).toBeCloseTo(280000, 7)
    expect(source).toEqual(original)
    expect(progress.length).toBeGreaterThan(0)
    expect(incomeReportLines(result, settings, source, '主表').join('\n')).toContain('统计 28 天')
  }, 30000)
  it.each([['流明', '杜林', 'Free', 'Free', 'Free'], Array(5).fill('Free')])(
    'completes a staffed rotation with dormitory %j',
    (...occupants) => {
      const source = plan()
      source.plan1.room_1_1.plans = [{ agent: '芬', group: '', replacement: ['香草'] }]
      source.plan1.room_2_3 = { name: '发电站', plans: [] }
      source.facility_levels = { dormitory_1: 5 }
      source.plan1.dormitory_1 = {
        name: '',
        plans: occupants.map((agent) => ({
          agent,
          group: '',
          replacement: []
        }))
      }
      const dorm = incomeRequest(source, modelSettings()).workspace.mainPlan.facilities.dormitory_1
      expect(dorm.level).toBeGreaterThan(0)
      expect(dorm.slots).toHaveLength(5)
      const result = calculateIncome(source, modelSettings())
      expect(result.success, JSON.stringify(result)).toBe(true)
      const track = result.timelineData.operatorTracks.find((row) => row.operatorName === '芬')
      expect(track.intervals[0].start).toBe(0)
      expect(track.intervals.at(-1).end).toBeCloseTo(672, 7)
      expect(track.workHours).toBeGreaterThan(0)
      expect(track.restHours).toBeGreaterThan(0)
      expect(
        track.workHours + track.restHours + track.idleHours + track.exhaustedHours
      ).toBeCloseTo(672, 7)
      expect(result.simulationReport.segments[0].start).toBeGreaterThanOrEqual(72)
      expect(result).not.toHaveProperty('morale')
      expect(result.observedHours).toBeCloseTo(672, 7)
      expect(result.summary.goldCount).toBeGreaterThan(0)
      expect(
        result.rooms.find((r) => r.roomId === 'room_1_1').averageEfficiencyPercent
      ).toBeGreaterThan(0)
    },
    30000
  )
  it('does not report invalid duplicate staffing as completed income', () => {
    const source = plan()
    source.plan1.room_1_1.plans = [{ agent: '芬' }, { agent: '芬' }]
    const result = calculateIncome(source, modelSettings())
    expect(result.success).toBe(false)
    expect(result.summary).toBeUndefined()
    expect(result.diagnostics.length).toBeGreaterThan(0)
  })
  it('excludes initial resources from income and cannot pay unfunded orders', () => {
    const source = plan()
    delete source.plan1.room_1_1
    source.plan1.room_2_1 = { name: '贸易站', product: 'lmd', plans: [] }
    const settings = {
      ...modelSettings(),
      warmupDays: 0,
      sampleDays: 1,
      finiteInventory: true
    }
    const empty = calculateIncome(source, settings)
    expect(empty.success, empty.error).toBe(true)
    expect(empty.summary.orderLmd).toBe(0)
    const funded = calculateIncome(source, {
      ...settings,
      initialInventory: { gold: 1000, lmd: 1000000 }
    })
    expect(funded.success, funded.error).toBe(true)
    expect(funded.summary.orderLmd).toBeGreaterThan(0)
    expect(funded.summary.orderLmd).toBeLessThan(1000000)
    expect(funded.summary.goldCount).toBe(0)
    expect(funded.summary.goldConsumed).toBeGreaterThan(0)
  }, 30000)
})

it('defaults to cached growth, cached finite stock, Mower weights and gold debt', () => {
  expect(defaultIncomeSettings()).toMatchObject({
    operatorMode: 'cache',
    inventorySource: 'cache',
    finiteInventory: true,
    weightMode: 'mower',
    allowGoldDebt: true,
    warmupDays: 3,
    sampleDays: 28
  })
  expect(() => incomeRequest(plan(), defaultIncomeSettings())).toThrow(/森空岛/)
})
it('keeps gold delivery debt across warmup and measures only sampled receipts', () => {
  const source = plan()
  delete source.plan1.room_1_1
  source.plan1.room_2_1 = { name: '贸易站', product: 'lmd', plans: [] }
  const result = calculateIncome(source, {
    ...modelSettings(),
    warmupDays: 3,
    sampleDays: 28,
    finiteInventory: true,
    allowGoldDebt: true,
    initialInventory: { gold: 0 }
  })
  expect(result.success, result.error).toBe(true)
  expect(result.summary.orderLmd).toBeGreaterThan(0)
  expect(result.goldInventory.sampleOpening).toBeLessThan(0)
  expect(result.goldInventory.closing).toBeLessThan(result.goldInventory.sampleOpening)
  expect(result.goldInventory.closing - result.goldInventory.sampleOpening).toBeCloseTo(
    -result.summary.goldConsumed * 28,
    7
  )
  expect(result.summary.netGoldCount).toBe(-result.summary.goldConsumed)
})
it('gold debt does not allow unfunded orundum delivery', () => {
  const source = plan()
  delete source.plan1.room_1_1
  source.plan1.room_2_1 = { name: '贸易站', product: 'orundum', plans: [] }
  const result = calculateIncome(source, {
    ...modelSettings(),
    warmupDays: 0,
    sampleDays: 1,
    finiteInventory: true,
    allowGoldDebt: true
  })
  expect(result.success, result.error).toBe(true)
  expect(result.summary.orundum).toBe(0)
  expect(result.goldInventory.closing).toBe(0)
})
it('reports recycling counts without material inventory or score', () => {
  const source = plan()
  delete source.plan1.room_1_1
  source.plan1.recycle = { name: '回收站', plans: [], level: 3 }
  const result = calculateIncome(source, { ...modelSettings(), warmupDays: 0, sampleDays: 5 })
  expect(result.success, result.error).toBe(true)
  expect(result.summary.recycleCount * 5).toBeCloseTo(3, 8) // 120 hours / (48 hours / 1.2)
  expect(result.summary.totalScore82).toBe(0)
  expect(result.summary.orderLmd).toBe(0)
  expect(result.summary.goldCount).toBe(0)
  expect(incomeMetrics(result.summary, 1).find((row) => row.unit === '次').total).toBe(
    result.summary.recycleCount
  )
})

it('reports manufactured and premium gold as LMD equivalent while retaining net LMD', () => {
  const rows = incomeImageMetrics(
    {
      exp: 1000,
      goldCount: 10,
      goldConsumed: 12,
      netGoldCount: -2,
      virtualGoldCount: 1.4,
      orderLmd: 4000,
      lmdConsumed: 4000,
      netLmd: 0,
      fragments: 0,
      orundum: 0,
      recycleCount: 0
    },
    28
  )
  expect(rows.map((row) => row.key)).toEqual(['exp', 'gold', 'lmd'])
  expect(rows[1]).toMatchObject({
    daily: 5700,
    total: 159600,
    unit: '龙门币',
    icon: '/product/gold.png'
  })
  expect(rows[1].signed).toBeUndefined()
  expect(rows[2]).toMatchObject({ daily: 0, total: 0 })
})
it.each([
  ['orirock', 1600],
  ['orirock_device', 1000]
])('reports sample LMD costs for potential %s production after warmup', (product, cost) => {
  const source = plan()
  source.plan1.room_1_1 = {
    name: '制造站',
    product,
    plans: [{ agent: '芬' }, { agent: '香草' }, { agent: '翎羽' }]
  }
  const result = calculateIncome(source, { ...modelSettings(), warmupDays: 1, sampleDays: 1 })
  expect(result.success, result.error).toBe(true)
  expect(result.summary.lmdConsumed).toBeGreaterThan(0)
  const totalCost = (result.summary.lmdConsumed * result.observedHours) / 24
  expect(totalCost / cost).toBeCloseTo(Math.round(totalCost / cost), 6)
  const funded = calculateIncome(source, {
    ...modelSettings(),
    finiteInventory: true,
    initialInventory: { lmd: 10000000, orirock: 10000, device: 10000 },
    warmupDays: 1,
    sampleDays: 1
  })
  expect(funded.success, funded.error).toBe(true)
  expect(result.summary.netLmd).toBeCloseTo(funded.summary.netLmd, 6)
  expect(result.summary.netLmd).toBe(-result.summary.lmdConsumed)
})
it('reports actual sample LMD balance changes and drone rooms with event logs', () => {
  const source = plan()
  const result = calculateIncome(source, {
    ...modelSettings(),
    finiteInventory: true,
    warmupDays: 0,
    sampleDays: 1,
    droneRoom: 'room_1_1'
  })
  expect(result.success, result.error).toBe(true)
  expect(result.summary.netLmd).toBe(
    (result.resources.closing.lmd ?? 0) - (result.resources.opening.lmd ?? 0)
  )
  expect(result.droneRooms).toEqual(['room_1_1'])
  expect(result.eventLog.entries.some((event) => event.type === '制造加速')).toBe(true)
})

it('uses the source Gantt timeline without changing production or staffing', () => {
  const source = plan()
  source.plan1.room_1_1.plans = [{ agent: '芬', group: '', replacement: ['香草'] }]
  source.plan1.room_2_3 = { name: '发电站', plans: [] }
  source.facility_levels = { dormitory_1: 5 }
  source.plan1.dormitory_1 = {
    name: '',
    plans: Array.from({ length: 5 }, () => ({ agent: 'Free', group: '', replacement: [] }))
  }
  const settings = { ...modelSettings(), warmupDays: 1, sampleDays: 1 }
  const { workspace, options } = incomeRequest(source, settings)
  options.simulationOptions.recordSegments = false
  const without = runCalculationBridge(workspace, options)
  const withTimeline = calculateIncome(source, settings)
  expect(without.success).toBe(true)
  expect(withTimeline.success).toBe(true)
  expect(withTimeline.summary.totalScore82).toBe(without.report.summary.totalScore82)
  expect(withTimeline.summary.netGoldCount).toBe(without.report.summary.netGoldCount)
  expect(withTimeline.resources).toEqual(without.simulationReport.production.sample)
  expect(withTimeline.simulationReport.operators).toEqual(without.simulationReport.operators)
  expect(withTimeline.timelineData).toEqual(buildTimelineData(withTimeline.simulationReport))
  expect(withTimeline.timelineData.observedHours).toBeCloseTo(24, 8)
  expect(withTimeline.timelineData.warmupHours).toBe(24)
  expect(
    withTimeline.timelineData.operatorTracks
      .find((row) => row.operatorName === '芬')
      .intervals.at(-1).end
  ).toBeCloseTo(24, 8)
  expect(withTimeline.simulationReport).not.toHaveProperty('moraleTimeline')
  expect(withTimeline.simulationReport.inputs.options).not.toHaveProperty('recordMorale')
  expect(withTimeline.simulationReport.inputs.options.observeInterval).toBeUndefined()
})

it('caps recovered drones at 250 even when an imported legacy field says 200', () => {
  const source = { ...plan(), efficiencyResources: { droneCapacity: 200 } }
  const original = structuredClone(source)
  const { workspace, options } = incomeRequest(source, {
    ...modelSettings(),
    warmupDays: 0,
    sampleDays: 3
  })
  const result = runCalculationBridge(workspace, options)
  expect(result.success, result.error).toBe(true)
  const drones = result.simulationReport.production.drones
  expect(drones.capacity).toBe(250)
  expect(drones.initial).toBe(0)
  expect(drones.stock).toBe(250)
  expect(drones.generated).toBeGreaterThan(250)
  expect(drones.overflow).toBeCloseTo(drones.generated - 250, 8)
  expect(source).toEqual(original)
})

it.each([undefined, false, true])(
  'ignores retired training state %s through the income worker',
  (present) => {
    expect(defaultIncomeSettings()).not.toHaveProperty('masteryPlanPresent')
    for (const [trigger, active] of [
      ["op_data.facility_has_mastery_plan('train')", false],
      ["not op_data.facility_has_mastery_plan('train')", true]
    ]) {
      const source = plan()
      source.backup_plans = [
        {
          name: '训练条件',
          trigger,
          plan: {}
        }
      ]
      const settings = {
        ...modelSettings(),
        warmupDays: 0,
        sampleDays: 1,
        masteryPlanPresent: present
      }
      const original = structuredClone({ source, settings })
      expect(incomeRequest(source, settings).options.simulationAssumptions).not.toHaveProperty(
        'masteryPlanPresent'
      )
      const result = calculateIncome(source, settings)
      expect(result.success, result.error).toBe(true)
      expect(
        result.eventLog.entries.some(
          (event) => event.type === '副表切换' && event.detail === '训练条件（启用）'
        )
      ).toBe(active)
      expect(result.summary.goldCount).toBeCloseTo(20, 8)
      expect(
        result.diagnostics.find((d) => d.code === 'MOWER_MASTERY_PLAN_ASSUMPTION')?.message
      ).toContain('固定为无')
      expect({ source, settings }).toEqual(original)
    }
  }
)

it('reports fixed training assumptions for new runs and preserves historical provenance', () => {
  const result = { observedHours: 24, summary: {} }
  const settings = modelSettings()
  expect(incomeReportLines(result, settings, plan(), '主表').join('\n')).toContain(
    '本次演算固定为无未完成训练计划'
  )
  expect(
    incomeReportLines(result, { ...settings, masteryPlanPresent: true }, plan(), '主表').join('\n')
  ).toContain('历史演算的未完成训练计划：有')
})

it('does not count ordinary gold delivery as gold income or deduct it from manufacturing', () => {
  const source = plan()
  source.plan1.room_2_3 = { name: '发电站', plans: [] }
  source.plan1.room_2_1 = { name: '贸易站', product: 'lmd', plans: [] }
  const result = calculateIncome(source, {
    ...modelSettings(),
    finiteInventory: true,
    allowGoldDebt: true,
    warmupDays: 0,
    sampleDays: 1
  })
  expect(result.success, result.error).toBe(true)
  expect(result.summary.goldConsumed).toBeGreaterThan(0)
  expect(incomeGoldEquivalentLmd(result.summary)).toBeCloseTo(9000, 8)
  expect(incomeImageMetrics(result.summary, 1).find((row) => row.key === 'gold').daily).toBeCloseTo(
    9000,
    8
  )
  const rows = incomeMetrics(result.summary, 1)
  expect(rows.find((row) => row.label === '赤金等价龙门币').daily).toBeCloseTo(9000, 8)
  expect(rows.some((row) => ['赤金产量', '赤金消耗', '赤金净增'].includes(row.label))).toBe(false)
  source.plan1.room_1_1.product = 'exp'
  const noGold = calculateIncome(source, {
    ...modelSettings(),
    finiteInventory: true,
    allowGoldDebt: true,
    warmupDays: 0,
    sampleDays: 1
  })
  expect(noGold.success, noGold.error).toBe(true)
  expect(noGold.summary.goldConsumed).toBeGreaterThan(0)
  expect(incomeGoldEquivalentLmd(noGold.summary)).toBe(0)
  expect(incomeImageMetrics(noGold.summary, 1).some((row) => row.key === 'gold')).toBe(false)
})

it.each(['龙舌兰', '可露希尔'])(
  'adds %s order premiums to manufacturing value without changing the ledger',
  (agent) => {
    const source = plan()
    source.plan1.room_2_3 = { name: '发电站', plans: [] }
    source.plan1.room_2_1 = {
      name: '贸易站',
      product: 'lmd',
      plans: [{ agent }, { agent: '巫恋' }, { agent: '柏喙' }]
    }
    const result = calculateIncome(source, {
      ...modelSettings(),
      finiteInventory: true,
      allowGoldDebt: true,
      warmupDays: 0,
      sampleDays: 3
    })
    expect(result.success, result.error).toBe(true)
    const premiums = result.simulationReport.production.events
      .filter((event) => event.type === 'order-collected' && event.time > 0 && event.order)
      .reduce(
        (total, event) => total + Math.max(0, event.order.lmdReward - event.order.goldCost * 500),
        0
      )
    expect(premiums).toBeGreaterThan(0)
    const value = incomeGoldEquivalentLmd(result.summary)
    expect(value).toBeCloseTo(
      (result.resources.inflows.gold * 500 + premiums) / (result.observedHours / 24),
      6
    )
    expect(result.summary.totalScore82).toBeCloseTo(value * 0.8 + result.summary.orderLmd * 0.2, 6)
    expect(result.resources.closing.gold).toBeCloseTo(
      (result.resources.opening.gold ?? 0) +
        (result.resources.inflows.gold ?? 0) -
        (result.resources.outflows.gold ?? 0),
      8
    )
  }
)

it('reads old frozen gold summaries without treating consumed inventory as income', () => {
  const original = { goldCount: 10, virtualGoldCount: 1.4, goldConsumed: 99, netGoldCount: -89 }
  const before = structuredClone(original)
  expect(incomeGoldEquivalentLmd(original)).toBe(5700)
  expect(incomeGoldEquivalentLmd({ goldValue: 5000, virtualGoldValue: 700 })).toBe(5700)
  expect(incomeGoldEquivalentLmd({ goldConsumed: 99, netGoldCount: -99 })).toBe(0)
  expect(original).toEqual(before)
})

it('retains advisory backup validation in the worker report even when the backup is inactive', async () => {
  const { backupWarningPlan } = await import('./backupWarningFixture')
  const source = backupWarningPlan()
  const result = calculateIncome(source, { ...modelSettings(), warmupDays: 0, sampleDays: 1 })
  expect(result.success, result.error).toBe(true)
  const warnings = result.diagnostics.filter((issue) => issue.code === 'CONFLICTING_REPLACEMENT')
  expect(warnings).toHaveLength(3)
  expect(warnings.every((issue) => issue.message.includes('鸿雪下班'))).toBe(true)
  source.backup_plans[0].plan.room_2_1.plans = structuredClone(source.plan1.room_2_1.plans)
  const fixed = calculateIncome(source, { ...modelSettings(), warmupDays: 0, sampleDays: 1 })
  expect(fixed.success, fixed.error).toBe(true)
  expect(fixed.diagnostics.some((issue) => issue.code === 'CONFLICTING_REPLACEMENT')).toBe(false)
}, 30000)

describe('cached simulation inventory', () => {
  it('normalizes absent and null cached quantities to zero without changing reported stock', () => {
    const settings = {
      ...modelSettings(),
      finiteInventory: true,
      inventorySource: 'cache',
      cachedInventory: { gold: null, lmd: 42 }
    }
    const before = structuredClone(settings)
    expect(
      incomeRequest(plan(), settings).options.simulationOptions.production.initialResources
    ).toEqual({ gold: 0, fragment: 0, orirock: 0, device: 0, lmd: 42, exp: 0 })
    expect(settings).toEqual(before)
  })
  it('accepts an available cache with no reported resources', () => {
    expect(
      incomeRequest(plan(), {
        ...modelSettings(),
        finiteInventory: true,
        inventorySource: 'cache',
        cachedInventory: {}
      }).options.simulationOptions.production.initialResources
    ).toEqual({ gold: 0, fragment: 0, orirock: 0, device: 0, lmd: 0, exp: 0 })
  })
  it.each([-1, true, '12', NaN, 1.5])('still rejects invalid reported stock %s', (gold) => {
    expect(() =>
      incomeRequest(plan(), {
        ...modelSettings(),
        finiteInventory: true,
        inventorySource: 'cache',
        cachedInventory: { gold }
      })
    ).toThrow('赤金')
  })
  it('still requires an available cache', () => {
    expect(() =>
      incomeRequest(plan(), {
        ...modelSettings(),
        finiteInventory: true,
        inventorySource: 'cache',
        cachedInventory: null
      })
    ).toThrow('没有可用')
  })
})

it('calculates product-count backup conditions through the income Worker with a zero-filled cache', () => {
  const source = plan()
  source.backup_plans = [
    {
      name: '产品统计',
      trigger:
        "op_data.facility_product_count('gold') >= 1 and op_data.facility_product_type_count() >= 1 and op_data.inventory_count('源石碎片') == 0",
      plan: {}
    }
  ]
  const result = calculateIncome(source, {
    ...modelSettings(),
    warmupDays: 0,
    sampleDays: 1,
    finiteInventory: true,
    inventorySource: 'cache',
    cachedInventory: { lmd: 42 }
  })
  expect(result.success, result.error).toBe(true)
  expect(result.inventoryMode).toBe('finite')
  expect(
    result.simulationReport.events
      .filter((event) => event.type === 'backup-plan')
      .map((event) => [event.backupName, event.active])
  ).toEqual([['产品统计', true]])
  expect(result.resources.opening.fragment).toBe(0)
  expect(result.observedHours).toBeCloseTo(24, 7)
})

it.each([
  ['刺玫', 18],
  ['撷英调香师', 20]
])(
  'integrates %s fatigue recovery separately from the all-room maximum until morale %s',
  (provider, threshold) => {
    const workspace = createDefaultWorkspace()
    workspace.mainPlan.facilities.dormitory_1.level = 5
    workspace.mainPlan.facilities.dormitory_1.slots = [provider, '杜林', '芬'].map((name) => ({
      occupant: { kind: 'operator', operatorId: name },
      groupId: null,
      replacements: []
    }))
    const target = resolveOperatorCharId('芬')
    const schedule = compileRosterSchedule(workspace, {
      operatorMorale: { [target]: threshold - 1 }
    })
    for (const maxStepHours of [0.05, 1]) {
      const report = simulateSchedule(schedule, { sampleHours: 0.5, maxStepHours })
      expect(report.success).toBe(true)
      expect(report.operators.find((op) => op.operatorId === target).finalMorale).toBeCloseTo(
        threshold + (0.5 - 1 / 4.35) * 4.25,
        7
      )
    }
  }
)
it('takes only one fatigue recovery extra with both providers in the Mower simulation', () => {
  const workspace = createDefaultWorkspace()
  workspace.mainPlan.facilities.dormitory_1.level = 5
  workspace.mainPlan.facilities.dormitory_1.slots = ['刺玫', '撷英调香师', '杜林', '芬'].map(
    (name) => ({
      occupant: { kind: 'operator', operatorId: name },
      groupId: null,
      replacements: []
    })
  )
  const target = resolveOperatorCharId('芬')
  const schedule = compileRosterSchedule(workspace, { operatorMorale: { [target]: 10 } })
  const report = simulateSchedule(schedule, { sampleHours: 1 })
  expect(report.success).toBe(true)
  expect(report.operators.find((op) => op.operatorId === target).finalMorale).toBeCloseTo(14.35, 8)
})

it.each([
  [true, 14.4],
  [false, 15.05]
])(
  'retains Coldshot shared recovery category with unfinished Fiammetta: %s',
  (withFiammetta, expected) => {
    const workspace = createDefaultWorkspace()
    workspace.mainPlan.facilities.dormitory_1.level = 5
    const names = ['冰酿', '杜林', '芬', ...(withFiammetta ? ['菲亚梅塔'] : [])]
    workspace.mainPlan.facilities.dormitory_1.slots = names.map((name) => ({
      occupant: { kind: 'operator', operatorId: name },
      groupId: null,
      replacements: []
    }))
    const target = resolveOperatorCharId('芬')
    const fia = resolveOperatorCharId('菲亚梅塔')
    const schedule = compileRosterSchedule(workspace, {
      operatorMorale: { [target]: 10, [fia]: 10 }
    })
    const report = simulateSchedule(schedule, { sampleHours: 1 })
    expect(report.success).toBe(true)
    expect(report.operators.find((op) => op.operatorId === target).finalMorale).toBeCloseTo(
      expected,
      8
    )
    if (withFiammetta)
      expect(report.operators.find((op) => op.operatorId === fia).finalMorale).toBeCloseTo(12, 8)
  }
)

it('preserves exchange assumptions when displaying saved clue results', () => {
  const result = { observedHours: 24, summary: { clueCount: 2 } }
  const lines = (value) => incomeReportLines(value, modelSettings(), plan(), '主表').join('\n')
  expect(lines(result)).toContain('历史记录按线索交流关闭')
  expect(lines({ ...result, clueExchangeMode: 'always-on' })).toContain('线索产量按全程开启交流')
  expect(lines({ ...result, clueExchangeMode: 'always-on' })).not.toContain(
    '历史记录按线索交流关闭'
  )
})

it.each([null, '组名', [''], ['  '], [123]])('模拟拒绝无效的延后回班排除组：%j', (groups) => {
  const workspace = createDefaultWorkspace()
  const compiled = compileRosterSchedule(workspace, { groupMoodGapExclusions: groups })
  expect(compiled.diagnostics).toContainEqual(
    expect.objectContaining({
      code: 'INVALID_ASSUMPTION',
      severity: 'error',
      path: 'assumptions.groupMoodGapExclusions'
    })
  )
})
