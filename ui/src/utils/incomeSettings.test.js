import { describe, expect, it, vi } from 'vitest'
import { incomeAlgorithms, loadIncomeSettings } from './incomeSettings'
const defaults = () => ({
  base_algorithm: 0,
  base_algorithm_saved: false,
  ratios: { experience: 1, gold: 0.8, order: 0.2, efficiency: 1.5 }
})
const storage = (value) => ({ getItem: vi.fn(() => value), removeItem: vi.fn() })
describe('统一收益设置迁移', () => {
  it.each([0, 1, 2, -1])('迁移旧基报算法 %s 并保留回收站效率', async (using) => {
    const custom = { exp: 2, gold: 0.3, lmb: 0.4 }
    const old = storage(JSON.stringify({ using, custom }))
    const saved = { ...defaults(), base_algorithm: using, base_algorithm_saved: true }
    const client = {
      get: vi.fn().mockResolvedValue({ data: defaults() }),
      put: vi.fn().mockResolvedValue({ data: saved })
    }
    expect(await loadIncomeSettings(client, old)).toEqual(saved)
    expect(client.put.mock.calls[0][1]).toEqual({
      base_algorithm: using,
      ratios: {
        ...(incomeAlgorithms.find((row) => row.value === using).ratios || {
          experience: 2,
          gold: 0.3,
          order: 0.4
        }),
        efficiency: 1.5
      }
    })
    expect(old.removeItem).toHaveBeenCalledWith('earning_algorithm_config')
  })
  it('旧回收站比例没有算法确认时，迁移已有基报选择', async () => {
    const old = storage('{"using":0}')
    const client = {
      get: vi.fn().mockResolvedValue({ data: { ...defaults(), base_algorithm: 1 } }),
      put: vi.fn().mockResolvedValue({ data: { ...defaults(), base_algorithm_saved: true } })
    }
    await loadIncomeSettings(client, old)
    expect(client.put.mock.calls[0][1].base_algorithm).toBe(0)
  })
  it('服务器已确认的算法优先，包括恢复默认值', async () => {
    const saved = { ...defaults(), base_algorithm_saved: true }
    const client = { get: vi.fn().mockResolvedValue({ data: saved }), put: vi.fn() }
    const old = storage(JSON.stringify({ using: 2 }))
    expect(await loadIncomeSettings(client, old)).toEqual(saved)
    expect(client.put).not.toHaveBeenCalled()
  })
  it.each(['invalid', '{"using":99}', '{"using":-1,"custom":{"exp":0}}'])(
    '无效旧配置保持服务器值 %s',
    async (raw) => {
      const client = { get: vi.fn().mockResolvedValue({ data: defaults() }), put: vi.fn() }
      expect(await loadIncomeSettings(client, storage(raw))).toEqual(defaults())
      expect(client.put).not.toHaveBeenCalled()
    }
  )
  it('迁移保存失败保留旧值以便重试', async () => {
    const old = storage('{"using":1}')
    const client = {
      get: vi.fn().mockResolvedValue({ data: defaults() }),
      put: vi.fn().mockRejectedValue(new Error('offline'))
    }
    await expect(loadIncomeSettings(client, old)).rejects.toThrow('offline')
    expect(old.removeItem).not.toHaveBeenCalled()
  })
})
