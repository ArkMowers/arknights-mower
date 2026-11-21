import { DRONE_CAPACITY } from '../domain/defaults'

export interface DroneState { capacity: number; initial: number; stock: number; generated: number; overflow: number; consumed: number }
export function createDroneState(initial: number, capacity = DRONE_CAPACITY): DroneState {
  if (!Number.isFinite(initial) || !Number.isFinite(capacity) || initial < 0 || capacity < 0 || initial > capacity) throw new Error('Invalid drone state')
  return { capacity, initial, stock: initial, generated: 0, overflow: 0, consumed: 0 }
}
export function generateDrones(state: DroneState, minutes: number, dronesPerMinute: number): DroneState {
  if (![minutes, dronesPerMinute].every(Number.isFinite) || minutes < 0 || dronesPerMinute < 0) throw new Error('Invalid drone generation')
  const generated = minutes * dronesPerMinute, accepted = Math.min(generated, state.capacity - state.stock)
  return { ...state, stock: state.stock + accepted, generated: state.generated + generated, overflow: state.overflow + generated - accepted }
}
export function spendDrones(state: DroneState, count: number) {
  if (!Number.isInteger(count) || count < 0 || count > state.stock + 1e-8) throw new Error('Invalid drone spend')
  return { state: { ...state, stock: Math.max(0, state.stock - count), consumed: state.consumed + count }, baseMinutes: count * 3 }
}
