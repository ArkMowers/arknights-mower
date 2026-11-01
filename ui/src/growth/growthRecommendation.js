const ORDINALS = ['一', '二', '三']

// 值得练的排序条件：只用“还没练完的目标”的公开比例，已练完的目标不参与。
export const RECOMMEND_SORT_OPTIONS = [
  { label: '剩余专三率', value: 'mastery' },
  { label: '剩余模组解锁率', value: 'module' },
  { label: '稀有度', value: 'rarity' },
  { label: '等级', value: 'level' }
]

export function surveySkillRate(survey, index) {
  const row = (survey?.skills || []).find((skill) => Number(skill.index) === Number(index))
  return row?.rate ?? null
}

export function surveyModuleRate(survey, id) {
  const row = (survey?.modules || []).find((module) => module.id === id)
  return row?.rate ?? null
}

// 全部技能（含已专三），名字优先取后端推荐行，其次取后端 skill_names，最后回退序数。
export function operatorSkillRows(operator) {
  if (!operator) return []
  const levels = operator.skill_levels || []
  const recommendations = operator.recommendations || []
  const names = operator.skill_names || []
  const count = Math.max(
    levels.length,
    names.length,
    ...recommendations.map((row) => Number(row.skill_index) + 1),
    0
  )
  if (!count) return []
  return Array.from({ length: count }, (_, index) => {
    const rec = recommendations.find((row) => Number(row.skill_index) === index)
    return {
      index,
      name: rec?.skill_name || names[index] || ORDINALS[index] + '技能',
      current: Number(levels[index] ?? rec?.current_level ?? 0)
    }
  })
}

// 后端 recommendations 只包含未专三技能；这里再过滤一次，兼容测试夹具与旧数据。
export function remainingSkillTargets(operator, survey) {
  const rows = operatorSkillRows(operator)
  return (operator?.recommendations || [])
    .filter((rec) => Number(rec.current_level) < 3)
    .map((rec) => {
      const index = Number(rec.skill_index)
      return {
        kind: 'skill',
        index,
        id: 'skill:' + index,
        name: rec.skill_name || rows[index]?.name || ORDINALS[index] + '技能',
        current: Number(rec.current_level) || 0,
        target: 3,
        rate: surveySkillRate(survey, index)
      }
    })
}

export function remainingModuleTargets(operator, survey) {
  return (operator?.modules || [])
    .filter((module) => Number(module.current_level) < Number(module.max_level))
    .map((module) => ({
      kind: 'module',
      id: module.id,
      name: module.type || module.name || '模组',
      current: Number(module.current_level) || 0,
      target: Number(module.max_level) || 0,
      rate: surveyModuleRate(survey, module.id)
    }))
}

function topRate(targets) {
  const rates = targets
    .map((target) => target.rate)
    .filter((rate) => rate !== null && rate !== undefined)
  return rates.length ? Math.max(...rates) : null
}

export function remainingSkillRate(operator, survey) {
  return topRate(remainingSkillTargets(operator, survey))
}

export function remainingModuleRate(operator, survey) {
  return topRate(remainingModuleTargets(operator, survey))
}

export function remainingLevelTarget(operator) {
  if (!operator) return null
  const fullGoal = (operator.level_goals || []).find((goal) =>
    ['elite2_max', 'level_max'].includes(goal.id)
  )
  const rarity = Number(operator.rarity)
  const legacyCap = {
    1: { elite: 0, level: 30 },
    2: { elite: 0, level: 30 },
    3: { elite: 1, level: 55 },
    4: { elite: 2, level: 70 },
    5: { elite: 2, level: 80 },
    6: { elite: 2, level: 90 }
  }[rarity]
  const validCap = (elite, level) =>
    Number.isInteger(elite) && elite >= 0 && Number.isInteger(level) && level > 0
  // 接口的资源上限优先；旧快照其次使用满级目标，最后兼容已知星级上限。
  const resourceElite = Number(operator.max_phase ?? NaN)
  const resourceLevel = Number(operator.max_level ?? NaN)
  const goalElite = Number(fullGoal?.elite ?? NaN)
  const goalLevel = Number(fullGoal?.level ?? NaN)
  const cap = validCap(resourceElite, resourceLevel)
    ? { elite: resourceElite, level: resourceLevel }
    : validCap(goalElite, goalLevel)
      ? { elite: goalElite, level: goalLevel }
      : legacyCap
  if (!cap) return null
  const currentElite = Number(operator.elite) || 0
  const currentLevel = Number(operator.level) || 1
  if (currentElite > cap.elite || (currentElite === cap.elite && currentLevel >= cap.level))
    return null
  return {
    kind: 'level',
    id: fullGoal?.id || (cap.elite >= 2 ? 'elite2_max' : 'level_max'),
    name: '满级',
    elite: cap.elite,
    level: cap.level,
    currentElite,
    currentLevel,
    rate: null
  }
}

// 等级与模组排序陈述对应的剩余目标；其他排序优先陈述未专三技能，再回退到未满模组。
export function recommendedTarget(operator, survey, sort = 'mastery') {
  if (sort === 'level') return remainingLevelTarget(operator)
  if (sort !== 'module') {
    const skills = remainingSkillTargets(operator, survey)
      .filter((target) => target.rate !== null && target.rate !== undefined)
      .sort((left, right) => right.rate - left.rate || left.index - right.index)
    if (skills.length) return skills[0]
  }
  const modules = remainingModuleTargets(operator, survey)
    .filter((target) => target.rate !== null && target.rate !== undefined)
    .sort((left, right) => right.rate - left.rate)
  return modules[0] || null
}

export function recommendationScore(operator, survey, sort = 'mastery') {
  return recommendedTarget(operator, survey, sort)?.rate ?? null
}

// 等级排序只保留未满级干员；其他排序沿用技能或模组尚未完成的候选。
export function hasRemainingTarget(operator, sort = 'mastery') {
  if (sort === 'level') return remainingLevelTarget(operator) !== null
  return remainingSkillTargets(operator).length > 0 || remainingModuleTargets(operator).length > 0
}

function cardRate(card, kind) {
  return kind === 'module'
    ? remainingModuleRate(card.operator, card.survey)
    : remainingSkillRate(card.operator, card.survey)
}

function cardTieBreak(left, right) {
  return (
    (Number(right.operator?.rarity) || 0) - (Number(left.operator?.rarity) || 0) ||
    String(left.operator?.name || '').localeCompare(String(right.operator?.name || ''), 'zh-CN')
  )
}

export function compareRecommendedCards(left, right, sort = 'mastery') {
  const leftScore = recommendationScore(left.operator, left.survey) ?? -1
  const rightScore = recommendationScore(right.operator, right.survey) ?? -1
  if (sort === 'rarity') {
    return cardTieBreak(left, right) || rightScore - leftScore
  }
  if (sort === 'level') {
    return (
      (Number(right.operator?.elite) || 0) - (Number(left.operator?.elite) || 0) ||
      (Number(right.operator?.level) || 0) - (Number(left.operator?.level) || 0) ||
      rightScore - leftScore ||
      cardTieBreak(left, right)
    )
  }
  const kind = sort === 'module' ? 'module' : 'skill'
  return (cardRate(right, kind) ?? -1) - (cardRate(left, kind) ?? -1) || cardTieBreak(left, right)
}

export function sortRecommendedCards(cards, sort = 'mastery') {
  return [...cards].sort((left, right) => compareRecommendedCards(left, right, sort))
}
