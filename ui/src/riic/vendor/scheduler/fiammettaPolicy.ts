import { MORALE_EPSILON, type RuntimeState } from './rosterRuntime'
export interface FiammettaPolicy { operatorId: string; orderedTargets: string[]; threshold?: number; fool?: boolean }
export function nextFiammettaSwap(s: RuntimeState): string | undefined {
  const f = s.config.fiammetta
  if (s.config.mowerPolicy && s.nextFiammettaCheckTime !== undefined && s.time < s.nextFiammettaCheckTime - MORALE_EPSILON) {
    const hasExhausted = f?.orderedTargets.some(id => (s.morale[id] ?? 24) <= MORALE_EPSILON)
    if (!hasExhausted) return
  }
  if (!f || (s.morale[f.operatorId] ?? 0) < 24 - MORALE_EPSILON || s.lastFiammettaTime === s.time) return
  const located = s.config.positions.some(p => p.dormitory && s.occupants[p.id] === f.operatorId) || Object.values(s.bedOccupants).includes(f.operatorId)
  if (!located) return
  const eligible = f.orderedTargets.filter(id => {
    if (id === f.operatorId || (s.morale[id] ?? 24) >= 24 - MORALE_EPSILON) return false
    const p = s.config.positions.find(p => p.primary === id)
    if (!p) return false
    if (p.restToFull && p.exhaustRequired && (s.morale[id] ?? 24) > (p.lowerLimit ?? 0) + MORALE_EPSILON && !Object.values(s.bedOccupants).includes(id)) return false
    return !p.group || s.config.positions.filter(other => other.group === p.group && (!other.permanent || f.orderedTargets.includes(other.primary))).every(other => (s.morale[other.primary] ?? 0) - (other.lowerLimit ?? 0) >= (s.morale[id] ?? 0) - (p.lowerLimit ?? 0) - MORALE_EPSILON)
  })
  return eligible.find(id => (s.morale[id] ?? 24) <= (f.threshold ?? 21.6) + MORALE_EPSILON)
    ?? (f.fool === false ? (s.config.mowerPolicy ? f.orderedTargets.filter(id => { const p=s.config.positions.find(p=>p.primary===id); return p && id!==f.operatorId && (s.morale[id] ?? 24)<24-MORALE_EPSILON && !(p.restToFull && p.exhaustRequired && (s.morale[id] ?? 24) > (p.lowerLimit ?? 0) + MORALE_EPSILON && !Object.values(s.bedOccupants).includes(id)) }) : [...eligible]).sort((a, b) => s.morale[a]! - s.morale[b]!)[0] : undefined)
}
export function applyFiammetta(s: RuntimeState): boolean {
  const target = nextFiammettaSwap(s); const f = s.config.fiammetta
  if (!target || !f) {
    if (f && s.config.mowerPolicy && (s.morale[f.operatorId] ?? 0)>=24-MORALE_EPSILON && (s.nextFiammettaCheckTime === undefined || s.time>=s.nextFiammettaCheckTime-MORALE_EPSILON)) s.nextFiammettaCheckTime=s.time+(24-(f.threshold ?? 21.6))/2
    return false
  }
  s.nextFiammettaCheckTime=undefined
  const before = s.morale[target]!
  s.morale[target] = 24; s.morale[f.operatorId] = before; s.lastFiammettaTime = s.time
  s.events.push({ time: s.time, type: 'fiammetta', operators: [f.operatorId, target], moraleBefore: [24, before], moraleAfter: [before, 24] })
  return true
}
