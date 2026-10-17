import {parseProduct, serializeProduct} from '../../domain/mowerProducts'
export {parseProduct, serializeProduct} from '../../domain/mowerProducts'
import { resolveOperatorCharId, restoreOperatorMowerName } from '../../domain/operatorIdentifiers'
export { resolveOperatorCharId, restoreOperatorMowerName } from '../../domain/operatorIdentifiers'
import { createDefaultWorkspace } from '../defaults'
import { migrateMowerAlphaDocument } from './mowerAlphaMigration'
import { inferFacilityLevels } from '../levelInference'
import { hasDormKeeper } from '../facilityState'
import {
  MOWER_ROOM_IDS,
  MOWER_OPERATOR_LIST_FIELDS,
  type MowerRoomId,
  type MowerSlot,
  type RosterWorkspace,
} from '../../domain/roster'

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value)
}

const CONF_LIST_FIELDS = MOWER_OPERATOR_LIST_FIELDS

type ConfListField = (typeof CONF_LIST_FIELDS)[number]

function isConfListField(key: string): key is ConfListField {
  return (CONF_LIST_FIELDS as readonly string[]).includes(key)
}

export function importMowerGroupBindings(value: unknown, roomId: string): NonNullable<MowerSlot['groupBindings']> {
  if (!Array.isArray(value)) throw new Error(`Invalid Mower JSON: group_bindings in room "${roomId}" must be an array`)
  return value.map((binding: unknown) => {
    if (!isRecord(binding) || !Array.isArray(binding.replacement ?? [])) throw new Error(`Invalid Mower JSON: Invalid group binding in room "${roomId}"`)
    const metadata = Object.fromEntries(Object.entries(binding).filter(([key]) => key !== 'group' && key !== 'replacement'))
    return {
      groupId: typeof binding.group === 'string' && binding.group ? binding.group : null,
      replacements: (binding.replacement as unknown[] ?? []).filter((name): name is string => typeof name === 'string').map(resolveOperatorCharId),
      ...(Object.keys(metadata).length ? { metadata } : {}),
    }
  })
}

