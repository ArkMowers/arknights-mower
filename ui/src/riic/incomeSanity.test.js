import { expect, it } from 'vitest'
import {
  createIncomeSanityValuation,
  calculateIncomeSanity,
  recyclingIncomeValue,
  validateIncomeSanityValuation
} from './incomeSanity'
import { calculateIncome } from './incomeWorker'
import { defaultIncomeSettings } from './income'

const prices = { 中级作战记录: 4, 赤金: 2, 合成玉: 0.75, 固源岩: 3, 装置: 8 }
const valuation = () =>
  createIncomeSanityValuation({
    prices,
    lmd_sanity: 0.0036,
    income_unit_values: {
      fragment: 5,
      recycle: 10,
      credit: 0.05,
      green_certificate: 0,
      recruitment_certificates: 0.2
    }
  })
const summary = () => ({
  exp: 1000,
  goldCount: 10,
  goldValue: 5000,
  virtualGoldValue: 2000,
  orderLmd: 4000,
  lmdConsumed: 1000,
  fragments: 4,
  orundum: 10,
  orirockConsumed: 2,
  deviceConsumed: 1,
  recycleCount: 0.5,
  recruitmentCount: 2,
  clueCount: 3
})
const simulation = () => ({
  observedHours: 48,
  assumptions: { warmupHours: 24 },
  elapsedHours: 72,
  production: {
    assumptions: { expectationMode: true },
    expected: { costs: { gold: 8, fragment: 4 } }
  }
})
it('prices physical net production without counting order premiums as gold again', () => {
  const result = calculateIncomeSanity(summary(), valuation(), simulation())
  // 4 EXP + 12 net gold + 10.8 net LMD + 10 fragments + 7.5 jade - 6 rocks - 8 devices + 5 recycle + refresh + 6 clues.
  expect(result.total).toBeCloseTo(41.3 + (((2 * 0.2 * 38) / 258) * 600 * 135) / 180)
  expect(result.partial).toBe(false)
  expect(result.parts.find((p) => p.key === 'gold').quantity).toBe(6)
})
it.each(['potential', 'settled'])(
  'subtracts selected output order costs in %s mode and excludes warmup',
  (outputMode) => {
    const sim = simulation()
    const event = (type, time, goldCost, fragmentCost) => ({
      type,
      time,
      order: { completedAt: time, goldCost, fragmentCost }
    })
    sim.production = {
      assumptions: { outputMode },
      events: [
        event('order-completed', 24, 99, 99),
        event('order-collected', 24, 99, 99),
        event('order-completed', 30, 4, 2),
        event('order-collected', 31, 4, 2)
      ]
    }
    const result = calculateIncomeSanity(summary(), valuation(), sim)
    expect(result.parts.find((p) => p.key === 'gold').quantity).toBe(8)
    expect(result.parts.find((p) => p.key === 'fragment').quantity).toBe(3)
  }
)
it('uses editable marginal yellow certificate and credit values, including zero', () => {
  const defaults = createIncomeSanityValuation({
    prices,
    lmd_sanity: 0.0036,
    credit_shop_value_threshold: 0.045,
    income_unit_values: { recruitment_certificates: 0.2, green_certificate: 0 }
  })
  expect(defaults.yellowCertificateValue).toBeCloseTo(66.2790697674)
  expect(defaults.unitValues.recruitment).toBeCloseTo(13.2558139535)
  expect(defaults.unitValues.clue).toBeCloseTo(1.8)
  const zero = createIncomeSanityValuation({
    prices,
    lmd_sanity: 0.0036,
    income_unit_values: { yellow_certificate: 0, green_certificate: 0, credit: 0 }
  })
  expect(zero.recruitmentCertificates).toBeCloseTo(0.2016555, 5)
  expect(zero.unitValues.recruitment).toBe(0)
  expect(zero.unitValues.clue).toBe(0)
  const changed = createIncomeSanityValuation({
    prices,
    income_unit_values: {
      yellow_certificate: 10,
      recruitment_certificates: 0.28,
      credit: 0.01,
      green_certificate: 0
    }
  })
  expect(changed.unitValues.recruitment).toBeCloseTo(2.8)
  expect(changed.unitValues.clue).toBe(0.4)
})
it('values one ordinary recycle cycle plus its long-run extra rewards', () => {
  const model = {
    ordinary: [
      { name: 'A', weight: 1, points: 20 },
      { name: 'B', weight: 3, points: 0 }
    ],
    extra: [{ name: 'C', weight: 1 }],
    point_threshold: 100
  }
  expect(recyclingIncomeValue({ A: 4, B: 8, C: 20 }, model)).toBe(8)
  expect(recyclingIncomeValue({ A: 4, B: 8 }, model)).toBeNull()
})
it('marks nonzero unpriced costs as partial and keeps zero prices distinct', () => {
  const values = valuation()
  values.unitValues.fragment = null
  const input = summary()
  input.fragments = 0
  const result = calculateIncomeSanity(input, values, simulation())
  expect(result.partial).toBe(true)
  expect(result.unpriced).toEqual(['源石碎片净产出'])
  input.fragments = 2
  expect(calculateIncomeSanity(input, values, simulation()).partial).toBe(false)
  values.unitValues.fragment = 0
  expect(calculateIncomeSanity(summary(), values, simulation()).partial).toBe(false)
})
it('rejects missing or invalid frozen unit values', () => {
  expect(() => validateIncomeSanityValuation(null)).toThrow()
  for (const value of [undefined, NaN, Infinity, -1]) {
    const invalid = valuation()
    invalid.unitValues.exp = value
    expect(() => validateIncomeSanityValuation(invalid)).toThrow()
  }
})
it.each([true, false])(
  'prices existing Worker output while preserving scheduling and resources (expected=%s)',
  (expectationMode) => {
    const plan = {
      default: 'plan1',
      conf: { workaholic: ['梓兰', '塞雷娅'] },
      backup_plans: [],
      plan1: {
        contact: { name: '', plans: [{ agent: '梓兰' }] },
        meeting: { name: '', plans: [{ agent: '塞雷娅' }] },
        room_1_1: { name: '制造站', product: 'gold', plans: [] },
        room_1_3: { name: '发电站', plans: [] }
      }
    }
    const settings = {
      ...defaultIncomeSettings(),
      operatorMode: 'maximum',
      weightMode: 'custom',
      finiteInventory: false,
      warmupDays: 0,
      sampleDays: 1,
      expectationMode,
      seed: 42
    }
    const before = calculateIncome(plan, settings)
    const after = calculateIncome(plan, {
      ...settings,
      weightMode: 'sanity',
      sanityValuation: valuation()
    })
    expect(after.success, after.error).toBe(true)
    expect(after.resources).toEqual(before.resources)
    expect(after.simulationReport.segments).toEqual(before.simulationReport.segments)
    expect(after.summary.totalScore82).toBe(before.summary.totalScore82)
    expect(after.summary.sanity.total).toBeCloseTo(
      ((after.summary.recruitmentCount * 0.2 * 38) / 258) * 450 +
        after.summary.clueCount * 2 +
        after.summary.recycleCount * 10 +
        210 * 0.05
    )
    expect(after.summary.recruitmentCount).toBeGreaterThan(0)
    expect(after.summary.clueCount).toBeGreaterThan(0)
  }
)

