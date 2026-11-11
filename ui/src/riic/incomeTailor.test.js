import { expect, it, vi } from 'vitest'
import { defaultIncomeSettings, incomeRequest } from './income'
import { calculateIncome } from './incomeWorker'
import { createIncomeSession } from './incomeSession'
import { createDefaultWorkspace } from './vendor/workbench/defaults'
import { compileRosterSchedule } from './vendor/scheduler/compileRosterSchedule'
import { simulateSchedule } from './vendor/simulator/scheduleSimulation'
import { resolveOperatorCharId } from './vendor/domain/operatorIdentifiers'
import { incomeOrderDistribution } from './incomeOrders'

const plan = () => ({
  default: 'plan1',
  conf: {},
  backup_plans: [],
  plan1: {
    room_1_1: { name: '贸易站', product: 'lmd', plans: [{ agent: '芬', replacement: [] }] },
    room_1_3: { name: '发电站', plans: [] },
    room_2_3: { name: '发电站', plans: [] }
  }
})
const settings = () => ({
  ...defaultIncomeSettings(),
  operatorMode: 'maximum',
  inventorySource: 'manual',
  finiteInventory: false,
  weightMode: 'custom',
  warmupDays: 0,
  sampleDays: 1
})

it.each(['primary', 'replacement', 'group', 'backup', 'task'])(
  'supports theoretical mode for a trade %s candidate',
  (kind) => {
    const source = plan()
    const slot = source.plan1.room_1_1.plans[0]
    if (kind === 'primary') slot.agent = '柏喙'
    if (kind === 'replacement') slot.replacement = ['卡夫卡']
    if (kind === 'group') slot.group_bindings = [{ group: '组', replacement: ['折光'] }]
    if (kind === 'backup')
      source.backup_plans = [
        {
          name: '裁缝',
          trigger: 'True',
          plan: {
            room_1_1: { plans: [{ agent: '巫恋', replacement: [] }] }
          }
        }
      ]
    if (kind === 'task')
      source.backup_plans = [{ name: '裁缝', trigger: 'True', task: { room_1_1: ['柏喙'] } }]
    const original = structuredClone(source)
    expect(incomeRequest(source, settings()).options.simulationOptions.production).toMatchObject({
      expectationMode: true,
      theoreticalMode: true
    })
    expect(source).toEqual(original)
  }
)

const inactiveTriggers = [
  'False',
  {},
  { left: 'op_data.major_maintenance_remaining_hours()', operator: '<', right: '4' },
  "op_data.major_maintenance_remaining_hours('>=', 4) < 2",
  "op_data.facility_has_crafting_plan('factory')",
  "op_data.facility_has_mastery_plan('train')",
  "op_data.facility_is_training('train')",
  "op_data.facility_is_protected('train')"
]

it.each(inactiveTriggers)('ignores a tailor backup with an inactive condition %j', (trigger) => {
  const source = plan()
  source.backup_plans = [
    {
      name: '不触发的副表',
      trigger,
      plan: {
        room_1_1: {
          plans: [
            {
              agent: '巫恋',
              replacement: ['卡夫卡'],
              group_bindings: [{ group: '备用', replacement: ['折光'] }]
            }
          ]
        }
      },
      task: { room_1_1: ['柏喙'] }
    }
  ]
  const original = structuredClone(source)
  expect(incomeRequest(source, settings()).options.simulationOptions.production).toMatchObject({
    expectationMode: true,
    theoreticalMode: true
  })
  expect(source).toEqual(original)
})

it('keeps maintenance-only tailors out of the session and real Worker order model', () => {
  const source = plan()
  source.backup_plans = [
    {
      name: '停服更新',
      trigger: inactiveTriggers[2],
      plan: { room_1_1: { plans: [{ agent: '柏喙', replacement: [] }] } }
    }
  ]
  const worker = { postMessage: vi.fn(), terminate: vi.fn() }
  const session = createIncomeSession({ createWorker: () => worker, update: vi.fn() })
  try {
    session.start(source, settings())
    const frozen = worker.postMessage.mock.calls[0][0]
    expect(frozen.settings.expectationMode).toBe(true)
    const result = calculateIncome(frozen.plan, frozen.settings)
    expect(result.success, result.error).toBe(true)
    expect(result.simulationReport.production.assumptions).toMatchObject({
      expectationMode: true,
      timingModel: 'theoretical-events-v1'
    })
    expect(result.simulationReport.production.assumptions).not.toHaveProperty('seed')
  } finally {
    session.dispose()
  }
})

