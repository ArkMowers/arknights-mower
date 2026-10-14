// Mower alpha ab0a4e5 resting_correction.preserve_backup_replacements (MIT).
import {isTradeRunOrderOperator} from '../domain/shiftRunPolicy'
import {mowerMatchReplacements} from './mowerAlphaDorm'
import {mowerReplacementCandidates} from './mowerOperatorState'
import {mowerRestingBindingGroups, mowerSameGroupPrimaryReplacement, mowerSharedReplacements} from './mowerSharedGroups'
import type {MowerSchedulingData, MowerDormState} from './mowerSchedulingData'
import type {MowerTaskPlan} from './mowerTaskQueue'

/** Preserve off-duty primaries while replacing their covers; commit only a complete matching. */
export function preserveMowerBackupReplacements(data: MowerSchedulingData, plan: MowerTaskPlan, positions: [string, number][], previousDorms: MowerDormState[]): boolean {
  const requested = (room: string, index: number) => plan[room]?.[index] ?? 'Current'
  const owners = new Map(positions.filter(([room, index]) => requested(room, index) === 'Current').map(position => [data.plan[position[0]]![position[1]]!, position]))
  const assigned = new Set(Object.values(plan).flat().filter(name => !['', 'Current', 'Free'].includes(name)))
  const reserved = new Set([...assigned, ...data.reservedProductReplacements])
  const key = (room: string, index: number) => `${room}_${index}`
  const beds = new Map(previousDorms.filter(bed => bed.name).map(bed => [key(...bed.position), bed.name]))
  const movable = new Set(Object.entries(plan).flatMap(([room, row]) => row.flatMap((name, index) => name !== 'Current' && data.currentOperator(room, index)?.name !== name ? [key(room, index)] : [])))
  const options: Record<string, string[]> = {}, changes: [string, number, string][] = []
  for (const [name, [room, index]] of owners) {
    const owner = data.operators[name]!, actual = data.currentOperator(room, index)
    if (actual?.name === name) continue
    if (data.reservedProductBeds.has(key(room, index))) {
      if (actual && owner.replacement.includes(actual.name)) { reserved.add(actual.name); continue }
      return false
    }
    if (room.startsWith('dorm') && owner.group && owner.replacement.includes('Free')) {
      if (!actual) changes.push([room, index, 'Free'])
      continue
    }
    options[name] = []
    movable.add(key(room, index))
  }
  for (const name of Object.keys(options)) {
    const owner = data.operators[name]!, position = owners.get(name)!, actual = data.currentOperator(...position)
    const candidates = owner.multiGroup ? mowerSharedReplacements(owner, mowerRestingBindingGroups(data, owner)).filter(n => n !== 'Free') : mowerReplacementCandidates(owner, data.operators, data.policy, data.nowMicros)
    if (actual && candidates.includes(actual.name)) candidates.unshift(...candidates.splice(candidates.indexOf(actual.name), 1))
    for (const candidate of candidates) {
      const cover = data.operators[candidate]
      if (!cover) continue
      if (cover.currentRoom === position[0] && cover.currentIndex === position[1] && !assigned.has(candidate)) { options[name]!.push(candidate); continue }
      if (reserved.has(candidate) || owners.has(candidate) || isTradeRunOrderOperator(candidate) || data.excludedCandidates.has(candidate) || data.busyRestingNames.has(candidate)
        || cover.isHigh() && (!mowerSameGroupPrimaryReplacement(data, owner, candidate) || cover.currentRoom === cover.room && cover.currentIndex === cover.index)
        || data.replacementExhausted(candidate) || cover.restInFull && cover.isResting() && cover.currentMood(data.nowMicros) < cover.upperLimit) continue
      if (!movable.has(key(cover.currentRoom, cover.currentIndex)) && (data.dormReplacementForSlot(candidate, cover.currentRoom, cover.currentIndex) || cover.currentRoom && !cover.isResting())) continue
      if (beds.has(key(...position)) && beds.get(key(...position)) !== candidate) continue
      options[name]!.push(candidate)
    }
  }
  // Seed with the maximum cover matching before allowing a primary to return.
  const matching = mowerMatchReplacements(options, true)!, coverOwners = new Map(Object.entries(matching).map(([name, cover]) => [cover, name]))
  for (const name of Object.keys(options)) {
    const owner = data.operators[name]!, position = owners.get(name)!
    if (!reserved.has(name) && !data.busyRestingNames.has(name) && !(owner.multiGroup && mowerRestingBindingGroups(data, owner).length)
      && !data.reservedProductBeds.has(key(owner.currentRoom, owner.currentIndex)) && (!owner.currentRoom || owner.isResting()) && !beds.has(key(...position))) options[name]!.push(name)
  }
  const reserve = (name: string, seen: Set<string>): boolean => {
    for (const cover of options[name]!) if (!coverOwners.has(cover)) { coverOwners.set(cover, name); return true }
    for (const cover of options[name]!) { if (seen.has(cover)) continue; seen.add(cover); if (reserve(coverOwners.get(cover)!, seen)) { coverOwners.set(cover, name); return true } }
    return false
  }
  for (const name of Object.keys(options)) if (![...coverOwners.values()].includes(name) && !reserve(name, new Set())) return false
  for (const [cover, name] of coverOwners) changes.push([...owners.get(name)!, cover])
  for (const [room, index, name] of changes) if (data.currentOperator(room, index)?.name !== name) (plan[room] ??= Array(data.plan[room]!.length).fill('Current'))[index] = name
  return true
}
