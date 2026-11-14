import { expect, it } from 'vitest'
import plan from './fixtures/income-no-training-plan.json'
import { defaultIncomeSettings } from './income'
import { calculateIncome } from './incomeWorker'
import { compileBackupExpression } from './vendor/scheduler/backupExpression'

it.each([
  ["op_data.facility_has_crafting_plan('factory') == True", false],
  ["op_data.facility_has_crafting_plan('factory') == False", true],
  ["not op_data.facility_has_crafting_plan('factory')", true],
  ["op_data.facility_has_crafting_plan('factory') or True", true],
  ["op_data.facility_has_crafting_plan('factory') and True", false]
])('keeps the no-crafting simulation assumption in %s', (source, expected) => {
  const compiled = compileBackupExpression(source, new Set())
  expect(compiled.usesCraftingPlan).toBe(true)
  expect(compiled.evaluate({})).toBe(expected)
})

it('calculates the imported no-training schedule and retains its training-room staffing', () => {
  const original = structuredClone(plan)
  const result = calculateIncome(plan, {
    ...defaultIncomeSettings(),
    operatorMode: 'maximum',
    inventorySource: 'manual',
    weightMode: 'custom',
    warmupDays: 0,
    sampleDays: 1
  })
  expect(result.success, result.error).toBe(true)
  expect(result.observedHours).toBeCloseTo(24, 8)
  expect(
    result.eventLog.entries.some(
      (event) => event.type === '副表切换' && event.detail === '无训练计划（启用）'
    )
  ).toBe(true)
  for (const name of ['桃金娘', '褐果']) {
    const operator = result.timelineData.operatorTracks.find((row) => row.operatorName === name)
    expect(operator.intervals.some((interval) => interval.roomId === 'train')).toBe(true)
  }
  expect(
    result.diagnostics.find((item) => item.code === 'MOWER_MASTERY_PLAN_ASSUMPTION')?.message
  ).toContain('且未在训练')
  expect(plan).toEqual(original)
}, 30000)

it.each([
  "op_data.facility_has_crafting_plan('train')",
  "op_data.facility_has_crafting_plan('room_1_1')",
  'op_data.facility_has_crafting_plan()',
  'op_data.facility_has_crafting_plan(1)',
  "op_data.facility_has_crafting_plan('factory', 'factory')",
  "op_data.facility_is_protected('room_1_1')",
  'op_data.facility_is_protected()',
  'op_data.facility_is_protected(1)',
  "op_data.facility_is_protected('train', 'train')",
  "op_data.facility_is_protected('train').constructor",
  "op_data.facility_is_protected('train')()",
  "op_data.facility_is_training('room_1_1')",
  "op_data.facility_is_training('dormitory_1')",
  'op_data.facility_is_training()',
  'op_data.facility_is_training(1)',
  "op_data.facility_is_training('train', 'train')",
  "op_data.facility_is_training('train').constructor",
  "op_data.facility_is_training('train')()"
])('rejects invalid training query %s', (source) => {
  expect(() => compileBackupExpression(source, new Set())).toThrow('副表：')
})

it('calculates a backup with no automatic growth crafting and reports the assumption', () => {
  const source = structuredClone(plan)
  const backup = source.backup_plans.find((entry) => entry.name === '无训练计划')
  backup.trigger = {
    left: "op_data.facility_has_crafting_plan('factory')",
    operator: '==',
    right: 'False'
  }
  const result = calculateIncome(source, {
    ...defaultIncomeSettings(),
    operatorMode: 'maximum',
    inventorySource: 'manual',
    weightMode: 'custom',
    warmupDays: 0,
    sampleDays: 1
  })
  expect(result.success, result.error).toBe(true)
  expect(
    result.eventLog.entries.some(
      (event) => event.type === '副表切换' && event.detail === '无训练计划（启用）'
    )
  ).toBe(true)
  expect(
    result.diagnostics.find((item) => item.code === 'MOWER_CRAFTING_PLAN_ASSUMPTION')?.message
  ).toContain('无自动养成合成计划')
}, 30000)

it('calculates idle training staffing with the protection condition', () => {
  const source = structuredClone(plan)
  const backup = source.backup_plans.find((entry) => entry.name === '无训练计划')
  backup.trigger = {
    left: "op_data.facility_is_training('train')",
    operator: '==',
    right: 'False'
  }
  backup.trigger = {
    left: backup.trigger,
    operator: 'and',
    right: {
      left: "op_data.facility_is_protected('train')",
      operator: '==',
      right: 'False'
    }
  }
  const result = calculateIncome(source, {
    ...defaultIncomeSettings(),
    operatorMode: 'maximum',
    inventorySource: 'manual',
    weightMode: 'custom',
    warmupDays: 0,
    sampleDays: 1
  })
  expect(result.success, result.error).toBe(true)
  expect(
    result.eventLog.entries.some(
      (event) => event.type === '副表切换' && event.detail === '无训练计划（启用）'
    )
  ).toBe(true)
  expect(
    result.diagnostics.find((item) => item.code === 'MOWER_MASTERY_PLAN_ASSUMPTION')?.message
  ).toContain('训练室不受保护')
}, 30000)
