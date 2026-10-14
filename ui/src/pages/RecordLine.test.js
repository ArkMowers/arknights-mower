import { afterEach, expect, it, vi } from 'vitest'
import { effectScope, reactive, nextTick } from 'vue'
import { createPinia, setActivePinia } from 'pinia'
import RecordLine from './RecordLine.vue'
import { useMoodBoardStore } from '@/stores/mood_board'
const io = vi.hoisted(() => ({ mounted: null, ratios: vi.fn(), catalog: vi.fn(), series: vi.fn() }))
vi.mock('@/stores/record', () => ({
  useRecordStore: () => ({
    getMoodRatios: io.ratios,
    getMoodCatalog: io.catalog,
    getMoodSeries: io.series
  })
}))
vi.mock('vue-chartjs', () => ({ Line: { render: () => null } }))
vi.mock('vue', async (original) => ({
  ...(await original()),
  useSSRContext: () => ({ modules: new Set() }),
  onMounted: (fn) => {
    io.mounted = fn
  }
}))
afterEach(() => {
  vi.unstubAllGlobals()
  vi.clearAllMocks()
})
it('reuses simulation interactions without fetching history or persisting custom views', async () => {
  const storage = { getItem: vi.fn(), setItem: vi.fn() }
  vi.stubGlobal('window', { localStorage: storage })
  setActivePinia(createPinia())
  const savedBoard = useMoodBoardStore()
  const props = reactive({
    simulation: {
      warmupHours: 72,
      groups: [
        {
          groupName: '制造',
          moodData: {
            datasets: [
              {
                label: '芬',
                data: [
                  { x: 0, y: 24 },
                  { x: 86400000, y: 12 }
                ]
              }
            ]
          }
        }
      ],
      catalog: [{ name: '芬' }],
      series: []
    }
  })
  const scope = effectScope()
  try {
    const page = scope.run(() => RecordLine.setup(props, { expose: vi.fn() }))
    await io.mounted()
    expect(page.orderedReportData.value.map((row) => row.groupName)).toEqual(['制造'])
    expect(page.board.views).toEqual([])
    expect(page.effectiveChartOptions.value.scales.x.type).toBe('linear')
    expect(page.orderedReportData.value[0].moodData.datasets[0].tension).toBe(0)
    page.saveView({ name: '自定义', operators: ['芬'] })
    expect(page.orderedReportData.value.map((row) => row.groupName)).toEqual(['自定义', '制造'])
    props.simulation = { ...props.simulation }
    await nextTick()
    expect(page.board.views).toHaveLength(1)
    expect(page.board.views[0].operators).toEqual(['芬'])
    page.toggleLine('制造', 0)
    expect(page.orderedReportData.value[1].moodData.datasets[0].hidden).toBe(true)
    await nextTick()
    expect(io.ratios).not.toHaveBeenCalled()
    expect(io.catalog).not.toHaveBeenCalled()
    expect(io.series).not.toHaveBeenCalled()
    expect(storage.getItem).not.toHaveBeenCalled()
    expect(storage.setItem).not.toHaveBeenCalled()
    expect(savedBoard.views).toEqual([])
    page.deleteView(page.board.views[0].id)
    props.simulation = { ...props.simulation }
    await nextTick()
    expect(page.board.views).toEqual([])
    expect(page.orderedReportData.value.map((row) => row.groupName)).toEqual(['制造'])
  } finally {
    scope.stop()
  }
})
it('keeps the ordinary mood page on saved preferences and real history', async () => {
  const storage = { getItem: vi.fn(() => null), setItem: vi.fn() }
  vi.stubGlobal('window', { localStorage: storage })
  setActivePinia(createPinia())
  io.ratios.mockResolvedValue([{ groupName: '历史组', moodData: { datasets: [] } }])
  io.catalog.mockResolvedValue([])
  const scope = effectScope()
  try {
    const page = scope.run(() => RecordLine.setup({ simulation: null }, { expose: vi.fn() }))
    await io.mounted()
    expect(io.ratios).toHaveBeenCalledOnce()
    expect(io.catalog).toHaveBeenCalledOnce()
    expect(storage.getItem).toHaveBeenCalled()
    expect(page.effectiveChartOptions.value.scales.x.type).toBe('time')
    expect(page.orderedReportData.value.map((row) => row.groupName)).toEqual(['历史组'])
  } finally {
    scope.stop()
  }
})
