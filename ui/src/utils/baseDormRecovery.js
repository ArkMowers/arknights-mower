import catalog from '../../../arknights_mower/data/building_skill.json'
import { hasValidProgression } from './basementSkills'

const skillsByName = new Map(catalog.map((operator) => [operator.name, operator.child_skill]))
const isRecovery = (skill) => skill.roomType === '宿舍' && skill.buffCategory === 'RECOVERY'
function highestVersions(skills) {
  const slots = new Map()
  for (const skill of skills) {
    if (!slots.has(skill.skill_key) || slots.get(skill.skill_key).skill_level < skill.skill_level)
      slots.set(skill.skill_key, skill)
  }
  return [...slots.values()]
}
function recoveryDescription(skill) {
  return skill.des
    .replace(/<[^>]*>/g, '')
    .replace(/^进驻宿舍时，(?:使)?/, '')
    .replaceAll('该宿舍内除自身以外心情未满的某个干员每小时恢复', '其他一名未满心情干员')
    .replace(/该宿舍内所有干员的?心情每小时恢复/g, '全体')
    .replaceAll('自身心情每小时恢复', '自身')
    .replaceAll('同时该宿舍每有1名心情未满的干员，则恢复效果额外', '每名未满心情干员额外')
    .replaceAll('当前宿舍每级为恢复效果额外', '每级宿舍额外')
    .replaceAll('同时每个招募位（不包含初始招募位）额外', '每个额外招募位')
    .replaceAll('恢复效果', '')
    .replaceAll('同种效果取最高', '同类取最高')
    .replaceAll('叠加后的最终值同类取最高', '叠加后同类取最高')
}

// Summaries retain catalog values and conditions; they do not estimate total dormitory recovery.
export function dormRecoveryFor(name, item) {
  const source = skillsByName.get(name) || []
  const maximum = highestVersions(source).filter(isRecovery)
  if (!maximum.length) return null
  const known = hasValidProgression(item)
  const active = known
    ? highestVersions(
        source.filter((skill) =>
          item.childSkill.some(
            (entry) =>
              entry.skill_key === skill.skill_key &&
              entry.skill_level === skill.skill_level &&
              entry.status === 'active'
          )
        )
      ).filter(isRecovery)
    : maximum
  const skills = active.length ? active : maximum
  return {
    available: active.length > 0,
    description: skills.map(recoveryDescription).join('；'),
    unlock: skills.map((skill) => skill.phase_level).join('、'),
    inactive:
      !active.length &&
      maximum.some((skill) =>
        item?.childSkill?.some(
          (entry) =>
            entry.skill_key === skill.skill_key &&
            entry.skill_level === skill.skill_level &&
            entry.status === 'locked'
        )
      )
        ? '当前未解锁'
        : '当前未生效'
  }
}
