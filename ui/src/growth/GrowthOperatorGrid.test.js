import { describe, expect, it, vi } from 'vitest'
import { effectScope, reactive } from 'vue'
import GrowthOperatorGrid from './GrowthOperatorGrid.vue'

vi.mock('vue', async (original) => ({
  ...(await original()),
  useSSRContext: () => ({ modules: new Set() })
}))

function setup(overrides = {}) {
  const props = reactive({
    cards: [],
    loading: false,
    error: '',
    emptyText: '',
    hasData: true,
    search: '',
    rarities: [],
    professions: [],
    idleFilter: 'all',
    idleOptions: [],
    rarityOptions: [],
    professionOptions: [],
    surveyFilters: {},
    survey: null,
    surveyLoading: false,
    batchAdding: false,
    batchProgress: null,
    filteredCount: 0,
    addableCount: 0,
    total: 0,
    page: 1,
    pageSize: 30,
    ...overrides
  })
  const scope = effectScope()
  const emit = vi.fn()
  const component = scope.run(() => GrowthOperatorGrid.setup(props, { expose: vi.fn(), emit }))
  return { props, component, emit, stop: () => scope.stop() }
}

describe('干员分页按筛选结果计算', () => {
  it('筛选结果不足一页时不显示分页，范围使用筛选数量', () => {
    const { component, stop } = setup({ filteredCount: 9, total: 391 })
    expect(component.listTotal.value).toBe(9)
    expect(component.totalPages.value).toBe(1)
    expect(component.rangeText.value).toBe('1–9 / 9')
    stop()
  })

  it('筛选结果超过一页时只显示筛选后的页数', () => {
    const { component, stop } = setup({ filteredCount: 35, total: 391 })
    expect(component.totalPages.value).toBe(2)
    expect(component.pageWindow.value).toEqual([1, 2])
    expect(component.rangeText.value).toBe('1–30 / 35')
    stop()
  })

  it('后一页范围按筛选数量截断', () => {
    const { component, stop } = setup({ filteredCount: 35, total: 391, page: 2 })
    expect(component.rangeText.value).toBe('31–35 / 35')
    expect(component.pageWindow.value).toEqual([1, 2])
    stop()
  })
})
