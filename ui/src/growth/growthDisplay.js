import { i18n } from '@/i18n'
import { skillDisplayName } from '@/i18n/gameNames'
import { moduleDisplayName } from '@/i18n/moduleNames'
import { RECOMMEND_SORT_OPTIONS } from './growthRecommendation'

export function skillRowDisplayName(row) {
  if (!row) return ''
  if (/^[一二三]技能$/.test(row.name)) {
    return i18n.global.t('growth.format.skillNumber', {
      ordinal: i18n.global.t(`growth.format.ordinal${row.index + 1}`)
    })
  }
  return skillDisplayName(row.name)
}

export function targetDisplayName(target, operator) {
  if (!target) return ''
  if (target.kind !== 'module') return skillRowDisplayName(target)
  const module = (operator?.modules || []).find((row) => row.id === target.id)
  return module?.type || moduleDisplayName(target.id, target.name)
}

export function recommendationSortOptions() {
  const keys = {
    mastery: 'growthUpdates.remainingMasteryRate',
    module: 'growthUpdates.remainingModuleUnlockRate',
    rarity: 'growth.grid.rarity',
    level: 'growth.card.level'
  }
  return RECOMMEND_SORT_OPTIONS.map((option) => ({
    ...option,
    label: i18n.global.t(keys[option.value])
  }))
}
