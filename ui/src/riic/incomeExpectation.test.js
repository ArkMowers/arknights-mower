import { expect, it } from 'vitest'
import { captureOrder, expectedBaseOrder, getOrderDistribution } from './vendor/rules/orderRules'
import { createDefaultWorkspace } from './vendor/workbench/defaults'
import { compileRosterSchedule } from './vendor/scheduler/compileRosterSchedule'
import { simulateSchedule } from './vendor/simulator/scheduleSimulation'
import { calculateIncome } from './incomeWorker'
import { defaultIncomeSettings, incomeRequest } from './income'
import { incomeOrderDistribution } from './incomeOrders'
import { incomeReportLines } from './incomeImage'
import { resolveOperatorCharId } from './vendor/domain/operatorIdentifiers'

const settings = () => ({
  ...defaultIncomeSettings(),
  operatorMode: 'maximum',
  inventorySource: 'manual',
  finiteInventory: false,
  weightMode: 'custom',
  warmupDays: 0,
  sampleDays: 1
})
const plan = () => ({
  default: 'plan1',
  conf: {},
  backup_plans: [],
  plan1: {
    room_1_1: { name: '制造站', product: 'gold', plans: [] },
    room_1_3: { name: '发电站', plans: [] },
    room_2_3: { name: '发电站', plans: [] },
    room_3_1: { name: '贸易站', product: 'lmd', plans: [] }
  }
})

it('uses the ratio of expected reward and workload for a fixed ordinary distribution', () => {
  const base = expectedBaseOrder(getOrderDistribution(3))
  expect(base.baseMinutes).toBeCloseTo(203.4, 10)
  expect(base.goldCost).toBeCloseTo(2.9, 10)
  expect(captureOrder(base, {}, 4).lmdReward).toBeCloseTo(1450, 10)
  expect((base.lmdReward * 60) / base.baseMinutes).toBeCloseTo(427.7286135693215, 9)
})

it.each([
  [{ proviso: 2 }, 4.5, 2250],
  [{ tequila: 2 }, 2.9, 1550],
  [{ proviso: 2, tequila: 2 }, 4.5, 2350],
  [{ uOfficial: true, proviso: 2, tequila: 2 }, 2, 1000]
])('applies nonlinear special effects to each tier before averaging %j', (capture, gold, lmd) => {
  const snapshot = captureOrder(expectedBaseOrder(getOrderDistribution(3)), capture, 4)
  expect(snapshot.kind).toBe('expected')
  expect(snapshot.goldCost).toBeCloseTo(gold, 10)
  expect(snapshot.lmdReward).toBeCloseTo(lmd, 10)
  expect(snapshot.expectationComponents.map((order) => order.goldCost)).toEqual([2, 3, 4])
})

it('captures the current tailor approximation without changing the acquisition distribution later', () => {
  const distribution = getOrderDistribution(3, 'alpha', 'gold', 0.5)
  const base = expectedBaseOrder(distribution)
  expect(base.expectationComponents[2].probability).toBeCloseTo(0.375, 10)
  expect(base.baseMinutes).toBeCloseTo(219.9, 10)
  distribution[2].probability = 1
  expect(base.expectationComponents[2].probability).toBeCloseTo(0.375, 10)
  expect(captureOrder(base, { tequila: 2 }, 4).lmdReward).toBeCloseTo(1762.5, 10)
})

it.each(['closure', 'pepe', 'orundum'])(
  'retains deterministic special acquisition mode %s',
  (mode) => {
    const base = expectedBaseOrder(getOrderDistribution(3, 'normal', mode))
    const result = captureOrder(base, { closure: mode === 'closure', pepe: mode === 'pepe' }, 5)
    expect(result.mode).toBe(mode)
    expect(result.lmdReward).toBe(base.lmdReward)
    expect(result.orundumReward).toBe(base.orundumReward)
    expect(base.efficiencyAffected).toBe(mode !== 'pepe')
  }
)

