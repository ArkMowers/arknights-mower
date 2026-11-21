import { expect, it } from 'vitest'
import process from 'node:process'
import { appendFileSync } from 'node:fs'
import originalPlan from './fixtures/income-drone-feedback.json'
import { defaultIncomeSettings } from './income'
import { calculateIncome } from './incomeWorker'

const plan = {
  ...originalPlan,
  advanced_settings: { ...originalPlan.advanced_settings, drone_room: 'room_1_2' }
}

const longRun = process.env.MOWER_DRONE_LONG_TEST === '1'

it(
  'calculates the supplied drone-feedback plan with a shared generated acceleration budget',
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
      weightMode: 'custom'
    })
    expect(result.success, result.error).toBe(true)
    expect(result.observedHours).toBeCloseTo(days * 24, 6)
    const production = result.simulationReport.production
    expect(production.assumptions.droneAllocationModel).toBe('generated-capacity-v1')
    const spends = production.events.filter(
      (event) => event.type === 'native-manufacture-drone' && event.amount > 0
    )
    expect(spends).toEqual([])
    expect(production.events.some((event) => event.type === 'theoretical-drone')).toBe(false)
    expect(production.sampleDrones).toBeUndefined()
    const drones = production.expected
    expect(drones.droneGenerated).toBeGreaterThan(0)
    expect(drones.droneGenerated).toBeCloseTo(
      drones.droneAllocated + drones.droneUnallocated + drones.droneLost,
      6
    )
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
