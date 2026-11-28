import { describe, expect, it } from 'vitest'
import { maintenance_trigger } from '@/utils/trigger_maintenance'
import { compileBackupExpression } from './vendor/scheduler/backupExpression'
import { createRosterRuntime } from './vendor/scheduler/rosterRuntime'
import { createDefaultWorkspace } from './vendor/workbench/defaults'
import { compileRosterSchedule } from './vendor/scheduler/compileRosterSchedule'
import { compiledScheduleToRuntimeConfig } from './vendor/scheduler/scheduleAdapter'
import { createBackupPlanController } from './vendor/scheduler/backupPlans'

describe('stop duration conditions in income simulation', () => {
  it.each([
    ['<', false],
    ['<=', true],
    ['==', true],
    ['!=', false],
    ['>=', true],
    ['>', false]
  ])('compares the total duration with %s at the six-hour boundary', (operator, expected) => {
    const expression = compileBackupExpression(maintenance_trigger(0.5, operator, 6), new Set())
    const runtime = createRosterRuntime({
      positions: [],
      beds: [],
      majorMaintenanceStartHours: 1,
      majorMaintenanceDurationHours: 6
    })
    expect(expression.usesMajorMaintenance).toBe(true)
    expect(expression.evaluate(runtime)).toBe(false)
    runtime.time = 0.5
    expect(expression.evaluate(runtime)).toBe(expected)
    runtime.time = 0.9
    expect(expression.evaluate(runtime)).toBe(expected)
    runtime.time = 1
    expect(expression.evaluate(runtime)).toBe(false)
  })

  it.each([undefined, 0])('does not invent a matching duration for %s hours', (duration) => {
    const runtime = createRosterRuntime({
      positions: [],
      beds: [],
      majorMaintenanceStartHours: 0.25,
      majorMaintenanceDurationHours: duration
    })
    for (const operator of ['<', '<=', '==', '!=', '>=', '>']) {
      expect(
        compileBackupExpression(maintenance_trigger(0.5, operator, 6), new Set()).evaluate(runtime)
      ).toBe(false)
    }
    expect(compileBackupExpression(maintenance_trigger(), new Set()).evaluate(runtime)).toBe(true)
  })

  it.each([5, 6, 7])(
    'selects the corresponding backup through the actual controller for %s hours',
    (duration) => {
      const workspace = createDefaultWorkspace()
      workspace.compatibility.backupPlans = ['>=', '<'].map((operator) => ({
        trigger: maintenance_trigger(0.5, operator, 6)
      }))
      const schedule = compileRosterSchedule(workspace, {
        majorMaintenanceStartHours: 1,
        majorMaintenanceDurationHours: duration
      })
      const runtime = createRosterRuntime(compiledScheduleToRuntimeConfig(schedule))
      const controller = createBackupPlanController(schedule, runtime)
      controller.evaluate('END')
      expect(controller.active).toEqual([false, false])
      runtime.time = 0.5
      controller.evaluate('END')
      expect(controller.active).toEqual(duration >= 6 ? [true, false] : [false, true])
      runtime.time = 1
      controller.evaluate('END')
      expect(controller.active).toEqual([false, false])
    }
  )

  it.each([-1, Infinity, NaN])('rejects illegal simulation durations %s', (duration) => {
    const schedule = compileRosterSchedule(createDefaultWorkspace(), {
      majorMaintenanceDurationHours: duration
    })
    expect(
      schedule.diagnostics.some(
        (diagnostic) =>
          diagnostic.path === 'assumptions.majorMaintenanceDurationHours' &&
          diagnostic.severity === 'error'
      )
    ).toBe(true)
  })
})