it('settles an expected order at its exact mean duration with fractional finite inventory costs', () => {
  const workspace = createDefaultWorkspace()
  for (const room of Object.values(workspace.mainPlan.facilities)) {
    room.level = 0
    room.slots = []
  }
  Object.assign(workspace.mainPlan.facilities.room_3_1, {
    level: 3,
    product: 'money',
    slots: [{ occupant: { kind: 'operator', operatorId: '芬' }, groupId: null, replacements: [] }]
  })
  const schedule = compileRosterSchedule(workspace, { idleOperators: [] })
  const run = (seed, gold = 10, sampleHours = 3.39) =>
    simulateSchedule(schedule, {
      sampleHours,
      production: {
        expectationMode: true,
        seed,
        outputMode: 'settled',
        inventoryMode: 'finite',
        initialResources: { gold },
        droneTarget: 'none'
      }
    })
  const report = run(1)
  expect(report.success).toBe(true)
  expect(report.production).toEqual(run(999).production)
  expect(report.production.assumptions).not.toHaveProperty('seed')
  expect(report.production.sample.inflows.lmd).toBeCloseTo(1450, 8)
  expect(report.production.sample.outflows.gold).toBeCloseTo(2.9, 10)
  expect(report.production.sample.closing.gold).toBeCloseTo(7.1, 10)
  expect(report.production.trading[0].completedOrders).toBe(1)
  const orderCount =
    (report.rooms.find((room) => room.roomId === 'room_3_1').efficiencyPercentHours * 60) /
    100 /
    203.4
  expect(incomeOrderDistribution(report)).toMatchObject({
    expected: true,
    total: expect.closeTo(orderCount, 8),
    rows: [
      { gold: 2, count: expect.closeTo(orderCount * 0.3, 8) },
      { gold: 3, count: expect.closeTo(orderCount * 0.5, 8) },
      { gold: 4, count: expect.closeTo(orderCount * 0.2, 8) }
    ]
  })
  const exhausted = run(1, 29, 33.9)
  expect(exhausted.production.sample.inflows.lmd).toBeCloseTo(14500, 8)
  expect(exhausted.production.sample.closing.gold).toBeCloseTo(0, 8)
  const unfunded = run(1, 2)
  expect(unfunded.production.sample.inflows.lmd ?? 0).toBe(0)
  expect(unfunded.production.trading[0].pendingOrders).toHaveLength(1)
})

it('uses tier-specific Proviso and Tequila effects through the production timeline', () => {
  const workspace = createDefaultWorkspace()
  for (const room of Object.values(workspace.mainPlan.facilities)) {
    room.level = 0
    room.slots = []
  }
  Object.assign(workspace.mainPlan.facilities.room_3_1, {
    level: 3,
    product: 'money',
    slots: ['但书', '龙舌兰'].map((name) => ({
      occupant: { kind: 'operator', operatorId: resolveOperatorCharId(name) },
      groupId: null,
      replacements: []
    }))
  })
  const report = simulateSchedule(compileRosterSchedule(workspace, { idleOperators: [] }), {
    sampleHours: 8,
    production: {
      expectationMode: true,
      outputMode: 'settled',
      inventoryMode: 'finite',
      initialResources: { gold: 100 },
      droneTarget: 'none'
    }
  })
  expect(report.success).toBe(true)
  const completed = report.production.events.filter((event) => event.type === 'order-completed')
  expect(completed.length).toBeGreaterThan(0)
  for (const event of completed) {
    expect(event.order.goldCost).toBeCloseTo(4.5, 10)
    expect(event.order.lmdReward).toBeCloseTo(2350, 10)
  }
})

it('defaults new requests and Worker results to expectation mode and keeps old seeded requests available', () => {
  expect(defaultIncomeSettings()).toMatchObject({ expectationMode: true })
  expect(defaultIncomeSettings()).not.toHaveProperty('seed')
  const request = incomeRequest(plan(), settings())
  expect(request.options.simulationOptions.production).toMatchObject({ expectationMode: true })
  expect(request.options.simulationOptions.production).not.toHaveProperty('seed')
  const legacy = settings()
  delete legacy.expectationMode
  legacy.seed = 42
  expect(incomeRequest(plan(), legacy).options.simulationOptions.production).toMatchObject({
    expectationMode: false,
    seed: 42
  })
  expect(() => incomeRequest(plan(), { ...legacy, seed: NaN })).toThrow()
  const result = calculateIncome(plan(), settings())
  expect(result.success, result.error).toBe(true)
  expect(result.simulationReport.production.assumptions.expectationMode).toBe(true)
  expect(result.orderDistribution.expected).toBe(true)
  const lines = incomeReportLines(result, settings(), plan(), '排班').join('\n')
  expect(lines).toContain('数学期望模式（连续产出）')
  expect(lines).not.toContain('随机种子')
  const oldResult = structuredClone(result)
  delete oldResult.simulationReport.production.assumptions.expectationMode
  expect(incomeReportLines(oldResult, legacy, plan(), '旧排班').join('\n')).toContain('随机种子 42')
})
