import { describe, expect, it } from 'vitest'
import { growthHistoryPoints, growthValueCoverage, sumGrowthStatistics } from './growthPlanning'

describe('已完成养成估值', () => {
  const data = {
    6: {
      sanity_value: 100.25,
      module_blocks: 4,
      consumed_lmd: 100,
      consumed_exp: 200,
      skill_book_equivalent: 2.5,
      sanity_unpriced: [{ id: 'x', name: '数据增补条', count: 20 }]
    },
    5: {
      sanity_value: 50.5,
      module_blocks: 2,
      consumed_lmd: 50,
      consumed_exp: 80,
      skill_book_equivalent: 1,
      sanity_unpriced: [{ id: 'x', name: '数据增补条', count: 10 }]
    }
  }
  it('随星级累计价值和模组数据块、技巧概要，不篡改原始数据', () => {
    expect(sumGrowthStatistics(data, [6, 5]).sanity_value).toBe(150.75)
    expect(growthValueCoverage(data, [6, 5])).toMatchObject({
      moduleBlocks: 6,
      consumedLmd: 150,
      consumedExp: 280,
      skillBookEquivalent: 3.5,
      unpriced: [{ id: 'x', count: 30 }]
    })
    expect(growthValueCoverage(data, []).moduleBlocks).toBe(0)
    expect(data[6].sanity_unpriced[0].count).toBe(20)
  })
  it('旧历史没有价值时跳过，不能填零制造趋势', () => {
    const history = [
      { time: 1, rarities: { 6: { elite2: 3 } } },
      { time: 2, rarities: data }
    ]
    expect(growthHistoryPoints(history, [6], 'sanity_value')).toEqual([[2000, 100.25]])
    expect(sumGrowthStatistics(data, [6, 5, 4]).sanity_value).toBeNull()
    expect(sumGrowthStatistics(data, []).sanity_value).toBe(0)
  })
})
