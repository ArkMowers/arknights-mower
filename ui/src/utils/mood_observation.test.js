import { describe, expect, it } from 'vitest'
import {
  MAX_MOOD_VIEWS,
  MOOD_VIEWS_KEY,
  buildObservationGroups,
  mergeOperatorCatalog,
  normalizeMoodViews,
  orderedBoardNames,
  readMoodViews,
  saveMoodViews
} from './mood_observation'
import { moodBadgeBackground, moodStroke } from './mood_colors'

const storage = () => {
  const map = new Map()
  return {
    getItem: (key) => map.get(key) || null,
    setItem: (key, value) => map.set(key, value)
  }
}
const view = (id, name, operators) => ({ id, name, operators })

describe('custom mood observation boards', () => {
  it('normalizes invalid, duplicate, oversized and extra entries', () => {
    const raw = [
      view('abcd', '甲表', ['阿米娅', '阿米娅', '  煌  ', '', null]),
      view('abcd', '同 ID', ['煌']),
      view('../../oops', 'bad', ['煌']),
      view('bbbb', '', []),
      ...Array.from({ length: 18 }, (_, index) =>
        view('valid-' + index, '自选 ' + index, ['干员' + index])
      )
    ]
    const result = normalizeMoodViews(raw)
    expect(result).toHaveLength(MAX_MOOD_VIEWS)
    expect(result[0]).toEqual(view('abcd', '甲表', ['阿米娅', '煌']))
    expect(result.some((item) => item.name === 'bad')).toBe(false)
  })

  it('migrates no data when storage is missing or corrupt; roundtrips valid views', () => {
    const s = storage()
    expect(readMoodViews(s)).toEqual([])
    s.setItem(MOOD_VIEWS_KEY, '{oops')
    expect(readMoodViews(s)).toEqual([])
    const views = [view('card-1', '重点', ['阿米娅', '煌'])]
    expect(saveMoodViews(s, views)).toBe(true)
    expect(readMoodViews(s)).toEqual(views)
    expect(
      saveMoodViews(
        {
          setItem: () => {
            throw Error('private mode')
          }
        },
        views
      )
    ).toBe(false)
  })

  it('can combine two original groups into one virtual card without mutating raw data', () => {
    const groups = [
      { groupName: '一组', moodData: { datasets: [{ label: '阿米娅', data: [{ x: 1, y: 12 }] }] } },
      { groupName: '二组', moodData: { datasets: [{ label: '煌', data: [{ x: 2, y: 11 }] }] } }
    ]
    const selected = [view('custom-1', '我关注的', ['煌', '无记录', '阿米娅'])]
    const output = buildObservationGroups(selected, groups)
    expect(output[0].boardKey).toBe('custom:custom-1')
    expect(output[0].moodData.datasets.map((dataset) => dataset.label)).toEqual(['煌', '阿米娅'])
    expect(output[0].missing).toEqual(['无记录'])
    expect(groups[0].moodData.datasets[0].data).toEqual([{ x: 1, y: 12 }])
  })

  it('a long-term database series supersedes only its matching short default series', () => {
    const groups = [
      { groupName: '默认', moodData: { datasets: [{ label: '阿米娅', data: [{ x: 2, y: 12 }] }] } }
    ]
    const series = [
      {
        name: '阿米娅',
        data: [
          { x: 1, y: 14 },
          { x: 2, y: 12 }
        ]
      },
      { name: '低优先干员', data: [{ x: 1, y: 10 }] }
    ]
    const output = buildObservationGroups(
      [view('custom-2', '低优先也可看', ['低优先干员', '阿米娅'])],
      groups,
      series
    )
    expect(output[0].missing).toEqual([])
    expect(output[0].moodData.datasets[0].data[0].y).toBe(10)
    expect(output[0].moodData.datasets[1].data).toHaveLength(2)
  })

  it('unifies the manual card order while preserving cards hidden on the other page', () => {
    expect(
      orderedBoardNames(
        ['一组', 'custom:mine', '二组', '三组'],
        ['三组', '一组', '二组'],
        '三组',
        '一组'
      )
    ).toEqual(['三组', '一组', 'custom:mine', '二组'])
    expect(orderedBoardNames([], ['甲', '乙', '丙'], '甲', '丙')).toEqual(['乙', '丙', '甲'])
  })

  it('merges all historic operators with fallback recently reported operators', () => {
    const result = mergeOperatorCatalog(
      [{ name: '低优先干员', sampleCount: 9, lastRecordedAt: '2026-09-22' }],
      [{ moodData: { datasets: [{ label: '阿米娅', data: [{ x: '2026-09-23', y: 12 }] }] } }]
    )
    expect(result.map(({ name }) => name)).toEqual(['低优先干员', '阿米娅'])
    expect(result[1].sampleCount).toBe(1)
  })

  it('uses contrast-safe translucent badge fills and stable stroke colours', () => {
    expect(moodStroke(0)).toMatch(/^#[a-fA-F0-9]{6}$/)
    expect(moodStroke(1)).not.toBe(moodStroke(0))
    expect(moodBadgeBackground('#287FC0')).toBe('rgba(40, 127, 192, 0.14)')
    expect(moodBadgeBackground('invalid')).toBe('rgba(40, 127, 192, 0.14)')
  })
})
