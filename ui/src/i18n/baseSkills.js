import { i18n } from '@/i18n'
import { baseSkillMessages } from './messages/baseSkills'
import { planDisplayName } from './plans'

const labelKeys = new Map(
  Object.entries(baseSkillMessages['zh-CN'])
    .filter(([, value]) => typeof value === 'string')
    .map(([key, value]) => [value, key])
)

export function baseGroupTitle(group) {
  return i18n.global.te(`baseSkills.groupsById.${group.id}.title`)
    ? i18n.global.t(`baseSkills.groupsById.${group.id}.title`)
    : group.title
}

export function baseGroupNote(group) {
  return i18n.global.te(`baseSkills.groupsById.${group.id}.note`)
    ? i18n.global.t(`baseSkills.groupsById.${group.id}.note`)
    : group.note
}

export function baseSkillText(value) {
  const key = labelKeys.get(value)
  return key
    ? i18n.global.t(`baseSkills.${key}`)
    : planDisplayName(value === '中枢' ? '控制中枢' : value)
}

export function baseSkillProgression(value) {
  if (i18n.global.locale.value === 'zh-CN') return value
  const match = /^精(?:英)?(\d+)\s+(\d+)级$/.exec(value || '')
  return match
    ? i18n.global.t('baseSkills.progression', { phase: match[1], level: match[2] })
    : value
}