it.each([false, true])(
  'uses the same random and fixed seed choices with a tailor candidate=%s',
  (tailor) => {
    const source = plan()
    if (tailor) source.plan1.room_1_1.plans[0].agent = '柏喙'
    const worker = { postMessage: vi.fn(), terminate: vi.fn() }
    const session = createIncomeSession({ createWorker: () => worker, update: vi.fn() })
    let next = 100
    const random = vi.spyOn(crypto, 'getRandomValues').mockImplementation((array) => {
      array[0] = ++next
      return array
    })
    try {
      const editable = { ...settings(), expectationMode: false }
      for (const seed of [101, 102]) {
        session.start(source, editable)
        const frozen = worker.postMessage.mock.calls.at(-1)[0].settings
        expect(frozen).toMatchObject({ expectationMode: false, seed })
        expect(incomeRequest(source, frozen).options.simulationOptions.production.seed).toBe(seed)
        session.cancel()
      }
      session.start(source, { ...editable, fixedSeed: 77 })
      expect(worker.postMessage.mock.calls.at(-1)[0].settings).toMatchObject({
        expectationMode: false,
        seed: 77
      })
      expect(random).toHaveBeenCalledTimes(2)
      expect(editable).not.toHaveProperty('seed')
    } finally {
      session.dispose()
      random.mockRestore()
    }
  }
)

it('keeps the real Worker calculation on the sampled path for a tailor roster', () => {
  const source = plan()
  source.plan1.room_1_1.plans[0].agent = '柏喙'
  const result = calculateIncome(source, { ...settings(), expectationMode: false, fixedSeed: 42 })
  expect(result.success, result.error).toBe(true)
  expect(result.simulationReport.production.assumptions).toMatchObject({
    expectationMode: false,
    seed: 42
  })
  expect(
    result.simulationReport.production.events
      .filter((event) => event.type === 'order-completed')
      .every((event) => !event.order.expectationComponents)
  ).toBe(true)
})

it.each(['巫恋', '柏喙'])('keeps expected Worker output independent of seeds for %s', (tailor) => {
  const source = plan()
  source.plan1.room_1_1.plans = [tailor, '但书', '龙舌兰'].map((agent) => ({
    agent,
    replacement: []
  }))
  const worker = { postMessage: vi.fn(), terminate: vi.fn() }
  const session = createIncomeSession({ createWorker: () => worker, update: vi.fn() })
  const random = vi.spyOn(crypto, 'getRandomValues')
  try {
    session.start(source, { ...settings(), fixedSeed: 42 })
    const frozen = worker.postMessage.mock.calls[0][0]
    expect(frozen.settings.expectationMode).toBe(true)
    expect(frozen.settings).not.toHaveProperty('seed')
    expect(random).not.toHaveBeenCalled()
    const result = calculateIncome(frozen.plan, frozen.settings)
    const other = calculateIncome(source, { ...settings(), seed: 999, fixedSeed: 999 })
    expect(result.success, result.error).toBe(true)
    expect(other.success, other.error).toBe(true)
    expect(result.simulationReport.production.assumptions).toMatchObject({
      expectationMode: true,
      timingModel: 'theoretical-events-v1'
    })
    expect(result.simulationReport.production.assumptions).not.toHaveProperty('seed')
    expect(result.simulationReport.production).toEqual(other.simulationReport.production)
    expect(result.orderDistribution.expected).toBe(true)
    expect(result.orderDistribution.rows.find((row) => row.gold === 4).count).toBeGreaterThan(0)
    expect(
      result.simulationReport.diagnostics.some((d) => d.code === 'TRADE_QUALITY_WARMUP_MODEL')
    ).toBe(true)
  } finally {
    session.dispose()
    random.mockRestore()
  }
})

