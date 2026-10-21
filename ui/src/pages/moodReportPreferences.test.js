import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { effectScope, nextTick } from 'vue'
import { createPinia, setActivePinia } from 'pinia'
import axios from 'axios'
import RecordLine from './RecordLine.vue'
import RecordPie from './RecordPie.vue'
import { useMoodBoardStore } from '@/stores/mood_board'
import { LEGACY_MOOD_GROUP_ORDER_KEY, MOOD_ORDER_KEY } from '@/utils/mood_order'

const state = vi.hoisted(() => ({ mounted: [], record: null, preferences: null }))
vi.mock('vue', async (original) => ({
  ...(await original()),
  useSSRContext: () => ({ modules: new Set() }),
  onMounted: (callback) => state.mounted.push(callback)
}))
vi.mock('axios', () => ({
  default: {
    get: vi.fn(async () => ({ data: { preferences: state.preferences } })),
    post: vi.fn(async (_url, preferences) => {
      state.preferences ??= preferences
      return { data: { preferences: state.preferences } }
    }),
    patch: vi.fn(async (_url, patch) => {
      state.preferences = { ...state.preferences, ...patch }
      return { data: { preferences: state.preferences } }
    }),
    delete: vi.fn(async () => ({}))
  }
}))
vi.mock('@/stores/record', () => ({ useRecordStore: () => state.record }))

const points = (workingHours, restingHours) => [
  { x: '2026-10-18T00:00:00Z', y: 24 },
  { x: `2026-10-18T0${workingHours}:00:00Z`, y: 20 },
  { x: `2026-10-18T0${workingHours + restingHours}:00:00Z`, y: 24 }
]
const dataset = (label, work, rest) => ({ label, data: points(work, rest) })
const group = (groupName, datasets) => ({ groupName, moodData: { datasets } })
const keys = (page) => page.orderedReportData.value.map((item) => item.boardKey)

