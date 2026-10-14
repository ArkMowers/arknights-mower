import { captureOrder, type BaseOrderChoice, type OrderSnapshot, type SpecialCapture } from '../rules/orderRules'

export interface ActiveOrder { id: string; startedAt: number; base: BaseOrderChoice; remainingBaseMinutes: number }
export function startOrder(input: { id: string; startedAt: number; base: BaseOrderChoice }): ActiveOrder {
  if (!input.id || !Number.isFinite(input.startedAt) || input.startedAt < 0) throw new Error('Invalid order start')
  return { ...structuredClone(input), remainingBaseMinutes: input.base.baseMinutes }
}
export function advanceOrder(order: ActiveOrder, input: { elapsedMinutes: number; efficiency: number; droneBaseMinutes?: number }) {
  const { elapsedMinutes, efficiency } = input
  const drone = input.droneBaseMinutes ?? 0
  if (![elapsedMinutes, efficiency, drone].every(Number.isFinite) || elapsedMinutes < 0 || efficiency < 0 || drone < 0) throw new Error('Invalid order progress')
  if (order.base.mode === 'pepe' && drone > 0) throw new Error('Pepe drone interaction is unverified')
  const effectiveEfficiency = order.base.efficiencyAffected ? efficiency : 1
  const natural = elapsedMinutes * effectiveEfficiency
  const remainingAfterNatural = Math.max(0, order.remainingBaseMinutes - natural)
  const usedDrone = Math.min(remainingAfterNatural, drone)
  const next = { ...structuredClone(order), remainingBaseMinutes: remainingAfterNatural - usedDrone }
  const unusedNaturalWork = Math.max(0, natural - order.remainingBaseMinutes)
  return {
    order: next,
    completed: next.remainingBaseMinutes <= 1e-9,
    unusedMinutes: effectiveEfficiency > 0 ? unusedNaturalWork / effectiveEfficiency : 0,
    unusedDroneBaseMinutes: drone - usedDrone,
  }
}
export function finishOrder(order: ActiveOrder, capture: SpecialCapture, completedAt: number): Readonly<OrderSnapshot & { id: string; startedAt: number }> {
  if (completedAt < order.startedAt) throw new Error('Invalid completion time: before acquisition start')
  if (order.remainingBaseMinutes > 1e-9) throw new Error('Cannot finish unfinished order')
  return Object.freeze({ ...captureOrder(order.base, capture, completedAt), id: order.id, startedAt: order.startedAt })
}
