import type { RosterWorkspace } from '../domain/roster'

export interface BackupGroup { id: string; name: string; trigger: unknown; exclusive_with: string[] }
export type BackupGroupState = string | readonly string[]
export interface BackupSelection { groupId: BackupGroupState; conditions: boolean[] }
export const selectedGroupIds = (selection: BackupGroupState): readonly string[] => typeof selection === 'string' ? [selection] : selection
export const sameBackupGroups = (left: BackupGroupState, right: BackupGroupState): boolean => {
  const a = selectedGroupIds(left), b = selectedGroupIds(right)
  return a.length === b.length && a.every((id, index) => id === b[index])
}
export function normalizeBackupGroups(raw: unknown): BackupGroup[] {
  if (!Array.isArray(raw)) throw new Error('副表分组必须为列表')
  const ids = new Set<string>()
  for (const value of raw) {
    if (!value || typeof value !== 'object' || typeof value.id !== 'string' || !value.id || typeof value.name !== 'string' || !value.name || ids.has(value.id)) throw new Error('副表分组名称或标识无效，标识不能重复')
    ids.add(value.id)
  }
  const legacy = raw.filter(value => value.id !== 'default' && !Object.hasOwn(value, 'exclusive_with')).map(value => value.id)
  const groups: BackupGroup[] = raw.map(value => {
    const excluded = Object.hasOwn(value, 'exclusive_with') ? value.exclusive_with : legacy.filter(id => value.id !== 'default' && id !== value.id)
    if (!Array.isArray(excluded) || new Set(excluded).size !== excluded.length || !excluded.every(id => typeof id === 'string' && ids.has(id) && id !== value.id) || excluded.length && (value.id === 'default' || excluded.includes('default'))) throw new Error('副表分组的互斥对象无效，不能重复、引用自身或默认分组')
    return { ...value, trigger: Object.hasOwn(value, 'trigger') ? value.trigger : (legacy.includes(value.id) || value.id === 'default' ? {} : {left:'True',operator:'',right:''}), exclusive_with: [...excluded] }
  })
  for (const group of groups) for (const other of groups) if (other.exclusive_with.includes(group.id) && !group.exclusive_with.includes(other.id)) group.exclusive_with.push(other.id)
  if (!ids.has('default')) groups.unshift({ id: 'default', name: '默认分组', trigger: {}, exclusive_with: [] })
  return groups.sort((a, b) => Number(b.id === 'default') - Number(a.id === 'default'))
}
export function readBackupGroups(workspace: RosterWorkspace): BackupGroup[] {
  return normalizeBackupGroups(workspace.compatibility.unrecognizedFields.backup_groups ?? [])
}
export function readBackupMembership(raw: Record<string, unknown>, groups: readonly BackupGroup[]) {
  const groupIds = raw.group_ids ?? ['default']
  const backupType = raw.type ?? 'global'
  if (!Array.isArray(groupIds) || !groupIds.length || new Set(groupIds).size !== groupIds.length || !groupIds.every(id => typeof id === 'string' && groups.some(group => group.id === id)) || typeof backupType !== 'string' || !['global', 'exclusive'].includes(backupType)) throw new Error('副表分组或类型无效')
  return { groupIds: groupIds as string[], backupType: backupType as 'global' | 'exclusive' }
}
export function selectBackupPlans(
  plans: readonly { groupIds: readonly string[]; backupType: 'global' | 'exclusive' }[],
  eligibleGroups: readonly string[], eligiblePlans: readonly boolean[] | ((index: number) => boolean),
  currentGroup: BackupGroupState = 'default', current: readonly boolean[] = [], groups?: readonly BackupGroup[],
): BackupSelection {
  const selected: string[] = []
  // The optional catalog preserves the old helper's single-group interface.
  for (const id of eligibleGroups) {
    const excluded = groups?.find(group => group.id === id)?.exclusive_with ?? selected
    if (!selected.some(other => excluded.includes(other))) selected.push(id)
  }
  if (!selected.length) selected.push('default')
  const conditions = plans.map((plan, index) => plan.groupIds.some(id => selected.includes(id)) && (typeof eligiblePlans === 'function' ? eligiblePlans(index) : !!eligiblePlans[index]))
  const exclusive = plans.flatMap((plan, index) => conditions[index] && plan.backupType === 'exclusive' ? [index] : [])
  const occupied = new Set<string>()
  exclusive.sort((a, b) => Number(!!current[b]) - Number(!!current[a]))
  for (const index of exclusive) {
    const memberships = plans[index]!.groupIds.filter(id => selected.includes(id))
    conditions[index] = !memberships.some(id => occupied.has(id))
    if (conditions[index]) memberships.forEach(id => occupied.add(id))
  }
  return { groupId: selected.length === 1 ? selected[0]! : selected, conditions }
}
