import { effectiveMowerDormOrder } from '../domain/mowerDormOrder'
import {orderMowerRecoveryBeds} from './mowerGlobalDormOrder'
import {readMowerMoodLimits} from './mowerMoodLimits'
import {restingThresholdFor} from './mowerOperatorState'
import { isTradeRunOrderOperator } from '../domain/shiftRunPolicy'
import { OPERATOR_MAP } from '../domain/operators'
import { resolveOperatorCharId } from '../domain/operatorIdentifiers'
import type { CompiledSchedule } from './types'
import type { RuntimeBed, RuntimeConfig, RuntimePosition } from './rosterRuntime'

const SHIFT_RUN_OPERATOR_NAMES = new Set(['但书', '龙舌兰'])

/**
 * Returns true if an operator is a shift-run dedicated operator (Proviso, Tequila).
 */
export function isShiftRunOperator(operatorId: string): boolean {
  const charId = resolveOperatorCharId(operatorId)
  const name = OPERATOR_MAP.get(charId)?.name
  return name ? SHIFT_RUN_OPERATOR_NAMES.has(name) : false
}

export function isOrdinaryReplacementCandidate(operatorId: string, roomType: string): boolean {
  return !isShiftRunOperator(operatorId) && (roomType !== 'trading' || !isTradeRunOrderOperator(operatorId))
}

/**
 * Pure function adapter converting a CompiledSchedule to a RuntimeConfig.
 *
 * Rules:
 * 1. Trading positions exclude all five dedicated run-order operators from ordinary replacements.
 * 2. schedule.runOrderPolicies retains its exact original order.
 * 3. RuntimeConfig.excludedCandidates includes configured run-order candidates.
 * 4. Fiammetta swap policy is mapped to runtime fiammetta config.
 * 5. Dormitory Free slots are mapped to runtime beds.
 * 6. Dorm-keepers without candidates are marked permanent to avoid invalid shifts.
 * 7. Does NOT mutate the input CompiledSchedule.
 */
