import { RECYCLE_RULES } from '../engine/supportFacilitySkills'

export interface RecycleProduction {
  roomId: 'recycle'
  capacity: number
  completedItems: number
  sampleCompletedItems: number
  collectedItems: number
  pendingItems: number
  remainingBaseHours: number
  blockedHours: number
}

/** Deterministic conversion counts. Random material identities are outside this timer. */
export function createRecycleTimeline(level: number) {
  const phase = RECYCLE_RULES.phases.find(phase => phase.level === level)
  if (!phase) throw new Error(`Invalid recycle level: ${level}`)
  const duration = RECYCLE_RULES.recycleTimeRequirement / 3600
  const state: RecycleProduction = { roomId: 'recycle', capacity: phase.capacity, completedItems: 0,
    sampleCompletedItems: 0, collectedItems: 0, pendingItems: 0, remainingBaseHours: duration, blockedHours: 0 }
  let openingCompleted = 0
  return {
    advance(hours: number, efficiencyPercent: number): void {
      if (!Number.isFinite(hours) || hours < 0 || !Number.isFinite(efficiencyPercent) || efficiencyPercent < 0) throw new Error('Invalid recycle work interval')
      let remainingHours = hours
      const speed = efficiencyPercent / 100
      while (remainingHours > 1e-10) {
        if (state.pendingItems >= state.capacity) { state.blockedHours += remainingHours; break }
        if (speed === 0) break
        const step = Math.min(remainingHours, state.remainingBaseHours / speed)
        state.remainingBaseHours -= step * speed
        remainingHours -= step
        if (state.remainingBaseHours <= 1e-8) {
          state.completedItems++
          state.pendingItems++
          state.remainingBaseHours = duration
        }
      }
    },
    nextEventHours(efficiencyPercent: number): number {
      return state.pendingItems >= state.capacity || efficiencyPercent <= 0 ? Infinity : state.remainingBaseHours / (efficiencyPercent / 100)
    },
    collect(): number {
      const count = state.pendingItems
      state.collectedItems += count
      state.pendingItems = 0
      return count
    },
    markObservation(): void { openingCompleted = state.completedItems },
    report(): RecycleProduction { return { ...state, sampleCompletedItems: state.completedItems - openingCompleted } },
  }
}
