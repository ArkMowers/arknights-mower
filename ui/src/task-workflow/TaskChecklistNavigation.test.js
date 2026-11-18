import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { effectScope, nextTick, reactive } from 'vue'
import TaskChecklistNavigation from './TaskChecklistNavigation.vue'

vi.mock('vue', async (original) => ({
  ...(await original()),
  useId: () => 'settings-directory',
  useSSRContext: () => ({ modules: new Set() })
}))

let scope, component, props, viewport, row, writeScroll, emitted

beforeEach(() => {
  props = reactive({
    editors: [],
    favoriteIds: [],
    tasks: [
      { id: 'first', title: '首项', group: 'settings' },
      { id: 'last', title: '末项', group: 'settings' }
    ],
    groups: [{ id: 'settings', label: '设置' }],
    selectedId: 'first',
    statuses: {},
    connectionEnabled: false,
    connectionId: 'device',
    selectionRequest: 0,
    collapsed: false
  })
  let scrollTop = 200
  row = { top: 180, bottom: 220 }
  writeScroll = vi.fn((value) => (scrollTop = value))
  viewport = {
    clientHeight: 200,
    scrollHeight: 600,
    get scrollTop() {
      return scrollTop
    },
    set scrollTop(value) {
      writeScroll(value)
    },
    getBoundingClientRect: () => ({ top: 100, bottom: 300, height: 200 }),
    querySelectorAll: vi.fn(() => [{ getBoundingClientRect: () => row }]),
    scrollIntoView: vi.fn(),
    focus: vi.fn()
  }
  emitted = vi.fn()
  scope = effectScope()
  component = scope.run(() =>
    TaskChecklistNavigation.setup(props, { emit: emitted, expose: vi.fn() })
  )
})

afterEach(() => scope.stop())

async function mountDirectory() {
  component.directoryScroll.value = viewport
  await nextTick()
  writeScroll.mockClear()
}

async function selectLast() {
  props.selectedId = 'last'
  await nextTick()
}