export function importMowerJson(text: string): RosterWorkspace {
  let raw: unknown
  try {
    raw = JSON.parse(text)
  } catch (err) {
    throw new Error(`Invalid Mower JSON: ${err instanceof Error ? err.message : String(err)}`)
  }

  if (!isRecord(raw)) {
    throw new Error('Invalid Mower JSON: Root must be an object')
  }

  const migration = migrateMowerAlphaDocument(raw)
  const parsed = migration.document

  const defaultKey = typeof parsed.default === 'string' && parsed.default.trim()
    ? parsed.default.trim()
    : 'plan1'

  const rawPlan = parsed[defaultKey]
  if (rawPlan === undefined) {
    throw new Error(`Invalid Mower JSON: Main plan "${defaultKey}" not found`)
  }
  if (!isRecord(rawPlan)) {
    throw new Error(`Invalid Mower JSON: Main plan "${defaultKey}" must be an object`)
  }

  const ws = createDefaultWorkspace()
  ws.compatibility.defaultPlanKey = defaultKey
  if (migration.retiredBackupPlans.length) ws.compatibility.retiredBackupPlans = migration.retiredBackupPlans
  if (migration.warnings.length) ws.compatibility.migrationWarnings = migration.warnings
  ws.compatibility.facilityMetadata = {}
  ws.compatibility.unrecognizedRooms = {}

  const knownRoomSet = new Set<string>(MOWER_ROOM_IDS)
  const importedPresentRooms: string[] = []

  for (const [roomIdStr, rawFacility] of Object.entries(rawPlan)) {
    if (!knownRoomSet.has(roomIdStr)) {
      ws.compatibility.unrecognizedRooms[roomIdStr] = rawFacility
      continue
    }

    if (!isRecord(rawFacility)) {
      throw new Error(`Invalid Mower JSON: Room "${roomIdStr}" must be an object`)
    }

    importedPresentRooms.push(roomIdStr)
    const roomId = roomIdStr as MowerRoomId
    const facility = ws.mainPlan.facilities[roomId]

    // Native Mower plans omit right-side levels. As for existing support rooms,
    // assume the maximum built level unless explicit local metadata provides it.
    if (roomId === 'recycle') {
      facility.level = Number.isInteger(rawFacility.level) && Number(rawFacility.level) >= 0 && Number(rawFacility.level) <= 3
        ? Number(rawFacility.level) : 3
    }

    const facilityExtra: Record<string, unknown> = {}
    for (const [k, v] of Object.entries(rawFacility)) {
      if (k !== 'name' && k !== 'plans' && k !== 'product') {
        facilityExtra[k] = v
      }
    }

    if (rawFacility.name === '制造站') facility.type = 'manufacture'
    else if (rawFacility.name === '贸易站') facility.type = 'trading'
    else if (rawFacility.name === '发电站') facility.type = 'power'
    else if (roomId === 'recycle' && rawFacility.name === '回收站') {
      facility.type = 'recycle'
      facilityExtra.rawName = rawFacility.name
    }
    else if (typeof rawFacility.name === 'string' && rawFacility.name) {
      facility.type = ''
      facilityExtra.rawName = rawFacility.name
    }

    const parsedProduct = parseProduct(rawFacility.product)
    if (parsedProduct) {
      facility.product = parsedProduct
      if (rawFacility.product === 'orirock_device') facilityExtra.rawProduct = rawFacility.product
    } else {
      facility.product = undefined
      if (typeof rawFacility.product === 'string' && rawFacility.product) {
        facilityExtra.rawProduct = rawFacility.product
      }
    }

    if (Object.keys(facilityExtra).length > 0) {
      ws.compatibility.facilityMetadata[roomId] = facilityExtra
    }

    if (Array.isArray(rawFacility.plans)) {
      const slots: MowerSlot[] = []

      for (let i = 0; i < rawFacility.plans.length; i++) {
        const rawSlot = rawFacility.plans[i]
        if (!isRecord(rawSlot)) {
          throw new Error(`Invalid Mower JSON: Slot at index ${i} in room "${roomId}" must be an object`)
        }

        const slotExtra: Record<string, unknown> = {}
        for (const [sk, sv] of Object.entries(rawSlot)) {
          if (sk !== 'agent' && sk !== 'group' && sk !== 'replacement' && sk !== 'group_bindings') {
            slotExtra[sk] = sv
          }
        }

        const rawAgent = typeof rawSlot.agent === 'string' ? rawSlot.agent.trim() : ''
        const lowerAgent = rawAgent.toLowerCase()
        let occupant: MowerSlot['occupant'] = { kind: 'empty' }
        if (lowerAgent === 'free') {
          occupant = { kind: 'free' }
        } else if (lowerAgent === 'current') {
          occupant = { kind: 'current' }
        } else if (rawAgent) {
          occupant = { kind: 'operator', operatorId: resolveOperatorCharId(rawAgent) }
        }

        const replacements: string[] = []
        if (Array.isArray(rawSlot.replacement)) {
          for (const item of rawSlot.replacement) {
            if (typeof item === 'string' && item) {
              replacements.push(resolveOperatorCharId(item))
            }
          }
        }

        const slot: MowerSlot = {
          occupant,
          groupId: typeof rawSlot.group === 'string' && rawSlot.group ? rawSlot.group : null,
          replacements,
        }
        if (rawSlot.group_bindings !== undefined) {
          slot.groupBindings = importMowerGroupBindings(rawSlot.group_bindings, roomId)
        }
        if (Object.keys(slotExtra).length > 0) {
          slot.metadata = slotExtra
        }

        slots.push(slot)
      }

      facility.slots = slots
    }
  }

  ws.compatibility.importedPresentRooms = importedPresentRooms

  for (const roomId of MOWER_ROOM_IDS) {
    const facility = ws.mainPlan.facilities[roomId]
    if (!importedPresentRooms.includes(roomId) ||
      (!Object.prototype.hasOwnProperty.call(parsed.facility_levels ?? {}, roomId) && facility.type === 'dormitory' && !hasDormKeeper(facility) &&
        !facility.slots.some(slot => slot.occupant.kind === 'free'))) {
      facility.level = ['meeting', 'factory', 'contact', 'train', 'recycle'].includes(roomId) ? 3 : 0
      facility.slots = []
    }
  }

  // Building levels are shared by the main roster and all backup arrangements.
  if (parsed.facility_levels !== undefined) {
    if (!isRecord(parsed.facility_levels)) throw new Error('设施等级必须为对象')
    for (const [room, level] of Object.entries(parsed.facility_levels)) {
      const maximum = room === 'central' || room.startsWith('dormitory_') ? 5 : 3
      if (!knownRoomSet.has(room) || room.startsWith('gaming_') ||
        !Number.isInteger(level) || Number(level) < 0 || Number(level) > maximum) {
        throw new Error(`设施 ${room} 等级必须为 0–${maximum} 的整数`)
      }
      if (Number(level) > 0 && room.startsWith('room_') &&
        !['制造站', '贸易站', '发电站'].includes(String((rawPlan[room] as Record<string, unknown> | undefined)?.name))) {
        throw new Error(`请先设置 ${room} 的设施类别`)
      }
      ws.mainPlan.facilities[room as MowerRoomId].level = Number(level)
    }
  }

  // Infer unset levels using the actual built-room layout, then restore explicit values.
  inferFacilityLevels(ws.mainPlan.facilities)
  for (const [room, level] of Object.entries(parsed.facility_levels ?? {})) {
    ws.mainPlan.facilities[room as MowerRoomId].level = Number(level)
  }

  // Parse conf
  const hasConf = parsed.conf !== undefined
  ws.compatibility.importedHasConf = hasConf

  if (hasConf) {
    if (!isRecord(parsed.conf)) {
      throw new Error('Invalid Mower JSON: "conf" must be an object')
    }
    const c = parsed.conf
    if (c.ling_xi === 0 || c.ling_xi === 1 || c.ling_xi === 2 || c.ling_xi === 3) {
      ws.mainPlan.conf.ling_xi = c.ling_xi
    } else {
      ws.mainPlan.conf.ling_xi = 1
    }

    for (const key of CONF_LIST_FIELDS) {
      const val = c[key]
      if (val === undefined && ws.mainPlan.conf[key] === undefined) continue
      let items: string[] = []
      if (typeof val === 'string') {
        items = val
          .split(/[,，]/)
          .map((s) => s.trim())
          .filter(Boolean)
      } else if (Array.isArray(val)) {
        items = val
          .filter((item): item is string => typeof item === 'string')
          .map((s) => s.trim())
          .filter(Boolean)
      }
      ws.mainPlan.conf[key] = items.map(resolveOperatorCharId)
    }

    // Preserve unknown/extra conf fields (e.g. free_blacklist)
    for (const [k, v] of Object.entries(c)) {
      if (k !== 'ling_xi' && !isConfListField(k)) {
        ws.mainPlan.conf[k] = v
      }
    }
  }

  // Retain backup_plans
  const hasBackupPlans = parsed.backup_plans !== undefined
  ws.compatibility.importedHasBackupPlans = hasBackupPlans

  if (hasBackupPlans) {
    if (!Array.isArray(parsed.backup_plans)) {
      throw new Error('Invalid Mower JSON: "backup_plans" must be an array')
    }
    ws.compatibility.backupPlans = parsed.backup_plans
  } else {
    ws.compatibility.backupPlans = []
  }

  // Retain other secondary plans and unrecognized top-level fields
  const knownRootKeys = new Set(['default', defaultKey, 'conf', 'backup_plans'])
  for (const [k, v] of Object.entries(parsed)) {
    if (knownRootKeys.has(k)) continue
    if (k.startsWith('plan') && isRecord(v)) {
      ws.compatibility.otherPlans[k] = v
    } else {
      ws.compatibility.unrecognizedFields[k] = v
    }
  }

  return ws
}

