import type { MowerFacility, MowerRoomId, RosterWorkspace } from './roster'

// Mower alpha ab0a4e5 utils.plan.RIGHT_SIDE_ROOM_CAPACITY and Operators.merge_plan.
export const MOWER_RIGHT_SIDE_CAPACITY: Readonly<Partial<Record<MowerRoomId, number>>> = {
  meeting: 2, factory: 1, contact: 1, train: 2, recycle: 2,
}

/** Right-side backups can introduce positions absent from the main plan. */
export function mowerBackupRoomCapacity(workspace: RosterWorkspace, roomId: string): number {
  const facility = workspace.mainPlan.facilities[roomId as MowerRoomId]
  if (!facility) throw new Error(`未知副表房间：${roomId}`)
  const capacity = MOWER_RIGHT_SIDE_CAPACITY[roomId as MowerRoomId]
  if (capacity !== undefined) return capacity
  if (facility.level === 0) throw new Error(`副表房间不在主表设施中：${roomId}`)
  return facility.slots.length
}

/** Mutates only an effective-plan copy; the imported main plan remains unchanged. */
export function prepareMowerBackupRoom(workspace: RosterWorkspace, roomId: string, count: number): MowerFacility {
  if (count > mowerBackupRoomCapacity(workspace, roomId)) throw new Error(`副表岗位数量超出设施容量：${roomId}`)
  const facility = workspace.mainPlan.facilities[roomId as MowerRoomId]
  if (count && MOWER_RIGHT_SIDE_CAPACITY[roomId as MowerRoomId] !== undefined) {
    // Native documents omit right-side levels; use the existing built-room assumption.
    if (facility.level === 0) facility.level = 3
    while (facility.slots.length < count) facility.slots.push({occupant: {kind: 'current'}, groupId: null, replacements: []})
  }
  return facility
}

/** A new Current slot has no main-plan owner, unless an earlier overlay supplied one. */
export function assertMowerBackupRoomOwners(base: RosterWorkspace, effective: RosterWorkspace): void {
  for (const roomId of Object.keys(MOWER_RIGHT_SIDE_CAPACITY) as MowerRoomId[]) {
    const originalCount = base.mainPlan.facilities[roomId]?.slots.length ?? 0
    if (effective.mainPlan.facilities[roomId]?.slots.slice(originalCount).some(slot => slot.occupant.kind === 'current')) {
      throw new Error(`副表新增岗位不能使用 Current：${roomId}`)
    }
  }
}

/** Tasks use established effective positions; a task alone cannot create a room. */
export function assertMowerBackupTaskRooms(effective: RosterWorkspace, task: Record<string, readonly string[]>): void {
  for (const [roomId, targets] of Object.entries(task)) {
    if (!targets.length) continue
    const facility = effective.mainPlan.facilities[roomId as MowerRoomId]
    if (!facility || facility.level === 0 || targets.length > facility.slots.length) {
      throw new Error(`副表任务缺少有效排班岗位：${roomId}`)
    }
  }
}
