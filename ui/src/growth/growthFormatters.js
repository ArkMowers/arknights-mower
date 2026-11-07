export const professionMap = {
  WARRIOR: '近卫',
  SNIPER: '狙击',
  TANK: '重装',
  MEDIC: '医疗',
  SUPPORT: '辅助',
  CASTER: '术师',
  SPECIAL: '特种',
  PIONEER: '先锋'
}

export const professions = ['先锋', '近卫', '重装', '狙击', '术师', '医疗', '辅助', '特种']

export function professionName(profession) {
  return professionMap[profession] || profession || '未知职业'
}

export function eliteLabel(elite) {
  if (elite === null || elite === undefined || elite === 0) return '精零'
  return ['精零', '精一', '精二'][elite] || '精' + elite
}

export function masteryLabel(level) {
  return ['未专精', '专一', '专二', '专三'][level] ?? '专' + (level ?? 0)
}

export function masteryMark(level) {
  return ['', '一', '二', '三'][level] || ''
}

export function formatDuration(seconds) {
  const value = Number(seconds)
  if (!Number.isFinite(value) || value <= 0) return '—'
  const hours = Math.floor(value / 3600)
  const minutes = Math.floor((value % 3600) / 60)
  if (hours > 0 && minutes > 0) return hours + ' 小时 ' + minutes + ' 分'
  if (hours > 0) return hours + ' 小时'
  return (minutes || 1) + ' 分钟'
}

export function formatRate(rate) {
  if (rate === null || rate === undefined) return '暂无样本'
  return rate.toFixed(1) + '%'
}

export function formatCompactNumber(value) {
  const number = Number(value)
  if (!Number.isFinite(number)) return '—'
  if (Math.abs(number) >= 1000000) return (number / 1000000).toFixed(1) + 'M'
  if (Math.abs(number) >= 10000) return (number / 10000).toFixed(1) + ' 万'
  return number.toLocaleString('zh-CN')
}

export function gradeLabel(rarity) {
  return rarity ? rarity + '★' : ''
}

export function materialIcon(material) {
  if (!material) return ''
  const name = material.id === 'growth_exp' ? 'EXP' : material.name
  return '/depot/' + encodeURIComponent(name) + '.webp'
}

export function skillSummaryLabel(operator, recommendation) {
  if (!recommendation) return ''
  const target = recommendation.target_level || 3
  return (
    recommendation.skill_name +
    ' · ' +
    masteryLabel(recommendation.current_level) +
    ' → ' +
    masteryLabel(target)
  )
}

export function goalLabel(operator, goal) {
  if (!operator || !goal) return goal?.module_id || ''
  const levelGoal = (operator.level_goals || []).find((row) => row.id === goal.module_id)
  if (levelGoal?.label) return levelGoal.label
  if (goal.module_id === 'elite1') return '精一 1 级'
  if (goal.module_id === 'elite2') return '精二 1 级'
  if (goal.module_id === 'elite2_module') return '达到模组开启等级'
  if (goal.module_id === 'elite2_max') return '满练'
  if (goal.module_id === 'level_max') return '满练'
  if (goal.module_id === 'skill7') return '基础技能 7 级'
  const currentModule = (operator.modules || []).find((entry) => entry.id === goal.module_id)
  if (!currentModule) return goal.module_id
  const level = goal.target_level || currentModule.max_level || 1
  return (currentModule.name || currentModule.type || goal.module_id) + ' · 模组 ' + level + ' 级'
}

export const planStatusLabels = {
  idle: '待执行',
  arranging: '安排中',
  training: '训练中',
  waiting_collect: '待收取',
  waiting: '等待材料',
  failed: '执行失败',
  completed: '已完成',
  manual: '待完成'
}

export function planStatusLabel(status) {
  return planStatusLabels[status] || '待执行'
}
