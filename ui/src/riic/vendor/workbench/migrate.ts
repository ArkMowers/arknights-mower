import { importMowerGroupBindings } from './compat/mowerJson'
import { migrateMowerAlphaDocument } from './compat/mowerAlphaMigration'
import { resolveOperatorCharId } from '../domain/operatorIdentifiers'
import type { AppConfig, OutputRoom } from '../domain/types'
import { createDefaultWorkspace } from './defaults'
import {
  MOWER_OUTPUT_ROOM_IDS,
  MOWER_OPERATOR_LIST_FIELDS,
  mowerRoomToOutputRoomId,
  type MowerProduct,
  type MowerSlot,
  type RosterWorkspace,
} from '../domain/roster'

const DORM_ROOM_IDS = [
  'dormitory_1',
  'dormitory_2',
  'dormitory_3',
  'dormitory_4',
] as const

export const COMPAT_OPERATOR_GROUPS_KEY = '__operatorGroupMetadata' as const


function createOperatorSlot(opId: string, config: AppConfig): MowerSlot {
  const group = config.operatorGroups?.find((g) => g.operatorIds.includes(opId))
  const backup = config.operatorBackups?.[opId]
  return {
    occupant: { kind: 'operator', operatorId: opId },
    groupId: group ? group.id : null,
    replacements: backup ? [backup] : [],
  }
}

function mapProduct(legacyRoom: OutputRoom): MowerProduct | undefined {
  if (legacyRoom.type === 'manufacture') {
    if (legacyRoom.product === 'exp') return 'exp'
    if (legacyRoom.product === 'fragment') return 'fragment'
    return 'gold'
  }
  if (legacyRoom.type === 'trading') {
    if (legacyRoom.strategy === 'orundum') return 'orundum'
    return 'money'
  }
  return undefined
}

export function migrateAppConfigToWorkspace(config: AppConfig): RosterWorkspace {
  const ws = createDefaultWorkspace()
  const facilities = ws.mainPlan.facilities

  if (config.planName !== undefined && config.planName !== null) {
    ws.name = config.planName
    ws.mainPlan.name = config.planName
  }
  ws.mainPlan.conf.workaholic = [...(config.workaholicOperatorIds ?? [])]

  // 1. Map 9 output rooms (B101..B303)
  const hasStableRoomIds = config.rooms.some(room => /^B[123]0[123]$/.test(room.id))
  for (let i = 0; i < 9; i++) {
    const roomId = MOWER_OUTPUT_ROOM_IDS[i]
    if (!roomId) continue
    const legacyRoom = hasStableRoomIds ? config.rooms.find(room => room.id === mowerRoomToOutputRoomId(roomId)) : config.rooms[i]
    if (!legacyRoom) {
      facilities[roomId].level = 0
      facilities[roomId].slots = []
      continue
    }

    const facility = facilities[roomId]
    facility.type = legacyRoom.type
    facility.level = legacyRoom.level
    facility.product = mapProduct(legacyRoom)
    facility.slots = legacyRoom.operatorIds.map((opId) => createOperatorSlot(opId, config))
  }

  // 2. Central (control)
  facilities.central.level = config.facilities.central ?? 5
  if (config.controlOperatorIds) {
    facilities.central.slots = config.controlOperatorIds.map((opId) =>
      createOperatorSlot(opId, config),
    )
  }

  // 3. Four dormitories
  for (let i = 0; i < 4; i++) {
    const dormId = DORM_ROOM_IDS[i]
    if (!dormId) continue

    const dormLevel = config.facilities?.dormitories?.[i]
    facilities[dormId].level = dormLevel ?? 0

    const dormOperators = config.facilityOperatorIds?.dormitories?.[i]
    if (dormOperators) {
      facilities[dormId].slots = dormOperators.map((opId) =>
        createOperatorSlot(opId, config),
      )
    }
  }

  // 4. Functional facilities: reception (meeting), workshop (factory), office (contact), training (train)
  if (config.facilities?.reception !== undefined) {
    facilities.meeting.level = config.facilities.reception
  }
  if (config.facilityOperatorIds?.reception) {
    facilities.meeting.slots = config.facilityOperatorIds.reception.map((opId) =>
      createOperatorSlot(opId, config),
    )
  }

  if (config.facilities?.workshop !== undefined) {
    facilities.factory.level = config.facilities.workshop
  }
  if (config.facilityOperatorIds?.workshop) {
    facilities.factory.slots = config.facilityOperatorIds.workshop.map((opId) =>
      createOperatorSlot(opId, config),
    )
  }

  if (config.facilities?.office !== undefined) {
    facilities.contact.level = config.facilities.office
  }
  if (config.facilityOperatorIds?.office) {
    facilities.contact.slots = config.facilityOperatorIds.office.map((opId) =>
      createOperatorSlot(opId, config),
    )
  }

  if (config.facilities?.training !== undefined) {
    facilities.train.level = config.facilities.training
  }
  if (config.facilityOperatorIds?.training) {
    facilities.train.slots = config.facilityOperatorIds.training.map((opId) =>
      createOperatorSlot(opId, config),
    )
  }

  if (config.facilities?.recycle !== undefined) {
    facilities.recycle.level = config.facilities.recycle
    facilities.recycle.slots = (config.facilityOperatorIds?.recycle ?? []).map(opId => createOperatorSlot(opId, config))
  }

  // 5. Initial morale and extra simulation fields preserved in compatibility envelope
  for (const facility of Object.values(facilities)) {
    if (facility.level === 0) facility.slots = []
  }
  ws.compatibility.sourceVersion = '7'
  if (Array.isArray(config.operatorGroups) && config.operatorGroups.length > 0) {
    ws.compatibility.unrecognizedFields[COMPAT_OPERATOR_GROUPS_KEY] = structuredClone(
      config.operatorGroups,
    )
  }
  if (config.operatorMorale && Object.keys(config.operatorMorale).length > 0) {
    ws.compatibility.unrecognizedFields.operatorMorale = structuredClone(config.operatorMorale)
  }
  if (config.zeroMoraleOperatorIds && config.zeroMoraleOperatorIds.length > 0) {
    ws.compatibility.unrecognizedFields.zeroMoraleOperatorIds = structuredClone(config.zeroMoraleOperatorIds)
  }
  if (typeof config.hours === 'number') {
    ws.compatibility.unrecognizedFields.hours = config.hours
  }
  if (typeof config.dormitoryOccupantCount === 'number') {
    ws.compatibility.unrecognizedFields.dormitoryOccupantCount = config.dormitoryOccupantCount
  }
  if (typeof config.droneTarget === 'string') {
    ws.compatibility.unrecognizedFields.droneTarget = config.droneTarget
  }
  if (config.efficiencyResources) {
    ws.compatibility.unrecognizedFields.efficiencyResources = structuredClone(config.efficiencyResources)
  }

  return ws
}

