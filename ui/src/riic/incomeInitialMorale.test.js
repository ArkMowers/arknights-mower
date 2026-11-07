import { describe, expect, it } from 'vitest'
import { defaultIncomeSettings, incomeRequest } from './income'
import { compileRosterSchedule } from './vendor/scheduler/compileRosterSchedule'
import { compiledScheduleToRuntimeConfig } from './vendor/scheduler/scheduleAdapter'
import { createRosterRuntime } from './vendor/scheduler/rosterRuntime'
import {
  getMowerSourceRuntime,
  makeMowerSchedulingData
} from './vendor/scheduler/mowerSourceRuntime'
import { resolveOperatorCharId } from './vendor/domain/operatorIdentifiers'
import { createBackupPlanController } from './vendor/scheduler/backupPlans'

describe('income request Fiammetta initial condition', () => {
  it.each(['main', 'backup'])(
    'starts a Fiammetta from %s at sixteen and preserves later mood',
    (where) => {
      const dorm = {
        name: '',
        plans: ['菲亚梅塔', 'Free', 'Free', 'Free', 'Free'].map((agent) => ({
          agent,
          group: '',
          replacement: []
        }))
      }
      const plan = {
        default: 'plan1',
        conf: {},
        plan1: {
          dormitory_1:
            where === 'main'
              ? dorm
              : { ...dorm, plans: dorm.plans.map((slot) => ({ ...slot, agent: 'Free' })) }
        },
        backup_plans:
          where === 'backup'
            ? [{ name: '充能', trigger: 'False', plan: { dormitory_1: dorm } }]
            : []
      }
      const original = structuredClone(plan)
      const request = incomeRequest(plan, {
        ...defaultIncomeSettings(),
        operatorMode: 'maximum',
        inventorySource: 'manual',
        finiteInventory: false,
        weightMode: 'custom'
      })
      const compiled = compileRosterSchedule(
        request.workspace,
        request.options.simulationAssumptions
      )
      const runtime = createRosterRuntime(compiledScheduleToRuntimeConfig(compiled))
      createBackupPlanController(compiled, runtime)
      const source = getMowerSourceRuntime(runtime)
      const fia = resolveOperatorCharId('菲亚梅塔')
      expect(runtime.morale[fia]).toBe(16)
      expect(runtime.initialMorale[fia]).toBe(16)
      runtime.morale[fia] = 19
      makeMowerSchedulingData(runtime, source)
      createBackupPlanController(compiled, runtime)
      expect(runtime.morale[fia]).toBe(19)
      expect(runtime.initialMorale[fia]).toBe(16)
      expect(plan).toEqual(original)
    }
  )
})
