import { describe, expect, it, vi } from 'vitest'
import {
  loadWorkshopOperators,
  loadWorkshopReference,
  selectedWorkshopOperators,
  syncWorkshopOperators,
  usesLegacyWorkshopDefaults,
  workshopRecommendationText,
  workshopTraineeWarning
} from './workshopOperators'

const data = {
  defaults: {
    fodder_operators: ['空爆', '苏苏洛', '号角'],
    t5_operators: ['年'],
    book_operators: ['赫拉格']
  },
  recommendations: { fodder_operators: [], t5_operators: [], book_operators: [] }
}

describe('training plan workshop warnings', () => {
  it('includes saved manual selections while the runtime config is automatic', () => {
    const operators = selectedWorkshopOperators({
      workshop_settings: [{ operator: '赫拉格', source: 'mastery' }],
      workshop_manual_settings: [{ operator: '空爆' }, { operator: '年', enabled: false }]
    })
    expect([...operators]).toEqual(['赫拉格', '空爆'])
  })

  it('includes selections in every category and enabled manual synthesis configurations', () => {
    const operators = selectedWorkshopOperators({
      fodder_operators: ['九色鹿', '年', 'Free'],
      t5_operators: ['年'],
      book_operators: ['赫拉格'],
      workshop_settings: [
        { operator: '号角', enabled: true },
        { operator: '空爆' },
        { operator: '苏苏洛', enabled: false },
        { operator: '九色鹿' },
        { operator: 'Current' },
        { operator: '' }
      ]
    })
    expect([...operators]).toEqual(['九色鹿', '年', '赫拉格', '号角', '空爆'])
    expect(workshopTraineeWarning('年', operators)).toBe(
      '年 已在合成计划中被选为加工站干员，专精期间可能影响合成，请留意。'
    )
    expect(workshopTraineeWarning('号角', operators)).toContain('可能影响合成')
    expect(workshopTraineeWarning('苏苏洛', operators)).toBe('')
    expect(workshopTraineeWarning('未选中的干员', operators)).toBe('')
    expect(workshopTraineeWarning(undefined, operators)).toBe('')
  })

  it('uses current selections and does not treat recommendations as selected operators', () => {
    const settings = { fodder_operators: ['九色鹿'], recommendations: data.recommendations }
    expect(selectedWorkshopOperators(settings).has('九色鹿')).toBe(true)
    settings.fodder_operators = []
    expect([...selectedWorkshopOperators(settings)]).toEqual([])
    expect([...selectedWorkshopOperators()]).toEqual([])
  })
})

