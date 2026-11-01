import { pinyin_match } from './common'
import { builtinGroups } from '@/data/baseGroups'

export const groupFacilities = [...new Set(builtinGroups.map((group) => group.facility))]

export function groupMembers(group, items) {
  const operators = new Map(items.map((operator) => [operator.avatar, operator]))
  return [
    ...group.core.map((name) => [name, 'core']),
    ...group.support.map((name) => [name, 'support']),
    ...group.accessory.map((name) => [name, 'accessory'])
  ].map(([name, role]) => ({
    name,
    role,
    note: group.memberNotes[name] || '',
    ownership: operators.get(name)?.ownership || 'unknown',
    progression: operators.get(name)?.progression || ''
  }))
}

export function filterGroups(
  groups,
  items,
  { search = '', facility = null, ownership = null } = {}
) {
  const query = search.trim()
  return groups.filter((group) => {
    if (facility && group.facility !== facility) return false
    const text = [
      group.title,
      group.note,
      ...group.core,
      ...group.support,
      ...group.accessory,
      ...Object.values(group.memberNotes)
    ].join(' ')
    if (query && !text.includes(query) && !pinyin_match(text, query, { precision: 'every' }))
      return false
    const members = groupMembers(group, items)
    if (ownership === 'core-owned')
      return members
        .filter((member) => member.role === 'core')
        .every((member) => member.ownership === 'owned')
    if (ownership === 'missing') return members.some((member) => member.ownership === 'unowned')
    if (ownership === 'unknown') return members.some((member) => member.ownership === 'unknown')
    return true
  })
}
