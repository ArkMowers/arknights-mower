import { describe, expect, it } from 'vitest'
import { personalStatisticsRows, sumPersonalStatistics } from './operatorStatistics'

describe('个人干员统计', () => {
  const statistics = {
    rarities: {
      6: {
        owned: 2,
        available: 4,
        elite2: 1,
        sanity: 120,
        module_blocks: 4,
        consumed_exp: 500,
        consumed_lmd: 1000,
        skill_book_equivalent: 8,
        skills: { 1: 1, 2: 2, 3: 3 },
        modules: { 1: 1, 2: 1, 3: 2 },
        materials: [
          { id: 'a', name: '材料A', count: 2, value: 10, sanity: 20 },
          { id: 'x', name: '未知材料', count: 4, value: null, sanity: null }
        ],
        ranking: [{ char_id: 'six', name: '六星', sanity: 120, unpriced: ['x'] }]
      },
      5: {
        owned: 1,
        available: 5,
        elite2: 1,
        sanity: 150,
        module_blocks: 2,
        materials: [{ id: 'a', name: '材料A', count: 3, value: 10, sanity: 30 }],
        ranking: [{ char_id: 'five', name: '五星', sanity: 150, unpriced: [] }]
      }
    }
  }
  it('仅累加所选星级，材料按ID合并而未知价值保持未知', () => {
    const total = sumPersonalStatistics(statistics, [6, 5])
    expect(total).toMatchObject({
      owned: 3,
      available: 9,
      sanity: 270,
      module_blocks: 6,
      consumed_exp: 500,
      consumed_lmd: 1000,
      skill_book_equivalent: 8
    })
    expect(total.materials).toMatchObject([
      { id: 'a', count: 5, sanity: 50 },
      { id: 'x', count: 4, sanity: null }
    ])
    expect(total.ranking.map((row) => row.char_id)).toEqual(['five', 'six'])
    expect(statistics.rarities[6].materials[0].count).toBe(2)
  })
  it('全部取消星级保持零值，排行与材料为空', () => {
    expect(sumPersonalStatistics(statistics, [])).toMatchObject({
      owned: 0,
      available: 0,
      sanity: 0,
      ranking: [],
      materials: []
    })
    expect(personalStatisticsRows(statistics, []).map((row) => row.label)).toEqual(['全部所选'])
  })
  it('汇总行与单星级行同口径且顺序固定', () => {
    const rows = personalStatisticsRows(statistics, [5, 6])
    expect(rows.map((row) => row.key)).toEqual(['all', 6, 5])
    expect(rows[0].skills[3]).toBe(3)
    expect(rows[1].owned).toBe(2)
  })
})

it('所有星级按高到低列出，保留低星实际能力字段', () => {
  const statistics = {
    rarities: {
      3: { owned: 4, max_level: 2, max_phase: 1, supports_mastery: false, supports_modules: false },
      1: { owned: 2, max_level: 1, max_phase: 0 }
    }
  }
  const rows = personalStatisticsRows(statistics, [1, 3])
  expect(rows.map((row) => row.key)).toEqual(['all', 3, 1])
  expect(rows[1].supports_mastery).toBe(false)
  expect(rows[0].max_level).toBe(3)
})