describe('shared mood report preferences', () => {
  let scope
  let board
  let stored
  let report

  beforeEach(async () => {
    state.preferences = null
    state.mounted = []
    stored = new Map()
    vi.stubGlobal('window', {
      localStorage: {
        getItem: (key) => stored.get(key) ?? null,
        setItem: (key, value) => stored.set(key, value)
      }
    })
    vi.stubGlobal('alert', vi.fn())
    report = [
      group('一组', [dataset('阿米娅', 3, 1), dataset('银灰', 1, 3)]),
      group('二组', [dataset('能天使', 2, 2)])
    ]
    state.record = {
      getMoodRatios: vi.fn(async () => report),
      getMoodCatalog: vi.fn(async () => []),
      getMoodSeries: vi.fn(async (names) =>
        names.map((name) => ({
          name,
          data: name === '无记录' ? [] : points(3, 1)
        }))
      )
    }
    setActivePinia(createPinia())
    board = useMoodBoardStore()
    await board.load()
    scope = effectScope()
  })

  afterEach(() => {
    scope.stop()
    vi.unstubAllGlobals()
    vi.clearAllMocks()
  })

  async function mount(component) {
    const page = scope.run(() => component.setup({}, { expose: vi.fn() }))
    const callbacks = state.mounted.splice(0)
    await Promise.all(callbacks.map((callback) => callback()))
    await nextTick()
    return page
  }

  it('shows custom history in the pie even when names are absent from the default report', async () => {
    const id = board.upsertView({ name: '重点', operators: ['煌', '无记录'] })
    const pie = await mount(RecordPie)
    const custom = pie.orderedReportData.value[0]

    expect(custom.boardKey).toBe('custom:' + id)
    expect(custom.operatorRatios).toEqual([{ name: '煌', ratio: 75 }])
    expect(custom.missing).toEqual(['无记录'])
    expect(custom.work_break_group.datasets[0].data).toEqual([25, 75])
    expect(state.record.getMoodSeries).toHaveBeenCalledExactlyOnceWith(['煌', '无记录'])
  })

  it('persists sorting from either page, including custom cards with an existing group name', async () => {
    const id = board.upsertView({ name: '一组', operators: ['煌'] })
    const custom = 'custom:' + id
    const line = await mount(RecordLine)
    const pie = await mount(RecordPie)
    expect(keys(line)).toEqual([custom, '一组', '二组'])
    expect(keys(pie)).toEqual([custom, '一组', '二组'])

    line.reorderCards(custom, '二组')
    expect(keys(pie)).toEqual(['一组', '二组', custom])
    pie.reorderCards('二组', '一组')
    expect(keys(line)).toEqual(['二组', '一组', custom])

    await board.flushSaves()
    setActivePinia(createPinia())
    board = useMoodBoardStore()
    const reloaded = await mount(RecordPie)
    expect(keys(reloaded)).toEqual(['二组', '一组', custom])
    expect(JSON.parse(stored.get(LEGACY_MOOD_GROUP_ORDER_KEY))).toEqual(['二组', '一组', custom])
  })

  it('keeps a selected default while exclusions temporarily use another operator or hide all data', async () => {
    const original = JSON.stringify(report)
    const line = await mount(RecordLine)
    const pie = await mount(RecordPie)
    const first = () => pie.orderedReportData.value.find((item) => item.boardKey === '一组')
    expect(first().defaultOperator).toBe('银灰')

    pie.selectOperator('一组', '阿米娅')
    expect(first().work_break_group.datasets[0].data).toEqual([25, 75])
    line.toggleLine('一组', 0)
    expect(first().defaultOperator).toBe('银灰')
    expect(first().work_break_group.datasets[0].data).toEqual([75, 25])
    expect(board.defaultOperators['一组']).toBe('阿米娅')

    line.setGroupVisibility('一组', false)
    expect(first().operatorRatios).toEqual([])
    expect(first().hasValidRatio).toBe(false)
    line.setGroupVisibility('一组', true)
    expect(first().defaultOperator).toBe('阿米娅')
    expect(JSON.stringify(report)).toBe(original)
  })

  it('restores hidden windows without clearing exclusions, default operators or order', async () => {
    const line = await mount(RecordLine)
    const pie = await mount(RecordPie)
    pie.reorderCards('二组', '一组')
    line.toggleLine('一组', 0)
    pie.selectOperator('一组', '银灰')
    board.hideGroup('一组')
    expect(keys(line)).toEqual(['二组'])
    expect(keys(pie)).toEqual(['二组'])

    await board.flushSaves()
    setActivePinia(createPinia())
    board = useMoodBoardStore()
    const reloaded = await mount(RecordLine)
    expect(keys(reloaded)).toEqual(['二组'])
    board.restoreGroups()
    expect(keys(reloaded)).toEqual(['二组', '一组'])
    expect(board.hiddenLines).toEqual({ 一组: ['阿米娅'] })
    expect(board.defaultOperators).toEqual({ 一组: '银灰' })
  })

  it('removes deleted custom preferences without removing the ordinary group of the same name', async () => {
    const id = board.upsertView({ name: '一组', operators: ['煌'] })
    const custom = 'custom:' + id
    board.setHiddenLines(custom, ['煌'])
    board.setDefaultOperator(custom, '煌')
    board.hideGroup(custom)
    board.setDefaultOperator('一组', '银灰')
    board.removeView(id)

    const saved = JSON.parse(stored.get(MOOD_ORDER_KEY))
    expect(saved.hiddenGroups).toEqual([])
    expect(saved.hiddenLines).toEqual({})
    expect(saved.defaultOperators).toEqual({ 一组: '银灰' })
    expect(keys(await mount(RecordPie))).toEqual(['一组', '二组'])
  })

  it('reloads custom history after deleting samples rather than retaining the previous ratio', async () => {
    board.upsertView({ name: '重点', operators: ['煌'] })
    const pie = await mount(RecordPie)
    expect(pie.orderedReportData.value[0].hasValidRatio).toBe(true)
    state.record.getMoodSeries.mockResolvedValueOnce([{ name: '煌', data: [] }])

    await pie.clearData()

    expect(axios.delete).toHaveBeenCalledOnce()
    expect(state.record.getMoodSeries).toHaveBeenCalledTimes(2)
    expect(pie.orderedReportData.value[0].hasValidRatio).toBe(false)
  })
})
