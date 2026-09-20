import { beforeEach, describe, expect, it, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
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
})