/** Promote pre-alpha opaque fields without rebuilding user-edited facility levels. */
export function promoteMowerAlphaWorkspace(workspace: RosterWorkspace): void {
  const migration = migrateMowerAlphaDocument(JSON.parse(JSON.stringify({
    conf: workspace.mainPlan.conf,
    backup_plans: workspace.compatibility.backupPlans,
    advanced_settings: workspace.compatibility.unrecognizedFields.advanced_settings,
  })))
  Object.assign(workspace.mainPlan.conf, migration.document.conf)
  workspace.compatibility.backupPlans = migration.document.backup_plans as unknown[]
  if (migration.document.advanced_settings !== undefined) workspace.compatibility.unrecognizedFields.advanced_settings = migration.document.advanced_settings
  if (migration.retiredBackupPlans.length) workspace.compatibility.retiredBackupPlans = [...(workspace.compatibility.retiredBackupPlans ?? []), ...migration.retiredBackupPlans]
  const warnings = [...(workspace.compatibility.migrationWarnings ?? []), ...migration.warnings]
  for (const key of MOWER_OPERATOR_LIST_FIELDS) {
    const value: unknown = workspace.mainPlan.conf[key]
    if (typeof value === 'string') workspace.mainPlan.conf[key] = value.split(/[,，]/).map(item => item.trim()).filter(Boolean).map(resolveOperatorCharId)
  }
  for (const facility of Object.values(workspace.mainPlan.facilities)) {
    if (facility.product === undefined && workspace.compatibility.facilityMetadata?.[facility.roomId]?.rawProduct === 'orirock_device') facility.product = 'fragment'
    for (const slot of facility.slots) {
      if (slot.groupBindings !== undefined || slot.metadata?.group_bindings === undefined) continue
      try {
        slot.groupBindings = importMowerGroupBindings(slot.metadata.group_bindings, facility.roomId)
        delete slot.metadata.group_bindings
        if (!Object.keys(slot.metadata).length) delete slot.metadata
      } catch {
        warnings.push(`${facility.roomId} 的旧分组数据格式无效，已保留原始内容`)
      }
    }
  }
  if (warnings.length) workspace.compatibility.migrationWarnings = [...new Set(warnings)]
}
