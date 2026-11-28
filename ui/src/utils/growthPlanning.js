export const growthMetrics = [
  { key: 'max_level', label: '满练干员', detail: '达到该星级实际精英化与等级上限' },
  { key: 'module_level', label: '达到模组开启等级', detail: '精二 ≥60 / 50 / 40 级' },
  { key: 'elite2', label: '精二干员', detail: '已完成精英化二' },
  { key: 'modules', label: '已开启模组', detail: '按模组数量统计' },
  { key: 'masteries', label: '已专精技能', detail: '仅专三，每技能计一次' },
  { key: 'sanity_value', label: '总消耗等效理智', detail: '已完成养成投入 · 一图流估值' }
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

export function operatorLevelGoals(op) {
  if (op.level_goals) return op.level_goals.map((goal) => ({ ...goal, key: goal.id }))
  if (op.rarity < 4) return []
  return [
    { key: 'elite2', elite: 2, level: 1, label: '精二 1 级', summary: op.promotion_summary },
    {
      key: 'elite2_module',
      elite: 2,
      level: op.module_level,
      label: `精二 ${op.module_level} 级（达到模组开启等级）`,
      summary: op.module_level_summary
    },
    {
      key: 'elite2_max',
      elite: 2,
      level: op.max_level,
      label: `精二 ${op.max_level} 级（满练）`,
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
