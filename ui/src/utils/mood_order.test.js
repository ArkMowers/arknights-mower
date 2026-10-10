import { describe, expect, it } from 'vitest'
import {
  LEGACY_MOOD_GROUP_ORDER_KEY,
  MOOD_ORDER_KEY,
  normalizeMoodPreferences,
  orderMoodDatasets,
  orderMoodGroups,
  readMoodPreferences,
  reorderedGroupNames,
  saveMoodPreferences
} from './mood_order'

const group = (name, ...operators) => ({
  groupName: name,
  moodData: { datasets: operators.map((label) => ({ label, data: [{ x: 1, y: 12 }] })) }
})
const names = (groups) => groups.map(({ groupName }) => groupName)
const storage = () => {
  const data = new Map()
  return {
    getItem: (key) => data.get(key) ?? null,
    setItem: (key, value) => data.set(key, value)
  }
}

describe('mood priority preferences', () => {
  it('reads the existing reportDataOrder without adding arbitrary priorities', () => {
    const s = storage()
    s.setItem(LEGACY_MOOD_GROUP_ORDER_KEY, JSON.stringify(['乙组', '甲组']))
    expect(readMoodPreferences(s)).toEqual({
      groupOrder: ['乙组', '甲组'],
      pinnedGroups: [],
      pinnedOperators: []
    })
  })

  it('safely handles malformed, absent or inaccessible stored preferences', () => {
    const s = storage()
    s.setItem(MOOD_ORDER_KEY, '{oops')
    s.setItem(LEGACY_MOOD_GROUP_ORDER_KEY, '{oops')
    expect(readMoodPreferences(s)).toEqual({
      groupOrder: [],
      pinnedGroups: [],
      pinnedOperators: []
    })
    expect(
      readMoodPreferences({
        getItem: () => {
          throw Error('blocked')
        }
      }).groupOrder
    ).toEqual([])
    expect(
      saveMoodPreferences(
        {
          setItem: () => {
            throw Error('blocked')
          }
        },
        {}
      )
    ).toBe(false)
  })

  it('normalizes duplicate or empty selection values', () => {
    expect(
      normalizeMoodPreferences({
        groupOrder: ['甲组', '甲组', '', 12],
        pinnedGroups: ['乙组', '乙组'],
        pinnedOperators: ['能天使', '能天使', null]
      })
    ).toEqual({
      groupOrder: ['甲组'],
      pinnedGroups: ['乙组'],
      pinnedOperators: ['能天使']
    })
  })

  it('saves group and operator preferences and mirrors legacy group ordering', () => {
    const s = storage()
    const data = {
      groupOrder: ['乙组', '甲组'],
      pinnedGroups: ['甲组'],
      pinnedOperators: ['能天使']
    }
    expect(saveMoodPreferences(s, data)).toBe(true)
    expect(readMoodPreferences(s)).toEqual(data)
    expect(JSON.parse(s.getItem(LEGACY_MOOD_GROUP_ORDER_KEY))).toEqual(data.groupOrder)
  })

  it('places pinned groups before groups containing prioritized operators', () => {
    const raw = [group('普通组', '阿米娅'), group('干员组', '能天使'), group('置顶组', '煌')]
    const result = orderMoodGroups(raw, {
      pinnedGroups: ['置顶组'],
      pinnedOperators: ['能天使']
    })
    expect(names(result)).toEqual(['置顶组', '干员组', '普通组'])
    expect(names(raw)).toEqual(['普通组', '干员组', '置顶组'])
  })

  it('uses the earliest matching operator priority for multi-operator groups', () => {
    const raw = [group('乙组', '塞雷娅'), group('甲组', '能天使'), group('丙组', '煌')]
    expect(
      names(
        orderMoodGroups(raw, {
          pinnedOperators: ['能天使', '塞雷娅']
        })
      )
    ).toEqual(['甲组', '乙组', '丙组'])
  })

  it('puts previously ordered groups ahead of new names while keeping unlisted stable', () => {
    const raw = [group('新组甲'), group('已保存甲'), group('新组乙'), group('已保存乙')]
    expect(
      names(
        orderMoodGroups(raw, {
          groupOrder: ['已不存在', '已保存乙', '已保存甲']
        })
      )
    ).toEqual(['已保存乙', '已保存甲', '新组甲', '新组乙'])
  })

  it('keeps unchanged groups stable without any user preferences', () => {
    const raw = [group('甲组'), group('乙组')]
    expect(names(orderMoodGroups(raw, {}))).toEqual(['甲组', '乙组'])
    expect(orderMoodGroups(null, {})).toEqual([])
  })

  it('prioritizes operators inside each group without mutating source datasets', () => {
    const raw = [group('甲组', '阿米娅', '能天使', '煌')]
    const sorted = orderMoodGroups(raw, { pinnedOperators: ['煌', '能天使'] })
    expect(sorted[0].moodData.datasets.map((d) => d.label)).toEqual(['煌', '能天使', '阿米娅'])
    expect(raw[0].moodData.datasets.map((d) => d.label)).toEqual(['阿米娅', '能天使', '煌'])
    expect(orderMoodDatasets(null, ['煌'])).toEqual([])
  })

  it('handles operator-less groups and unknown priority names', () => {
    const raw = [group('空组'), group('普通组', '阿米娅')]
    expect(names(orderMoodGroups(raw, { pinnedOperators: ['未知干员'] }))).toEqual([
      '空组',
      '普通组'
    ])
  })

  it('persists the visible manual order without losing a group', () => {
    const raw = [group('甲组'), group('乙组'), group('丙组')]
    expect(reorderedGroupNames(raw, '甲组', '丙组')).toEqual(['乙组', '丙组', '甲组'])
    expect(reorderedGroupNames(raw, '无效组', '甲组')).toEqual(['甲组', '乙组', '丙组'])
  })

  it('does not read or write storage when it is unavailable', () => {
    expect(readMoodPreferences(null).pinnedGroups).toEqual([])
    expect(saveMoodPreferences(null, {})).toBe(false)
  })
})
