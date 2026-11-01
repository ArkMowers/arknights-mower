import { expect, it } from 'vitest'
import { defaultIncomeSettings } from './income'
import { calculateIncome } from './incomeWorker'

it('completes ninety sampled days without resetting stock at the warmup boundary', () => {
  const plan = {
    default: 'plan1',
    conf: {},
    backup_plans: [],
    plan1: {
      room_1_1: { name: '制造站', product: 'gold', plans: [] },
      room_1_3: { name: '发电站', plans: [] }
    }
  }
  const result = calculateIncome(plan, {
    ...defaultIncomeSettings(),
    operatorMode: 'maximum',
    inventorySource: 'manual',
    weightMode: 'custom',
    warmupDays: 3,
    sampleDays: 90
  })
  expect(result.success, result.error).toBe(true)
  expect(result.observedHours).toBeCloseTo(2160, 5)
  expect(result.simulationReport.elapsedHours).toBeCloseTo(2232, 5)
  expect(result.diagnostics.some((d) => d.code === 'SIMULATION_EVENT_LIMIT')).toBe(false)
  // An unstaffed factory makes one gold bar every 72 minutes: twenty per day.
  expect(result.summary.goldCount).toBeCloseTo(20, 5)
  expect(result.goldInventory.initial).toBe(0)
  // Products awaiting collection at the sampling boundary are not opening stock yet.
  expect(result.goldInventory.sampleOpening).toBeGreaterThan(0)
  expect(result.goldInventory.closing).toBe(1860)
  expect(result.resources.closing.gold).toBe(1860)
}, 30000)
