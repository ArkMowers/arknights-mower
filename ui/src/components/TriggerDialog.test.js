import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { createSSRApp, effectScope, nextTick, ref } from 'vue'
import { renderToString } from '@vue/server-renderer'
import { createPinia, defineStore, setActivePinia } from 'pinia'
import TriggerDialog from './TriggerDialog.vue'

const state = vi.hoisted(() => ({ injections: {}, groupsExpanded: false }))
vi.mock('vue', async (original) => ({
  ...(await original()),
  useSSRContext: () => ({ modules: new Set() }),
  inject: (key, fallback) => state.injections[key] ?? fallback
}))
vi.mock('@/stores/plan', () => ({ usePlanStore: vi.fn() }))
vi.mock('@/stores/depot', () => ({ usedepotStore: () => ({}) }))
vi.mock('@/stores/facility', () => ({ useFacilityStore: () => ({}) }))
vi.mock('@/stores/mastery', () => ({ useMasteryStore: () => ({}) }))
vi.mock('./TriggerEditor.vue', () => ({ default: { render: () => null } }))
vi.mock('naive-ui', async () => {
  const { h } = await import('vue')
  const content = {
    setup:
      (_, { slots }) =>
      () =>
        h('div', slots.default?.())
  }
  return {
    ...Object.fromEntries(
      [
        'NModal',
        'NScrollbar',
        'NForm',
        'NFormItem',
        'NSelect',
        'NRadioGroup',
        'NRadioButton',
        'NText',
        'NSpace',
        'NInput',
        'NButton',
        'NPopconfirm',
        'NCard',
        'NCode',
        'NCollapseItem'
      ].map((name) => [name, content])
    ),
    NCollapse: {
      setup:
        (_, { slots }) =>
        () =>
          state.groupsExpanded ? h('div', slots.default?.()) : null
    },
    NAlert: {
      props: ['title'],
      setup:
        (props, { slots }) =>
        () =>
          h('section', [props.title, slots.default?.()])
    }
  }
})

let scope
let component
let store
beforeEach(() => {
  state.groupsExpanded = false
  setActivePinia(createPinia())
  store = defineStore('trigger-dialog-test', {
    state: () => ({
      sub_plan: 0,
      backup_plans: [{ group_ids: ['default'], type: 'global' }],
      backup_groups: [{ id: 'default', name: '默认分组' }]
    })
  })()
  state.injections = {
    planStore: store,
    planEditLocked: ref(false),
    show_trigger_editor: ref(false)
  }
  scope = effectScope()
  component = scope.run(() => TriggerDialog.setup({}, { expose: () => {} }))
})
afterEach(() => {
  scope.stop()
  vi.unstubAllGlobals()
})

it.each([
  ['HTTP without randomUUID', {}],
  ['HTTPS with randomUUID', { randomUUID: () => 'secure-uuid' }],
  ['browser without crypto', undefined]
])('creates and selects a group on %s', async (_, crypto) => {
  vi.stubGlobal('crypto', crypto)
  component.new_group_name.value = '  夜间  '
  component.create_group()
  await nextTick()
  const group = store.backup_groups[1]
  expect(group).toMatchObject({
    name: '夜间',
    trigger: { left: '', operator: '', right: '' }
  })
  expect(group.id).toBeTruthy()
  expect(store.backup_plans[0].group_ids).toEqual(['default', group.id])
  expect(component.selected_group.value).toEqual(group)
  expect(component.new_group_name.value).toBe('')
  component.update_group_trigger({ left: '1', operator: '==', right: '1' })
  expect(group.trigger).toEqual({ left: '1', operator: '==', right: '1' })
})

it('preserves imported groups and avoids duplicate IDs when creating and deleting groups', async () => {
  store.backup_groups.push(
    { id: 'group-1', name: '已有分组' },
    { id: 'legacy-uuid', name: '导入分组' }
  )
  store.backup_plans[0].group_ids.push('legacy-uuid')
  const original = JSON.parse(JSON.stringify(store.backup_groups))
  for (const name of ['新增一', '新增二']) {
    component.new_group_name.value = name
    component.create_group()
    await nextTick()
  }
  const ids = store.backup_groups.map((group) => group.id)
  expect(new Set(ids).size).toBe(5)
  expect(store.backup_groups.slice(0, 3)).toEqual(original)
  expect(store.backup_plans[0].group_ids).toEqual(['default', 'legacy-uuid', ...ids.slice(3)])
  component.remove_group(ids[3])
  component.new_group_name.value = '重新创建'
  component.create_group()
  await nextTick()
  expect(new Set(store.backup_groups.map((group) => group.id)).size).toBe(5)
  expect(store.backup_plans[0].group_ids).toEqual([
    'default',
    'legacy-uuid',
    ids[4],
    store.backup_groups[4].id
  ])
})

it('ignores empty names and prevents creation while editing is locked', () => {
  component.new_group_name.value = '  '
  component.create_group()
  state.injections.planEditLocked.value = true
  component.new_group_name.value = '夜间'
  component.create_group()
  expect(store.backup_groups).toEqual([{ id: 'default', name: '默认分组' }])
  expect(store.backup_plans[0].group_ids).toEqual(['default'])
})

it('shows both group hints only inside expanded group management', async () => {
  store.backup_groups.push(
    { id: 'deep', name: '深海', trigger: { left: '', operator: '', right: '' } },
    { id: 'pine', name: '红松', trigger: {} }
  )
  const collapsed = await renderToString(createSSRApp(TriggerDialog))
  expect(collapsed).not.toContain('自定义分组同时只生效一个')
  expect(collapsed).not.toContain('请为分组添加生效条件')
  state.groupsExpanded = true
  const html = await renderToString(createSSRApp(TriggerDialog))
  expect(html).toContain('自定义分组同时只生效一个')
  expect(html).toContain('请为分组添加生效条件')
  expect(html).toContain('深海、红松')
  expect(html).toContain('不会生效')
  expect(html).not.toContain('默认分组、')
})

it('clears the empty-group hint when a condition is set and preserves configured false conditions', async () => {
  state.groupsExpanded = true
  component.new_group_name.value = '夜间'
  component.create_group()
  await nextTick()
  expect(component.groups_without_condition.value.map((group) => group.name)).toEqual(['夜间'])
  component.update_group_trigger({ left: 'False', operator: '', right: '' })
  expect(component.groups_without_condition.value).toEqual([])
  const html = await renderToString(createSSRApp(TriggerDialog))
  expect(html).not.toContain('请为分组添加生效条件')
  expect(html).toContain('自定义分组同时只生效一个')
})
