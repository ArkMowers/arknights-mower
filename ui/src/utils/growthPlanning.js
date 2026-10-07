export const growthMetrics = [
  { key: 'max_level', label: '满练干员', detail: '精二 90 / 80 / 70 级' },
  { key: 'module_level', label: '达到模组等级', detail: '精二 ≥60 / 50 / 40 级' },
  { key: 'elite2', label: '精二干员', detail: '已完成精英化二' },
  { key: 'modules', label: '已开启模组', detail: '按模组数量统计' },
  { key: 'masteries', label: '已专精技能', detail: '仅专三，每技能计一次' },
  { key: 'sanity_value', label: '总消耗等效理智', detail: '已完成养成投入 · 一图流估值' }
]

export function sumGrowthStatistics(statistics, rarities) {
  return Object.fromEntries(
    growthMetrics.map(({ key }) => [
      key,
      key === 'sanity_value' &&
      rarities.some((rarity) => !Number.isFinite(statistics?.[rarity]?.[key]))
        ? null
        : rarities.reduce((sum, rarity) => sum + (statistics?.[rarity]?.[key] || 0), 0)
    ])
  )
}

export function growthValueCoverage(statistics, rarities) {
  const unpriced = new Map()
  const incomplete = new Set()
  let source = null
  let moduleBlocks = 0
  let skillBookEquivalent = 0
  let consumedLmd = 0
  let consumedExp = 0
  for (const rarity of rarities) {
    const row = statistics?.[rarity] || {}
    moduleBlocks += row.module_blocks || 0
    skillBookEquivalent += row.skill_book_equivalent || 0
    consumedLmd += row.consumed_lmd || 0
    consumedExp += row.consumed_exp || 0
    source ||= row.sanity_source
    for (const item of row.sanity_unpriced || []) {
      const previous = unpriced.get(item.id)
      unpriced.set(item.id, { ...item, count: (previous?.count || 0) + item.count })
    }
    for (const name of row.sanity_incomplete || []) incomplete.add(name)
  }
  return {
    unpriced: [...unpriced.values()],
    incomplete: [...incomplete],
    source,
    moduleBlocks,
    skillBookEquivalent,
    consumedLmd,
    consumedExp
  }
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

export function prerequisiteLevelGoal(op, skillPlanned, goals) {
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
  const required = prerequisiteLevelGoal(op, skillPlanned, goals)
  const explicit = goals
    .filter((goal) => goal.char_id === op.char_id)
    .map((goal) => levelGoals.indexOf(goal.module_id))
  return levelGoals[Math.max(levelGoals.indexOf(required), ...explicit)] || null
}
