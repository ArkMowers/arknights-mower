import { expect, it } from 'vitest'
import process from 'node:process'
import { writeFileSync } from 'node:fs'
import baseline from './fixtures/income-21trade-generated.json'
import { defaultIncomeSettings } from './income'
import { calculateIncome } from './incomeWorker'

const longRun = process.env.MOWER_RETURN_LONG_TEST === '1'

it(
  'completes the 3-book plan with Aroma after the existing Fiammetta charging targets',
  () => {
    const plan = structuredClone(baseline)
    plan.advanced_settings.group_resting_thresholds.自动化 = 0.5
    const fia = plan.plan1.dormitory_1.plans.find((slot) => slot.agent === '菲亚梅塔')
    fia.replacement = ['机械师', '歌蕾蒂娅', '阿罗玛']
    const original = structuredClone(plan)
    const sampleDays = longRun ? 90 : 1
    const result = calculateIncome(plan, {
      ...defaultIncomeSettings(),
      expectationMode: true,
      warmupDays: 3,
      sampleDays,
      operatorMode: 'maximum',
      inventorySource: 'manual',
      finiteInventory: false,
      weightMode: 'custom',
      droneRoom: 'room_3_3'
    })
    expect(result.success, result.error).toBe(true)
    expect(result.simulationReport.observedHours).toBeCloseTo(sampleDays * 24, 6)
    expect(result.summary.totalScore82).toBeGreaterThan(0)
    expect(result.diagnostics.some((item) => item.code === 'BACKUP_EXECUTION_FAILED')).toBe(false)
    expect(plan).toEqual(original)
    if (process.env.MOWER_RETURN_RESULT_LOG)
      writeFileSync(
        process.env.MOWER_RETURN_RESULT_LOG,
        JSON.stringify(
          { sampleDays, summary: result.summary, operators: result.simulationReport.operators },
          null,
          2
        )
      )
  },
  longRun ? 1200000 : 60000
)
