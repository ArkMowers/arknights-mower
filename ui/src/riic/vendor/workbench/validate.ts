import {validateBackupPlans} from './validateBackupPlans'
import {validateMowerRosterRules} from '../domain/mowerRosterRules'
import {resolveOperatorCharId} from '../domain/operatorIdentifiers'
import {
  MOWER_OUTPUT_ROOM_IDS,
  MOWER_ROOM_IDS,
  type MowerFacilityType,
  type MowerProduct,
  type MowerRoomId,
  type RosterWorkspace,
} from '../domain/roster'
import {
  getOperatorName,
  getRoomDisplayName,
  isFiammetta,
} from './operatorHelpers'
import { facilityCapacity } from '../domain/facilities'

export type ValidationSeverity = 'critical' | 'warning' | 'info'

export type ValidationIssueCode =
  | 'DUPLICATE_OPERATOR'
  | 'CONFLICTING_REPLACEMENT'
  | 'DUPLICATE_REPLACEMENT'
  | 'SLOT_OVERFLOW'
  | 'INVALID_CONFIG'
  | 'UNSUPPORTED_SPECIAL_ORDER'
  | 'POWER_DEFICIT'
  | 'NO_REPLACEMENT'
  | 'PLACEHOLDER_SLOT'
  | 'UNSUPPORTED_GAMING'

export interface ValidationIssue {
  readonly code: ValidationIssueCode
  readonly severity: ValidationSeverity
  readonly roomId: MowerRoomId
  readonly slotIndex?: number
  readonly message: string
}

export interface ValidationPowerSummary {
  readonly generation: number
  readonly consumption: number
  readonly margin: number
  readonly sufficient: boolean
}

export interface ValidationResult {
  readonly isValid: boolean
  readonly criticalErrors: ValidationIssue[]
  readonly warnings: ValidationIssue[]
  readonly issues: ValidationIssue[]
  readonly power: ValidationPowerSummary
}

// Source-backed power generation & consumption tables
const POWER_GENERATION: Record<number, number> = { 1: 60, 2: 130, 3: 270 }
const OUTPUT_POWER_CONSUMPTION: Record<number, number> = { 1: 10, 2: 30, 3: 60 }
const DORM_POWER_CONSUMPTION: Record<number, number> = { 1: 10, 2: 20, 3: 30, 4: 45, 5: 65 }
const FUNCTIONAL_POWER_CONSUMPTION: Record<number, number> = { 1: 10, 2: 30, 3: 60 }

const VALID_MANUFACTURE_PRODUCTS: readonly MowerProduct[] = ['gold', 'exp', 'fragment']
const VALID_TRADING_PRODUCTS: readonly MowerProduct[] = ['money', 'orundum']

function getFacilityCapacity(type: MowerFacilityType, level: number): number {
  return facilityCapacity(type, level)
}

