import { expect, it, vi } from 'vitest'
import { incomeHasTailor } from './incomeTailor'
import { defaultIncomeSettings, incomeRequest } from './income'
import { calculateIncome } from './incomeWorker'
import { createIncomeSession } from './incomeSession'

const plan = () => ({
  default: 'plan1',
  conf: {},
  backup_plans: [],
  plan1: {
    room_1_1: { name: '贸易站', product: 'lmd', plans: [{ agent: '芬', replacement: [] }] },
    room_1_3: { name: '发电站', plans: [] },
    room_2_3: { name: '发电站', plans: [] }
  }
})
const settings = () => ({
  ...defaultIncomeSettings(),
  operatorMode: 'maximum',
  inventorySource: 'manual',
  finiteInventory: false,
  weightMode: 'custom',
  warmupDays: 0,
  sampleDays: 1
})

it.each(['primary', 'replacement', 'group', 'backup', 'task'])(
  'uses the fixed tailor seed for a trade %s candidate',
  (kind) => {
    const source = plan()
    const slot = source.plan1.room_1_1.plans[0]
    if (kind === 'primary') slot.agent = '柏喙'
    if (kind === 'replacement') slot.replacement = ['卡夫卡']
    if (kind === 'group') slot.group_bindings = [{ group: '组', replacement: ['折光'] }]
    if (kind === 'backup')
      source.backup_plans = [
        {
          name: '裁缝',
          trigger: 'False',
          plan: {
            room_1_1: { plans: [{ agent: '巫恋', replacement: [] }] }
          }
        }
      ]
    if (kind === 'task')
      source.backup_plans = [{ name: '裁缝', trigger: 'False', task: { room_1_1: ['柏喙'] } }]
    const original = structuredClone(source)
    expect(incomeHasTailor(source, settings())).toBe(true)
    expect(incomeRequest(source, settings()).options.simulationOptions.production).toMatchObject({
      expectationMode: false,
      seed: 42
    })
    expect(source).toEqual(original)
  }
)

it('checks unlocked skills and ignores tailor operators outside trade rosters', () => {
  const source = plan()
  source.plan1.room_1_1.plans[0].agent = '贝娜'
  expect(
    incomeHasTailor(source, { ...settings(), operatorMode: 'custom', operatorText: '贝娜,0,1' })
  ).toBe(false)
  expect(
    incomeHasTailor(source, { ...settings(), operatorMode: 'custom', operatorText: '贝娜,2,1' })
  ).toBe(true)
  expect(
    incomeHasTailor(source, {
      ...settings(),
      operatorMode: 'cache',
      cachedOperators: [{ operator: '贝娜', elitePhase: 0, level: 1 }]
    })
  ).toBe(false)
  source.plan1.room_1_1.plans[0].agent = '芬'
  source.plan1.factory = { plans: [{ agent: '柏喙', replacement: ['卡夫卡'] }] }
  expect(incomeHasTailor(source, settings())).toBe(false)
})

it('freezes the selected tailor seed and never generates an automatic seed', () => {
  const source = plan()
  source.plan1.room_1_1.plans[0].agent = '柏喙'
  const worker = { postMessage: vi.fn(), terminate: vi.fn() }
  const session = createIncomeSession({ createWorker: () => worker, update: vi.fn() })
  const random = vi.spyOn(crypto, 'getRandomValues')
  try {
    session.start(source, settings())
    expect(worker.postMessage.mock.calls[0][0].settings).toMatchObject({
      expectationMode: false,
      seed: 42
    })
    session.cancel()
    session.start(source, { ...settings(), tailorSeed: 77 })
    expect(worker.postMessage.mock.calls[1][0].settings).toMatchObject({
      expectationMode: false,
      seed: 77
    })
    expect(random).not.toHaveBeenCalled()
  } finally {
    session.dispose()
    random.mockRestore()
  }
})

it('keeps the real Worker calculation on the sampled path for a tailor roster', () => {
  const source = plan()
  source.plan1.room_1_1.plans[0].agent = '柏喙'
  const result = calculateIncome(source, settings())
  expect(result.success, result.error).toBe(true)
  expect(result.simulationReport.production.assumptions).toMatchObject({
    expectationMode: false,
    seed: 42
  })
  expect(
    result.simulationReport.production.events
      .filter((event) => event.type === 'order-completed')
      .every((event) => !event.order.expectationComponents)
  ).toBe(true)
})