it('caps credit value jointly for gifts and continuous exchange without inventing more exchanges', () => {
  const sim = simulation()
  sim.inputs = { schedule: { rooms: [{ type: 'meeting', level: 1 }] } }
  const values = createIncomeSanityValuation({
    prices,
    lmd_sanity: 0.0036,
    income_unit_values: { credit: 0.1, credit_daily_limit: 250 }
  })
  const input = summary()
  input.clueCount = 8
  const result = calculateIncomeSanity(input, values, sim)
  expect(result.credits).toEqual({ produced: 530, valued: 250 })
  expect(result.parts.find((p) => p.key === 'exchange').value).toBe(21)
  expect(result.parts.find((p) => p.key === 'clue').value).toBe(4)
  values.creditDailyLimit = 0
  const zero = calculateIncomeSanity(input, values, sim)
  expect(zero.parts.find((p) => p.key === 'exchange').value).toBe(0)
  expect(zero.parts.find((p) => p.key === 'clue').value).toBe(0)
  sim.inputs.schedule.rooms[0].level = 0
  expect(calculateIncomeSanity(input, values, sim).credits.produced).toBe(320)
})

it('allows negative sanity income when producing and selling Orundum at a lower resource value', () => {
  const plan = {
    default: 'plan1',
    conf: { workaholic: '杜林,安赛尔' },
    backup_plans: [],
    facility_levels: { room_1_1: 3, room_3_3: 1, room_2_1: 3, room_1_3: 3, room_2_3: 3 },
    plan1: {
      room_1_1: { name: '制造站', product: 'gold', plans: [] },
      room_3_3: { name: '制造站', product: 'orirock', plans: [{ agent: '杜林', replacement: [] }] },
      room_2_1: {
        name: '贸易站',
        product: 'orundum',
        plans: [{ agent: '安赛尔', replacement: [] }]
      },
      room_1_3: { name: '发电站', plans: [] },
      room_2_3: { name: '发电站', plans: [] }
    }
  }
  const snapshot = createIncomeSanityValuation({
    prices,
    lmd_sanity: 0.0036,
    income_unit_values: {
      fragment: 3 + 800 * 0.0036,
      recycle: 0,
      credit: 0,
      yellow_certificate: 0,
      green_certificate: 0
    }
  })
  const result = calculateIncome(plan, {
    ...defaultIncomeSettings(),
    warmupDays: 0,
    sampleDays: 1,
    operatorMode: 'maximum',
    inventorySource: 'manual',
    finiteInventory: false,
    weightMode: 'sanity',
    sanityValuation: snapshot
  })
  expect(result.success, result.error).toBe(true)
  expect(result.summary.orundum).toBeGreaterThan(0)
  expect(result.summary.fragments).toBeGreaterThan(0)
  // Each five Orundum consumes one shard. Manufactured shards and the deficit
  // share the supplied recipe value, so intermediate production cancels out.
  expect(result.summary.sanity.total).toBeCloseTo(
    result.summary.orundum * (0.75 - (3 + 800 * 0.0036) / 5)
  )
  expect(result.summary.sanity.total).toBeLessThan(0)
})
