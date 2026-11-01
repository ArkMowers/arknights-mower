export const surveyThresholds = [90, 80, 70, 60, 50, 40, 30, 20, 10, 0.325]
export const surveyDimensions = [
  { key: 'mastery', label: '专三率', detail: '高亮达到比例的技能' },
  { key: 'module', label: '模组解锁率', detail: '高亮达到比例的模组' },
  { key: 'elite1', label: '精一率', detail: '样本已达到精一或精二' },
  { key: 'elite2', label: '精二率', detail: '高亮达到比例的干员' }
]

export function defaultSurveyFilters() {
  return {
    mastery: null,
    module: null,
    elite1: null,
    elite2: null,
    hideCompleted: true,
    sort: 'default'
  }
}

export function surveyRate(row, field, ranks) {
  if (!row || !(row.own > 0) || !row[field]) return null
  const counts = Object.values(row[field])
  if (
    !counts.length ||
    counts.some((count) => !Number.isInteger(count) || count < 0) ||
    counts.reduce((sum, count) => sum + count, 0) !== row.own
  )
    return null
  const count = ranks.reduce((sum, rank) => sum + (row[field][rank] || 0), 0)
  return Math.min(100, (count / row.own) * 100)
}

export function moduleSurveyField(module) {
  const suffix = module.type?.split('-').at(-1)
  return ['A', 'B', 'X', 'Y', 'D'].includes(suffix) ? `mod${suffix}` : null
}

export function operatorSurvey(op, row, filters) {
  const maxPhase = op.max_phase ?? (op.rarity < 3 ? 0 : op.rarity === 3 ? 1 : 2)
  const supportsMastery = maxPhase >= 2
  const skills = (supportsMastery ? op.skill_levels || [] : []).map((current, index) => ({
    index,
    current,
    rate: surveyRate(row, `skill${index + 1}`, [3])
  }))
  // Older cached rosters still provide levels for their unfinished skills.
  for (const rec of supportsMastery ? op.recommendations || [] : []) {
    if (!skills.some((skill) => skill.index === rec.skill_index))
      skills.push({
        index: rec.skill_index,
        current: rec.current_level,
        rate: surveyRate(row, `skill${rec.skill_index + 1}`, [3])
      })
  }
  const modules = (op.modules || []).map((module) => ({
    id: module.id,
    current: module.current_level,
    rate: surveyRate(row, moduleSurveyField(module), [1, 2, 3])
  }))
  const qualifies = (rate, threshold) => threshold !== null && rate !== null && rate >= threshold
  const selectedSkills = skills.filter((skill) => qualifies(skill.rate, filters.mastery))
  const selectedModules = modules.filter((module) => qualifies(module.rate, filters.module))
  const elite1 = surveyRate(row, 'elite', [1, 2])
  const elite2 = surveyRate(row, 'elite', [2])
  const first = maxPhase >= 1 && qualifies(elite1, filters.elite1)
  const second = maxPhase >= 2 && qualifies(elite2, filters.elite2)
  const outstanding =
    selectedSkills.some((skill) => skill.current < 3) ||
    selectedModules.some((module) => !module.current) ||
    (first && op.elite < 1) ||
    (second && op.elite < 2)
  const active = surveyDimensions.some(({ key }) => filters[key] !== null)
  const knownLevel = (level) => Number.isInteger(level) && level >= 0 && level <= 3
  const coverage =
    (filters.mastery === null ||
      !supportsMastery ||
      (skills.length > 0 &&
        skills.every((skill) => skill.rate !== null && knownLevel(skill.current)))) &&
    (filters.module === null ||
      modules.every((module) => module.rate !== null && knownLevel(module.current))) &&
    (filters.elite1 === null || maxPhase < 1 || (elite1 !== null && knownLevel(op.elite))) &&
    (filters.elite2 === null || maxPhase < 2 || (elite2 !== null && knownLevel(op.elite)))
  return {
    skills,
    modules,
    elite1,
    elite2,
    skillHighlights: selectedSkills.map((skill) => skill.index),
    moduleHighlights: selectedModules.map((module) => module.id),
    eliteHighlight: first || second,
    known: Boolean(row?.own > 0),
    visible: !filters.hideCompleted || !active || !row?.own || !coverage || outstanding,
    score: Math.max(
      0,
      ...selectedSkills.map((skill) => skill.rate),
      ...selectedModules.map((module) => module.rate),
      first ? elite1 : 0,
      second ? elite2 : 0
    )
  }
}

export function formatSurveyRate(rate) {
  return rate === null || rate === undefined ? '暂无样本' : `${rate.toFixed(1)}%`
}
