import { beforeEach, describe, expect, it, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import { isReactive } from 'vue'
import axios from 'axios'

import { useMasteryStore } from './mastery'

vi.mock('axios', () => ({ default: { get: vi.fn() } }))

describe('专精计划摘要', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    vi.clearAllMocks()
  })

  it('复用专精计划接口统计条目和训练状态', async () => {
    axios.get.mockResolvedValue({
      data: {
        plans: [
          { id: 1, status: 'idle' },
          { id: 2, status: 'training' },
          { id: 3, status: 'failed' }
        ]
      }
    })
    const store = useMasteryStore()

    await store.loadPlanSummary()

    expect(axios.get).toHaveBeenCalledOnce()
    expect(axios.get.mock.calls[0][0]).toContain('/mastery-plan')
    expect(store.planCount).toBe(3)
    expect(store.isTraining).toBe(true)
    expect(store.planSummaryLoaded).toBe(true)

    await store.loadPlanSummary()
    expect(axios.get).toHaveBeenCalledOnce()
  })

  it('一图流上传失败不影响森空岛成功及干员列表刷新', async () => {
    const upload = { success: false, message: '上传失败，请稍后重试' }
    axios.get
      .mockResolvedValueOnce({ data: { success: true, yituliu_sync: upload } })
      .mockResolvedValueOnce({ data: { operators: [{ char_id: 'char_test' }], has_data: true } })
    const store = useMasteryStore()

    await store.fetchCultivate()

    expect(store.cultivateOk).toBe(true)
    expect(store.error).toBe('')
    expect(store.yituliuSyncResult).toEqual(upload)
    expect(store.recommendations).toEqual([{ char_id: 'char_test' }])
    expect(store.loading).toBe(false)
  })

  it('下一次刷新清除旧的上传结果', async () => {
    const store = useMasteryStore()
    store.yituliuSyncResult = { success: true, message: '已同步' }
    axios.get.mockRejectedValueOnce(new Error('网络不可用'))

    await store.fetchCultivate()

    expect(store.yituliuSyncResult).toBeNull()
    expect(store.cultivateOk).toBe(false)
    expect(store.loading).toBe(false)
  })
})

describe('养成概览快照', () => {
  it('初始化只读取轻量概览，服务端数据保持浅层快照', async () => {
    setActivePinia(createPinia())
    axios.get.mockReset()
    const operators = [{ char_id: 'char_test', recommendations: [{ skill_index: 0 }] }]
    axios.get.mockResolvedValue({ data: { operators, has_data: true } })
    const store = useMasteryStore()
    await store.fetchRecommendations()
    expect(axios.get).toHaveBeenCalledExactlyOnceWith(
      expect.stringContaining('/mastery-recommendation'),
      { params: { materials: 0 }, timeout: 30000 }
    )
    expect(store.recommendations).toBe(operators)
    expect(isReactive(store.recommendations[0])).toBe(false)
    expect(store.hasData).toBe(true)
  })

  it('不同前端实例的概览与错误互不覆盖', async () => {
    axios.get.mockReset()
    const first = useMasteryStore(createPinia())
    const second = useMasteryStore(createPinia())
    axios.get.mockResolvedValueOnce({ data: { operators: [{ char_id: 'first' }], has_data: true } })
    await first.fetchRecommendations()
    axios.get.mockRejectedValueOnce(new Error('second offline'))
    await second.fetchRecommendations()
    expect(first.recommendations[0].char_id).toBe('first')
    expect(first.error).toBe('')
    expect(second.recommendations).toEqual([])
    expect(second.error).toContain('second offline')
  })
})
