import { expect, it } from 'vitest'
import process from 'node:process'
import plan from './fixtures/income-automation-rest.json'
import { incomeWorkspace, defaultIncomeSettings } from './income'
import { calculateIncome } from './incomeWorker'
import { compileRosterSchedule } from './vendor/scheduler/compileRosterSchedule'
import { compiledScheduleToRuntimeConfig } from './vendor/scheduler/scheduleAdapter'
import { createRosterRuntime } from './vendor/scheduler/rosterRuntime'
import { createBackupPlanController } from './vendor/scheduler/backupPlans'
import { getMowerSourceRuntime } from './vendor/scheduler/mowerSourceRuntime'

it.each([true, false])('applies FarTooth priority while Aroma working is %s', (working) => {
  const original = structuredClone(plan)
  const compiled = compileRosterSchedule(incomeWorkspace(plan))
  const config = compiledScheduleToRuntimeConfig(compiled)
  config.mowerAlpha = true
  const state = createRosterRuntime(config)
  const controller = createBackupPlanController(compiled, state)
  const source = getMowerSourceRuntime(state)
  // Imported runtime keys use game operator IDs.
  const farTooth = 'char_430_fartth'
  const aroma = 'char_446_aroma'
  const pine = ['char_420_flamtl', 'char_4098_vvana', 'char_496_wildmn', 'char_431_ashlok']
  expect(source.data.operators[farTooth]).toBeDefined()
  expect(source.data.operators[aroma]).toBeDefined()
  for (const [operator, mood] of [[farTooth, 24], ...pine.map((id) => [id, 12])]) {
    state.morale[operator] = mood
    Object.assign(source.data.operators[operator], { mood, timeStampMicros: 0, depletionRate: 0 })
  }
  Object.assign(source.data.operators[aroma], {
    currentRoom: working ? 'room_1_1' : '',
    currentIndex: working ? 0 : -1
  })
  controller.evaluate('END')
  const index = plan.backup_plans.findIndex((backup) => backup.name === '远牙动态低优')
  expect(controller.active[index]).toBe(true)
  expect(source.data.backupGroup).toContain('default')
  expect(source.data.backupGroup).toContain(working ? 'group-1' : 'group-2')
  expect(source.data.lowPriorityNames).toContain(farTooth)
  state.morale[farTooth] = 0
  Object.assign(source.data.operators[farTooth], { mood: 0, timeStampMicros: 0 })
  controller.evaluate('END')
  expect(controller.active[index]).toBe(false)
  expect(source.data.lowPriorityNames).not.toContain(farTooth)
  expect(controller.evaluate('END')).toBe(false)
  expect(plan).toEqual(original)
})

const longRun = process.env.MOWER_INCOME_LONG_TEST === '1'
it.runIf(longRun)(
  'activates the supplied default backup during the full income cycle',
  () => {
    const original = structuredClone(plan)
    const result = calculateIncome(plan, {
      ...defaultIncomeSettings(),
      operatorMode: 'maximum',
      inventorySource: 'manual',
      finiteInventory: false,
      weightMode: 'custom',
      warmupDays: 3,
      sampleDays: 28
    })
    expect(result.success, result.error).toBe(true)
    expect(result.observedHours).toBeCloseTo(672, 6)
    const events = result.simulationReport.events.filter(
      (event) => event.type === 'backup-plan' && event.backupName === '远牙动态低优'
    )
    expect(events.some((event) => event.active)).toBe(true)
    expect(events.some((event) => !event.active)).toBe(true)
    expect(plan).toEqual(original)
  },
  1200000
)
