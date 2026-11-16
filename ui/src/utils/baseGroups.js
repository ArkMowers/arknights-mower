import { pinyin_match } from './common'
import { builtinGroups, singleRecommendations } from '@/data/baseGroups'

export const groupFacilities = [
  '通用',
  '经验',
  '金属',
  '源石',
  '贸易',
  '发电',
  '中枢',
  '办公',
  '会客',
  '回收'
].filter((value) =>
  [...builtinGroups, ...singleRecommendations].some((group) => group.facility === value)
)

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
  { search = '', facility = null, ownership = null, recovery = {} } = {}
) {
  const query = search.trim()
  return groups.filter((group) => {
    if (facility && group.facility !== facility) return false
    const text = [
      group.title,
      group.note,
      recovery[group.id]?.description || '',
      recovery[group.id] ? '宿舍恢复' : '',
      ...group.core,
      ...group.support,
      ...group.accessory,
      ...Object.values(group.memberNotes),
      ...(
        builtinGroups.find((parent) => parent.id === (group.parentId || group.id))?.variants || []
      ).flatMap((variant) => [
        variant.title,
        variant.note,
        ...variant.core,
        ...variant.support,
        ...variant.accessory
      ])
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

export function groupSingleRecommendations(groups, estimates, recovery = {}) {
  const buckets = new Map()
  for (const group of groups) {
    if (group.kind === 'roster') {
      buckets.set(group.id, {
        id: group.id,
        facility: group.facility,
        roster: true,
        groups: [group]
      })
      continue
    }
    if (group.facility === '中枢') {
      const key = 'control-' + group.effect
      if (!buckets.has(key))
        buckets.set(key, {
          id: key,
          facility: group.facility,
          control: true,
          effect: group.effect,
          title: '中枢 · ' + group.effect,
          groups: []
        })
      buckets.get(key).groups.push(group)
      continue
    }
    const estimate = estimates[group.id]
    const primary = estimate.valid
      ? estimate.metrics.find((metric) => metric.unit === '%') || estimate.metrics[0]
      : undefined
    const average = estimate.details.some((line) => line.includes('用尽') || line.includes('暖机'))
    const key = JSON.stringify([
      group.facility,
      primary?.label,
      primary?.value,
      primary?.unit,
      average
    ])
    if (!buckets.has(key))
      buckets.set(key, { id: key, facility: group.facility, metric: primary, average, groups: [] })
    buckets.get(key).groups.push(group)
  }
  for (const section of buckets.values()) {
    if (!section.roster)
      section.groups.sort(
        (a, b) =>
          Number(Boolean(recovery[b.id]?.available)) - Number(Boolean(recovery[a.id]?.available))
      )
  }
  return [...buckets.values()].sort((a, b) => {
    const facilityOrder = groupFacilities.indexOf(a.facility) - groupFacilities.indexOf(b.facility)
    if (facilityOrder) return facilityOrder
    if (a.control && b.control) {
      const order = ['制造支援', '贸易支援', '制造 / 贸易切换', '办公支援', '会客支援', '心情支援']
      return order.indexOf(a.effect) - order.indexOf(b.effect)
    }
    if (a.roster || b.roster) return Number(Boolean(b.roster)) - Number(Boolean(a.roster))
    if (!a.metric || !b.metric) return Number(!a.metric) - Number(!b.metric)
    if (a.metric.unit !== b.metric.unit) return a.metric.unit === '%' ? -1 : 1
    return a.metric.unit === '/小时'
      ? a.metric.value - b.metric.value
      : b.metric.value - a.metric.value
  })
}
