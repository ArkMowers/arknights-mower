import type { RosterWorkspace } from './roster'

export const DEFAULT_DRONE_CAPACITY = 250

export function isDroneCapacity(value: unknown): value is number {
  return typeof value === 'number' && Number.isSafeInteger(value) && value >= 0
}

/** Local preference wins; v7 preserved resources remain the fallback. */
export function resolveDroneCapacity(workspace: RosterWorkspace, fallback: number = DEFAULT_DRONE_CAPACITY): number {
  if (isDroneCapacity(workspace.droneCapacity)) return workspace.droneCapacity
  const legacy = workspace.compatibility.unrecognizedFields.efficiencyResources
  if (legacy && typeof legacy === 'object' && !Array.isArray(legacy)) {
    const capacity = (legacy as Record<string, unknown>).droneCapacity
    if (isDroneCapacity(capacity)) return capacity
  }
  return isDroneCapacity(fallback) ? fallback : DEFAULT_DRONE_CAPACITY
}
