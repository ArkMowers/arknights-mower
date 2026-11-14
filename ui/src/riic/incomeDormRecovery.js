import { operatorFor } from './vendor/domain/operatorContext'
import { evaluateDormitoryRecovery } from './vendor/engine/dormitoryRecovery'
import { buildRiicGlobalContext } from './vendor/engine/globalContext'
import {
  eligibleSingleRecoveryTargets,
  hasSingleRecoverySkill
} from './vendor/engine/singleRecoveryEligibility'
import { isMowerDormFiller, MOWER_DORM_FILLER_NAME } from './vendor/scheduler/mowerDormFiller'

function fillerRecord(charId) {
  return {
    charId,
    name: MOWER_DORM_FILLER_NAME,
    appellation: '',
    rarity: 0,
    profession: '',
    isAlter: false,
    nationId: null,
    groupId: null,
    teamId: null,
    skills: []
  }
}

// 填充干员只在估值副本中视为持续待恢复，不修改真实心情、技能或排班。
export function createDormRecoveryObservation(warmupHours) {
  const rooms = new Map()
  const warnings = new Set()
  return {
    observe(config, start, end) {
      const duration = Math.max(0, end - Math.max(start, warmupHours))
      if (!duration) return
      const fillers = config.facilityOperatorIds.dormitories.flat().filter(isMowerDormFiller)
      if (!fillers.length) return
      const projected = {
        ...config,
        operatorRecords: {
          ...config.operatorRecords,
          ...Object.fromEntries(fillers.map((id) => [id, fillerRecord(id)]))
        },
        operatorMorale: {
          ...config.operatorMorale,
          ...Object.fromEntries(fillers.map((id) => [id, 0]))
        }
      }
      const morale = new Map(Object.entries(projected.operatorMorale))
      const global = buildRiicGlobalContext(config)
      config.facilityOperatorIds.dormitories.forEach((ids, index) => {
        const occupants = ids.filter(isMowerDormFiller)
        if (!occupants.length) return
        const roomId = `dormitory_${index + 1}`
        const operators = ids.map((id) => operatorFor(projected, id)).filter(Boolean)
        const targets = new Map()
        for (const provider of operators.filter(hasSingleRecoverySkill)) {
          const candidates = eligibleSingleRecoveryTargets(
            operators,
            provider.charId,
            (id) => morale.get(id) ?? 24
          ).sort((a, b) => (morale.get(a.charId) ?? 24) - (morale.get(b.charId) ?? 24))
          if (candidates[0]) targets.set(provider.charId, candidates[0].charId)
        }
        const recovery = evaluateDormitoryRecovery(
          projected,
          index,
          morale,
          config.facilities.dormitories[index] * 1000,
          targets,
          false,
          global
        )
        for (const warning of recovery.unquantified) warnings.add(`${roomId}: ${warning}`)
        const room = rooms.get(roomId) ?? { roomId, total: 0, bedHours: 0 }
        room.bedHours += occupants.length * duration
        for (const id of occupants) {
          const rate = recovery.rates.get(id)
          if (Number.isFinite(rate)) room.total += rate * duration
          else warnings.add(`${roomId}: 填充干员恢复速度未知`)
        }
        rooms.set(roomId, room)
      })
    },
    result(observedHours) {
      const days = observedHours / 24
      if (!(days > 0)) throw new Error('宿舍填充恢复量的统计时长无效')
      const rows = [...rooms.values()]
        .sort((a, b) => a.roomId.localeCompare(b.roomId))
        .map((room) => ({ ...room, daily: room.total / days }))
      const total = rows.reduce((sum, room) => sum + room.total, 0)
      return {
        model: 'neutral-filler-recovery-v1',
        total,
        daily: total / days,
        rooms: rows,
        partial: warnings.size > 0,
        warnings: [...warnings]
      }
    }
  }
}
