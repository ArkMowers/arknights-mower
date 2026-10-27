import { i18n } from '@/i18n'
export function masteryLevelLabel(mainLevel, masteryLevel) {
  if (Number.isInteger(masteryLevel) && masteryLevel >= 1 && masteryLevel <= 3) {
    return [
      i18n.global.t('growth.masteryLevel.m1'),
      i18n.global.t('growth.masteryLevel.m2'),
      i18n.global.t('growth.masteryLevel.m3')
    ][masteryLevel - 1]
  }
  return Number.isInteger(mainLevel) && mainLevel >= 1
    ? i18n.global.t('growth.masteryLevel.rank', { value0: mainLevel })
    : i18n.global.t('growth.masteryLevel.unknownRank')
}
