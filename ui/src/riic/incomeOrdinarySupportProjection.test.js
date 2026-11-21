import { expect, it } from 'vitest'
import process from 'node:process'
import plan from './fixtures/income-21trade-generated.json'
import { defaultIncomeSettings } from './income'
import { calculateIncome } from './incomeWorker'

const longRun = process.env.MOWER_SUPPORT_LONG_TEST === '1'

it(
  'continues ordinary group admission after recalling a group that releases dormitory replacements',
  () => {
    const input = structuredClone(plan)
    input.advanced_settings.group_resting_thresholds = { 自动化: 0.8 }
    const original = structuredClone(input)
    const result = calculateIncome(input, {
      ...defaultIncomeSettings(),
      expectationMode: true,
      warmupDays: longRun ? 3 : 0,
      sampleDays: longRun ? 7 : 3,
      operatorMode: 'maximum',
      finiteInventory: false,
      inventorySource: 'manual',
      weightMode: 'custom',
      droneRoom: 'room_3_3'
    })
    expect(result.success, result.error).toBe(true)
    expect(result.observedHours).toBeCloseTo((longRun ? 7 : 3) * 24, 6)
    expect(result.summary.totalScore82).toBeGreaterThan(0)
    const operators = result.simulationReport.operators
    expect(operators.find((op) => op.operatorName === '承曦格雷伊').restHours).toBeGreaterThan(0)
    expect(
      result.diagnostics.some((diagnostic) => diagnostic.code === 'BACKUP_EXECUTION_FAILED')
    ).toBe(false)
    expect(input).toEqual(original)
  },
  longRun ? 1200000 : 120000
)
