import type {
  AppConfig,
  EfficiencyResources,
  ManufactureProduct,
  OutputRoom,
  TradeStrategy,
} from '../domain/types'
import { EDITION } from '../domain/edition'
import { resolveDroneCapacity } from '../domain/droneCapacity'
import {
  MOWER_OUTPUT_ROOM_IDS,
  MOWER_ROOM_IDS,
  mowerRoomToOutputRoomId,
  type MowerFacility,
  type MowerMainPlan,
  type MowerOutputRoomId,
  type RosterWorkspace,
} from '../domain/roster'
import { COMPAT_OPERATOR_GROUPS_KEY } from './migrate'
import { isRunOrderOperator } from './operatorHelpers'

const DORMITORY_ROOM_IDS = [
  'dormitory_1',
  'dormitory_2',
  'dormitory_3',
  'dormitory_4',
] as const

/**
 * Filter valid operator ID string from an occupant.
 * Free, Current, and Empty occupants return null.
 */
function extractOperatorId(slot: { occupant: { kind: string; operatorId?: string } }): string | null {
  if (slot.occupant.kind === 'operator' && typeof slot.occupant.operatorId === 'string') {
    const trimmed = slot.occupant.operatorId.trim()
    return trimmed.length > 0 ? trimmed : null
  }
  return null
}

function restoreOperatorMorale(
  unrecognizedValue: unknown,
  fallback: Record<string, number>,
): Record<string, number> {
  if (!unrecognizedValue || typeof unrecognizedValue !== 'object') {
    return structuredClone(fallback)
  }
  const result: Record<string, number> = {}
  for (const [k, v] of Object.entries(unrecognizedValue)) {
    if (typeof v === 'number') {
      result[k] = v
    }
  }
  return result
}

function restoreZeroMoraleOperatorIds(
  unrecognizedValue: unknown,
  fallback: string[],
): string[] {
  if (Array.isArray(unrecognizedValue)) {
    return unrecognizedValue.filter((id): id is string => typeof id === 'string')
  }
  return [...fallback]
}

function restoreEfficiencyResources(
  unrecognizedValue: unknown,
  fallback: EfficiencyResources,
): EfficiencyResources {
  if (!unrecognizedValue || typeof unrecognizedValue !== 'object') {
    return structuredClone(fallback)
  }
  const rec = unrecognizedValue as Record<string, unknown>
  return {
    manufacturePerceptionInformation:
      typeof rec.manufacturePerceptionInformation === 'number'
        ? rec.manufacturePerceptionInformation
        : fallback.manufacturePerceptionInformation,
    tradingPerceptionInformation:
      typeof rec.tradingPerceptionInformation === 'number'
        ? rec.tradingPerceptionInformation
        : fallback.tradingPerceptionInformation,
    additionalGoldProductionLines:
      typeof rec.additionalGoldProductionLines === 'number'
        ? rec.additionalGoldProductionLines
        : fallback.additionalGoldProductionLines,
    monsterCuisine:
      typeof rec.monsterCuisine === 'number'
        ? rec.monsterCuisine
        : fallback.monsterCuisine,
    worldlyFireworks:
      typeof rec.worldlyFireworks === 'number'
        ? rec.worldlyFireworks
        : fallback.worldlyFireworks,
    suiFacilities:
      typeof rec.suiFacilities === 'number'
        ? rec.suiFacilities
        : fallback.suiFacilities,
    droneCapacity:
      typeof rec.droneCapacity === 'number'
        ? rec.droneCapacity
        : fallback.droneCapacity,
    extraWorkplaceOperatorIds: Array.isArray(rec.extraWorkplaceOperatorIds)
      ? rec.extraWorkplaceOperatorIds.filter((id): id is string => typeof id === 'string')
      : [...fallback.extraWorkplaceOperatorIds],
    trainingOperatorIds: Array.isArray(rec.trainingOperatorIds)
      ? rec.trainingOperatorIds.filter((id): id is string => typeof id === 'string')
      : [...fallback.trainingOperatorIds],
  }
}


/**
 * Pure compiler: transforms a MowerMainPlan and workspace context into schema-v7 AppConfig.
 * Never mutates mainPlan, baseWorkspace, or existingConfig.
 */
