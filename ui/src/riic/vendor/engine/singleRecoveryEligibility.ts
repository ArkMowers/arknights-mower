import type { OperatorRecord } from '../domain/operators'

type SkilledOperator = Pick<OperatorRecord, 'skills'>

/** Read the active skill snapshot, not every unlock stage in the catalog. */
export function hasSingleRecoverySkill(operator: SkilledOperator | undefined): boolean {
  return operator?.skills.some(skill => skill.roomType === 'DORMITORY'
    && /某个干员(?:的心情)?每小时恢复\+[\d.]+/.test(skill.description)) ?? false
}

/** A single-recovery provider can receive another provider's bonus only as its sole unfinished recipient. */
export function eligibleSingleRecoveryTargets(
  operators: readonly OperatorRecord[],
  providerId: string,
  mood: (id: string) => number,
): OperatorRecord[] {
  const candidates = operators.filter(operator => operator.charId !== providerId
    && mood(operator.charId) < 24 - 1e-8
    && !operator.skills.some(skill => skill.buffId === 'dorm_recExcludeOther[000]'))
  return candidates.length === 1 ? candidates : candidates.filter(operator => !hasSingleRecoverySkill(operator))
}
