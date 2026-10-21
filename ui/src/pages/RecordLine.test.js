import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { effectScope, nextTick } from 'vue'
import { createPinia, setActivePinia } from 'pinia'
import RecordLine from './RecordLine.vue'
import RecordPie from './RecordPie.vue'
import { useMoodBoardStore } from '@/stores/mood_board'
import { MOOD_VIEWS_KEY } from '@/utils/mood_observation'

const state = vi.hoisted(() => ({ mounted: [], record: null }))
vi.mock('vue', async (original) => ({
  ...(await original()),
  useSSRContext: () => ({ modules: new Set() }),
  onMounted: (callback) => state.mounted.push(callback)
}))
vi.mock('axios', () => ({
  default: {
    get: vi.fn(async () => ({ data: { preferences: null } })),
    post: vi.fn(async (_url, preferences) => ({ data: { preferences } })),
    patch: vi.fn(async () => ({}))
  }
}))
vi.mock('@/stores/record', () => ({ useRecordStore: () => state.record }))
vi.mock('@/components/MoodCardGrid.vue', () => ({ default: {} }))
vi.mock('@/components/MoodRateLegend.vue', () => ({ default: {} }))
vi.mock('@/components/MoodObservationEditor.vue', () => ({ default: {} }))

const series = (names) => names.map((name) => ({ name, data: [{ x: '2026-10-18', y: 12 }] }))

describe.each([
  ['curve', RecordLine],
  ['pie', RecordPie]
])('%s observation history requests', (_name, page) => {
  let scope
  let board
  let component
  let storage

  beforeEach(() => {
    state.mounted = []
    state.record = {
      getMoodRatios: vi.fn(async () => []),
      getMoodCatalog: vi.fn(async () => []),
      getMoodSeries: vi.fn(async (names) => series(names))
    }
    const stored = new Map()
    storage = {
      getItem: (key) => stored.get(key) ?? null,
      setItem: (key, value) => stored.set(key, value)
    }
    vi.stubGlobal('window', { localStorage: storage })
    setActivePinia(createPinia())
    board = useMoodBoardStore()
    scope = effectScope()
  })

  afterEach(() => {
    scope.stop()
    board.$dispose()
    vi.unstubAllGlobals()
  })

  function saveInitialViews(views) {
    storage.setItem(MOOD_VIEWS_KEY, JSON.stringify(views))
  }

  async function mount() {
    scope.run(() => {
      component = page.setup({}, { expose: () => {} })
    })
    for (const callback of state.mounted) await callback()
    await nextTick()
  }

  it.each([false, true])(
    'loads persisted names once when the board is already initialized: %s',
    async (initialized) => {
      saveInitialViews([{ id: 'card-one', name: '重点观察', operators: ['阿米娅', '煌'] }])
      if (initialized) board.load()

      await mount()
      await vi.waitFor(() => expect(component.viewHistory.fetchedSeries.value).toHaveLength(2))

      expect(state.record.getMoodSeries).toHaveBeenCalledExactlyOnceWith(['阿米娅', '煌'])
      expect(state.record.getMoodRatios).toHaveBeenCalledOnce()
      expect(state.record.getMoodCatalog).toHaveBeenCalledTimes(page === RecordLine ? 1 : 0)
    }
  )

  it('keeps all twelve batches within the sixteen-name and 192-name bounds', async () => {
    const views = Array.from({ length: 12 }, (_, index) => ({
      id: `card-${index}`,
      name: `观察表${index}`,
      operators: Array.from({ length: 16 }, (_, offset) => `干员${index * 16 + offset}`)
    }))
    saveInitialViews(views)

    await mount()
    await vi.waitFor(() => expect(component.viewHistory.fetchedSeries.value).toHaveLength(192))

    expect(state.record.getMoodSeries).toHaveBeenCalledTimes(12)
    const batches = state.record.getMoodSeries.mock.calls.map(([names]) => names)
    expect(batches.every((names) => names.length === 16)).toBe(true)
    expect(batches.flat()).toEqual(views.flatMap((view) => view.operators))
  })

  it('loads edited names and clears removed views after an empty first load', async () => {
    await mount()
    expect(state.record.getMoodSeries).not.toHaveBeenCalled()

    board.upsertView({ name: '重点观察', operators: ['阿米娅', '煌', '阿米娅'] })
    await vi.waitFor(() =>
      expect(component.viewHistory.fetchedSeries.value).toEqual(series(['阿米娅', '煌']))
    )
    const id = board.views[0].id
    board.upsertView({ name: '重点观察', operators: ['银灰'] }, id)
    await vi.waitFor(() =>
      expect(component.viewHistory.fetchedSeries.value).toEqual(series(['银灰']))
    )

    expect(state.record.getMoodSeries.mock.calls).toEqual([[['阿米娅', '煌']], [['银灰']]])
    board.removeView(id)
    await nextTick()
    expect(component.viewHistory.fetchedSeries.value).toEqual([])
    expect(state.record.getMoodSeries).toHaveBeenCalledTimes(2)
  })

  it.each(['resolve', 'reject'])(
    'ignores an obsolete request that later finishes with %s',
    async (outcome) => {
      const oldNames = Array.from({ length: 17 }, (_, index) => `旧干员${index}`)
      saveInitialViews([
        { id: 'card-one', name: '第一表', operators: oldNames.slice(0, 16) },
        { id: 'card-two', name: '第二表', operators: oldNames.slice(16) }
      ])
      let finishOld
      let failOld
      state.record.getMoodSeries.mockImplementationOnce(
        () =>
          new Promise((resolve, reject) => {
            finishOld = resolve
            failOld = reject
          })
      )

      const mounting = mount()
      await vi.waitFor(() => expect(state.record.getMoodSeries).toHaveBeenCalledTimes(1))
      board.upsertView({ name: '第一表', operators: ['银灰'] }, 'card-one')
      board.removeView('card-two')
      await vi.waitFor(() =>
        expect(component.viewHistory.fetchedSeries.value).toEqual(series(['银灰']))
      )

      if (outcome === 'resolve') finishOld(series(oldNames.slice(0, 16)))
      else failOld(new Error('obsolete response'))
      await mounting
      await nextTick()

      expect(component.viewHistory.fetchedSeries.value).toEqual(series(['银灰']))
      expect(component.historyLimited.value).toBe(false)
      expect(state.record.getMoodSeries.mock.calls).toEqual([[oldNames.slice(0, 16)], [['银灰']]])
    }
  )

  it('loads custom history even when the default report is unavailable', async () => {
    saveInitialViews([{ id: 'card-one', name: '重点观察', operators: ['阿米娅'] }])
    state.record.getMoodRatios.mockRejectedValueOnce(new Error('report unavailable'))

    await mount()
    await vi.waitFor(() =>
      expect(component.viewHistory.fetchedSeries.value).toEqual(series(['阿米娅']))
    )

    expect(component.loadError.value).not.toBe('')
    expect(state.record.getMoodSeries).toHaveBeenCalledExactlyOnceWith(['阿米娅'])
  })
})