/** Older versions retained recycle as an opaque room. Promote it without touching other plans. */
export function promotePreservedRecycleRoom(workspace: RosterWorkspace): void {
  const raw = workspace.compatibility.unrecognizedRooms?.recycle
  if (!isRecord(raw) || workspace.mainPlan.facilities.recycle?.level) return
  let imported: RosterWorkspace
  try {
    imported = importMowerJson(JSON.stringify({ default: 'plan1', plan1: { recycle: raw } }))
  } catch {
    // An old opaque room may be malformed. Retain it for export and inspection;
    // migration must not make the rest of the user's workspace inaccessible.
    return
  }
  workspace.mainPlan.facilities.recycle = imported.mainPlan.facilities.recycle
  const metadata = imported.compatibility.facilityMetadata?.recycle
  if (metadata) (workspace.compatibility.facilityMetadata ??= {}).recycle = metadata
  const present = workspace.compatibility.importedPresentRooms
  if (present && !present.includes('recycle')) present.push('recycle')
  delete workspace.compatibility.unrecognizedRooms!.recycle
}

export function exportMowerJson(workspace: RosterWorkspace): string {
  const planObj: Record<string, unknown> = {}
  const facilities = workspace.mainPlan.facilities
  const roomIdsToExport: MowerRoomId[] = []
  if (workspace.compatibility.importedPresentRooms) {
    const seen = new Set<string>()
    for (const rid of workspace.compatibility.importedPresentRooms) {
      if ((MOWER_ROOM_IDS as readonly string[]).includes(rid) && !seen.has(rid)) {
        seen.add(rid)
        roomIdsToExport.push(rid as MowerRoomId)
      }
    }
  } else {
    for (const rid of MOWER_ROOM_IDS) {
      roomIdsToExport.push(rid)
    }
  }

  for (const roomId of roomIdsToExport) {
    const f = facilities[roomId]
    if (!f || f.level === 0) continue
    const meta = workspace.compatibility.facilityMetadata?.[roomId]
    const extraMeta: Record<string, unknown> = {}
    if (meta) {
      for (const [k, v] of Object.entries(meta)) {
        if (
          k !== 'rawName' &&
          k !== 'rawProduct' &&
          k !== 'name' &&
          k !== 'product' &&
          k !== 'plans'
        ) {
          extraMeta[k] = v
        }
      }
    }

    let name = ''
    if (f.type === 'manufacture') name = '制造站'
    else if (f.type === 'trading') name = '贸易站'
    else if (f.type === 'power') name = '发电站'
    else if (typeof meta?.rawName === 'string' && meta.rawName) name = meta.rawName

    const plans = f.slots.map((slot) => {
      let agent = ''
      if (slot.occupant.kind === 'free') agent = 'Free'
      else if (slot.occupant.kind === 'current') agent = 'Current'
      else if (slot.occupant.kind === 'operator') {
        agent = restoreOperatorMowerName(slot.occupant.operatorId)
      }

      const replacement = slot.replacements.map(restoreOperatorMowerName)

      const slotObj: Record<string, unknown> = {
        ...(slot.metadata ?? {}),
        agent,
        group: slot.groupId || '',
        replacement,
      }
      if (slot.groupBindings !== undefined) slotObj.group_bindings = slot.groupBindings.map(binding => ({
        ...(binding.metadata ?? {}), group: binding.groupId || '', replacement: binding.replacements.map(restoreOperatorMowerName),
      }))
      return slotObj
    })

    const facilityData: Record<string, unknown> = {
      name,
      plans,
      ...extraMeta,
    }

    let exportedProduct: string | undefined
    if (f.type !== 'power') {
      const serialized = serializeProduct(f.type, f.product)
      if (f.product === 'fragment' && meta?.rawProduct === 'orirock_device') {
        exportedProduct = 'orirock_device'
      } else if (serialized !== undefined) {
        exportedProduct = serialized
      } else if (f.product === undefined && typeof meta?.rawProduct === 'string' && meta.rawProduct) {
        exportedProduct = meta.rawProduct
      } else if (f.type === 'manufacture') {
        exportedProduct = 'gold'
      } else if (f.type === 'trading') {
        exportedProduct = 'lmd'
      }
    }

    if (exportedProduct !== undefined) {
      facilityData.product = exportedProduct
    }

    planObj[roomId] = facilityData
  }

  // Include any unrecognized rooms preserved from import
  if (workspace.compatibility.unrecognizedRooms) {
    for (const [uRoomId, uRoomData] of Object.entries(workspace.compatibility.unrecognizedRooms)) {
      if (uRoomId === 'recycle' && planObj.recycle !== undefined) continue
      planObj[uRoomId] = uRoomData
    }
  }

  // Serialize conf
  const conf: Record<string, unknown> = {}
  for (const [k, v] of Object.entries(workspace.mainPlan.conf)) {
    if (k !== 'ling_xi' && !isConfListField(k)) {
      conf[k] = v
    }
  }
  conf.ling_xi = workspace.mainPlan.conf.ling_xi
  for (const field of CONF_LIST_FIELDS) {
    const value: unknown = workspace.mainPlan.conf[field]
    if (value === undefined) continue
    // Persisted pre-alpha workspaces retained these newer lists as native CSV.
    const list = Array.isArray(value) ? value.filter((item): item is string => typeof item === 'string')
      : typeof value === 'string' ? value.split(/[,，]/).map(item => item.trim()).filter(Boolean) : []
    conf[field] = list.map(restoreOperatorMowerName).join(',')
  }

  const defaultKey = workspace.compatibility.defaultPlanKey || 'plan1'
  const output: Record<string, unknown> = {
    ...workspace.compatibility.otherPlans,
    ...workspace.compatibility.unrecognizedFields,
    default: defaultKey,
    [defaultKey]: planObj,
  }

  if (workspace.compatibility.importedHasConf !== false) {
    output.conf = conf
  }

  if (workspace.compatibility.importedHasBackupPlans !== false) {
    output.backup_plans = workspace.compatibility.backupPlans || []
  }

  return JSON.stringify(output, null, 2)
}
