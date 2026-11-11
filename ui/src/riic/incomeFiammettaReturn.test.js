import { expect, it } from 'vitest'
import { appendFileSync } from 'node:fs'
import process from 'node:process'
import plan from './fixtures/income-fiammetta-return.json'
import { defaultIncomeSettings } from './income'
import { calculateIncome } from './incomeWorker'

const longRun = process.env.MOWER_INCOME_LONG_TEST === '1'

it(
  'returns Aroma after cross-dorm charging and exhaustion-timer refresh in the seed 42 plan',
  () => {
    const sampleDays = longRun ? 28 : 2
    const result = calculateIncome(plan, {
      ...defaultIncomeSettings(),
      expectationMode: false,
      fixedSeed: 42,
      operatorMode: 'maximum',
      inventorySource: 'manual',
      weightMode: 'custom',
      sampleDays
    })
    expect(result.success).toBe(true)
    const report = result.simulationReport
    const aroma = report.operators.find((op) => op.operatorId === 'char_446_aroma')
    const events = report.events.filter((event) => event.operators.includes(aroma.operatorId))
    const charge = events.find((event) => event.type === 'fiammetta')
    const returned = events.find((event) => event.type === 'shift-on' && event.time > charge?.time)
    if (process.env.MOWER_INCOME_TEST_LOG) {
      appendFileSync(
        process.env.MOWER_INCOME_TEST_LOG,
        JSON.stringify({ sampleDays, aroma, charge, returned, diagnostics: report.diagnostics }) +
          '\n'
      )
    }
    expect(report.elapsedHours).toBe((3 + sampleDays) * 24)
    expect(charge).toBeDefined()
    expect(returned).toBeDefined()
    expect(returned.time - charge.time).toBeLessThan(10 / 3600)
    expect(aroma.workHours).toBeGreaterThan(sampleDays * 24 * 0.75)
    expect(aroma.idleHours).toBeLessThan(1)
  },
  longRun ? 1200000 : 120000
)
