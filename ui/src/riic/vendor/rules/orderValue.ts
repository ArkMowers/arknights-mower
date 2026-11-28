/** Report-only gold equivalent of an order's reward above its gold cost. */
export function virtualGoldEquivalent(order: { goldCost: number; lmdReward: number }): number {
  return Math.max(0, order.lmdReward - order.goldCost * 500) / 500
}
