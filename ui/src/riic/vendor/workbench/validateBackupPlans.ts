import {resolveOperatorCharId} from '../domain/operatorIdentifiers'
import {parseProduct} from '../domain/mowerProducts'
import {assertMowerBackupRoomOwners, assertMowerBackupTaskRooms, mowerBackupRoomCapacity, prepareMowerBackupRoom} from '../domain/mowerBackupFacilities'
import {mergeMowerBackupConfig} from '../scheduler/mowerBackupConfig'
import type {MowerGroupBinding, MowerRoomId, RosterWorkspace} from '../domain/roster'
import type {ValidationIssue, ValidationResult} from './validate'

const record = (value: unknown): value is Record<string, unknown> => !!value && typeof value === 'object' && !Array.isArray(value)

/** Format errors block import; unproven single-backup states are advisory only.
 * The runtime validates the actual combined state before committing activation.
 */
export function validateBackupPlans(workspace: RosterWorkspace, validate: (workspace: RosterWorkspace) => ValidationResult): ValidationIssue[] {
  const issues: ValidationIssue[] = []
  for (const [index, raw] of workspace.compatibility.backupPlans.entries()) {
    const label = record(raw) && typeof raw.name === 'string' ? raw.name : String(index + 1)
    let roomId: MowerRoomId = 'central'
    try {
      if (!record(raw) || raw.plan !== undefined && !record(raw.plan) || raw.conf !== undefined && !record(raw.conf) || raw.task !== undefined && !record(raw.task)) throw new Error('plan/conf/task 格式错误')
      const effective: RosterWorkspace = JSON.parse(JSON.stringify(workspace))
      effective.compatibility.backupPlans = []
      for (const [room, value] of Object.entries(record(raw.plan) ? raw.plan : {})) {
        roomId = room as MowerRoomId
        if (!record(value) || !Array.isArray(value.plans)) throw new Error(`房间或岗位数量无效：${room}`)
        const facility = prepareMowerBackupRoom(effective, room, value.plans.length)
        if (value.product) {
          const product = parseProduct(value.product)
          if (!product) throw new Error(`未知产物：${String(value.product)}`)
          facility.product = product
        }
        const binding = (value: unknown): MowerGroupBinding => {
          if (!record(value) || !Array.isArray(value.replacement ?? []) || (value.replacement as unknown[] | undefined)?.some(name => typeof name !== 'string')) throw new Error('绑组替班必须为干员列表')
          return {groupId: typeof value.group === 'string' ? value.group : null, replacements: (value.replacement as string[] ?? []).map(resolveOperatorCharId)}
        }
        value.plans.forEach((slot, slotIndex) => {
          if (!record(slot) || typeof slot.agent !== 'string') throw new Error('岗位干员格式错误')
          if (slot.agent === 'Current') return
          if (slot.agent === 'Free' && facility.type !== 'dormitory') throw new Error('Free 只能用于宿舍')
          if (slot.group_bindings !== undefined && !Array.isArray(slot.group_bindings)) throw new Error('group_bindings 必须为列表')
          facility.slots[slotIndex] = {...binding(slot), occupant: slot.agent === 'Free' ? {kind: 'free'} : {kind: 'operator', operatorId: resolveOperatorCharId(slot.agent)}, groupBindings: (slot.group_bindings as unknown[] | undefined)?.map(binding)}
        })
      }
      mergeMowerBackupConfig(effective.mainPlan.conf, record(raw.conf) ? raw.conf : {})
      const task: Record<string, string[]> = {}
      for (const [room, targets] of Object.entries(record(raw.task) ? raw.task : {})) {
        roomId = room as MowerRoomId
        if (!Array.isArray(targets) || targets.some(name => typeof name !== 'string') || targets.length > mowerBackupRoomCapacity(workspace, room)) throw new Error(`任务房间或岗位数量无效：${room}`)
        task[room] = targets
      }
      // Independent overlays need not be reachable: two backups can share a
      // trigger and become valid only together. Only one unconditional backup
      // proves that this isolated state can occur without condition analysis.
      const reachable = workspace.compatibility.backupPlans.length === 1 && (raw.trigger === true || typeof raw.trigger === 'string' && raw.trigger.trim() === 'True')
      try { assertMowerBackupRoomOwners(workspace, effective); assertMowerBackupTaskRooms(effective, task) }
      catch (error) {
        issues.push({code: 'INVALID_CONFIG', severity: reachable ? 'critical' : 'warning', roomId,
          message: `副表 ${label}：${error instanceof Error ? error.message : String(error)}`})
      }
      issues.push(...validate(effective).criticalErrors.map(issue => ({...issue,
        severity: reachable ? 'critical' as const : 'warning' as const,
        message: reachable ? `副表 ${label}：${issue.message}` : `副表 ${label} 单独生效时：${issue.message} 实际组合将在切表前校验。`,
      })))
    } catch (error) {
      issues.push({code: 'INVALID_CONFIG', severity: 'critical', roomId, message: `副表 ${label}：${error instanceof Error ? error.message : String(error)}`})
    }
  }
  return issues
}
