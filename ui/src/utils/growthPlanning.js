import { i18n } from '@/i18n'
export const growthMetrics = [
  {
    key: 'max_level',
    get label() {
      return i18n.global.t('growth.planning.maxedOperators')
    },
    get detail() {
      return i18n.global.t('growth.planning.atTheActualPromotionAndLevelCap')
    }
  },
  {
    key: 'module_level',
    get label() {
      return i18n.global.t('growth.planning.moduleUnlockLevel')
    },
    get detail() {
      return i18n.global.t('growth.planning.elite2Level605040Or')
    }
  },
  {
    key: 'elite2',
    get label() {
      return i18n.global.t('growth.planning.elite2Operators')
    },
    get detail() {
      return i18n.global.t('growth.planning.promotedToElite2')
    }
  },
  {
    key: 'modules',
    get label() {
      return i18n.global.t('growth.planning.unlockedModules')
    },
    get detail() {
      return i18n.global.t('growth.planning.countedPerModule')
    }
  },
  {
    key: 'masteries',
    get label() {
      return i18n.global.t('growth.planning.masteredSkills')
    },
    get detail() {
      return i18n.global.t('growth.planning.m3OnlyEachSkillCountedOnce')
    }
  },
  {
    key: 'sanity_value',
    get label() {
      return i18n.global.t('growth.planning.totalSanityEquivalent')
    },
    get detail() {
      return i18n.global.t('growth.planning.completedGrowthInvestmentYituliuValuation')
    }
  }
]

export function sumGrowthStatistics(statistics, rarities) {
  return Object.fromEntries(
    growthMetrics.map(({ key }) => [
      key,
      rarities.some((rarity) => !Number.isFinite(statistics?.[rarity]?.[key]))
        ? null
        : rarities.reduce((sum, rarity) => sum + (statistics?.[rarity]?.[key] || 0), 0)
    ])
  )
}

export function growthHistoryPoints(history, rarities, key) {
  return history.flatMap((entry) => {
    const value = sumGrowthStatistics(entry.rarities, rarities)[key]
    return value === null ? [] : [[entry.time * 1000, value]]
  })
}

export function selectedRecommendation(rec, target = 3) {
  return { ...rec, ...(rec.targets?.[target] || {}), target_level: target }
}

export function goalSelected(goals, charId, moduleId) {
  return goals.some((goal) => goal.char_id === charId && goal.module_id === moduleId)
}

export const levelGoals = ['elite2', 'elite2_module', 'elite2_max']

export function localizedLevelGoalLabel(goal) {
  if (i18n.global.locale.value === 'zh-CN') return goal.label
  const key = goal.id ?? goal.key
  if (!['elite1', 'elite2', 'elite2_module', 'elite2_max', 'level_max'].includes(key))
    return goal.label
  if (!Number.isInteger(goal.elite) || !Number.isInteger(goal.level)) return goal.label
  const kind =
    key === 'elite2_module'
      ? 'moduleUnlock'
      : ['elite2_max', 'level_max'].includes(key)
        ? 'maximum'
        : 'level'
  return i18n.global.t(`growth.format.${kind}Goal`, { elite: goal.elite, level: goal.level })
}

export function operatorLevelGoals(op) {
  if (op.level_goals)
    return op.level_goals.map((goal) => ({
      ...goal,
      key: goal.id,
      label: localizedLevelGoalLabel(goal)
    }))
  if (op.rarity < 4) return []
  return [
    {
      key: 'elite2',
      elite: 2,
      level: 1,
      get label() {
        return i18n.global.t('growth.planning.elite2Lv1')
      },
      summary: op.promotion_summary
    },
    {
      key: 'elite2_module',
      elite: 2,
      level: op.module_level,
      label: i18n.global.t('growth.planning.elite2LvModuleUnlock', { value0: op.module_level }),
      summary: op.module_level_summary
    },
    {
      key: 'elite2_max',
      elite: 2,
      level: op.max_level,
      label: i18n.global.t('growth.planning.elite2LvMaxed', { value0: op.max_level }),
      summary: op.max_level_summary
    }
  ]
}

export function isGrowthOperatorIdle(name, scheduled, routes, workshop, blacklist = []) {
  return (
    !scheduled.has(name) && !routes.has(name) && !workshop.has(name) && !blacklist.includes(name)
  )
}

export function prerequisiteLevelGoal(op, skillPlanned, goals) {
  const basic = op.basic_skill_prerequisite
  if (
    op.max_phase < 2 &&
    basic &&
    goalSelected(goals, op.char_id, 'skill7') &&
    (op.elite < basic.elite || (op.elite === basic.elite && op.level < basic.level))
  ) {
    return (
      operatorLevelGoals(op).find(
        (goal) =>
          goal.elite > basic.elite || (goal.elite === basic.elite && goal.level >= basic.level)
      )?.key || null
    )
  }
  const modules = op.modules?.filter((module) => goalSelected(goals, op.char_id, module.id)) || []
  if (
    modules.some(
      (module) => op.elite < module.elite || (op.elite === module.elite && op.level < module.level)
    )
  )
    return 'elite2_module'
  return skillPlanned && op.elite < 2 ? 'elite2' : null
}

export function selectedLevelGoal(op, skillPlanned, goals) {
  const choices = operatorLevelGoals(op).map((goal) => goal.key)
  const required = prerequisiteLevelGoal(op, skillPlanned, goals)
  const explicit = goals
    .filter((goal) => goal.char_id === op.char_id)
    .map((goal) => choices.indexOf(goal.module_id))
  return choices[Math.max(choices.indexOf(required), ...explicit)] || null
}
