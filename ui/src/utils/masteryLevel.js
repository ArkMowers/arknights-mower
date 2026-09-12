export function masteryLevelLabel(mainLevel, masteryLevel) {
  if (Number.isInteger(masteryLevel) && masteryLevel >= 1 && masteryLevel <= 3) {
    return ['专一', '专二', '专三'][masteryLevel - 1]
  }
  return Number.isInteger(mainLevel) && mainLevel >= 1 ? `${mainLevel} 级` : '等级未知'
}
