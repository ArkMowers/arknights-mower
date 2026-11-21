import { expect, it } from 'vitest'
import { incomeImageMetrics } from './income'
import { incomeImageMetricText } from './incomeImage'
import { calculateIncomeSanity, createIncomeSanityValuation } from './incomeSanity'

const makeSummary = (overrides = {}, prices = {}) => {
  const summary = {
    exp: 1000,
    goldCount: 10,
    virtualGoldValue: 2000,
    orderLmd: 6000,
    fragments: 2,
    orundum: 20,
    lmdConsumed: 3200,
    orirockConsumed: 4,
    deviceConsumed: 1,
    recycleCount: 0.5,
    recruitmentCount: 2,
    clueCount: 3,
    ...overrides
  }
  const valuation = createIncomeSanityValuation({
    prices: { 中级作战记录: 4, 赤金: 2, 合成玉: 0.9225, 固源岩: 3, 装置: 8, ...prices },
    lmd_sanity: 0.0036,
    income_unit_values: {
      fragment: 5,
      recycle: 10,
      credit: 0.05,
      yellow_certificate: 0,
      green_certificate: 0
    }
  })
  summary.sanity = calculateIncomeSanity(summary, valuation, {
    observedHours: 24,
    production: {
      assumptions: { expectationMode: true },
      expected: { costs: { gold: 12, fragment: 4 } }
    },
    inputs: { schedule: { rooms: [{ type: 'meeting', level: 3 }] } }
  })
  return { summary, valuation }
}
const assertTotals = (summary, rows) => {
  expect(rows.reduce((sum, row) => sum + (row.sanityValue ?? 0), 0)).toBeCloseTo(
    summary.sanity.total,
    9
  )
  const displayedCents = rows.reduce(
    (sum, row) => sum + Math.round((row.sanityDisplayValue ?? 0) * 100),
    0
  )
  expect(displayedCents).toBe(Math.round(Number(summary.sanity.total.toFixed(2)) * 100))
}

it('counts gold manufacturing, net trade, manufactured shards and separate manufacturing costs exactly once', () => {
  const { summary, valuation } = makeSummary()
  // Export uses the completed values even if the editor's prices change later.
  valuation.unitValues.gold = 100
  valuation.unitValues.fragment = 100
  const rows = incomeImageMetrics(summary, 28)
  const row = (key) => rows.find((item) => item.key === key)
  expect(row('gold')).toMatchObject({ daily: 10, unit: '个', sanityValue: 20 })
  expect(row('lmd').sanityValue).toBeCloseTo(6000 * 0.0036 - 12 * 2)
  expect(row('fragment')).toMatchObject({ daily: 2, total: 56, sanityValue: 10 })
  expect(incomeImageMetricText(row('fragment'))).toBe('2 / 10')
  expect(row('orundum').sanityValue).toBeCloseTo(-1.55)
  expect(row('lmdCost').sanityValue).toBeCloseTo(-11.52)
  expect(row('orirockCost').sanityValue).toBe(-12)
  expect(row('deviceCost').sanityValue).toBe(-8)
  expect(row('clue').sanityValue).toBeCloseTo(16.5)
  assertTotals(summary, rows)
})

it('shows manufactured shards when all are sold and continuous exchange without generated clues', () => {
  const { summary } = makeSummary({ goldCount: 0, fragments: 4, clueCount: 0 })
  const rows = incomeImageMetrics(summary, 1)
  expect(rows.some((row) => row.key === 'gold')).toBe(false)
  expect(rows.find((row) => row.key === 'fragment')).toMatchObject({ daily: 4, sanityValue: 20 })
  expect(rows.find((row) => row.key === 'clue')).toMatchObject({ daily: 0, sanityValue: 10.5 })
  assertTotals(summary, rows)
})

it('keeps known contributions in partly unpriced trade and labels the missing price', () => {
  const { summary } = makeSummary({}, { 赤金: null, 装置: null })
  const rows = incomeImageMetrics(summary, 1)
  expect(rows.find((row) => row.key === 'gold').sanityValue).toBeNull()
  const trade = rows.find((row) => row.key === 'lmd')
  expect(trade.sanityValue).toBeCloseTo(21.6)
  expect(trade.sanityPartial).toBe(true)
  expect(incomeImageMetricText(trade)).toContain('（部分）')
  expect(incomeImageMetricText(rows.find((row) => row.key === 'deviceCost'))).toContain('未估值')
  assertTotals(summary, rows)
})

it('deducts shard consumption only from orders when no shards are manufactured', () => {
  const { summary } = makeSummary({ fragments: 0 })
  const rows = incomeImageMetrics(summary, 1)
  expect(rows.some((row) => row.key === 'fragment')).toBe(false)
  expect(rows.find((row) => row.key === 'orundum').sanityValue).toBeCloseTo(-1.55)
  assertTotals(summary, rows)
})

it('retains known Orundum value and marks trade partial when shard price is missing', () => {
  const { summary } = makeSummary()
  const shard = summary.sanity.parts.find((part) => part.key === 'fragment')
  summary.sanity.total -= shard.value
  shard.unitValue = shard.value = null
  summary.sanity.partial = true
  const rows = incomeImageMetrics(summary, 1)
  expect(rows.find((row) => row.key === 'fragment').sanityValue).toBeNull()
  const trade = rows.find((row) => row.key === 'orundum')
  expect(trade.sanityValue).toBeCloseTo(18.45)
  expect(trade.sanityPartial).toBe(true)
  assertTotals(summary, rows)
})

it.each([0.006, -0.006])(
  'reconciles displayed cents while preserving unrounded saved values: %s',
  (value) => {
    const { summary } = makeSummary()
    const original = JSON.stringify(summary)
    const rows = incomeImageMetrics(summary, 1)
    expect(JSON.stringify(summary)).toBe(original)
    assertTotals(summary, rows)
    const minimal = {
      exp: 1,
      goldCount: 0,
      orderLmd: 0,
      fragments: 0,
      lmdConsumed: 0,
      orirockConsumed: 0,
      deviceConsumed: 0,
      orundum: 1,
      recycleCount: 0,
      recruitmentCount: 0,
      clueCount: 0,
      sanity: {
        total: value * 2,
        parts: [
          { key: 'exp', quantity: 1, value, unitValue: value },
          { key: 'orundum', quantity: 1, value, unitValue: value },
          ...[
            'gold',
            'lmd',
            'fragment',
            'orirock',
            'device',
            'recycle',
            'recruitment',
            'clue',
            'exchange'
          ].map((key) => ({ key, quantity: 0, unitValue: null, value: null }))
        ]
      }
    }
    const rounded = incomeImageMetrics(minimal, 1)
    expect(rounded.every((row) => row.sanityValue === value)).toBe(true)
    assertTotals(minimal, rounded)
  }
)

it('preserves legacy badges without fabricating sanity details', () => {
  const { summary } = makeSummary()
  delete summary.sanity
  const rows = incomeImageMetrics(summary, 1)
  expect(rows.every((row) => !Object.hasOwn(row, 'sanityValue'))).toBe(true)
  expect(rows.find((row) => row.key === 'gold').daily).toBe(7000)
  expect(incomeImageMetricText(rows.find((row) => row.key === 'fragment'))).toBe('2')
})
