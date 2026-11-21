import { expect, it } from 'vitest'
import process from 'node:process'
import plan from './fixtures/income-21trade-generated.json'
import { defaultIncomeSettings } from './income'
import { calculateIncome } from './incomeWorker'

const longRun = process.env.MOWER_GENERATED_LONG_TEST === '1'

it(
  'calculates the current 21-trade plan without a drone inventory boundary',
  () => {
    const original = structuredClone(plan)
    const result = calculateIncome(plan, {
      ...defaultIncomeSettings(),
      expectationMode: true,
      warmupDays: 3,
      sampleDays: longRun ? 28 : 1,
      operatorMode: 'maximum',
      finiteInventory: false,
      inventorySource: 'manual',
      weightMode: 'custom',
      droneRoom: 'room_3_3'
    })
    expect(result.success, result.error).toBe(true)
    const production = result.simulationReport.production
    const expected = production.expected
    expect(production.assumptions.droneAllocationModel).toBe('generated-capacity-v1')
    expect(production.sampleDrones).toBeUndefined()
    expect(result.stability.drones).toBeUndefined()
    expect(expected.droneGenerated).toBeGreaterThan(0)
    expect(Math.abs(expected.droneAllocated - expected.droneGenerated)).toBeLessThan(
      1e-8 * expected.droneGenerated
    )
    expect(expected.pendingSwitchDrones).toBe(0)
    expect(expected.droneLost).toBe(0)
    expect(expected.droneUnallocated).toBeLessThan(1e-8 * expected.droneGenerated)
    expect(result.summary.totalScore82).toBeCloseTo(
      result.summary.exp + result.summary.goldValue * 0.8 + result.summary.orderLmd * 0.2,
      6
    )
    expect(plan).toEqual(original)
  },
  longRun ? 1200000 : 60000
)
