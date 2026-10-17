/** Mower item names and the finite simulation ledger resources they observe. */
export const MOWER_INVENTORY_ITEMS = [
  { name: '赤金', resource: 'gold', label: '赤金', unit: '个' },
  { name: '源石碎片', resource: 'fragment', label: '源石碎片', unit: '个' },
  { name: '固源岩', resource: 'orirock', label: '固源岩', unit: '个' },
  { name: '装置', resource: 'device', label: '装置', unit: '个' },
  { name: '龙门币', resource: 'lmd', label: '龙门币', unit: '龙门币' },
  { name: '全部经验（计算）', resource: 'exp', label: '全部经验（计算）', unit: '经验值' },
] as const

export type SimulationInventoryResource = typeof MOWER_INVENTORY_ITEMS[number]['resource']
export type SimulationInventory = Partial<Record<SimulationInventoryResource, number>>

/** Undefined preserves potential output; an object, including {}, opens a finite ledger. */
export function normalizeSimulationInventory(value: unknown): Record<SimulationInventoryResource, number> | undefined {
  if (value === undefined) return undefined
  if (value === null || typeof value !== 'object' || Array.isArray(value)) throw new Error('初始库存必须为物品数量对象')
  const input = value as Record<string, unknown>
  for (const key of Object.keys(input)) {
    if (!MOWER_INVENTORY_ITEMS.some(item => item.resource === key)) throw new Error(`不支持的初始库存物品：${key}`)
  }
  return Object.fromEntries(MOWER_INVENTORY_ITEMS.map(item => {
    const amount = Object.prototype.hasOwnProperty.call(input, item.resource) ? input[item.resource] : 0
    if (typeof amount !== 'number' || !Number.isSafeInteger(amount) || amount < 0) throw new Error(`${item.label}初始库存必须为不小于 0 的安全整数`)
    return [item.resource, amount]
  })) as Record<SimulationInventoryResource, number>
}
