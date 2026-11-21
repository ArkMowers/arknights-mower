import process from 'node:process'
import { expect, it } from 'vitest'
import plan from './fixtures/income-shared-working-swap.json'
import { defaultIncomeSettings } from './income'
import { calculateIncome } from './incomeWorker'

const longRun = process.env.MOWER_INCOME_LONG_TEST === '1'

it(
  'rotates the working swap group through the production income entry point',
  () => {
    const before = structuredClone(plan)
    const sampleDays = longRun ? 28 : 1
    const result = calculateIncome(plan, {
      ...defaultIncomeSettings(),
      warmupDays: longRun ? 3 : 0,
      sampleDays,
      operatorMode: 'maximum',
      finiteInventory: false,
      weightMode: 'custom',
      droneRoom: 'room_3_1'
    })
    expect(result.success, JSON.stringify(result.diagnostics)).toBe(true)
    expect(result.observedHours).toBeCloseTo(sampleDays * 24, 6)
    const operators = result.simulationReport.operators
    for (const name of ['歌蕾蒂娅', '斯卡蒂', '幽灵鲨']) {
      const operator = operators.find((item) => item.operatorName === name)
      expect(operator.restHours, name).toBeGreaterThan(0)
      expect(operator.workHours, name).toBeGreaterThan(0)
    }
    const departures = result.simulationReport.events.filter((event) => event.type === 'shift-off')
    expect(departures.some((event) => event.operators.includes('char_474_glady'))).toBe(true)
    expect(plan).toEqual(before)
  },
  longRun ? 1200000 : 30000
)
