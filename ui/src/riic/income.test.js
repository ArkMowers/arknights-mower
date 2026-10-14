import { describe, expect, it } from 'vitest'
import { defaultIncomeSettings, incomeRequest, incomeMetrics, inventoryRequired } from './income'
const modelSettings = () => ({
  ...defaultIncomeSettings(),
  operatorMode: 'maximum',
  inventorySource: 'manual',
  finiteInventory: false,
  weightMode: 'custom',
  allowGoldDebt: false
})
import { calculateIncome } from './incomeWorker'
import { incomeReportLines } from './incomeImage'
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
    source.advanced_settings = { resting_threshold: 0.7, fia_fool: false }
    const original = structuredClone(source),
      request = incomeRequest(source, settings)
    expect(request.options.simulationOptions).toMatchObject({
      warmupHours: 72,
      sampleHours: 672,
      recordSegments: false
    })
    expect(request.options.simulationAssumptions).toMatchObject({
      restingThreshold: 0.7,
      fiammettaFool: false
    })
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
    expect(
      incomeMetrics(result.summary, 28).find((row) => row.label === '赤金产量').total
    ).toBeCloseTo(560, 7)
    expect(source).toEqual(original)
    expect(progress.length).toBeGreaterThan(0)
    expect(incomeReportLines(result, settings, source, '主表').join('\n')).toContain('统计 28 天')
  }, 30000)
  it.each([['流明', '杜林', 'Free', 'Free', 'Free'], Array(5).fill('Free')])(
    'completes a staffed rotation with dormitory %j',
    (...occupants) => {
      const source = plan()
      source.plan1.room_1_1.plans = [{ agent: '芬', group: '', replacement: ['香草'] }]
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
