import { afterEach, expect, it, vi } from 'vitest'
import { createDefaultWorkspace } from './vendor/workbench/defaults'
import { compileRosterSchedule } from './vendor/scheduler/compileRosterSchedule'
import { simulateSchedule } from './vendor/simulator/scheduleSimulation'
import { resolveOperatorCharId } from './vendor/domain/operatorIdentifiers'
import * as recovery from './vendor/scheduler/mowerDormRecovery'

const id = resolveOperatorCharId
function run(
  moods,
  { names = ['闪灵', '芬', '香草', '翎羽', '菲亚梅塔'], confirmed, ...options } = {}
) {
  const workspace = createDefaultWorkspace()
  workspace.mainPlan.facilities.dormitory_1.level = 5
  workspace.mainPlan.facilities.dormitory_1.slots = names.map((name) => ({
    occupant: { kind: 'operator', operatorId: name },
    groupId: null,
    replacements: []
  }))
  if (confirmed)
    vi.spyOn(recovery, 'mowerConfirmedRecoveryTargets').mockReturnValue(
      new Map([['dormitory_1', new Map([[id('闪灵'), id(confirmed)]])]])
    )
  const schedule = compileRosterSchedule(workspace, {
    operatorMorale: Object.fromEntries(
      Object.entries(moods).map(([name, mood]) => [id(name), mood])
    )
  })
  const report = simulateSchedule(schedule, {
    schedulingModel: 'mower-alpha',
    sampleHours: 0.1,
    maxStepHours: 0.05,
    ...options
  })
  expect(report.success, JSON.stringify(report.diagnostics)).toBe(true)
  return Object.fromEntries(report.operators.map((op) => [op.operatorName, op.finalMorale]))
}
afterEach(() => vi.restoreAllMocks())

it('gives unconfirmed recovery to the lowest-morale eligible resident instead of the first slot', () => {
  const result = run({ 芬: 15, 香草: 5, 翎羽: 10 })
  expect(result.芬).toBeCloseTo(15.4, 7)
  expect(result.香草).toBeCloseTo(5.475, 7)
  expect(result.翎羽).toBeCloseTo(10.4, 7)
})
it('preserves a valid confirmed target even when another resident has lower morale', () => {
  const result = run({ 芬: 15, 香草: 5 }, { confirmed: '芬' })
  expect(result.芬).toBeCloseTo(15.475, 7)
  expect(result.香草).toBeCloseTo(5.4, 7)
})
it.each(['满心情', '已离宿'])(
  'chooses the lowest eligible morale when the confirmed target is %s',
  (kind) => {
    const result = run(
      { 芬: kind === '满心情' ? 24 : 15, 香草: 5, 翎羽: 10 },
      { confirmed: kind === '满心情' ? '芬' : '黑键' }
    )
    expect(result.香草).toBeCloseTo(5.475, 7)
    expect(result.翎羽).toBeCloseTo(10.4, 7)
  }
)
it('excludes the provider and Fiammetta even when their morale is lower', () => {
  const result = run({ 闪灵: 0, 菲亚梅塔: 0, 芬: 20, 香草: 18 })
  expect(result.闪灵).toBeCloseTo(0.4, 7)
  expect(result.菲亚梅塔).toBeCloseTo(16.2, 7)
  expect(result.香草).toBeCloseTo(18.475, 7)
})
it('uses slot order only to break an equal-morale tie', () => {
  const result = run({ 芬: 5, 香草: 5 })
  expect(result.芬).toBeCloseTo(5.475, 7)
  expect(result.香草).toBeCloseTo(5.4, 7)
})

it.each([0.05, 0.25, 1])(
  'keeps the selected automatic target across morale crossings, step=%s',
  (maxStepHours) => {
    const result = run({ 芬: 5.01, 香草: 5 }, { sampleHours: 3, maxStepHours })
    expect(result.芬).toBeCloseTo(17.01, 7)
    expect(result.香草).toBeCloseTo(19.25, 7)
  }
)
it.each([0.05, 0.25, 1])(
  'selects a new lowest-morale target after the automatic target fills, step=%s',
  (maxStepHours) => {
    const result = run({ 芬: 5.01, 香草: 5 }, { sampleHours: 4.2, maxStepHours })
    expect(result.香草).toBe(24)
    expect(result.芬).toBeCloseTo(21.96, 7)
  }
)

it('retains explicit target override precedence over confirmation and automatic selection', () => {
  const result = run(
    { 芬: 15, 香草: 5, 翎羽: 10 },
    {
      confirmed: '芬',
      recoveryTargetByProvider: { [id('闪灵')]: id('翎羽') }
    }
  )
  expect(result.芬).toBeCloseTo(15.4, 7)
  expect(result.香草).toBeCloseTo(5.4, 7)
  expect(result.翎羽).toBeCloseTo(10.475, 7)
})
