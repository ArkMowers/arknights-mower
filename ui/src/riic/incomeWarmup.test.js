import { expect, it } from 'vitest'
import { createDefaultConfig, createRoom } from './vendor/domain/defaults'
import { evaluateOperators } from './vendor/engine/operatorRules'
import { temporalTradeQuality } from './vendor/engine/timeDependentSkills'
import { getOrderDistribution } from './vendor/rules/orderRules'
import { createDefaultWorkspace } from './vendor/workbench/defaults'
import { compileRosterSchedule } from './vendor/scheduler/compileRosterSchedule'
import { simulateSchedule } from './vendor/simulator/scheduleSimulation'
import { createClueObservation } from './incomeClues'

const bibeak = 'char_252_bibeak',
  shamare = 'char_254_vodfox'
const fang = 'char_123_fang',
  vanilla = 'char_240_wyvern',
  spot = 'char_284_spot'
function quality(id, hours) {
  const config = createDefaultConfig()
  const room = createRoom('room_1_1', 'trading')
  room.level = 3
  room.operatorIds = [id]
  config.rooms = [room]
  const result = evaluateOperators(room, config, undefined, undefined, undefined, {
    workHoursByOperator: new Map([[id, hours]]),
    warmupModel: 'hourly'
  })
  return getOrderDistribution(3, result.quality, 'gold', result.qualityWarmup).map(
    (o) => o.probability
  )
}
it.each([
  [shamare, 3, [0.15, 0.3, 0.55]],
  [bibeak, 5, [0.05, 0.1, 0.85]]
])(
  'uses continuous linear quality warmup for %s even with hourly efficiency curves',
  (id, cap, peak) => {
    expect(quality(id, 0)).toEqual([0.3, 0.5, 0.2])
    quality(id, cap / 2).forEach((p, i) =>
      expect(p).toBeCloseTo(([0.3, 0.5, 0.2][i] + peak[i]) / 2)
    )
    expect(quality(id, cap)).toEqual(peak)
    expect(quality(id, cap + 10)).toEqual(peak)
  }
)
it('retains stable static estimates and selects the strongest warmed effect without stacking', () => {
  expect(temporalTradeQuality([shamare], 'beta', {})).toEqual({
    quality: 'alpha',
    qualityWarmup: 1
  })
  expect(temporalTradeQuality([bibeak], 'normal', {})).toEqual({
    quality: 'beta',
    qualityWarmup: 1
  })
  expect(
    temporalTradeQuality(
      [shamare, bibeak],
      'normal',
      {},
      {
        workHoursByOperator: new Map([
          [shamare, 3],
          [bibeak, 0.5]
        ])
      }
    )
  ).toEqual({ quality: 'alpha', qualityWarmup: 1 })
})
it('interpolates from the actual low-level normal distribution', () => {
  expect(getOrderDistribution(1, 'beta', 'gold', 0).map((o) => o.probability)).toEqual([1, 0, 0])
  expect(getOrderDistribution(2, 'alpha', 'gold', 0.5).map((o) => o.probability)).toEqual([
    0.375, 0.35, 0.275
  ])
})

