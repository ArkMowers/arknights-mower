import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { effectScope, reactive } from 'vue'
import axios from 'axios'
import RecordLine from './RecordLine.vue'
import RecordPie from './RecordPie.vue'

const state = vi.hoisted(() => ({ mounted: [], board: null, getMoodRatios: vi.fn() }))

vi.mock('vue', async (original) => ({
  ...(await original()),
  useSSRContext: () => ({ modules: new Set() }),
  onMounted: (callback) => state.mounted.push(callback)
}))
vi.mock('axios', () => ({ default: { delete: vi.fn() } }))
vi.mock('@/stores/mood_board', () => ({ useMoodBoardStore: () => state.board }))
vi.mock('@/stores/record', () => ({
  useRecordStore: () => ({
    getMoodRatios: state.getMoodRatios,
    getMoodCatalog: async () => [],
    getMoodSeries: async () => []
  })
}))

describe('current mood pages load curves without monthly work/rest data', () => {
  let scope

  beforeEach(() => {
    state.mounted = []
    state.board = reactive({ views: [], groupOrder: [], load: vi.fn() })
    state.getMoodRatios.mockReset().mockResolvedValue([])
    axios.delete.mockReset().mockResolvedValue({})
    vi.stubGlobal('alert', vi.fn())
    scope = effectScope()
  })

  afterEach(() => {
    scope.stop()
    vi.unstubAllGlobals()
  })

  it.each([
    ['curve', RecordLine],
    ['pie', RecordPie]
  ])('%s page opts out while loading', async (_name, component) => {
    scope.run(() => component.setup({}, { expose: vi.fn() }))
    await Promise.all(state.mounted.map((callback) => callback()))

    expect(state.getMoodRatios).toHaveBeenCalledExactlyOnceWith({ includeWorkRest: false })
  })

  it('pie page also opts out when reloading after a history deletion', async () => {
    const page = scope.run(() => RecordPie.setup({}, { expose: vi.fn() }))

    await page.clearData()

    expect(axios.delete).toHaveBeenCalledOnce()
    expect(state.getMoodRatios).toHaveBeenCalledExactlyOnceWith({ includeWorkRest: false })
    expect(page.loadError.value).toBe('')
  })
})