describe('selected settings directory entry visibility', () => {
  it('centers the selected row by moving only the directory viewport', async () => {
    await mountDirectory()
    row = { top: 310, bottom: 350 }
    await selectLast()
    expect(writeScroll).toHaveBeenCalledExactlyOnceWith(330)
    expect(viewport.scrollIntoView).not.toHaveBeenCalled()
    expect(viewport.focus).not.toHaveBeenCalled()
    expect(component.mobileOpen.value).toBe(false)
    expect(emitted).not.toHaveBeenCalled()
  })

  it('centers an item above the viewport without resetting the directory to its start', async () => {
    await mountDirectory()
    row = { top: 50, bottom: 90 }
    await selectLast()
    expect(writeScroll).toHaveBeenCalledExactlyOnceWith(70)
  })

  it.each([
    [{ top: 100, bottom: 140 }, 120],
    [{ top: 160, bottom: 200 }, 180],
    [{ top: 260, bottom: 300 }, 280]
  ])('centers an already visible row %j', async (bounds, scrollTop) => {
    await mountDirectory()
    row = bounds
    await selectLast()
    expect(writeScroll).toHaveBeenCalledExactlyOnceWith(scrollTop)
  })

  it('keeps a row that is already centered in place', async () => {
    await mountDirectory()
    await selectLast()
    expect(writeScroll).not.toHaveBeenCalled()
    expect(viewport.scrollTop).toBe(200)
  })

  it.each([
    [0, { top: 10, bottom: 50 }, 0],
    [390, { top: 500, bottom: 540 }, 400]
  ])(
    'clamps centering to the directory scroll range from %s',
    async (initial, bounds, expected) => {
      await mountDirectory()
      viewport.scrollTop = initial
      writeScroll.mockClear()
      row = bounds
      await selectLast()
      expect(viewport.scrollTop).toBe(expected)
      if (initial === expected) expect(writeScroll).not.toHaveBeenCalled()
      else expect(writeScroll).toHaveBeenCalledExactlyOnceWith(expected)
    }
  )

  it('accounts for interface zoom when revealing a partially clipped row', async () => {
    await mountDirectory()
    viewport.getBoundingClientRect = () => ({ top: 150, bottom: 450, height: 300 })
    row = { top: 450, bottom: 510 }
    await selectLast()
    expect(writeScroll).toHaveBeenCalledExactlyOnceWith(320)
  })

  it('reveals the selected entry when the directory first becomes available', async () => {
    row = { top: 290, bottom: 330 }
    component.directoryScroll.value = viewport
    await nextTick()
    expect(writeScroll).toHaveBeenCalledExactlyOnceWith(310)
  })

  it('leaves closed or collapsed directories closed without moving focus or scrolling', async () => {
    await mountDirectory()
    props.collapsed = true
    viewport.clientHeight = 0
    row = { top: 310, bottom: 350 }
    const mobileFocus = vi.fn()
    component.mobileToggle.value = { focus: mobileFocus }
    await selectLast()
    expect(writeScroll).not.toHaveBeenCalled()
    expect(viewport.focus).not.toHaveBeenCalled()
    expect(mobileFocus).not.toHaveBeenCalled()
    expect(props.collapsed).toBe(true)
    expect(component.mobileOpen.value).toBe(false)
  })

  it('waits until a selected entry excluded by the old search has returned', async () => {
    await mountDirectory()
    component.query.value = '首项'
    await nextTick()
    viewport.querySelectorAll = () =>
      component.query.value ? [] : [{ getBoundingClientRect: () => row }]
    row = { top: 310, bottom: 350 }
    await selectLast()
    expect(component.query.value).toBe('')
    expect(writeScroll).toHaveBeenCalledExactlyOnceWith(330)
  })

  it('does not move the viewport when an entry is missing from the directory', async () => {
    await mountDirectory()
    viewport.querySelectorAll = () => []
    props.selectedId = 'device'
    await nextTick()
    expect(writeScroll).not.toHaveBeenCalled()
  })

  it('keeps the scroll position when one of two matching rows is already visible', async () => {
    await mountDirectory()
    row = { top: 330, bottom: 370 }
    viewport.querySelectorAll = () => [
      { getBoundingClientRect: () => row },
      { getBoundingClientRect: () => ({ top: 155, bottom: 195 }) }
    ]
    await selectLast()
    expect(writeScroll).not.toHaveBeenCalled()
  })

  it('keeps focus and scroll in place when reward checkbox states change', async () => {
    await mountDirectory()
    const mobileFocus = vi.fn()
    component.mobileToggle.value = { focus: mobileFocus }
    component.mobileOpen.value = true
    props.tasks.push({
      id: 'rewards',
      title: 'MAA 领取奖励',
      group: 'settings',
      mode: 'aggregate',
      indeterminate: true
    })
    props.statuses.rewards = false
    await nextTick()
    props.tasks[2].indeterminate = false
    props.statuses.rewards = true
    await nextTick()
    props.statuses.rewards = false
    await nextTick()
    expect(writeScroll).not.toHaveBeenCalled()
    expect(viewport.scrollIntoView).not.toHaveBeenCalled()
    expect(viewport.focus).not.toHaveBeenCalled()
    expect(mobileFocus).not.toHaveBeenCalled()
    expect(component.mobileOpen.value).toBe(true)
    expect(emitted).not.toHaveBeenCalled()
  })

  it('retains explicit entry selection and mobile focus restoration', async () => {
    await mountDirectory()
    const mobileFocus = vi.fn()
    component.mobileToggle.value = { focus: mobileFocus }
    component.mobileOpen.value = true
    component.selectEntry('last')
    expect(component.mobileOpen.value).toBe(false)
    expect(mobileFocus).toHaveBeenCalledExactlyOnceWith({ preventScroll: true })
    expect(emitted).toHaveBeenCalledExactlyOnceWith('select', 'last')
  })
})

describe('settings favorites editor', () => {
  it('includes every available editor and keeps the draft after a failed save', async () => {
    props.editors = [
      { id: 'first', title: '首项' },
      { id: 'last', title: '末项' },
      { id: 'extra', title: '独立设置', searchKeywords: '额外关键字' }
    ]
    props.favoriteIds = ['first', 'unavailable']
    props.loadFavorites = vi.fn().mockResolvedValue(true)
    props.saveFavorites = vi
      .fn()
      .mockResolvedValueOnce(false)
      .mockImplementation(async (ids) => {
        props.favoriteIds = ids
        return true
      })

    await component.editFavorites()
    expect(component.favoriteOptions.value.map(({ id }) => id)).toEqual(['first', 'last', 'extra'])
    component.favoriteQuery.value = '关键字'
    expect(component.favoriteOptions.value.map(({ id }) => id)).toEqual(['extra'])
    component.favoriteDraft.value = ['unavailable', 'extra']

    await component.confirmFavorites()
    expect(component.editingFavorites.value).toBe(true)
    expect(component.favoriteError.value).toContain('保存失败')
    expect(component.visibleFavorites.value.map(({ id }) => id)).toEqual(['first'])
    await component.confirmFavorites()
    expect(component.editingFavorites.value).toBe(false)
    expect(props.saveFavorites).toHaveBeenLastCalledWith(['unavailable', 'extra'])
    expect(component.visibleFavorites.value.map(({ id }) => id)).toEqual(['extra'])
    expect(component.visibleGroups.value.flatMap(({ tasks }) => tasks.map(({ id }) => id))).toEqual(
      ['first', 'last']
    )
  })
})
