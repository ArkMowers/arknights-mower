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

// 推荐目标：优先取还没专三技能里公开专三率最高的一个；技能全部专三后再看未满模组。
export function recommendedTarget(operator, survey) {
  const skills = remainingSkillTargets(operator, survey)
    .filter((target) => target.rate !== null)
    .sort((left, right) => right.rate - left.rate || left.index - right.index)
  if (skills.length) return skills[0]
  const modules = remainingModuleTargets(operator, survey)
    .filter((target) => target.rate !== null)
    .sort((left, right) => right.rate - left.rate)
  return modules[0] || null
}

export function recommendationScore(operator, survey) {
  return recommendedTarget(operator, survey)?.rate ?? null
}

// 只要还有没练完的目标就保留在值得练里；公开样本缺失时排在有样本的干员之后。
export function hasRemainingTarget(operator) {
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
