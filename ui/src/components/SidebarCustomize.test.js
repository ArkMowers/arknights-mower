import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { createSSRApp, effectScope, reactive } from 'vue'
import { renderToString } from 'vue/server-renderer'
import SidebarCustomize from './SidebarCustomize.vue'
import { createSidebarPreferences } from '@/composables/sidebarPreferences'
import { i18n } from '@/i18n'

const state = vi.hoisted(() => ({ preferences: null }))
vi.mock('@/composables/sidebarPreferences', async (original) => ({
  ...(await original()),
  useSidebarPreferences: () => state.preferences
}))
vi.mock('vue', async (original) => ({
  ...(await original()),
  useSSRContext: () => ({ modules: new Set() })
}))
vi.mock('naive-ui', async (original) => {
  const { defineComponent, h } = await import('vue')
  return {
    ...(await original()),
    NModal: defineComponent({
      props: ['show', 'preset', 'title'],
      setup:
        (props, { slots }) =>
        () =>
          props.show
            ? h('section', { role: 'dialog', 'data-preset': props.preset }, [
                h('h2', props.title),
                slots.default?.(),
                slots.footer?.()
              ])
            : null
    })
  }
})

describe('sidebar page dialog', () => {
  let scope
  let component
  let props
  let emit
  let storage
  const availableKeys = () => component.availableEntries.value.map((item) => item.key)
  const placements = (key) =>
    state.preferences.state.value.placements.filter((item) => item.key === key)
  const render = (groupKey = props.groupKey) =>
    renderToString(createSSRApp(SidebarCustomize, { groupKey }))

  beforeEach(() => {
    storage = { getItem: () => null, setItem: vi.fn() }
    state.preferences = createSidebarPreferences({ storage })
    props = reactive({ groupKey: 'daily' })
    emit = vi.fn()
    scope = effectScope()
    component = scope.run(() => SidebarCustomize.setup(props, { expose: vi.fn(), emit }))
  })
  afterEach(() => {
    scope.stop()
    i18n.global.locale.value = 'zh-CN'
  })

  it('searches English page labels after a live locale change and saves original page keys only on confirmation', async () => {
    props.groupKey = 'reports'
    const original = JSON.stringify(state.preferences.state.value)
    component.selectedKeys.value = ['log']
    i18n.global.locale.value = 'en-US'
    component.search.value = 'logs'
    expect(component.availableEntries.value.map(({ key }) => key)).toEqual(['log'])
    expect(component.availableEntries.value[0].label).toBe('Logs')
    expect(component.selectedKeys.value).toEqual(['log'])
    expect(JSON.stringify(state.preferences.state.value)).toBe(original)
    expect(storage.setItem).not.toHaveBeenCalled()
    expect(await render()).toContain('Add pages')
    const add = vi.spyOn(state.preferences, 'addEntry')
    component.confirm()
    expect(add).toHaveBeenCalledExactlyOnceWith('log', 'reports')
  })

  it('cancels through the button and modal dismissal without saving or adding pages', async () => {
    const initial = JSON.stringify(state.preferences.state.value)
    expect(SidebarCustomize.props.groupKey.default).toBeNull()
    expect(await render(null)).not.toContain('role="dialog"')
    const html = await render()
    expect(html).toContain('data-preset="card"')
    expect(html).toContain('添加页面')
    expect(html).toContain('aria-label="取消添加页面"')
    expect(html).toMatch(/<button[^>]*disabled[^>]*aria-label="确认添加页面"/)
    component.confirm()
    component.updateShow(true)
    expect(emit).not.toHaveBeenCalled()

    // The modal emits update:show=false for its close button, Escape and mask clicks.
    for (const dismiss of [component.close, () => component.updateShow(false)]) {
      component.search.value = '运行'
      component.selectedKeys.value = ['record-line']
      dismiss()
      expect(component.search.value).toBe('')
      expect(component.selectedKeys.value).toEqual([])
    }
    expect(emit.mock.calls).toEqual([['close'], ['close']])
    expect(storage.setItem).not.toHaveBeenCalled()
    expect(JSON.stringify(state.preferences.state.value)).toBe(initial)
  })

  it('adds only confirmed selections and retains the draft when adding fails', () => {
    props.groupKey = 'reports'
    const originalLog = { ...placements('log')[0] }
    const originalPlan = { ...placements('plan')[0] }
    const addEntry = vi.spyOn(state.preferences, 'addEntry')
    component.selectedKeys.value = ['log', 'plan']
    expect(storage.setItem).not.toHaveBeenCalled()
    component.confirm()
    expect(addEntry.mock.calls).toEqual([
      ['log', 'reports'],
      ['plan', 'reports']
    ])
    expect(placements('log')).toEqual(
      expect.arrayContaining([originalLog, expect.objectContaining({ group: 'reports' })])
    )
    expect(placements('plan')).toEqual(
      expect.arrayContaining([originalPlan, expect.objectContaining({ group: 'reports' })])
    )
    expect(emit.mock.calls).toEqual([['close']])

    emit.mockClear()
    addEntry.mockReturnValueOnce(false)
    component.selectedKeys.value = ['doc']
    component.confirm()
    expect(component.error.value).toBe('暂时无法添加页面，请重试。')
    expect(component.selectedKeys.value).toEqual(['doc'])
    expect(emit).not.toHaveBeenCalled()
  })

  it('disables visible pages in the target while allowing copies from other groups', async () => {
    expect(component.addedKeys.value.has('log')).toBe(true)
    expect(component.addedKeys.value.has('record-line')).toBe(false)
    const html = await render()
    expect(html).toMatch(/<input[^>]*disabled[^>]*data-page-key="log"/)
    expect(html).toMatch(/data-sidebar-entry="log"[\s\S]*?已添加/)
    expect(html.match(/<input[^>]*data-page-key="record-line"/)[0]).not.toContain('disabled')

    state.preferences.addEntry('log', 'reports')
    props.groupKey = 'reports'
    expect(component.addedKeys.value.has('log')).toBe(true)
    expect(component.addedKeys.value.has('plan')).toBe(false)
    state.preferences.setVisible('record-line', false)
    expect(component.addedKeys.value.has('record-line')).toBe(false)

    state.preferences.addEntry('record-line', 'pinned')
    props.groupKey = 'pinned'
    expect(component.addedKeys.value.has('record-line')).toBe(true)
    expect(component.addedKeys.value.has('log')).toBe(false)
    component.selectedKeys.value = ['log']
    component.confirm()
    expect(placements('log').some((item) => item.group === 'daily' && !item.pinned)).toBe(true)
    expect(placements('log').some((item) => item.group === 'reports' && !item.pinned)).toBe(true)
    expect(placements('log').some((item) => item.pinned)).toBe(true)
  })

  it('clears selections, search and errors when the group changes or the dialog reopens', () => {
    for (const nextGroup of ['reports', null, 'reports']) {
      component.search.value = '运行'
      component.selectedKeys.value = ['log']
      component.error.value = '暂时无法添加页面，请重试。'
      props.groupKey = nextGroup
      expect(component.search.value).toBe('')
      expect(component.selectedKeys.value).toEqual([])
      expect(component.error.value).toBe('')
    }
    component.selectedKeys.value = ['log']
    component.close()
    props.groupKey = null
    props.groupKey = 'reports'
    expect(component.selectedKeys.value).toEqual([])
    expect(storage.setItem).not.toHaveBeenCalled()
  })

  it('searches the fixed page catalog and excludes the fixed footer pages', async () => {
    expect(availableKeys()).not.toContain('chat')
    expect(availableKeys()).not.toContain('mower-settings')
    const html = await render()
    expect(html).toContain('aria-label="搜索页面"')
    expect(html).not.toContain('data-page-key="chat"')
    expect(html).not.toContain('data-page-key="mower-settings"')
    component.search.value = '  PrTs  '
    expect(availableKeys()).toEqual(['prts'])
    component.search.value = '心情'
    expect(availableKeys()).toEqual(['record-line'])
    component.search.value = '不存在的页面'
    expect(availableKeys()).toEqual([])
  })
})