function swapSchedule(mode) {
  const workspace = createDefaultWorkspace()
  for (const room of Object.values(workspace.mainPlan.facilities)) {
    room.level = 0
    room.slots = []
  }
  const room = workspace.mainPlan.facilities.room_1_1
  room.level = 3
  room.product = 'gold'
  room.slots = [fang, vanilla, spot].map((operatorId) => ({
    occupant: { kind: 'operator', operatorId },
    groupId: null,
    replacements: []
  }))
  workspace.mainPlan.conf.workaholic = [fang, vanilla, spot]
  const names = mode === 'swap' ? ['香草', '芬', '斑点'] : ['芬', '香草', '斑点']
  workspace.compatibility.backupPlans = [
    {
      name: 'slot-order',
      trigger: 'True',
      plan: { room_1_1: { plans: names.map((agent) => ({ agent, group: '', replacement: [] })) } },
      task: { room_1_1: names }
    }
  ]
  return compileRosterSchedule(workspace, { idleOperators: [] })
}
it.each(['swap', 'same'])('tracks physical slots through a real alpha backup task: %s', (mode) => {
  const observations = []
  const report = simulateSchedule(swapSchedule(mode), {
    schedulingModel: 'mower-alpha',
    sampleHours: 1,
    warmupModel: 'hourly',
    initialWorkHours: { [fang]: 10, [vanilla]: 10, [spot]: 10 },
    consumptionOverrides: { [fang]: 0, [vanilla]: 0, [spot]: 0 },
    production: { outputMode: 'potential', droneTarget: 'none', seed: 42 },
    observeInterval(config, start, end, workHours) {
      observations.push({ start, ids: config.rooms[0].operatorIds, hours: new Map(workHours) })
    }
  })
  expect(report.success, JSON.stringify(report.diagnostics)).toBe(true)
  expect(report.events.some((e) => e.type === 'backup-plan' && e.active)).toBe(true)
  const last = observations.at(-1)
  expect(last.ids).toEqual(mode === 'swap' ? [vanilla, fang, spot] : [fang, vanilla, spot])
  expect(last.hours.get(fang)).toBeCloseTo(last.start + (mode === 'swap' ? 0 : 10), 2)
  expect(last.hours.get(spot)).toBeCloseTo(last.start + 10, 5)
  const efficiency = report.rooms.find((r) => r.roomId === 'room_1_1').averageEfficiencyPercent
  expect(efficiency).toBeCloseTo(mode === 'swap' ? 178 : 183, 1)
})
it('resets reception warmup after moving slots and keeps unmoved tenure', () => {
  const config = createDefaultConfig(),
    id = 'char_4087_ines'
  config.facilityOperatorIds.reception = [id, 'char_202_demkni']
  const observer = createClueObservation(0)
  observer.observe(config, 0, 5)
  const before = observer.result()
  config.facilityOperatorIds.reception.reverse()
  observer.observe(config, 5, 6)
  const total = (r) => r.completed + r.progress
  expect(total(observer.result()) - total(before)).toBeCloseTo(2.09 / 20, 8)
  const beforeNext = observer.result()
  observer.observe(config, 6, 7)
  expect(total(observer.result()) - total(beforeNext)).toBeCloseTo(2.11 / 20, 8)
})

it('restarts quality for later orders after a slot move without changing the active order', () => {
  const orders = []
  for (const move of [false, true]) {
    const workspace = createDefaultWorkspace()
    for (const room of Object.values(workspace.mainPlan.facilities)) {
      room.level = 0
      room.slots = []
    }
    const room = workspace.mainPlan.facilities.room_3_1
    room.level = 3
    room.product = 'gold'
    room.slots = [bibeak, vanilla, spot].map((operatorId) => ({
      occupant: { kind: 'operator', operatorId },
      groupId: null,
      replacements: []
    }))
    workspace.mainPlan.conf.workaholic = [bibeak, vanilla, spot]
    if (move)
      workspace.compatibility.backupPlans = [
        {
          name: 'tailor-slot',
          trigger: 'True',
          plan: {
            room_3_1: {
              plans: ['香草', '柏喙', '斑点'].map((agent) => ({
                agent,
                group: '',
                replacement: []
              }))
            }
          },
          task: { room_3_1: ['香草', '柏喙', '斑点'] }
        }
      ]
    const report = simulateSchedule(compileRosterSchedule(workspace, { idleOperators: [] }), {
      schedulingModel: 'mower-alpha',
      sampleHours: 8,
      warmupModel: 'hourly',
      initialWorkHours: { [bibeak]: 10 },
      consumptionOverrides: { [bibeak]: 0, [vanilla]: 0, [spot]: 0 },
      production: { outputMode: 'potential', droneTarget: 'none', seed: 14 }
    })
    expect(report.success, JSON.stringify(report.diagnostics)).toBe(true)
    expect(report.diagnostics.some((d) => d.code === 'TRADE_QUALITY_WARMUP_MODEL')).toBe(true)
    orders.push(
      report.production.events
        .filter((e) => e.type === 'order-completed')
        .map((e) => e.order.goldCost)
    )
  }
  expect(orders[0].slice(0, 2)).toEqual([4, 4])
  expect(orders[1].slice(0, 2)).toEqual([4, 3])
})

