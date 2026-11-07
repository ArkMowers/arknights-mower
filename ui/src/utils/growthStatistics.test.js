import { describe, expect, it } from 'vitest'
import { growthHistoryPoints, sumGrowthStatistics } from './growthPlanning'

describe('真实养成历史', () => {
  it('缺少等效理智的旧记录不补零', () => {
    const data = { 6: { sanity_value: 100.25 }, 5: { sanity_value: 50.5 } }
    const history = [
      { time: 1, rarities: { 6: { elite2: 3 } } },
      { time: 2, rarities: data }
    ]
    expect(growthHistoryPoints(history, [6], 'sanity_value')).toEqual([[2000, 100.25]])
    expect(sumGrowthStatistics(data, [6, 5]).sanity_value).toBe(150.75)
    expect(sumGrowthStatistics(data, [6, 5, 4]).sanity_value).toBeNull()
    expect(sumGrowthStatistics(data, []).sanity_value).toBe(0)
  })
})