export function validateRosterWorkspace(workspace: RosterWorkspace): ValidationResult {
  const criticalErrors: ValidationIssue[] = []
  const warnings: ValidationIssue[] = []

  const facilities = workspace.mainPlan.facilities

  // Track primary operators: operatorId -> { roomId, slotIndex }
  const primaryOperators = new Map<string, { roomId: MowerRoomId; slotIndex: number }>()

  // 1. First pass: Collect all active primary operators and check duplicates
  for (const roomId of MOWER_ROOM_IDS) {
    const facility = facilities[roomId]
    if (!facility || facility.level === 0) continue

    facility.slots.forEach((slot, slotIndex) => {
      if (slot.occupant.kind === 'operator') {
        const opId = resolveOperatorCharId(slot.occupant.operatorId)
        if (!opId || opId.toLowerCase() === 'free' || opId.toLowerCase() === 'current') {
          return
        }
        const existing = primaryOperators.get(opId)
        if (existing) {
          criticalErrors.push({
            code: 'DUPLICATE_OPERATOR',
            severity: 'critical',
            roomId,
            slotIndex,
            message: `干员 ${getOperatorName(opId)} 在 ${getRoomDisplayName(existing.roomId)} 和 ${getRoomDisplayName(roomId)} 同时在岗，不可重复指派主力。`,
          })
        } else {
          primaryOperators.set(opId, { roomId, slotIndex })
        }
      }
    })
  }

  criticalErrors.push(...validateMowerRosterRules(workspace))

  // 2. Power calculation
  let totalGeneration = 0
  let totalConsumption = 0

  for (const roomId of MOWER_ROOM_IDS) {
    const facility = facilities[roomId]
    if (!facility || facility.level === 0) continue

    // Gaming is strictly excluded from power totals
    if (facility.type === 'gaming' || roomId.startsWith('gaming_')) {
      continue
    }

    if (facility.type === 'power') {
      totalGeneration += POWER_GENERATION[facility.level] ?? 0
    } else if (facility.type === 'manufacture' || facility.type === 'trading') {
      totalConsumption += OUTPUT_POWER_CONSUMPTION[facility.level] ?? 0
    } else if (facility.type === 'dormitory') {
      totalConsumption += DORM_POWER_CONSUMPTION[facility.level] ?? 0
    } else if (facility.type === 'meeting' || facility.type === 'contact' || facility.type === 'train') {
      totalConsumption += FUNCTIONAL_POWER_CONSUMPTION[facility.level] ?? 0
    } else if (facility.type === 'factory') {
      // Factory consumes fixed 10
      totalConsumption += 10
    }
    // Central consumes 0
  }

  if (totalConsumption > totalGeneration) {
    criticalErrors.push({
      code: 'POWER_DEFICIT',
      severity: 'critical',
      roomId: 'room_1_3',
      message: `基建总耗电量 (${totalConsumption}) 超过总发电量 (${totalGeneration})，存在电力赤字。`,
    })
  }

  // 3. Room-by-room constraint validation
  for (const roomId of MOWER_ROOM_IDS) {
    const facility = facilities[roomId]
    if (!facility) continue

    if (facility.level === 0) {
      if (facility.slots.some(slot => slot.occupant.kind !== 'empty' || slot.groupId || slot.replacements.length)) {
        criticalErrors.push({ code: 'INVALID_CONFIG', severity: 'critical', roomId,
          message: `${getRoomDisplayName(roomId)} 未建造，不能配置干员、休息床位或替补。` })
      }
      continue
    }

    const isOutputRoom = (MOWER_OUTPUT_ROOM_IDS as readonly string[]).includes(roomId)

    // Facility Type & Level validation
    if (isOutputRoom) {
      if (facility.type !== 'manufacture' && facility.type !== 'trading' && facility.type !== 'power') {
        criticalErrors.push({
          code: 'INVALID_CONFIG',
          severity: 'critical',
          roomId,
          message: `${roomId} 为产出设施，类型必须为制造站、贸易站或发电站，当前为 ${facility.type}。`,
        })
      }
      if (facility.level < 1 || facility.level > 3) {
        criticalErrors.push({
          code: 'INVALID_CONFIG',
          severity: 'critical',
          roomId,
          message: `${roomId} 等级必须为 1~3 级，当前为 ${facility.level}。`,
        })
      }
      if (facility.type === 'manufacture') {
        if (facility.product && !VALID_MANUFACTURE_PRODUCTS.includes(facility.product)) {
          criticalErrors.push({
            code: 'INVALID_CONFIG',
            severity: 'critical',
            roomId,
            message: `制造站 ${roomId} 产物配置无效：${facility.product}，必须为赤金、作战记录或源石碎片。`,
          })
        }
      } else if (facility.type === 'trading') {
        if (facility.product && !VALID_TRADING_PRODUCTS.includes(facility.product)) {
          criticalErrors.push({
            code: 'INVALID_CONFIG',
            severity: 'critical',
            roomId,
            message: `贸易站 ${roomId} 产物配置无效：${facility.product}，必须为龙门币或源石订单。`,
          })
        }
      }
    } else if (roomId === 'central') {
      if (facility.type !== 'central' || facility.level < 1 || facility.level > 5) {
        criticalErrors.push({
          code: 'INVALID_CONFIG',
          severity: 'critical',
          roomId,
          message: `控制中枢等级必须为 1~5 级，当前等级 ${facility.level}，类型 ${facility.type}。`,
        })
      }
    } else if (roomId.startsWith('dormitory_')) {
      if (facility.type !== 'dormitory' || facility.level < 1 || facility.level > 5) {
        criticalErrors.push({
          code: 'INVALID_CONFIG',
          severity: 'critical',
          roomId,
          message: `宿舍 ${roomId} 等级必须为 1~5 级，当前等级 ${facility.level}，类型 ${facility.type}。`,
        })
      }
    } else if (roomId === 'meeting' || roomId === 'factory' || roomId === 'contact' || roomId === 'train' || roomId === 'recycle') {
      if (facility.level < 1 || facility.level > 3) {
        criticalErrors.push({
          code: 'INVALID_CONFIG',
          severity: 'critical',
          roomId,
          message: `功能设施 ${roomId} 等级必须为 1~3 级，当前等级 ${facility.level}。`,
        })
      }
    } else if (roomId.startsWith('gaming_')) {
      // Check if gaming is configured
      const hasConfiguredOccupant = facility.slots.some((s) => s.occupant.kind !== 'empty')
      if (hasConfiguredOccupant) {
        warnings.push({
          code: 'UNSUPPORTED_GAMING',
          severity: 'warning',
          roomId,
          message: `活动室 (${roomId}) 暂不支持收益计算与电力模拟，已从电力总计中忽略。`,
        })
      }
    }

    // Capacity check
    const capacity = getFacilityCapacity(facility.type, facility.level)
    const activeStaff = facility.slots.filter((s) => s.occupant.kind !== 'empty').length
    if (activeStaff > capacity) {
      criticalErrors.push({
        code: 'SLOT_OVERFLOW',
        severity: 'critical',
        roomId,
        message: `${roomId} 的在岗人数 (${activeStaff}) 超过了设施等级容量 (${capacity})。`,
      })
    }

    // Slot-level validation
    facility.slots.forEach((slot, slotIndex) => {
      const isDorm = facility.type === 'dormitory' || roomId.startsWith('dormitory_') || roomId.startsWith('dorm_')

      if (slot.occupant.kind === 'operator') {
        const opId = resolveOperatorCharId(slot.occupant.operatorId)
        if (!opId || opId.toLowerCase() === 'free' || opId.toLowerCase() === 'current') {
          if (!(isDorm && opId?.toLowerCase() === 'free')) {
            warnings.push({
              code: 'PLACEHOLDER_SLOT',
              severity: 'warning',
              roomId,
              slotIndex,
              message: `${getRoomDisplayName(roomId, facility.type)} 席位使用 ${opId} 占位，在收益模拟中将视为空席。`,
            })
          }
          return
        }

        const isFiam = isFiammetta(opId)
        const isFiamInDorm = isDorm && isFiam
        const isWorkaholic = workspace.mainPlan.conf.workaholic.includes(opId)

        // Missing replacements warning:
        // Ordinary dormitory keepers do not need replacements and do not warn.
        // Fiammetta requires replacements (morale swap targets) and warns if missing.
        // Non-dormitory rooms require replacements.
        if (slot.replacements.length === 0) {
          if ((!isDorm || isFiamInDorm) && !isWorkaholic) {
            warnings.push({
              code: 'NO_REPLACEMENT',
              severity: 'warning',
              roomId,
              slotIndex,
              message: `${getRoomDisplayName(roomId, facility.type)} 席位干员 (${getOperatorName(opId)}) 未配置替补。`,
            })
          }
        }

      } else if (slot.occupant.kind === 'free' || slot.occupant.kind === 'current') {
        // dorm Free is a rest pool placeholder, should not be warned as an illegal empty placeholder slot.
        if (!(isDorm && slot.occupant.kind === 'free')) {
          warnings.push({
            code: 'PLACEHOLDER_SLOT',
            severity: 'warning',
            roomId,
            slotIndex,
            message: `${getRoomDisplayName(roomId, facility.type)} 席位使用 ${slot.occupant.kind} 占位，在收益模拟中将视为空席。`,
          })
        }
      }
    })
  }

  for (const issue of validateBackupPlans(workspace, validateRosterWorkspace)) (issue.severity === 'critical' ? criticalErrors : warnings).push(issue)
  const isValid = criticalErrors.length === 0

  return {
    isValid,
    criticalErrors,
    warnings,
    issues: [...criticalErrors, ...warnings],
    power: {
      generation: totalGeneration,
      consumption: totalConsumption,
      margin: totalGeneration - totalConsumption,
      sufficient: totalGeneration >= totalConsumption,
    },
  }
}