const tailorModels = [
  ['巫恋', 3, [0.15, 0.3, 0.55]],
  ['柏喙', 5, [0.05, 0.1, 0.85]]
]
function tailorSchedule(name, companions = []) {
  const workspace = createDefaultWorkspace()
  for (const room of Object.values(workspace.mainPlan.facilities)) {
    room.level = 0
    room.slots = []
  }
  const ids = [name, ...companions].map(resolveOperatorCharId)
  Object.assign(workspace.mainPlan.facilities.room_3_1, {
    level: 3,
    product: 'money',
    slots: ids.map((operatorId) => ({
      occupant: { kind: 'operator', operatorId },
      groupId: null,
      replacements: []
    }))
  })
  workspace.mainPlan.conf.workaholic = ids
  return compileRosterSchedule(workspace, { idleOperators: [] })
}
const productionOptions = {
  expectationMode: true,
  theoreticalMode: true,
  outputMode: 'potential',
  droneTarget: 'none'
}

it.each(tailorModels)(
  'freezes each %s order at its linear warmup acquisition probabilities',
  (name, cap, peak) => {
    const id = resolveOperatorCharId(name)
    const report = simulateSchedule(tailorSchedule(name), {
      schedulingModel: 'mower-alpha',
      sampleHours: 16,
      warmupModel: 'hourly',
      consumptionOverrides: { [id]: 0 },
      production: productionOptions
    })
    expect(report.success, JSON.stringify(report.diagnostics)).toBe(true)
    const orders = report.production.events
      .filter((event) => event.type === 'order-completed')
      .map((event) => event.order)
    expect(orders.length).toBeGreaterThanOrEqual(3)
    orders.forEach((order, index) => {
      const acquiredAt = index === 0 ? 0 : orders[index - 1].completedAt
      const progress = Math.min(acquiredAt / cap, 1)
      order.expectationComponents.forEach((component, tier) => {
        expect(component.probability).toBeCloseTo(
          [0.3, 0.5, 0.2][tier] * (1 - progress) + peak[tier] * progress,
          9
        )
      })
    })
    expect(orders.at(-1).expectationComponents.map((component) => component.probability)).toEqual(
      peak
    )
  }
)

it.each(tailorModels)(
  'keeps fully warmed %s tier ratios and special premiums across efficiency changes',
  (name, cap, peak) => {
    const id = resolveOperatorCharId(name)
    const reports = []
    for (const companions of [[], ['但书', '龙舌兰']]) {
      const schedule = tailorSchedule(name, companions)
      const report = simulateSchedule(schedule, {
        schedulingModel: 'mower-alpha',
        sampleHours: 8,
        warmupModel: 'hourly',
        initialWorkHours: { [id]: cap },
        consumptionOverrides: Object.fromEntries(
          [name, ...companions].map((name) => [resolveOperatorCharId(name), 0])
        ),
        production: productionOptions
      })
      expect(report.success, JSON.stringify(report.diagnostics)).toBe(true)
      reports.push(report)
      const distribution = incomeOrderDistribution(report)
      distribution.rows.forEach((row, index) =>
        expect(row.count / distribution.total).toBeCloseTo(peak[index], 9)
      )
      const count = distribution.total
      const expectedGold = companions.length
        ? peak[0] * 4 + peak[1] * 5 + peak[2] * 4
        : peak[0] * 2 + peak[1] * 3 + peak[2] * 4
      const expectedLmd = companions.length
        ? peak[0] * 2000 + peak[1] * 2500 + peak[2] * 2500
        : expectedGold * 500
      expect(report.production.expected.costs.gold).toBeCloseTo(count * expectedGold, 8)
      expect(report.production.expected.output.orderLmd).toBeCloseTo(count * expectedLmd, 8)
    }
    expect(incomeOrderDistribution(reports[0]).total).not.toBeCloseTo(
      incomeOrderDistribution(reports[1]).total,
      2
    )
  }
)
