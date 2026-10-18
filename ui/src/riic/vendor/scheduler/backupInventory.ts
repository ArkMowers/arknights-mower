import type { RosterWorkspace } from '../domain/roster'
import { compileBackupExpression } from './backupExpression'

/** Invalid expressions remain the compiler's error; quoted text is not an inventory query. */
export function workspaceUsesInventoryConditions(workspace: RosterWorkspace): boolean {
  const groups=workspace.compatibility.unrecognizedFields.backup_groups
  return [...workspace.compatibility.backupPlans,...(Array.isArray(groups)?groups.filter(group=>group?.id!=='default'):[])].some(plan => {
    if (!plan || typeof plan !== 'object') return false
    try { return compileBackupExpression((plan as Record<string, unknown>).trigger, new Set()).usesInventory }
    catch { return false }
  })
}
