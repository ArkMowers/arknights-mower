import process from 'node:process'
import { appendFileSync } from 'node:fs'
import { expect, it } from 'vitest'
import supportPlan from './fixtures/income-support-request-recovery.json'
import tradePlan from './fixtures/income-21trade-mastery.json'
import { defaultIncomeSettings } from './income'
import { calculateIncome } from './incomeWorker'

const longRun = process.env.MOWER_SUPPORT_LONG_TEST === '1'

it.each([
  ['support recovery', supportPlan, ['令', '温蒂', '森蚺', '冬时', '承曦格雷伊']],
  [
    '21-trade mastery',
    tradePlan,
    ['令', '温蒂', '森蚺', '承曦格雷伊', ...(longRun ? ['苍苔', '阿罗玛', '机械师'] : [])]
  ]
])(
  'completes the supplied %s plan with working and resting progress',
  (name, plan, rotatingNames) => {
    const original = structuredClone(plan)
    const result = calculateIncome(plan, {
      ...defaultIncomeSettings(),
      expectationMode: true,
      warmupDays: 3,
      sampleDays: longRun ? 28 : 1,
      operatorMode: 'maximum',
      inventorySource: 'manual',
      finiteInventory: false,
      weightMode: 'custom',
      seed: 42
    })
    expect(result.success, result.error).toBe(true)
    expect(result.observedHours).toBeCloseTo((longRun ? 28 : 1) * 24, 8)
    expect(result.simulationReport.elapsedHours).toBeCloseTo((longRun ? 31 : 4) * 24, 8)
    expect(result.diagnostics.some(({ code }) => code === 'BACKUP_EXECUTION_FAILED')).toBe(false)
    expect(plan).toEqual(original)
    if (process.env.MOWER_SUPPORT_RESULT_LOG)
      appendFileSync(
        process.env.MOWER_SUPPORT_RESULT_LOG,
        JSON.stringify({
          name,
          warmupDays: 3,
          sampleDays: longRun ? 28 : 1,
          summary: result.summary,
          observedHours: result.observedHours,
          operators: result.simulationReport.operators,
          diagnostics: result.diagnostics,
          modelProvenance: result.modelProvenance
        }) + '\n'
      )
    for (const name of rotatingNames) {
      const operator = result.simulationReport.operators.find((item) => item.operatorName === name)
      expect(operator.workHours, name).toBeGreaterThan(0)
      expect(operator.restHours, name).toBeGreaterThan(0)
    }
  },
  longRun ? 1200000 : 120000
)
