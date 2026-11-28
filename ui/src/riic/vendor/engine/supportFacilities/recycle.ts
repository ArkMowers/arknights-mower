import rules from '../../data/support-facilities.generated.json'
import { operatorFor } from '../../domain/operatorContext'
import type { AppConfig } from '../../domain/types'
import { isSupportOperatorWorking, recyclingOccupants } from './conditions'

export const RECYCLE_RULES = rules.recycle
const RECYCLE_SKILL_BONUSES: Readonly<Record<string, number>> = {
  'recycle_spd&cost[000]': 20,
  'recycle_spd&cost[010]': 30,
  'recycle_spd&cost[001]': 20,
  'recycle_spd&cost[011]': 30,
  'recycle_spd&cost[100]': 20,
  'recycle_spd&cost[110]': 30,
}

export interface RecycleEfficiency {
  efficiencyPercent: number
  hoursPerMaterial: number | null
  capacity: number
  operatorCapacity: number
  details: string[]
}

/** Basic conversion survives departures; only positive-mood occupants contribute staff/skill bonuses. */
export function evaluateRecycleEfficiency(
  config: AppConfig,
  options: { activeIds?: ReadonlySet<string>; boosted?: boolean } = {},
): RecycleEfficiency {
  const level = config.facilities.recycle ?? 0
  if (level === 0) return { efficiencyPercent: 0, hoursPerMaterial: null, capacity: 0, operatorCapacity: 0, details: [] }
  const phase = RECYCLE_RULES.phases.find(phase => phase.level === level)
  if (!phase) throw new Error(`Invalid recycle level: ${level}`)
  const occupants = [...new Set(recyclingOccupants(config))]
  if (occupants.length > phase.operatorCapacity) throw new Error('Recycle staffing exceeds facility level capacity')
  const ids = occupants.filter(id => isSupportOperatorWorking(config, id, options.activeIds))
  let efficiencyPercent = phase.baseSpeed * 100 + ids.length * RECYCLE_RULES.staffedSpeed * 100
  const details = [`设施基础 ${phase.baseSpeed * 100}%`, `在岗 ${ids.length} 人：+${ids.length * RECYCLE_RULES.staffedSpeed * 100}%`]
  for (const id of ids) {
    const operator = operatorFor(config, id)
    if (!operator) throw new Error(`Unknown recycle operator: ${id}`)
    for (const skill of operator.skills) {
      if (skill.roomType !== 'RECYCLE') continue
      const value = RECYCLE_SKILL_BONUSES[skill.buffId]
      const moodReduction = ['recycle_spd&cost[100]', 'recycle_spd&cost[110]'].includes(skill.buffId)
        ? '，心情每小时消耗-0.1' : ''
      // A percentage regex alone could silently erase a future skill's prerequisite.
      if (value === undefined || skill.description !== `进驻回收站时，材料转化效率+${value}%${moodReduction}`) {
        throw new Error(`Unquantified recycle skill: ${id}/${skill.buffId}`)
      }
      efficiencyPercent += value
      details.push(`${operator.name}·${skill.name}：+${value}%`)
    }
  }
  if (options.boosted) {
    if (level < RECYCLE_RULES.recycleSpeedUpUnlockLevel) throw new Error('Recycle boost requires level three')
    efficiencyPercent += RECYCLE_RULES.recycleBoostSpeed * 100
    details.push(`转化提效：+${RECYCLE_RULES.recycleBoostSpeed * 100}%`)
  }
  return {
    efficiencyPercent,
    hoursPerMaterial: RECYCLE_RULES.recycleTimeRequirement / 3600 / (efficiencyPercent / 100),
    capacity: phase.capacity,
    operatorCapacity: phase.operatorCapacity,
    details,
  }
}
