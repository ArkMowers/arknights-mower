import { expect, it } from 'vitest'
import { incomeOrderDistribution } from './incomeOrders'
import { captureOrder, getOrderDistribution } from './vendor/rules/orderRules'

const report = (events) => ({
  assumptions: { warmupHours: 72 },
  elapsedHours: 240,
  production: { events }
})
const completed = (order, time = 100) => ({ type: 'order-completed', time, order })

it('classifies raw gold tiers before Proviso, Tequila and U-Official conversions', () => {
  const [two, three, four] = getOrderDistribution(3)
  const orders = [
    captureOrder(two, { proviso: 2 }, 100),
    captureOrder(three, { proviso: 2 }, 100),
    captureOrder(four, { tequila: 2 }, 100),
    captureOrder(four, { uOfficial: true }, 100)
  ]
  expect(orders.map((order) => order.goldCost)).toEqual([4, 5, 4, 2])
  expect(incomeOrderDistribution(report(orders.map((order) => completed(order))))).toEqual({
    total: 4,
    other: 0,
    rows: [
      { gold: 2, count: 1, ratio: 0.25 },
      { gold: 3, count: 1, ratio: 0.25 },
      { gold: 4, count: 2, ratio: 0.5 }
    ]
  })
})

it('counts completed orders once inside the window, including special orders in the denominator', () => {
  const ordinary = captureOrder(getOrderDistribution(3)[0], {}, 100)
  const special = captureOrder(
    getOrderDistribution(3, 'normal', 'closure')[0],
    { closure: true },
    100
  )
  const events = [
    completed(ordinary, 72),
    completed(ordinary, 100),
    completed(ordinary, 241),
    completed(special, 240),
    { type: 'order-collected', time: 120, order: ordinary },
    { type: 'order-started', time: 130, order: ordinary }
  ]
  const original = structuredClone(events)
  expect(incomeOrderDistribution(report(events))).toEqual({
    total: 2,
    other: 1,
    rows: [
      { gold: 2, count: 1, ratio: 0.5 },
      { gold: 3, count: 0, ratio: 0 },
      { gold: 4, count: 0, ratio: 0 }
    ]
  })
  expect(events).toEqual(original)
})

it('distinguishes missing records from a completed window with no orders', () => {
  expect(incomeOrderDistribution(undefined)).toBeNull()
  expect(incomeOrderDistribution({ production: { events: [] } })).toBeNull()
  expect(incomeOrderDistribution(report([]))).toMatchObject({ total: 0, other: 0 })
  expect(incomeOrderDistribution(report([])).rows.every((row) => row.ratio === 0)).toBe(true)
  const unknown = completed({ mode: 'gold', baseMinutes: 999, goldCost: 4 })
  expect(incomeOrderDistribution(report([unknown]))).toMatchObject({ total: 1, other: 1 })
})
