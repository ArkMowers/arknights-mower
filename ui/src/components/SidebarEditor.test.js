import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { createSSRApp, effectScope, reactive } from 'vue'
import { renderToString } from 'vue/server-renderer'
import SidebarEditor from './SidebarEditor.vue'
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
    NPopconfirm: defineComponent({
      setup:
        (_, { slots }) =>
        () =>
          h('span', slots.trigger?.())
    }),
    NModal: defineComponent({
      props: ['show'],
      setup:
        (props, { slots }) =>
        () =>
          props.show
            ? h('section', { role: 'dialog' }, [slots.default?.(), slots.footer?.()])
            : null
    })
  }
})

describe('sidebar editing window', () => {
  let scope
  let component
  let props
  let emit
  beforeEach(() => {
    state.preferences = createSidebarPreferences({
      storage: { getItem: () => null, setItem: vi.fn() }
    })
    props = reactive({ show: true, request: {} })
    emit = vi.fn()
    scope = effectScope()
    component = scope.run(() => SidebarEditor.setup(props, { expose: vi.fn(), emit }))
  })
  afterEach(() => {
    scope.stop()
    i18n.global.locale.value = 'zh-CN'
  })

  it('updates built-in labels and current validation while preserving custom group names and drafts', async () => {
    const customKey = state.preferences.addGroup('我的分组')
    const original = JSON.stringify(state.preferences.state.value)
    component.startNaming({ action: 'rename-group', groupKey: customKey })
    component.groupDraft.value = '  '
    component.saveName()
    const chineseError = component.nameError.value
    component.groupDraft.value = '还没有保存的名称'
    i18n.global.locale.value = 'en-US'
    expect(component.nameError.value).not.toBe(chineseError)
    expect(component.groups.value.find((group) => group.key === customKey).title).toBe('我的分组')
    expect(
      component.groups.value
        .find((group) => group.key === 'daily')
        .items.find((item) => item.key === 'log').label
    ).toBe('Logs')
    expect(component.groupDraft.value).toBe('还没有保存的名称')
    expect(JSON.stringify(state.preferences.state.value)).toBe(original)
    expect(await renderToString(createSSRApp(SidebarEditor, props))).toContain('Edit sidebar')
  })

  it('keeps adding pages and creating groups available after every group is dissolved', async () => {
    for (const group of [...state.preferences.state.value.groups])
      state.preferences.removeGroup(group.key)
    expect(component.groups.value).toEqual([])
    expect(
      component.outerSections.value
        .find((section) => section.key === 'ungrouped')
        .items.some((item) => item.key === 'log')
    ).toBe(true)
    const html = await renderToString(createSSRApp(SidebarEditor, props))
    expect(html).toContain('role="dialog"')
    expect(html).toContain('添加页面')
    expect(html).toContain('新建分组')
    expect(html).toContain('data-editor-section="ungrouped"')
    expect(html).toContain('data-editor-group="pinned"')
    expect(html).toContain('data-editor-group="ungrouped"')
    expect(html).not.toContain('<select')
    expect(html).toMatch(/<button[^>]*type="button"[^>]*aria-label="移除运行日志"/)
    component.pickerGroup.value = 'ungrouped'
    component.close()
    expect(component.pickerGroup.value).toBeNull()
    expect(emit).toHaveBeenCalledWith('update:show', false)
  })

  it('offers task settings in the editing window and restores its route through the page picker', async () => {
    const renderEditor = () => renderToString(createSSRApp(SidebarEditor, props))
    const original = component.groups.value
      .find((group) => group.key === 'daily')
      .items.find((item) => item.key === 'task-settings')
    expect(original).toMatchObject({ label: '全部设置', to: '/settings' })
    expect(await renderEditor()).toContain('aria-label="移除全部设置"')
    expect(state.preferences.removeEntry(original.id)).toBe(true)
    expect(await renderEditor()).not.toContain('aria-label="移除全部设置"')

    const editorWithPicker = {
      ...SidebarEditor,
      setup(props, context) {
        const bindings = SidebarEditor.setup(props, context)
        bindings.pickerGroup.value = 'daily'
        return bindings
      }
    }
    const pickerHtml = await renderToString(createSSRApp(editorWithPicker, props))
    expect(pickerHtml).toContain('aria-label="添加全部设置"')
    expect(pickerHtml.match(/<input[^>]*data-page-key="task-settings"/)[0]).not.toContain(
      'disabled'
    )
    const picker = scope.run(() =>
      SidebarCustomize.setup(reactive({ groupKey: 'daily' }), { expose: vi.fn(), emit: vi.fn() })
    )
    picker.search.value = '全部设置'
    expect(picker.availableEntries.value.map((item) => item.key)).toEqual(['task-settings'])
    picker.selectedKeys.value = ['task-settings']
    picker.confirm()

    const restored = component.groups.value
      .find((group) => group.key === 'daily')
      .items.find((item) => item.key === 'task-settings')
    expect(restored).toMatchObject({ label: '全部设置', to: '/settings' })
    expect(await renderEditor()).toContain('aria-label="移除全部设置"')
  })

  it('does not offer removed settings or rescue entries through the page picker', async () => {
    const picker = scope.run(() =>
      SidebarCustomize.setup(reactive({ groupKey: 'daily' }), { expose: vi.fn(), emit: vi.fn() })
    )
    for (const query of ['Mower 设置', '救急排班编辑']) {
      picker.search.value = query
      expect(picker.availableEntries.value).toEqual([])
    }
    const html = await renderToString(createSSRApp(SidebarEditor, props))
    expect(html).not.toContain('救急排班编辑')
    expect(html).not.toContain('Mower 设置')
  })

  it('validates names and applies group creation and renaming only after confirmation', () => {
    const original = state.preferences.state.value.groups.length
    component.startNaming()
    component.groupDraft.value = '  '
    component.saveName()
    expect(component.nameError.value).toBe('请填写分组名称。')
    expect(state.preferences.state.value.groups).toHaveLength(original)
    component.groupDraft.value = '  我的页面  '
    component.saveName()
    const group = state.preferences.state.value.groups.at(-1)
    expect(group.title).toBe('我的页面')
    component.startNaming({ action: 'rename-group', groupKey: group.key })
    component.groupDraft.value = '工具'
    expect(state.preferences.state.value.groups.at(-1).title).toBe('我的页面')
    component.saveName()
    expect(state.preferences.state.value.groups.at(-1).title).toBe('工具')
  })

  it('moves the requested copy and rejects dragging into a group that already has that page', () => {
    const item = component.groups.value[0].items.find((item) => item.key === 'log')
    state.preferences.addEntry('log', 'reports')
    expect(
      component.canMovePage({
        to: { dataset: { editorGroup: 'reports' } },
        draggedContext: { element: item }
      })
    ).toBe(false)
    component.onPageSort({ added: { element: item, newIndex: 0 } }, 'ungrouped')
    expect(state.preferences.standaloneItems.value.map((item) => item.key)).toContain('log')
    expect(
      state.preferences.visibleSections.value
        .find((group) => group.key === 'reports')
        .items.map((item) => item.key)
    ).toContain('log')
    component.onPageSort({ added: { element: item, newIndex: 0 } }, 'pinned')
    expect(state.preferences.pinnedItems.value.map((item) => item.id)).toEqual([item.id])
  })

  it('orders dragged groups and pages using their destination position', () => {
    const groups = component.groups.value
    const lastGroup = groups.at(-1)
    component.onGroupSort({ moved: { element: lastGroup, newIndex: 0 } })
    expect(state.preferences.state.value.groups[0].key).toBe(lastGroup.key)
    const daily = component.groups.value.find((group) => group.key === 'daily')
    const item = daily.items.at(-1)
    component.onPageSort({ moved: { element: item, newIndex: 0 } }, 'daily')
    expect(
      state.preferences.visibleSections.value.find((group) => group.key === 'daily').items[0].id
    ).toBe(item.id)
  })
})
