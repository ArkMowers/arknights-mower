import { expect, it } from 'vitest'
import { MOWER_INVENTORY_ITEMS, normalizeSimulationInventory } from './simulationInventory'

it('distinguishes the old potential mode from an explicit finite empty inventory', () => {
  expect(normalizeSimulationInventory(undefined)).toBeUndefined()
  expect(normalizeSimulationInventory({})).toEqual({ gold: 0, fragment: 0, orirock: 0, device: 0, lmd: 0, exp: 0 })
  const input = { gold: 0, exp: 12345, orirock: Number.MAX_SAFE_INTEGER }
  expect(normalizeSimulationInventory(input)).toMatchObject(input)
  expect(input).toEqual({ gold: 0, exp: 12345, orirock: Number.MAX_SAFE_INTEGER })
  expect(MOWER_INVENTORY_ITEMS.map(item => item.name)).toEqual(['赤金', '源石碎片', '固源岩', '装置', '龙门币', '全部经验（计算）'])
})

it.each([-1, .5, NaN, Infinity, Number.MAX_SAFE_INTEGER + 1, '2', null, undefined])('rejects invalid explicitly supplied quantities: %s', gold => {
  expect(() => normalizeSimulationInventory({ gold })).toThrow('赤金初始库存')
})

it.each([null, [], 0, '0', { unknown: 0 }, { drone: 200 }])('rejects non-inventory values and unsupported resources: %s', value => {
  expect(() => normalizeSimulationInventory(value)).toThrow()
})
