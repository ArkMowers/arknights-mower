import { i18n } from '@/i18n'
import { itemDisplayName, skillDisplayName } from '@/i18n/gameNames'
import { localizedLevelGoalLabel } from '@/utils/growthPlanning'

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
  const code = Object.hasOwn(professionMap, profession)
    ? profession
    : Object.keys(professionMap).find((key) => professionMap[key] === profession)
  return code
    ? i18n.global.t(`growth.format.profession${code}`)
    : profession || i18n.global.t('growth.format.unknownProfession')
}

export function eliteLabel(elite) {
  if (elite === null || elite === undefined || elite === 0)
    return i18n.global.t('growth.format.elite0')
  return (
    [
      i18n.global.t('growth.format.elite0'),
      i18n.global.t('growth.format.elite1'),
      i18n.global.t('growth.format.elite2')
    ][elite] || i18n.global.t('growth.format.elite', { level: elite })
  )
}

export function masteryLabel(level) {
  return (
    [
      i18n.global.t('growth.format.unmastered'),
      i18n.global.t('growth.format.mastery1'),
      i18n.global.t('growth.format.mastery2'),
      i18n.global.t('growth.format.mastery3')
    ][level] ?? i18n.global.t('growth.format.mastery', { level: level ?? 0 })
  )
}

export function masteryMark(level) {
  return level >= 1 && level <= 3 ? i18n.global.t(`growth.format.ordinal${level}`) : ''
}

export function formatDuration(seconds) {
  const value = Number(seconds)
  if (!Number.isFinite(value) || value <= 0) return '—'
  const hours = Math.floor(value / 3600)
  const minutes = Math.floor((value % 3600) / 60)
  if (hours > 0 && minutes > 0)
    return i18n.global.t('growth.format.hoursMinutes', { hours, minutes })
  if (hours > 0) return i18n.global.t('growth.format.hours', { hours })
  return i18n.global.t('growth.format.minutes', { minutes: minutes || 1 })
}

export function formatRate(rate) {
  if (rate === null || rate === undefined) return i18n.global.t('growth.format.noSample')
  return rate.toFixed(1) + '%'
}

export function formatCompactNumber(value) {
  const number = Number(value)
  if (!Number.isFinite(number)) return '—'
  if (i18n.global.locale.value !== 'zh-CN' && i18n.global.locale.value !== 'zh-TW') {
    if (Math.abs(number) >= 1000000000) return (number / 1000000000).toFixed(1) + 'B'
    if (Math.abs(number) >= 1000000) return (number / 1000000).toFixed(1) + 'M'
    if (Math.abs(number) >= 1000) return (number / 1000).toFixed(1) + 'k'
    return number.toLocaleString(i18n.global.locale.value)
  }
  if (Math.abs(number) >= 1000000) return (number / 1000000).toFixed(1) + 'M'
  if (Math.abs(number) >= 10000) return (number / 10000).toFixed(1) + ' 万'
  return number.toLocaleString(i18n.global.locale.value)
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
    skillDisplayName(recommendation.skill_name) +
    ' · ' +
    masteryLabel(recommendation.current_level) +
    ' → ' +
    masteryLabel(target)
  )
}

export function goalLabel(operator, goal) {
  if (!operator || !goal) return goal?.module_id || ''
  const levelGoal = (operator.level_goals || []).find((row) => row.id === goal.module_id)
  if (levelGoal?.label) return localizedLevelGoalLabel(levelGoal)
  if (goal.module_id === 'elite1') return i18n.global.t('growth.format.elite1Level1')
  if (goal.module_id === 'elite2') return i18n.global.t('growth.format.elite2Level1')
  if (goal.module_id === 'elite2_module') return i18n.global.t('growth.format.moduleUnlockLevel')
  if (goal.module_id === 'elite2_max' || goal.module_id === 'level_max')
    return i18n.global.t('growth.format.maxed')
  if (goal.module_id === 'skill7') return i18n.global.t('growth.format.basicSkill7')
  const currentModule = (operator.modules || []).find((entry) => entry.id === goal.module_id)
  if (!currentModule) return goal.module_id
  const level = goal.target_level || currentModule.max_level || 1
  return i18n.global.t('growth.format.moduleLevel', {
    name: currentModule.name || currentModule.type || goal.module_id,
    level
  })
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
  const key = Object.hasOwn(planStatusLabels, status) ? status : 'idle'
  return i18n.global.t(`growth.format.status${key}`)
}

export function materialDisplayName(id, original) {
  return id === 'growth_exp' || (original ?? id) === '作战记录经验'
    ? i18n.global.t('growth.format.experience')
    : itemDisplayName(id, original)
}