export function compiledScheduleToRuntimeConfig(schedule: CompiledSchedule): RuntimeConfig {
  const positions: RuntimePosition[] = []
  const shiftRunIds = new Set<string>()

  // Register known shift-run IDs
  for (const name of SHIFT_RUN_OPERATOR_NAMES) {
    const id = resolveOperatorCharId(name)
    if (id) shiftRunIds.add(id)
  }

  // Also collect any from runOrderPolicies
  for (const policy of schedule.runOrderPolicies) {
    for (const id of policy.orderedOperatorIds) {
      shiftRunIds.add(id)
    }
  }

  for (const room of schedule.rooms) {
    if (room.type === 'gaming' || room.type === '') continue
    const isDorm = room.type === 'dormitory'
    for (const slot of room.slots) {
      if (!slot.primaryOperatorId) continue

      const primary = slot.primaryOperatorId
      const isDormKeeper = slot.role === 'dorm-keeper'
      const isFiammetta = slot.role === 'fiammetta'

      // Trading run-order candidates never fill ordinary replacement shifts.
      let candidates: string[]
      if (isDormKeeper || isFiammetta) {
        candidates = []
      } else {
        candidates = slot.orderedCandidates.filter(id => isOrdinaryReplacementCandidate(id, room.type))
      }

      const exhaustRequired = Boolean(schedule.policies.exhaust_require?.includes(primary))
      const restToFull = Boolean(schedule.policies.rest_in_full?.includes(primary))
      const restingPriority = schedule.policies.resting_priority?.includes(primary) ? 'low' : 'high'

      const isAuxiliary = (room.roomId === 'factory' || room.roomId === 'train') && !slot.groupId
      const position: RuntimePosition = {
        id: `${room.roomId}_${slot.slotIndex}`,
        roomId: room.roomId,
        primary,
        candidates,
        group: slot.groupId?.trim() ? slot.groupId.trim() : undefined,
        dormitory: isDorm,
        permanent: (isDormKeeper && candidates.length === 0) || schedule.policies.workaholic?.includes(primary) || isAuxiliary || undefined,
        exhaustRequired: exhaustRequired || undefined,
        restToFull: restToFull || undefined,
        restingPriority,
      }

      positions.push(position)
    }
  }

  // operators.py:init_mood_limit: policy limits are separate from skill boundaries.
  const mode = Number(schedule.policies.ling_xi ?? 1)
  const named = (name: string) => positions.find(p => p.primary === resolveOperatorCharId(name))
  for (const p of positions) { p.lowerLimit = 0; p.upperLimit = 24 }
  if (mode === 1 || mode === 2) {
    const lowHalf = named(mode === 1 ? '令' : '夕')
    const highHalf = named(mode === 1 ? '夕' : '令')
    if (lowHalf) { lowHalf.upperLimit = 12; lowHalf.restMoodLimit = true }
    if (highHalf) highHalf.lowerLimit = 12
    const groups = new Set([named('令')?.group, named('夕')?.group].filter(Boolean))
    for (const p of positions) if (p.group && groups.has(p.group) && !['令', '夕'].includes(OPERATOR_MAP.get(p.primary)?.name ?? '')) p.lowerLimit = 12
  }
  const totter = named('铅踝')
  if (totter) {
    const vermeil = named('红云')
    totter.lowerLimit = vermeil?.roomId === totter.roomId ? 8 : 20
    totter.upperLimit = vermeil?.roomId === totter.roomId ? 12 : 24
  }
  const limitedId = mode === 1 ? resolveOperatorCharId('令') : mode === 2 ? resolveOperatorCharId('夕') : undefined
  const restMoodLimits = limitedId && schedule.rooms.some(room => room.slots.some(slot => slot.primaryOperatorId === limitedId || slot.orderedCandidates.includes(limitedId))) ? {[limitedId]:12} : undefined
  const restingThreshold = schedule.assumptions.restingThreshold ?? 0.65
  const groupRestingThresholds = {...schedule.assumptions.groupRestingThresholds}
  const sharedPrimaries = new Set(schedule.rooms.flatMap(room => room.slots.filter(slot => (slot.groupBindings?.length ?? 0) > 1).map(slot => slot.primaryOperatorId)))
  const exhaustedGroups = new Set(positions.filter(p => p.exhaustRequired && p.group).map(p => p.group))
  for (const p of positions) {
    const exhaustGroup = p.group && exhaustedGroups.has(p.group)
    p.shiftOffThreshold = p.exhaustRequired ? p.lowerLimit : exhaustGroup ? -1 : Math.floor((p.upperLimit! - p.lowerLimit!) * restingThresholdFor({group:p.group,multiGroup:sharedPrimaries.has(p.primary)},{restingThreshold,groupRestingThresholds}) + p.lowerLimit!)
  }

  // Beds from restPools
  const beds: RuntimeBed[] = []
  for (const pool of schedule.restPools) {
    for (const [freeIndex, idx] of pool.freeSlotIndices.entries()) {
      beds.push({
        id: `${pool.roomId}_${idx}`,
        roomId: pool.roomId,
        // Mower reserves the first Free slot in each dormitory as its VIP bed.
        vip: freeIndex === 0,
      })
    }
  }

  // Initial morale
  const initialMorale: Record<string, number> = {}
  for (const [id, st] of Object.entries(schedule.operators)) {
    initialMorale[id] = st.morale
  }
  for (const id of [...positions.flatMap(p=>p.candidates),...schedule.runOrderPolicies.flatMap(p=>p.orderedOperatorIds),...schedule.fiammettaPolicies.flatMap(p=>p.orderedTargets),...(schedule.assumptions.idleOperators ?? [])]) initialMorale[id] ??= schedule.assumptions.initialMorale
  if (schedule.assumptions.operatorMorale) {
    for (const [id, m] of Object.entries(schedule.assumptions.operatorMorale)) {
      initialMorale[id] = m
    }
  }

  // Fiammetta policy
  let fiammetta: RuntimeConfig['fiammetta'] = undefined
  if (schedule.fiammettaPolicies.length > 0) {
    const fp = schedule.fiammettaPolicies[0]!
    fiammetta = {
      operatorId: fp.operatorId,
      orderedTargets: [...fp.orderedTargets],
      threshold: (schedule.assumptions.fiammettaFool === false ? schedule.assumptions.fiammettaThreshold ?? 0.9 : 0.9) * 24,
      fool: schedule.assumptions.fiammettaFool ?? true,
    }
  }

  // Preserved runOrderPolicies (original order maintained)
  const runOrderPolicies = schedule.runOrderPolicies.map(p => ({
    roomId: p.roomId,
    orderedOperatorIds: [...p.orderedOperatorIds],
  }))

  const sourceList=(key:string)=>{const raw=(schedule.policies as Record<string,unknown>)[key];return (Array.isArray(raw)?raw:typeof raw==='string'?raw.split(','):[]).map(String).filter(Boolean).map(resolveOperatorCharId)}
  return {
    mowerDormIsolation:schedule.assumptions.dormIsolation,
    mowerDormOrder:effectiveMowerDormOrder(schedule.assumptions.dormOrder?schedule.assumptions.dormOrder.split(','):typeof schedule.rawConf.dorm_order==='string'?schedule.rawConf.dorm_order.split(','):[]),
    majorMaintenanceStartHours:schedule.assumptions.majorMaintenanceStartHours,
    majorMaintenanceDurationHours:schedule.assumptions.majorMaintenanceDurationHours,
    mowerMoodLimits:readMowerMoodLimits(schedule.rawConf,resolveOperatorCharId),
    mowerDroneRoom:schedule.assumptions.droneRoom??null,
    // Preserve ideal runner metadata; excludedCandidates below blocks ordinary shift use.
    mowerRunOrderEnabled:schedule.assumptions.idealRunOrderWakeOnly!==false,
    mowerServices:{enableParty:false,leifengMode:schedule.assumptions.leifengMode??true,droneIntervalHours:schedule.assumptions.droneIntervalHours??3,reloadRooms:schedule.assumptions.reloadRooms===null?null:schedule.assumptions.reloadRooms??[],maaGapHours:schedule.assumptions.maaGapHours??3},
    mowerDeviceTiming:{roomReturnMicros:500_000},
    mowerTaskScheduling:{configuredDelayMinutes:3,enableMastery:schedule.assumptions.enableMastery},
    mowerDroneCountLimit:schedule.assumptions.droneCountLimit??100,
    mowerRecycleBuilt:schedule.rooms.some(room=>room.type==='recycle')||undefined,
    mowerRunLoopClock:{minimumClockStepMicros:1,notificationSleepMicros:1_000_000},
    mowerSourcePlan:Object.fromEntries(schedule.rooms.filter(r=>r.type!=='gaming'&&r.type!=='').flatMap(r=>{let last=r.slots.length-1;while(last>=0&&!r.slots[last]!.primaryOperatorId&&r.slots[last]!.occupant.kind!=='free')last--;return last<0?[]:[[r.roomId,r.slots.slice(0,last+1).map(slot=>({agent:slot.primaryOperatorId??(slot.occupant.kind==='free'?'Free':'Current'),group:slot.groupId??'',replacement:[...slot.orderedCandidates],groupBindings:slot.groupBindings?structuredClone(slot.groupBindings):undefined}))]]})),
    mowerSourceRules:{workaholic:sourceList('workaholic'),exhaustRequire:sourceList('exhaust_require'),restInFull:sourceList('rest_in_full'),lowPriority:sourceList('resting_priority'),refreshDrained:sourceList('refresh_drained'),refreshTrading:sourceList('refresh_trading'),lingMode:mode,standby:sourceList('resting_standby'),priorityReplacement:sourceList('resting_priority_replacement'),freeRoomExclusions:sourceList('free_room_exclusions')},
    idleOperators: schedule.assumptions.idleOperators,
    freeBlacklist: [...new Set([...sourceList('free_blacklist'),...sourceList('workaholic')])],
    mowerPolicy: { predictiveMoodControl:schedule.assumptions.predictiveMoodControl??false, groupRestInFullOnMoodGap:schedule.assumptions.groupRestInFullOnMoodGap, groupMoodGapThresholdMinutes:schedule.assumptions.groupMoodGapThresholdMinutes, groupMoodGapMaxExtraWaitHours:schedule.assumptions.groupMoodGapMaxExtraWaitHours, groupMoodGapExclusions:[...(schedule.assumptions.groupMoodGapExclusions??[])], mergeIntervalMinutes:schedule.assumptions.mergeIntervalMinutes, restMoodLimits, restingThreshold, groupRestingThresholds, freeRoom: schedule.assumptions.freeRoom ?? false, rescueThreshold: schedule.assumptions.rescueThreshold ?? 0.75, taskBuffers: true, powerPlantCount: schedule.rooms.filter(r => r.type === 'power').length, opeRestingPriority: [...(schedule.policies.ope_resting_priority ?? [])] },
    positions,
    beds:orderMowerRecoveryBeds(beds,schedule.assumptions.dormOrder??''),
    initialMorale,
    mowerInitialMorale: {fromUpperLimit: schedule.assumptions.defaultsApplied.includes('initialMorale'), explicitOperators: Object.keys(schedule.assumptions.operatorMorale)},
    fiammetta,
    excludedCandidates: Array.from(shiftRunIds),
    runOrderPolicies,
  }
}

export const scheduleToRuntimeConfig = compiledScheduleToRuntimeConfig
