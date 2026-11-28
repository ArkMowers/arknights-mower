import { afterEach, expect, it, vi } from 'vitest'
import { defaultIncomeSettings, incomeRequest, incomeSeed } from './income'

const plan = {
  default: 'plan1',
  conf: {},
  backup_plans: [],
  plan1: { room_1_1: { name: '贸易站', product: 'lmd', plans: [{ agent: '芬' }] } }
}
const settings = () => ({
  ...defaultIncomeSettings(),
  operatorMode: 'maximum',
  finiteInventory: false,
  weightMode: 'custom'
})
afterEach(() => vi.restoreAllMocks())

it('defaults to random seeds and keeps the editable fixed seed separate', () => {
  expect(defaultIncomeSettings()).toMatchObject({ fixedSeed: null })
  expect(defaultIncomeSettings()).not.toHaveProperty('seed')
  expect(defaultIncomeSettings()).not.toHaveProperty('tailorSeed')
  const random = vi.spyOn(crypto, 'getRandomValues').mockImplementation((array) => {
    array[0] = 91
    return array
  })
  expect(incomeSeed({})).toBe(91)
  expect(incomeSeed({ fixedSeed: null, tailorSeed: 77 })).toBe(91)
  expect(random).toHaveBeenCalledTimes(2)
})

it('keeps explicit frozen and legacy seeds, including zero, ahead of the editable policy', () => {
  const random = vi.spyOn(crypto, 'getRandomValues')
  for (const seed of [0, 42, 0xffffffff]) {
    expect(incomeSeed({ seed, fixedSeed: 77 })).toBe(seed)
    expect(incomeSeed({ fixedSeed: seed })).toBe(seed)
  }
  expect(incomeSeed({ tailorSeed: 88 })).toBe(88)
  expect(random).not.toHaveBeenCalled()
})

it.each([-1, 0x100000000, 1.5, NaN, '42'])('rejects an invalid selected seed %s', (seed) => {
  expect(() => incomeSeed({ seed })).toThrow('随机种子')
  expect(() => incomeSeed({ fixedSeed: seed })).toThrow('随机种子')
})

it('leaves theoretical requests free of seed generation and retains legacy seeded requests', () => {
  const random = vi.spyOn(crypto, 'getRandomValues')
  const request = incomeRequest(plan, settings())
  expect(request.options.simulationOptions.production.expectationMode).toBe(true)
  expect(request.options.simulationOptions.production).not.toHaveProperty('seed')
  expect(random).not.toHaveBeenCalled()
  const legacy = settings()
  delete legacy.expectationMode
  legacy.seed = 0
  expect(incomeRequest(plan, legacy).options.simulationOptions.production).toMatchObject({
    expectationMode: false,
    seed: 0
  })
  expect(random).not.toHaveBeenCalled()
})
