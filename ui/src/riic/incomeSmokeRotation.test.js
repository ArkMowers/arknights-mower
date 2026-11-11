import { appendFileSync, writeFileSync } from 'node:fs'
import process from 'node:process'
import { expect, it } from 'vitest'
import imagePlan from './fixtures/income-342-smoke-products.json'
import { defaultIncomeSettings } from './income'
import { calculateIncome } from './incomeWorker'

const longRun = process.env.MOWER_SMOKE_LONG_TEST === '1'

// Complete Scheduling Plan decoded from the supplied JPG, including all six backups.
it.each(['B202', 'B201'])(
  'continues the supplied smoke rotation with Vigil assigned to %s',
  (vigilRoom) => {
    const plan = structuredClone(imagePlan)
    if (vigilRoom === 'B201') {
      const smoke = plan.backup_plans.find((backup) => backup.name === '烟火下班')
      smoke.task.room_2_1 = smoke.task.room_2_2
      delete smoke.task.room_2_2
    }
    const sampleDays = longRun ? 28 : vigilRoom === 'B201' ? 3 : 2
    const original = structuredClone(plan)
    const resultLog = process.env.MOWER_SMOKE_RESULT_LOG
      ? `${process.env.MOWER_SMOKE_RESULT_LOG}.${vigilRoom}.json`
      : undefined
    let lastProgress = -1
    const result = calculateIncome(
      plan,
      {
        ...defaultIncomeSettings(),
        seed: 546609889,
        warmupDays: longRun ? 3 : 0,
        sampleDays,
        operatorMode: 'maximum',
        inventorySource: 'manual',
        finiteInventory: false,
        weightMode: 'custom'
      },
      (progress) => {
        const percent = Math.floor(progress.fraction * 100)
        if (resultLog && percent > lastProgress) {
          lastProgress = percent
          appendFileSync(
            resultLog + '.progress',
            JSON.stringify({ percent, label: progress.label }) + '\n'
          )
        }
      }
    )
    expect(result.success, result.error).toBe(true)
    const report = result.simulationReport
    if (resultLog)
      writeFileSync(
        resultLog,
        JSON.stringify({
          incomeSummary: result.summary,
          production: report.production?.sample,
          observedHours: report.observedHours,
          elapsedHours: report.elapsedHours,
          operators: report.operators,
          events: report.events,
          diagnostics: result.diagnostics
        })
      )
    expect(report.observedHours).toBeCloseTo(sampleDays * 24, 6)
    expect(report.elapsedHours).toBeCloseTo((sampleDays + (longRun ? 3 : 0)) * 24, 6)
    expect(report.production.assumptions.expectationMode).toBe(false)
    expect(report.production.assumptions.seed).toBe(546609889)
    expect(result.summary.totalScore82).toBeGreaterThan(0)
    expect(plan).toEqual(original)
    for (const name of ['重岳', '夕', '森蚺', '迷迭香', '乌有', '阿罗玛']) {
      const operator = report.operators.find((item) => item.operatorName === name)
      expect(operator.workHours, name).toBeGreaterThan(0)
      expect(operator.restHours, name).toBeGreaterThan(0)
    }
    if (!longRun && vigilRoom === 'B202') {
      const firstDeparture = report.events.find(
        (event) => event.type === 'shift-off' && event.operators.includes('char_2024_chyue')
      )
      expect(firstDeparture?.time).toBeGreaterThan(6)
      expect(firstDeparture?.time).toBeLessThan(7)
      expect(report.operators.find((item) => item.operatorName === '夕').exhaustedHours).toBe(0)
    }
    const windows = longRun ? [72, 240, 408, 576] : [0]
    for (const start of windows) {
      // Check continued activity in each sampled week, without requiring a fixed cycle length.
      for (const id of [
        'char_2024_chyue',
        'char_416_zumama',
        ...(longRun ? ['char_446_aroma'] : [])
      ]) {
        for (const type of ['shift-off', 'shift-on']) {
          expect(
            report.events.some(
              (event) =>
                event.time >= start &&
                event.time < start + (longRun ? 168 : sampleDays * 24) &&
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
