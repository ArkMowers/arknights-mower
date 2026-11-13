import process from 'node:process'
import { expect, it } from 'vitest'
import imagePlan from './fixtures/income-342-smoke-aroma.json'
import { defaultIncomeSettings } from './income'
import { calculateIncome } from './incomeWorker'

const longRun = process.env.MOWER_SMOKE_EXPECTATION_LONG_TEST === '1'

it.each([true, false])(
  'finishes the supplied smoke and Aroma plan with idle release %s',
  (freeRoom) => {
    const plan = structuredClone(imagePlan)
    plan.advanced_settings.free_room = freeRoom
    const original = structuredClone(plan)
    const warmupDays = longRun ? 3 : 0
    const sampleDays = longRun ? 28 : 1
    const result = calculateIncome(plan, {
      ...defaultIncomeSettings(),
      expectationMode: true,
      warmupDays,
      sampleDays,
      operatorMode: 'maximum',
      inventorySource: 'manual',
      finiteInventory: false,
      weightMode: 'custom',
      productionWeights: { exp: 1, gold: 0.8, orders: 0.4, fragments: 0, orundum: 0 }
    })
    expect(result.success, result.error).toBe(true)
    expect(plan).toEqual(original)
    const report = result.simulationReport
    expect(report.observedHours).toBeCloseTo(sampleDays * 24, 6)
    expect(report.elapsedHours).toBeCloseTo((warmupDays + sampleDays) * 24, 6)
    expect(report.production.assumptions.timingModel).toBe('theoretical-events-v1')
    for (const start of longRun ? [72, 240, 408, 576] : [0]) {
      for (const id of [
        'char_2024_chyue',
        'char_416_zumama',
        ...(longRun ? ['char_446_aroma'] : [])
      ]) {
        for (const type of ['shift-on', 'shift-off']) {
          expect(
            report.events.some(
              (event) =>
                event.time >= start &&
                event.time < start + (longRun ? 168 : 24) &&
                event.type === type &&
                event.operators.includes(id)
            ),
            `${id} ${type} after ${start}h`
          ).toBe(true)
        }
      }
    }
  },
  longRun ? 1200000 : 120000
)
