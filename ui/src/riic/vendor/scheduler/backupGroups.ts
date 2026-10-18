import type { RosterWorkspace } from '../domain/roster'

export interface BackupGroup { id: string; name: string; trigger: unknown }
export interface BackupSelection { groupId: string; conditions: boolean[] }
export function readBackupGroups(workspace: RosterWorkspace): BackupGroup[] {
  const raw = workspace.compatibility.unrecognizedFields.backup_groups ?? []
  if (!Array.isArray(raw)) throw new Error('副表分组必须为列表')
  const ids = new Set<string>()
  const groups = raw.map(value => {
    if (!value || typeof value !== 'object' || typeof value.id !== 'string' || !value.id || typeof value.name !== 'string' || !value.name || ids.has(value.id)) throw new Error('副表分组名称或标识无效，标识不能重复')
    ids.add(value.id)
    return { id: value.id, name: value.name, trigger: value.trigger }
  })
  if (!ids.has('default')) groups.unshift({ id: 'default', name: '默认分组', trigger: undefined })
  return groups
}
export function selectBackupPlans(
  plans: readonly { groupIds: readonly string[]; backupType: 'global' | 'exclusive' }[],
  eligibleGroups: readonly string[], eligiblePlans: readonly boolean[] | ((index:number)=>boolean),
  currentGroup = 'default', current: readonly boolean[] = [],
): BackupSelection {
  const groupId = eligibleGroups.includes(currentGroup) ? currentGroup : eligibleGroups[0] ?? 'default'
  const conditions = plans.map((plan, index) => plan.groupIds.includes(groupId) && (typeof eligiblePlans === 'function' ? eligiblePlans(index) : !!eligiblePlans[index]))
  const exclusive = plans.flatMap((plan, index) => conditions[index] && plan.backupType === 'exclusive' ? [index] : [])
  const winner = exclusive.find(index => current[index]) ?? exclusive[0]
  exclusive.forEach(index => { conditions[index] = index === winner })
  return { groupId, conditions }
}
