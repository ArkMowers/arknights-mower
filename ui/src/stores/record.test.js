import { beforeEach, describe, expect, it, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import axios from 'axios'
import { useRecordStore } from './record'

vi.mock('axios', () => ({ default: { get: vi.fn() } }))

describe('mood report requests', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    vi.clearAllMocks()
  })

  it('keeps monthly work/rest data enabled for callers without options', async () => {
    const report = [{ groupName: '深海', moodData: {}, workRestData: { datasets: [] } }]
    axios.get.mockResolvedValue({ data: report })

    await expect(useRecordStore().getMoodRatios()).resolves.toEqual(report)

    expect(axios.get).toHaveBeenCalledExactlyOnceWith(
      expect.stringContaining('/record/getMoodRatios'),
      { params: { include_work_rest: true } }
    )
  })

  it('requests curves without monthly work/rest data when the caller opts out', async () => {
    const report = [{ groupName: '深海', moodData: { datasets: [] } }]
    axios.get.mockResolvedValue({ data: report })

    await expect(useRecordStore().getMoodRatios({ includeWorkRest: false })).resolves.toEqual(
      report
    )

    expect(axios.get).toHaveBeenCalledExactlyOnceWith(
      expect.stringContaining('/record/getMoodRatios'),
      { params: { include_work_rest: false } }
    )
  })
})
