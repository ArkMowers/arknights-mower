import type { OperatorSkill } from '../../domain/operators'
import type { AppConfig } from '../../domain/types'

export const SUPPORT_OPERATOR_IDS = {
  toledo: 'char_393_toledo',
  clementia: 'char_4231_clemnt',
  homebound: 'char_4232_hbound',
} as const

/** A workplace provider must still be assigned, awake and positive in the current frame. */
export function isSupportOperatorWorking(
  config: AppConfig,
  id: string,
  activeIds?: ReadonlySet<string>,
  moraleValues?: ReadonlyMap<string, number>,
): boolean {
  return (activeIds?.has(id) ?? true) && !config.zeroMoraleOperatorIds.includes(id) &&
    (moraleValues?.get(id) ?? config.operatorMorale[id] ?? 24) > 0
}

/** A missing facility contributes no physical presence or workplace resources. */
export function recyclingOccupants(config: AppConfig): readonly string[] {
  return config.facilities.recycle ? config.facilityOperatorIds.recycle ?? [] : []
}

/** The cooperation gate is shared by speed and personal morale, without affecting coworkers. */
export function supportSkillConditionMatches(
  skill: OperatorSkill,
  providerId: string,
  activePeerIds: readonly string[],
): boolean {
  return skill.buffId !== 'meet_spd&cost_char[000]' || activePeerIds.some(id => id !== providerId)
}
