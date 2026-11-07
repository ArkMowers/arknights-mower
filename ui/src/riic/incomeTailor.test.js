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
  'disables theoretical mode while using the shared random policy for a trade %s candidate',
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
      seed: expect.any(Number)
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

it.each([false, true])(
  'uses the same random and fixed seed choices with a tailor candidate=%s',
  (tailor) => {
    const source = plan()
    if (tailor) source.plan1.room_1_1.plans[0].agent = '柏喙'
    const worker = { postMessage: vi.fn(), terminate: vi.fn() }
    const session = createIncomeSession({ createWorker: () => worker, update: vi.fn() })
    let next = 100
    const random = vi.spyOn(crypto, 'getRandomValues').mockImplementation((array) => {
      array[0] = ++next
      return array
    })
    try {
      const editable = { ...settings(), expectationMode: false }
      for (const seed of [101, 102]) {
        session.start(source, editable)
        const frozen = worker.postMessage.mock.calls.at(-1)[0].settings
        expect(frozen).toMatchObject({ expectationMode: false, seed })
        expect(incomeRequest(source, frozen).options.simulationOptions.production.seed).toBe(seed)
        session.cancel()
      }
      session.start(source, { ...editable, fixedSeed: 77 })
      expect(worker.postMessage.mock.calls.at(-1)[0].settings).toMatchObject({
        expectationMode: false,
        seed: 77
      })
      expect(random).toHaveBeenCalledTimes(2)
      expect(editable).not.toHaveProperty('seed')
    } finally {
      session.dispose()
      random.mockRestore()
    }
  }
)

it('keeps the real Worker calculation on the sampled path for a tailor roster', () => {
  const source = plan()
  source.plan1.room_1_1.plans[0].agent = '柏喙'
  const result = calculateIncome(source, { ...settings(), fixedSeed: 42 })
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
