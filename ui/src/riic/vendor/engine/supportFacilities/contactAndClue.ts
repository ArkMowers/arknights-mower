import { operatorFor } from '../../domain/operatorContext'
import type { AppConfig } from '../../domain/types'
import { isSupportOperatorWorking, supportSkillConditionMatches, SUPPORT_OPERATOR_IDS } from './conditions'

const TOLEDO = SUPPORT_OPERATOR_IDS.toledo
const CLEMENTIA = SUPPORT_OPERATOR_IDS.clementia
const CONTACT_BONUSES: Readonly<Record<string, number>> = {
  'hire_spd_cost[113]': 20,
  'hire_spd_cost[122]': 30,
}
const CLUE_BONUSES: Readonly<Record<string, number>> = {
  'meet_spd&cost[110]': 20,
  'meet_spd&cost_char[000]': 15,
}

function contactBonus(config: AppConfig): number {
  if (!config.facilities.office || !config.facilityOperatorIds.office.includes(TOLEDO) ||
      !isSupportOperatorWorking(config, TOLEDO)) return 0
  return (operatorFor(config, TOLEDO)?.skills ?? [])
    .filter(skill => skill.roomType === 'HIRE')
    .reduce((bonus, skill) => {
      const value = CONTACT_BONUSES[skill.buffId]
      if (value === undefined) throw new Error(`Unquantified contact skill: ${TOLEDO}/${skill.buffId}`)
      return bonus + value
    }, 0)
}

function clueBonus(config: AppConfig): number {
  if (!config.facilities.reception || !config.facilityOperatorIds.reception.includes(CLEMENTIA) ||
      !isSupportOperatorWorking(config, CLEMENTIA)) return 0
  const peers = config.facilityOperatorIds.reception.filter(id => isSupportOperatorWorking(config, id))
  return (operatorFor(config, CLEMENTIA)?.skills ?? [])
    .filter(skill => skill.roomType === 'MEETING')
    .reduce((bonus, skill) => {
      const value = CLUE_BONUSES[skill.buffId]
      if (value === undefined) throw new Error(`Unquantified clue skill: ${CLEMENTIA}/${skill.buffId}`)
      return bonus + (supportSkillConditionMatches(skill, CLEMENTIA, peers) ? value : 0)
    }, 0)
}

/** Numeric additions for the new office/reception skills, in percentage points. */
export function evaluateNewContactAndClueSkills(config: AppConfig): { contactBonus: number; clueBonus: number } {
  return { contactBonus: contactBonus(config), clueBonus: clueBonus(config) }
}
