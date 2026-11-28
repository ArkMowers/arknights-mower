import type { OperatorGroup } from '../domain/types'

export interface IndexedOperatorGroup {
  id: string
  name: string
  memberIds: Set<string>
}

export interface OperatorGroupSchedule {
  groups: IndexedOperatorGroup[]
  groupByOperator: Map<string, IndexedOperatorGroup>
  expandDepartures: (triggerIds: Iterable<string>) => Set<string>
}

/**
 * Turns persisted group definitions into a scheduling index. Invalid members are
 * ignored and the first group wins if malformed saved data contains duplicates.
 */
export function createOperatorGroupSchedule(
  groups: OperatorGroup[],
  assignedIds: Set<string>,
): OperatorGroupSchedule {
  const claimedIds = new Set<string>()
  const indexedGroups: IndexedOperatorGroup[] = []
  const groupByOperator = new Map<string, IndexedOperatorGroup>()

  for (const group of groups) {
    const memberIds = [...new Set(group.operatorIds)]
      .filter((id) => assignedIds.has(id) && !claimedIds.has(id))
    if (memberIds.length < 2) continue

    const indexed = {
      id: group.id,
      name: group.name.trim() || '未命名组合',
      memberIds: new Set(memberIds),
    }
    indexedGroups.push(indexed)
    for (const id of memberIds) {
      claimedIds.add(id)
      groupByOperator.set(id, indexed)
    }
  }

  return {
    groups: indexedGroups,
    groupByOperator,
    expandDepartures(triggerIds) {
      const result = new Set(triggerIds)
      for (const id of [...result]) {
        const group = groupByOperator.get(id)
        if (group) for (const memberId of group.memberIds) result.add(memberId)
      }
      return result
    },
  }
}
