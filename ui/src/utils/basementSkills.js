import { match } from 'pinyin-pro'

export const ownershipLabels = { owned: '已拥有', unowned: '未拥有' }
export const skillStatusLabels = {
  active: '已解锁',
  locked: '未解锁',
  replaced: '已替换',
  unowned: '未拥有'
}

export function annotateBasementSkills(catalog, snapshot) {
  const roster = new Map(
    snapshot?.has_data && Array.isArray(snapshot.operators)
      ? snapshot.operators.map((operator) => [operator.name, operator])
      : []
  )
  return catalog.map((operator) => {
    const growth = roster.get(operator.name)
    const ownership =
      growth?.owned === true ? 'owned' : growth?.owned === false ? 'unowned' : 'unknown'
    const statuses = new Map(
      (growth?.skills || []).map((skill) => [
        `${skill.skill_key}:${skill.skill_level}`,
        skill.status
      ])
    )
    return {
      key: operator.name,
      avatar: operator.name,
      ownership,
      progression:
        ownership === 'owned' && Number.isInteger(growth.phase) && Number.isInteger(growth.level)
          ? `精${growth.phase} ${growth.level}级`
          : '',
      childSkill: operator.child_skill.map((skill) => {
        const status = statuses.get(`${skill.skill_key}:${skill.skill_level}`)
        return {
          ...skill,
          status:
            ownership === 'unowned'
              ? 'unowned'
              : ownership === 'owned' && Object.hasOwn(skillStatusLabels, status)
                ? status
                : 'unknown'
        }
      })
    }
  })
}

function matches(text, query, precision) {
  return !query || text.includes(query) || Boolean(match(text, query, { precision }))
}

export function filterBasementSkills(items, filters) {
  const name = (filters.name || '').trim()
  const description = (filters.description || '').trim()
  return items.flatMap((item) => {
    if (!matches(item.avatar, name, 'start')) return []
    if (filters.ownership && filters.ownership !== item.ownership) return []
    const childSkill = item.childSkill.filter(
      (skill) =>
        (!filters.facility || skill.roomType === filters.facility) &&
        (!filters.status || skill.status === filters.status) &&
        matches(`${skill.skillname} ${skill.des.replace(/<[^>]*>/g, '')}`, description, 'every')
    )
    return childSkill.length ? [{ ...item, childSkill, span: childSkill.length }] : []
  })
}
