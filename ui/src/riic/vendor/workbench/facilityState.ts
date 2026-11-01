import { MOWER_ROOM_IDS, type MowerFacility, type RosterWorkspace } from '../domain/roster'
import { createDefaultWorkspace } from './defaults'

/** Level zero retains the map position without creating power use or staffing slots. */
export function isFacilityBuilt(facility: MowerFacility | undefined): facility is MowerFacility {
  return !!facility && facility.level > 0
}

export function hasDormKeeper(facility: MowerFacility): boolean {
  return facility.slots.some(slot => slot.occupant.kind === 'operator' &&
    !!slot.occupant.operatorId && !['free', 'current'].includes(slot.occupant.operatorId.toLowerCase()))
}

/** Normalize omitted records only; never infer a room from an empty staffing slot. */
export function normalizeMissingFacilities(workspace: RosterWorkspace): void {
  const defaults = createDefaultWorkspace().mainPlan.facilities
  for (const roomId of MOWER_ROOM_IDS) {
    if (!workspace.mainPlan.facilities[roomId]) {
      workspace.mainPlan.facilities[roomId] = { ...defaults[roomId], level: 0, slots: [] }
    }
  }
}
