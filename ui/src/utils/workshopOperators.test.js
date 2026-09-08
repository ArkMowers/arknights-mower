import { describe, expect, it, vi } from 'vitest'
import {
  loadWorkshopOperators,
  usesLegacyWorkshopDefaults,
  workshopRecommendationText
} from './workshopOperators'

const data = {
  defaults: {
    fodder_operators: ['空爆', '苏苏洛', '号角'],
    t5_operators: ['空爆', '苏苏洛'],
    book_operators: ['赫拉格']
  },
  recommendations: { fodder_operators: [], t5_operators: [], book_operators: [] }
}

describe('workshop owned defaults', () => {
  it('reads the existing BOX recommendation once and retains multiple operators', async () => {
    const http = { get: vi.fn().mockResolvedValue({ data }) }
    expect(await loadWorkshopOperators(http, '/api')).toEqual(data)
    expect(http.get).toHaveBeenCalledExactlyOnceWith('/api/workshop-operators/recommendations')
  })

  it.each([
    {},
    { defaults: data.defaults },
    { ...data, defaults: { ...data.defaults, book_operators: null } }
  ])('rejects incomplete responses without inventing defaults', async (data) => {
    await expect(loadWorkshopOperators({ get: async () => ({ data }) }, '/api')).rejects.toThrow(
      '不完整'
    )
  })

  it('propagates failed reads so saved selections can be retained', async () => {
    const get = vi.fn().mockRejectedValue(new Error('请同步干员数据'))
    await expect(loadWorkshopOperators({ get }, '/api')).rejects.toThrow('请同步干员数据')
  })

  it('migrates only the old factory defaults and preserves customized multiple choices', () => {
    const previous = {
      fodder_operators: ['九色鹿'],
      t5_operators: ['年'],
      book_operators: ['司霆惊蛰']
    }
    expect(usesLegacyWorkshopDefaults(previous)).toBe(true)
    expect(usesLegacyWorkshopDefaults(data.defaults)).toBe(false)
    expect(usesLegacyWorkshopDefaults({ ...previous, fodder_operators: [] })).toBe(false)
  })

  it('explains material-specific bonuses and the deer workflow', () => {
    expect(
      workshopRecommendationText({
        name: '号角',
        materials: ['炽合金块'],
        bonuses: { 炽合金块: 100 }
      })
    ).toBe('号角：炽合金块，副产品概率加成 +100%')
    expect(workshopRecommendationText({ name: '九色鹿', causality: true })).toContain('因果垫刀')
  })
})