it('resets warmup when a backup moves a worker to another room', () => {
  const workspace = swapSchedule('same').sourceWorkspace
  const other = workspace.mainPlan.facilities.room_1_2
  other.level = 3
  other.product = 'gold'
  other.slots = [
    {
      occupant: { kind: 'operator', operatorId: 'char_141_nights' },
      groupId: null,
      replacements: []
    }
  ]
  workspace.mainPlan.conf.workaholic.push('char_141_nights')
  workspace.compatibility.backupPlans = [
    {
      name: 'move-room',
      trigger: 'True',
      plan: {
        room_1_1: {
          plans: ['夜烟', '香草', '斑点'].map((agent) => ({ agent, group: '', replacement: [] }))
        },
        room_1_2: { plans: [{ agent: '芬', group: '', replacement: [] }] }
      },
      task: { room_1_1: ['夜烟', '香草', '斑点'], room_1_2: ['芬'] }
    }
  ]
  let last
  const report = simulateSchedule(compileRosterSchedule(workspace, { idleOperators: [] }), {
    schedulingModel: 'mower-alpha',
    sampleHours: 1,
    warmupModel: 'hourly',
    initialWorkHours: { [fang]: 10 },
    consumptionOverrides: { [fang]: 0, [vanilla]: 0, [spot]: 0, char_141_nights: 0 },
    observeInterval(config, start, end, hours) {
      last = { config, start, hours }
    }
  })
  expect(report.success, JSON.stringify(report.diagnostics)).toBe(true)
  expect(last.config.rooms.find((r) => r.id === 'room_1_2').operatorIds).toEqual([fang])
  expect(last.hours.get(fang)).toBeCloseTo(last.start, 2)
})
it('uses the shared session clock when a reception worker leaves and returns between observations', () => {
  const observer = createClueObservation(0),
    config = createDefaultConfig(),
    ines = 'char_4087_ines'
  config.facilityOperatorIds.reception = [ines]
  observer.observe(config, 0, 5, new Map([[ines, 0]]))
  const before = observer.result()
  observer.observe(config, 5, 6, new Map([[ines, 0]]))
  const after = observer.result()
  expect(after.completed + after.progress - before.completed - before.progress).toBeCloseTo(
    1.73 / 20
  )
})

it.each([
  ['char_4015_spuria', '空构', 'power', 'room_1_3', 5, 120],
  ['char_4230_mcnist', '机械师', 'manufacture', 'room_1_1', 12, 101]
])(
  'resets the production curve for %s after changing rooms',
  (id, name, type, roomId, warm, expected) => {
    const workspace = createDefaultWorkspace()
    for (const room of Object.values(workspace.mainPlan.facilities)) {
      room.level = 0
      room.slots = []
    }
    const room = workspace.mainPlan.facilities[roomId]
    room.level = 3
    room.product = 'gold'
    room.slots = [
      { occupant: { kind: 'operator', operatorId: id }, groupId: null, replacements: [] }
    ]
    workspace.mainPlan.conf.workaholic = [id]
    const otherId = type === 'power' ? 'room_2_3' : 'room_1_2'
    const other = workspace.mainPlan.facilities[otherId]
    other.level = 3
    other.product = 'gold'
    other.slots = [
      { occupant: { kind: 'operator', operatorId: vanilla }, groupId: null, replacements: [] }
    ]
    workspace.mainPlan.conf.workaholic.push(vanilla)
    workspace.compatibility.backupPlans = [
      {
        name: 'move-warmed-worker',
        trigger: 'True',
        plan: {
          [roomId]: { plans: [{ agent: '香草', group: '', replacement: [] }] },
          [otherId]: { plans: [{ agent: name, group: '', replacement: [] }] }
        },
        task: { [roomId]: ['香草'], [otherId]: [name] }
      }
    ]
    let last
    const report = simulateSchedule(compileRosterSchedule(workspace, { idleOperators: [] }), {
      schedulingModel: 'mower-alpha',
      sampleHours: 0.5,
      warmupModel: 'hourly',
      initialWorkHours: { [id]: warm },
      consumptionOverrides: { [id]: 0 },
      observeInterval(config, start, end, hours) {
        last = { start, hours }
      }
    })
    expect(report.success, JSON.stringify(report.diagnostics)).toBe(true)
    expect(last.hours.get(id)).toBeCloseTo(last.start, 2)
    expect(report.rooms.find((r) => r.roomId === otherId).averageEfficiencyPercent).toBeCloseTo(
      expected,
      1
    )
  }
)

it('compares the current four-gold probability using the room level', () => {
  const time = {
    workHoursByOperator: new Map([
      [shamare, 3],
      [bibeak, 2.85]
    ])
  }
  expect(temporalTradeQuality([shamare, bibeak], 'normal', {}, time, 2).quality).toBe('alpha')
  expect(temporalTradeQuality([shamare, bibeak], 'normal', {}, time, 3).quality).toBe('beta')
})