describe('workshop owned defaults', () => {
  it('waits for a successful roster update before loading fresh workshop choices', async () => {
    let finishSync
    const sync = new Promise((resolve) => {
      finishSync = resolve
    })
    const http = { get: vi.fn().mockReturnValueOnce(sync).mockResolvedValueOnce({ data }) }
    const setting = syncWorkshopOperators(http, '/api', 90)
    expect(http.get.mock.calls).toEqual([['/api/cultivate-fetch']])
    finishSync({ data: { success: true } })
    expect(await setting).toEqual(data)
    expect(http.get.mock.calls).toEqual([
      ['/api/cultivate-fetch'],
      ['/api/workshop-operators/recommendations', { params: { min_bonus: 90 } }]
    ])
  })

  it.each([
    { success: false, message: '登录已过期' },
    { success: false, message: '未同步到干员数据' },
    {}
  ])('does not replace selections using stale BOX when sync fails', async (response) => {
    const http = { get: vi.fn().mockResolvedValue({ data: response }) }
    await expect(syncWorkshopOperators(http, '/api')).rejects.toThrow(
      response.message || '干员数据同步失败'
    )
    expect(http.get).toHaveBeenCalledTimes(1)
  })

  it('stops setup if the roster update request fails', async () => {
    const http = { get: vi.fn().mockRejectedValue(new Error('连接超时')) }
    await expect(syncWorkshopOperators(http, '/api')).rejects.toThrow('连接超时')
    expect(http.get).toHaveBeenCalledTimes(1)
  })

  it('propagates invalid BOX errors even after the sync endpoint reports success', async () => {
    const error = {
      response: { status: 400, data: { error: '请先同步干员数据，再读取加工站推荐' } }
    }
    const http = {
      get: vi
        .fn()
        .mockResolvedValueOnce({ data: { success: true } })
        .mockRejectedValueOnce(error)
    }
    await expect(syncWorkshopOperators(http, '/api')).rejects.toBe(error)
    expect(http.get).toHaveBeenCalledTimes(2)
  })

  it.each([75, 65])('lowers only empty book selections from 80 to %i', async (minimum) => {
    const http = {
      get: vi.fn(async (url, options) => {
        if (url.endsWith('/cultivate-fetch')) return { data: { success: true } }
        const minBonus = options.params.book_min_bonus ?? options.params.min_bonus
        return {
          data: {
            ...data,
            defaults: {
              fodder_operators: minBonus === 80 ? ['空爆'] : ['空爆', '低档材料干员'],
              t5_operators: minBonus === 80 ? ['年'] : ['年', '低档 T5 干员'],
              book_operators: minBonus > minimum ? [] : ['赫拉格']
            }
          }
        }
      })
    }
    expect(await syncWorkshopOperators(http, '/api')).toEqual({
      ...data,
      defaults: { fodder_operators: ['空爆'], t5_operators: ['年'], book_operators: ['赫拉格'] }
    })
    expect(http.get.mock.calls).toEqual([
      ['/api/cultivate-fetch'],
      ...Array.from({ length: (80 - minimum) / 5 + 1 }, (_, index) => [
        '/api/workshop-operators/recommendations',
        {
          params:
            index === 0 ? { min_bonus: 80 } : { min_bonus: 80, book_min_bonus: 80 - index * 5 }
        }
      ])
    ])
  })

  it.each(['fodder_operators', 't5_operators', 'book_operators'])(
    'fills only the empty %s category and keeps populated lists unchanged',
    async (category) => {
      const fallback = {
        fodder_operators: ['低档材料干员'],
        t5_operators: ['低档 T5 干员'],
        book_operators: ['低档技巧概要干员']
      }
      const http = {
        get: vi
          .fn()
          .mockResolvedValueOnce({ data: { success: true } })
          .mockResolvedValueOnce({
            data: { ...data, defaults: { ...data.defaults, [category]: [] } }
          })
          .mockResolvedValueOnce({
            data: {
              ...data,
              defaults: fallback
            }
          })
      }
      const result = await syncWorkshopOperators(http, '/api')
      expect(result.defaults[category]).toEqual(fallback[category])
      for (const key of Object.keys(data.defaults)) {
        if (key !== category) expect(result.defaults[key]).toEqual(data.defaults[key])
      }
      expect(http.get).toHaveBeenCalledTimes(3)
      expect(http.get).toHaveBeenLastCalledWith('/api/workshop-operators/recommendations', {
        params: { min_bonus: 80, [category.replace('_operators', '_min_bonus')]: 75 }
      })
    }
  )

  it('stops each category at its first nonempty threshold', async () => {
    const choices = {
      80: { fodder_operators: ['空爆'], t5_operators: [], book_operators: [] },
      75: { fodder_operators: ['空爆', '低档材料干员'], t5_operators: ['年'], book_operators: [] },
      70: { fodder_operators: [], t5_operators: ['低档 T5 干员'], book_operators: ['赫拉格'] }
    }
    const http = {
      get: vi.fn(async (url, options) => ({
        data: url.endsWith('/cultivate-fetch')
          ? { success: true }
          : {
              ...data,
              defaults: choices[options.params.t5_min_bonus ?? options.params.book_min_bonus ?? 80]
            }
      }))
    }
    expect((await syncWorkshopOperators(http, '/api')).defaults).toEqual({
      fodder_operators: ['空爆'],
      t5_operators: ['年'],
      book_operators: ['赫拉格']
    })
    expect(http.get).toHaveBeenCalledTimes(5)
    expect(http.get.mock.calls.slice(2)).toEqual([
      ['/api/workshop-operators/recommendations', { params: { min_bonus: 80, t5_min_bonus: 75 } }],
      [
        '/api/workshop-operators/recommendations',
        { params: { min_bonus: 80, book_min_bonus: 75 } }
      ],
      ['/api/workshop-operators/recommendations', { params: { min_bonus: 80, book_min_bonus: 70 } }]
    ])
  })

  it.each([0, 3, 80])('terminates at zero when no operators qualify from %i', async (minimum) => {
    const empty = {
      ...data,
      defaults: { fodder_operators: [], t5_operators: [], book_operators: [] }
    }
    const http = {
      get: vi
        .fn()
        .mockResolvedValueOnce({ data: { success: true } })
        .mockResolvedValue({ data: empty })
    }
    expect(await syncWorkshopOperators(http, '/api', minimum)).toEqual(empty)
    expect(http.get).toHaveBeenCalledTimes(3 * Math.ceil(minimum / 5) + 2)
    expect(http.get).toHaveBeenLastCalledWith('/api/workshop-operators/recommendations', {
      params: minimum === 0 ? { min_bonus: 0 } : { min_bonus: minimum, book_min_bonus: 0 }
    })
  })

  it('keeps successful categories when one category stays empty at zero', async () => {
    const partial = { ...data, defaults: { ...data.defaults, book_operators: [] } }
    const http = {
      get: vi
        .fn()
        .mockResolvedValueOnce({ data: { success: true } })
        .mockResolvedValueOnce({ data: partial })
        .mockResolvedValueOnce({
          data: {
            ...data,
            defaults: { fodder_operators: [], t5_operators: [], book_operators: [] }
          }
        })
    }
    expect(await syncWorkshopOperators(http, '/api', 5)).toEqual(partial)
    expect(http.get).toHaveBeenCalledTimes(3)
  })

  it.each(['request', 'data'])(
    'rejects a failed fallback %s without returning partial results',
    async (failure) => {
      const http = {
        get: vi
          .fn()
          .mockResolvedValueOnce({ data: { success: true } })
          .mockResolvedValueOnce({
            data: { ...data, defaults: { ...data.defaults, book_operators: [] } }
          })
      }
      if (failure === 'request') http.get.mockRejectedValueOnce(new Error('连接超时'))
      else http.get.mockResolvedValueOnce({ data: {} })
      await expect(syncWorkshopOperators(http, '/api')).rejects.toThrow(
        failure === 'request' ? '连接超时' : '不完整'
      )
      expect(http.get).toHaveBeenCalledTimes(3)
    }
  )

  it('accepts an empty candidate list from a valid BOX', async () => {
    const empty = {
      defaults: { fodder_operators: [], t5_operators: [], book_operators: [] },
      recommendations: { fodder_operators: [], t5_operators: [], book_operators: [] }
    }
    const http = { get: vi.fn().mockResolvedValue({ data: empty }) }
    expect(await loadWorkshopOperators(http, '/api')).toEqual(empty)
  })

  it('reads the existing BOX recommendation once and retains multiple operators', async () => {
    const http = { get: vi.fn().mockResolvedValue({ data }) }
    expect(await loadWorkshopOperators(http, '/api')).toEqual(data)
    expect(http.get).toHaveBeenCalledExactlyOnceWith('/api/workshop-operators/recommendations', {
      params: { min_bonus: 80 }
    })
  })

  it('sends the selected bonus threshold for one-click setup', async () => {
    const http = { get: vi.fn().mockResolvedValue({ data }) }
    await loadWorkshopOperators(http, '/api', 90)
    expect(http.get).toHaveBeenCalledExactlyOnceWith('/api/workshop-operators/recommendations', {
      params: { min_bonus: 90 }
    })
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

  it('explains material-specific bonuses without adding a deer description', () => {
    expect(
      workshopRecommendationText({
        name: '号角',
        materials: ['炽合金块'],
        bonuses: { 炽合金块: 100 }
      })
    ).toBe('号角：炽合金块，副产品概率加成 +100%')
    expect(workshopRecommendationText({ name: '九色鹿', causality: true })).toBe('九色鹿')
  })

  it('summarizes Humus materials as T3', () => {
    const materials = ['全新装置', '酮凝集组', '异铁组', '聚酸酯组', '糖组', '固源岩组']
    expect(
      workshopRecommendationText({
        name: '休谟斯',
        specialist: true,
        materials,
        bonuses: Object.fromEntries(materials.map((name) => [name, 90]))
      })
    ).toBe('休谟斯：仅合成 T3 材料，副产品概率加成 +90%')
  })
})

describe('workshop cultivation reference', () => {
  it('marks only unowned operators, including deer', () => {
    const deer = { name: '九色鹿', causality: true }
    expect(workshopRecommendationText(deer)).toBe('九色鹿')
    expect(workshopRecommendationText(deer, false)).toBe('九色鹿')
    expect(workshopRecommendationText(deer, true)).toBe('九色鹿（未持有）')
    expect(workshopRecommendationText({ name: '休谟斯', bonuses: { 糖组: 90 } }, true)).toBe(
      '休谟斯（未持有）：仅合成 T3 材料，副产品概率加成 +90%'
    )
  })

  it('loads references independently without syncing BOX or requesting defaults', async () => {
    const http = {
      get: vi.fn().mockResolvedValue({ data: { recommendations: data.recommendations } })
    }
    expect(await loadWorkshopReference(http, '/api')).toEqual(data.recommendations)
    expect(http.get).toHaveBeenCalledExactlyOnceWith('/api/workshop-operators/reference')
  })

  it('rejects incomplete references', async () => {
    const http = { get: vi.fn().mockResolvedValue({ data: {} }) }
    await expect(loadWorkshopReference(http, '/api')).rejects.toThrow('不完整')
  })
})
