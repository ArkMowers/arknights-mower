import { expect, it } from 'vitest'
import { defaultIncomeSettings } from './income'
import { calculateIncome } from './incomeWorker'
import { createIncomeReview } from './incomeReview'

it('carries actual zero-morale statistics and the configured work rule into review materials', () => {
  const plan = {
    default: 'plan1',
    conf: { workaholic: '杜林' },
    backup_plans: [],
    plan1: {
      room_1_1: { name: '制造站', product: 'gold', plans: [{ agent: '杜林', replacement: [] }] },
      room_1_3: { name: '发电站', plans: [] }
    }
  }
  const settings = {
    ...defaultIncomeSettings(),
    warmupDays: 0,
    sampleDays: 2,
    operatorMode: 'maximum',
    inventorySource: 'manual',
    finiteInventory: false,
    weightMode: 'custom',
    expectationMode: true,
    allowMaterialDebt: false
  }
  const input = { plan, settings }
  const before = structuredClone(input)
  const result = calculateIncome(plan, settings)
  expect(result.success).toBe(true)
  const operator = result.simulationReport.operators.find((row) => row.operatorName === '杜林')
  expect(operator.exhaustedHours).toBeGreaterThan(0)
  expect(operator.restHours).toBe(0)
  expect(operator.workRestRatio).toBeNull()
  expect(operator.workHours + operator.exhaustedHours).toBeCloseTo(48, 6)

  const draft = createIncomeReview({ input, result, savedAt: 1 })
  const text = draft.files.map((file) => file.text).join('\n')
  expect(text).toContain('"workaholic":"杜林"')
  expect(text).toContain('"exhaustedHours":' + operator.exhaustedHours)
  expect(text).toContain('"workRestRatio":null')
  expect(text).toContain(result.modelProvenance.calculatorBaseRevision)
  expect(draft.files.every((file) => file.text.length <= 6000)).toBe(true)
  expect(input).toEqual(before)
})