export function compileMainPlanToAppConfig(
  mainPlan: MowerMainPlan,
  baseWorkspace: RosterWorkspace,
  existingConfig: AppConfig,
): AppConfig {
  // Deep clone existingConfig to ensure strict immutability of inputs
  const cloned = structuredClone(existingConfig)
  const hasStableRoomIds = cloned.rooms?.some(room => /^B[123]0[123]$/.test(room.id))

  // 1. Map 9 output rooms deterministically to B101..B303
  const rooms: OutputRoom[] = MOWER_OUTPUT_ROOM_IDS.map((roomId: MowerOutputRoomId, index: number) => {
    const facility: MowerFacility | undefined = mainPlan.facilities[roomId]
    const existingRoom = hasStableRoomIds
      ? cloned.rooms.find(room => room.id === mowerRoomToOutputRoomId(roomId))
      : cloned.rooms?.[index]

    const validOperatorIds: string[] = []
    if (facility?.slots) {
      for (const slot of facility.slots) {
        const opId = extractOperatorId(slot)
        if (opId) {
          validOperatorIds.push(opId)
        }
      }
    }

    const facilityType = facility?.type
    const type =
      facilityType === 'manufacture' || facilityType === 'trading' || facilityType === 'power'
        ? facilityType
        : existingRoom?.type ?? 'manufacture'

    const facilityLevel = facility?.level
    const level =
      facilityLevel !== undefined && facilityLevel >= 1 && facilityLevel <= 3
        ? (facilityLevel as 1 | 2 | 3)
        : (existingRoom?.level ?? 3)

    let product: ManufactureProduct = existingRoom?.product ?? 'gold'
    let strategy: TradeStrategy = existingRoom?.strategy ?? 'gold'

    if (facility?.product === 'gold' || facility?.product === 'exp' || facility?.product === 'fragment') {
      product = facility.product
    }
    if (facility?.product === 'orundum') {
      strategy = 'orundum'
    } else if (facility?.product === 'money') {
      strategy = 'gold'
    }

    return {
      id: mowerRoomToOutputRoomId(roomId),
      type,
      level,
      operatorCount: validOperatorIds.length,
      operatorIds: validOperatorIds,
      skillBonus: existingRoom?.skillBonus ?? 0,
      product,
      strategy,
      quality: existingRoom?.quality ?? 'normal',
      specialOrder:
        type === 'trading' && existingRoom?.type !== 'trading'
          ? EDITION.defaultSpecialOrder
          : existingRoom?.specialOrder ?? (type === 'trading' ? EDITION.defaultSpecialOrder : 'none'),
      powerStaffed: existingRoom?.powerStaffed ?? false,
    }
  })

  // Preserve stable room IDs while excluding absent production facilities.
  for (let index = rooms.length - 1; index >= 0; index--) {
    const facility = mainPlan.facilities[MOWER_OUTPUT_ROOM_IDS[index]!]
    if (!facility || facility.level === 0) rooms.splice(index, 1)
  }

  // 2. Aggregate group labels and project ordered Mower candidates onto the
  // legacy engine's one-to-one backup map. The workspace remains lossless;
  // this projection chooses the first candidate that is neither on duty nor
  // already assigned to another legacy work slot.
  const groupMap = new Map<string, string[]>()
  const backups: Record<string, string> = {}
  const usedBackupIds = new Set<string>()
  const activePrimaryIds = new Set<string>()
  const workaholicOperatorIds = [...new Set(mainPlan.conf.workaholic)]
  const workaholicIds = new Set(workaholicOperatorIds)

  for (const facility of Object.values(mainPlan.facilities)) {
    for (const slot of facility?.slots ?? []) {
      const opId = extractOperatorId(slot)
      if (opId) activePrimaryIds.add(opId)
    }
  }

  const legacyAssignmentRoomIds = new Set<string>([...MOWER_OUTPUT_ROOM_IDS, 'central'])

  const seenRooms = new Set<string>()
  const orderedRoomIds: string[] = [...MOWER_ROOM_IDS]
  for (const rId of Object.keys(mainPlan.facilities)) {
    if (!orderedRoomIds.includes(rId)) {
      orderedRoomIds.push(rId)
    }
  }

  for (const roomId of orderedRoomIds) {
    seenRooms.add(roomId)
    const facility = (mainPlan.facilities as Record<string, MowerFacility | undefined>)[roomId]
    if (!facility?.slots) continue

    for (const slot of facility.slots) {
      const opId = extractOperatorId(slot)
      if (!opId) continue

      // Group label aggregation
      if (slot.groupId && typeof slot.groupId === 'string') {
        const gId = slot.groupId.trim()
        if (gId.length > 0) {
          const list = groupMap.get(gId) ?? []
          if (!list.includes(opId)) {
            list.push(opId)
          }
          groupMap.set(gId, list)
        }
      }

      // Dormitory/right-side replacement metadata (notably Fiammetta's morale
      // swap targets) is intentionally not flattened into operatorBackups.
      if (
        legacyAssignmentRoomIds.has(roomId) &&
        !workaholicIds.has(opId) &&
        slot.replacements &&
        slot.replacements.length > 0
      ) {
        const firstValid = slot.replacements.find(
          (rep) => {
            if (typeof rep !== 'string') return false
            const candidate = rep.trim()
            return candidate.length > 0 &&
              !(facility.type === 'trading' && isRunOrderOperator(candidate)) &&
              !activePrimaryIds.has(candidate) &&
              !usedBackupIds.has(candidate)
          },
        )
        if (firstValid && !(opId in backups)) {
          const backupId = firstValid.trim()
          backups[opId] = backupId
          usedBackupIds.add(backupId)
        }
      }
    }
  }

  const unrecognized = baseWorkspace?.compatibility?.unrecognizedFields ?? {}
  const rawGroupMetadata = unrecognized[COMPAT_OPERATOR_GROUPS_KEY]
  const groupMetadata: Array<{ id: string; name?: string }> = Array.isArray(rawGroupMetadata)
    ? rawGroupMetadata.filter(
        (g): g is { id: string; name?: string } =>
          typeof g === 'object' && g !== null && typeof (g as { id?: unknown }).id === 'string',
      )
    : []

  const operatorGroups = Array.from(groupMap.entries()).map(([id, operatorIds]) => {
    const metaGroup = groupMetadata.find((g) => g.id === id)
    const existingGroup = cloned.operatorGroups?.find((g) => g.id === id)
    return {
      id,
      name: metaGroup?.name ?? existingGroup?.name ?? id,
      operatorIds,
    }
  })

  // 3. Central (control)
  const centralSlots = mainPlan.facilities.central?.level ? mainPlan.facilities.central.slots : []
  const controlOperatorIds = centralSlots
    .map((slot) => extractOperatorId(slot))
    .filter((id): id is string => id !== null)

  // 4. Dormitories (levels and occupants)
  const dormLevels = DORMITORY_ROOM_IDS.map((roomId) => {
    const dorm = mainPlan.facilities[roomId]
    const lvl = dorm?.level
    return (lvl !== undefined && lvl >= 0 && lvl <= 5 ? lvl : 0) as
      | 0
      | 1
      | 2
      | 3
      | 4
      | 5
  })

  const dormOperators: string[][] = DORMITORY_ROOM_IDS.map((roomId) => {
    const dorm = mainPlan.facilities[roomId]
    if (!dorm?.level || !dorm.slots) return []
    return dorm.slots
      .map((slot) => extractOperatorId(slot))
      .filter((id): id is string => id !== null)
  })
  const steadyDormitoryOccupancy = DORMITORY_ROOM_IDS.reduce((sum, roomId) => {
    const dorm = mainPlan.facilities[roomId]
    if (!dorm?.level || !dorm.slots) return sum
    return sum + dorm.slots.filter((slot) => slot.occupant.kind !== 'empty').length
  }, 0)

  // 5. Functional facilities: meeting (reception), factory (workshop), contact (office), train (training)
  const meetingFac = mainPlan.facilities.meeting
  const receptionLevel =
    meetingFac?.level !== undefined && meetingFac.level >= 0 && meetingFac.level <= 3
      ? (meetingFac.level as 0 | 1 | 2 | 3)
      : 0
  const receptionOperators = (receptionLevel ? meetingFac?.slots ?? [] : [])
    .map((slot) => extractOperatorId(slot))
    .filter((id): id is string => id !== null)

  const factoryFac = mainPlan.facilities.factory
  const workshopLevel =
    factoryFac?.level !== undefined && factoryFac.level >= 0 && factoryFac.level <= 3
      ? (factoryFac.level as 0 | 1 | 2 | 3)
      : 0
  const workshopOperators = (workshopLevel ? factoryFac?.slots ?? [] : [])
    .map((slot) => extractOperatorId(slot))
    .filter((id): id is string => id !== null)

  const contactFac = mainPlan.facilities.contact
  const officeLevel =
    contactFac?.level !== undefined && contactFac.level >= 0 && contactFac.level <= 3
      ? (contactFac.level as 0 | 1 | 2 | 3)
      : 0
  const officeOperators = (officeLevel ? contactFac?.slots ?? [] : [])
    .map((slot) => extractOperatorId(slot))
    .filter((id): id is string => id !== null)

  const trainFac = mainPlan.facilities.train
  const trainingLevel =
    trainFac?.level !== undefined && trainFac.level >= 0 && trainFac.level <= 3
      ? (trainFac.level as 0 | 1 | 2 | 3)
      : 0
  const trainingOperators = (trainingLevel ? trainFac?.slots ?? [] : [])
    .map((slot) => extractOperatorId(slot))
    .filter((id): id is string => id !== null)

  // 6. Typed whitelist restoration of simulation fields and planName
  const planName =
    mainPlan.name !== undefined && mainPlan.name !== null
      ? mainPlan.name
      : cloned.planName !== undefined && cloned.planName !== null
        ? cloned.planName
        : '默认排班'

  const hours =
    typeof unrecognized.hours === 'number'
      ? unrecognized.hours
      : cloned.hours

  const dormitoryOccupantCount =
    typeof unrecognized.dormitoryOccupantCount === 'number'
      ? unrecognized.dormitoryOccupantCount
      : cloned.dormitoryOccupantCount > 0
        ? cloned.dormitoryOccupantCount
        : steadyDormitoryOccupancy

  const droneTarget =
    typeof unrecognized.droneTarget === 'string'
      ? unrecognized.droneTarget
      : (cloned.droneTarget ?? 'none')

  const operatorMorale = restoreOperatorMorale(unrecognized.operatorMorale, cloned.operatorMorale ?? {})

  const zeroMoraleOperatorIds = restoreZeroMoraleOperatorIds(
    unrecognized.zeroMoraleOperatorIds,
    cloned.zeroMoraleOperatorIds ?? [],
  )

  const efficiencyResources = restoreEfficiencyResources(
    unrecognized.efficiencyResources,
    cloned.efficiencyResources,
  )
  efficiencyResources.droneCapacity = resolveDroneCapacity(baseWorkspace, efficiencyResources.droneCapacity)

  const result: AppConfig = {
    ...cloned,
    schemaVersion: 7,
    planName,
    hours,
    dormitoryOccupantCount,
    droneTarget,
    operatorMorale,
    zeroMoraleOperatorIds,
    efficiencyResources,
    rooms,
    facilities: {
      ...cloned.facilities,
      central: (mainPlan.facilities.central?.level ?? 0) as 0 | 1 | 2 | 3 | 4 | 5,
      dormitories: dormLevels,
      reception: receptionLevel,
      workshop: workshopLevel,
      office: officeLevel,
      training: trainingLevel,
    },
    facilityOperatorIds: {
      dormitories: dormOperators,
      reception: receptionOperators,
      workshop: workshopOperators,
      office: officeOperators,
      training: trainingOperators,
    },
    controlOperatorIds,
    workaholicOperatorIds,
    operatorBackups: backups,
    operatorGroups,
  }

  if (baseWorkspace.productionWeights) result.productionWeights = { ...baseWorkspace.productionWeights }
  // Retain the legacy default shape for full level-five layouts.
  if (result.facilities.central === 5 && cloned.facilities.central === undefined) delete result.facilities.central
  const recycle = mainPlan.facilities.recycle
  if (recycle?.level) {
    result.facilities.recycle = recycle.level as 1 | 2 | 3
    result.facilityOperatorIds.recycle = recycle.slots.map(extractOperatorId).filter((id): id is string => id !== null)
  } else {
    delete result.facilities.recycle
    delete result.facilityOperatorIds.recycle
  }
  return result
}
