import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import axios from 'axios'
import { useMoodBoardStore } from './mood_board'
import { LEGACY_MOOD_GROUP_ORDER_KEY, MOOD_ORDER_KEY } from '@/utils/mood_order'
import { MOOD_VIEWS_KEY } from '@/utils/mood_observation'

vi.mock('axios', () => ({ default: { get: vi.fn(), post: vi.fn(), patch: vi.fn() } }))

describe('mood board UI configuration', () => {
  let saved
  let local

  beforeEach(() => {
    vi.resetAllMocks()
    saved = null
    local = new Map()
    vi.stubGlobal('window', {
      localStorage: {
        getItem: (key) => local.get(key) ?? null,
        setItem: (key, value) => local.set(key, value)
      }
    })
    axios.get.mockImplementation(async () => ({ data: { preferences: saved } }))
    axios.post.mockImplementation(async (_url, preferences) => {
      saved ??= preferences
      return { data: { preferences: saved } }
    })
    axios.patch.mockImplementation(async (_url, patch) => {
      saved = { ...saved, ...patch }
      return { data: { preferences: saved } }
    })
    setActivePinia(createPinia())
  })

  afterEach(() => vi.unstubAllGlobals())

  it('migrates the old local order and views once, then loads without any browser storage', async () => {
    const views = [{ id: 'focus-card', name: '重点', operators: ['煌'] }]
    local.set(LEGACY_MOOD_GROUP_ORDER_KEY, JSON.stringify(['二组', '一组']))
    local.set(MOOD_VIEWS_KEY, JSON.stringify(views))
    const board = useMoodBoardStore()
    await board.load()
    board.setHiddenLines('一组', ['阿米娅'])
    board.hideGroup('二组')
    board.setDefaultOperator('一组', '银灰')
    await board.flushSaves()

    expect(saved).toEqual({
      groupOrder: ['二组', '一组'],
      hiddenLines: { 一组: ['阿米娅'] },
      hiddenGroups: ['二组'],
      defaultOperators: { 一组: '银灰' },
      views
    })
    local.clear()
    setActivePinia(createPinia())
    const reloaded = useMoodBoardStore()
    await reloaded.load()
    expect(reloaded.groupOrder).toEqual(['二组', '一组'])
    expect(reloaded.views).toEqual(views)
    expect(reloaded.hiddenLines).toEqual({ 一组: ['阿米娅'] })
    expect(reloaded.hiddenGroups).toEqual(['二组'])
    expect(reloaded.defaultOperators).toEqual({ 一组: '银灰' })
    expect(axios.post).toHaveBeenCalledOnce()
  })

  it('uses saved UI configuration instead of stale browser preferences', async () => {
    saved = { groupOrder: ['一组'], hiddenGroups: [], views: [] }
    local.set(MOOD_ORDER_KEY, JSON.stringify({ groupOrder: ['旧组'], hiddenGroups: ['一组'] }))
    local.set(MOOD_VIEWS_KEY, JSON.stringify([{ id: 'old-card', name: '旧表', operators: ['煌'] }]))
    const board = useMoodBoardStore()
    await board.load()

    expect(board.groupOrder).toEqual(['一组'])
    expect(board.hiddenGroups).toEqual([])
    expect(board.views).toEqual([])
    expect(axios.post).not.toHaveBeenCalled()
    expect(JSON.parse(local.get(MOOD_ORDER_KEY)).groupOrder).toEqual(['一组'])
  })

  it('preserves an edit made while loading and only patches the edited fields', async () => {
    let finish
    axios.get.mockReturnValueOnce(
      new Promise((resolve) => {
        finish = resolve
      })
    )
    const board = useMoodBoardStore()
    const loading = board.load()
    board.setHiddenLines('一组', ['阿米娅'])
    saved = { groupOrder: ['二组', '一组'], hiddenLines: { 一组: ['银灰'] }, views: [] }
    finish({ data: { preferences: saved } })
    await loading
    await board.flushSaves()

    expect(board.groupOrder).toEqual(['二组', '一组'])
    expect(board.hiddenLines).toEqual({ 一组: ['阿米娅'] })
    expect(axios.patch).toHaveBeenCalledExactlyOnceWith(
      expect.stringContaining('/ui-state/mood-board'),
      {
        hiddenLines: { 一组: ['阿米娅'] }
      },
      { timeout: 5000 }
    )
    expect(saved.hiddenLines).toEqual({ 一组: ['阿米娅'] })
  })

  it('retains a failed change and saves it together with the next explicit edit', async () => {
    const board = useMoodBoardStore()
    await board.load()
    axios.patch.mockRejectedValueOnce(new Error('offline'))
    board.hideGroup('一组')
    await board.flushSaves()
    expect(board.saveError).not.toBe('')
    expect(board.hiddenGroups).toEqual(['一组'])

    board.setDefaultOperator('二组', '煌')
    await board.flushSaves()
    expect(saved.hiddenGroups).toEqual(['一组'])
    expect(saved.defaultOperators).toEqual({ 二组: '煌' })
    expect(board.saveError).toBe('')
  })

  it('keeps the latest edit when an older save completes later', async () => {
    const board = useMoodBoardStore()
    await board.load()
    let finish
    axios.patch.mockImplementationOnce(
      (_url, patch) =>
        new Promise((resolve) => {
          finish = () => {
            saved = { ...saved, ...patch }
            resolve({ data: { preferences: saved } })
          }
        })
    )
    board.setDefaultOperator('一组', '阿米娅')
    await vi.waitFor(() => expect(axios.patch).toHaveBeenCalledTimes(1))
    board.setDefaultOperator('一组', '银灰')
    finish()
    await board.flushSaves()
    expect(board.defaultOperators).toEqual({ 一组: '银灰' })
    expect(saved.defaultOperators).toEqual({ 一组: '银灰' })
    expect(axios.patch).toHaveBeenCalledTimes(2)
  })

  it('falls back to local preferences when the backend is unavailable', async () => {
    axios.get.mockRejectedValue(new Error('offline'))
    local.set(MOOD_ORDER_KEY, JSON.stringify({ groupOrder: ['一组'] }))
    const board = useMoodBoardStore()
    await board.load()
    expect(board.groupOrder).toEqual(['一组'])
    expect(board.saveError).not.toBe('')
    board.hideGroup('一组')
    await board.flushSaves()
    expect(JSON.parse(local.get(MOOD_ORDER_KEY)).hiddenGroups).toEqual(['一组'])
    expect(axios.patch).not.toHaveBeenCalled()
  })
})
