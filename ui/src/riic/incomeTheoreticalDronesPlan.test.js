import { expect, it } from 'vitest'
import process from 'node:process'
import { appendFileSync } from 'node:fs'
import plan from './fixtures/income-drone-feedback.json'
import { defaultIncomeSettings } from './income'
import { calculateIncome } from './incomeWorker'

const longRun = process.env.MOWER_DRONE_LONG_TEST === '1'

it(
  'calculates the supplied drone-feedback plan with a shared threshold-controlled drone stock',
  () => {
    const original = structuredClone(plan)
    const days = longRun ? 90 : 1
    const result = calculateIncome(plan, {
      ...defaultIncomeSettings(),
      expectationMode: true,
      warmupDays: 3,
      sampleDays: days,
      operatorMode: 'maximum',
      inventorySource: 'manual',
      finiteInventory: false,
      weightMode: 'custom',
      droneRoom: 'room_1_2'
    })
    expect(result.success, result.error).toBe(true)
    expect(result.observedHours).toBeCloseTo(days * 24, 6)
    const production = result.simulationReport.production
    expect(production.assumptions.droneAllocationModel).toBe('threshold-v1')
    const spends = production.events.filter(
      (event) => event.type === 'native-manufacture-drone' && event.amount > 0
    )
    expect(spends.length).toBeGreaterThan(0)
    expect(spends.every((event) => event.roomId === 'room_1_2')).toBe(true)
    expect(spends.every((event) => Number.isInteger(event.amount))).toBe(true)
    expect(production.events.some((event) => event.type === 'theoretical-drone')).toBe(false)
    const drones = production.sampleDrones
    expect(drones.closing).toBeGreaterThanOrEqual(150)
    expect(drones.closing).toBeCloseTo(
      drones.opening + drones.generated - drones.overflow - drones.consumed,
      6
    )
    expect(production.expected.droneAllocated).toBeLessThanOrEqual(drones.consumed)
    expect(result.summary.totalScore82).toBeCloseTo(
      result.summary.exp +
        0.8 * (result.summary.goldValue + result.summary.virtualGoldValue) +
        0.2 * result.summary.orderLmd,
      6
    )
    expect(plan).toEqual(original)
    if (process.env.MOWER_DRONE_RESULT_LOG)
      appendFileSync(
        process.env.MOWER_DRONE_RESULT_LOG,
        JSON.stringify({ days, summary: result.summary, drones }) + '\n'
      )
  },
  longRun ? 1200000 : 60000
)
