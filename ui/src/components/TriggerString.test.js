import { renderToString } from '@vue/server-renderer'
import { createRenderer, createSSRApp, h, nextTick, ref, ssrContextKey } from 'vue'
import { createPinia } from 'pinia'
import { afterEach, describe, expect, it, vi } from 'vitest'
import TriggerString from './TriggerString.vue'
import { usePlanStore, useRescuePlanStore } from '@/stores/plan'
import { useConfigStore } from '@/stores/config'
import { usedepotStore } from '@/stores/depot'
import { useFacilityStore } from '@/stores/facility'
import { useMasteryStore } from '@/stores/mastery'

vi.mock('naive-ui', async (importOriginal) => ({
  ...(await importOriginal()),
  NSelect: {
    props: ['options', 'value', 'defaultValue', 'onUpdate:value'],
    setup(props) {
      return () =>
        h(
          'select',
          {},
          props.options.map(({ label, value }) => h('option', { value }, label))
        )
    }
  },
  NAutoComplete: { render: () => h('input') }
}))

const cleanups = []
afterEach(() => {
  for (const cleanup of cleanups.splice(0)) cleanup()
  vi.restoreAllMocks()
})

function setup(rescue = false) {
  const pinia = createPinia()
  const context = createSSRApp({})
  context.use(pinia)
  context.provide('loaded', ref(false))
  const plan = context.runWithContext(() => (rescue ? useRescuePlanStore() : usePlanStore()))
  const other = context.runWithContext(() => (rescue ? usePlanStore() : useRescuePlanStore()))
  other.plan = other.fill_empty({ central: { plans: [{ agent: '陈', group: '其他排班' }] } })
  plan.plan = plan.fill_empty({})
  Object.assign(plan.plan.central.plans[0], {
    agent: '讯使',
    group: '自动化',
    replacement: ['红'],
    group_bindings: [{ group: '感知', replacement: ['黑角'] }]
  })
  plan.backup_plans = [{ plan: plan.fill_empty({}) }, { plan: plan.fill_empty({}) }]
  Object.assign(plan.backup_plans[0].plan.meeting.plans[0], { agent: '银灰', group: '深海' })
  plan.sub_plan = 1
  useConfigStore(pinia).product_switching.enable = false
  vi.spyOn(usedepotStore(pinia), 'loadInventory').mockResolvedValue({})
  vi.spyOn(useFacilityStore(pinia), 'load').mockResolvedValue({})
  vi.spyOn(useMasteryStore(pinia), 'loadPlanSummary').mockResolvedValue({})
  cleanups.push(() => {
    for (const store of pinia._s.values()) store.$dispose()
  })
  function provide(app) {
    app.use(pinia)
    app.provide('loaded', ref(false))
    app.provide('planStore', plan)
    app.provide(ssrContextKey, {})
    return app
  }
  return { plan, provide }
}

function mount(provide, data, onUpdate) {
  const renderer = createRenderer({
    createElement: () => ({}),
    createText: () => ({}),
    createComment: () => ({}),
    insert: (node, parent) => {
      node.parent = parent
    },
    remove() {},
    setText() {},
    setElementText() {},
    patchProp() {},
    parentNode: (node) => node.parent,
    nextSibling: () => null
  })
  const app = provide(
    renderer.createApp({ ...TriggerString, render: () => h('div') }, { data, onUpdate })
  )
  app.mount({})
  cleanups.unshift(() => app.unmount())
  return app._instance.setupState
}

describe('副表绑组心情选择', () => {
  it.each([false, true])('空副表仍显示主表及其他副表的完整绑组（救急=%s）', async (rescue) => {
    const { plan, provide } = setup(rescue)
    const before = JSON.stringify([plan.plan, plan.backup_plans])
    expect(plan.groups).toEqual([])
    const html = await renderToString(
      provide(
        createSSRApp(TriggerString, {
          data: 'op_data.group_min_mood("自动化")'
        })
      )
    )
    expect(html).toContain('<option value="自动化">自动化</option>')
    expect(html).toContain('<option value="感知">感知</option>')
    expect(html).toContain('<option value="深海">深海</option>')
    expect(html).not.toContain('其他排班')
    expect(JSON.stringify([plan.plan, plan.backup_plans])).toBe(before)
  })

  it('新建条件可选择绑组、切换最高心情并保存转义组名', async () => {
    const { plan, provide } = setup()
    const update = vi.fn()
    const editor = mount(provide, 'True', update)
    editor.set_op_type('group_mood')
    await nextTick()
    expect(update).toHaveBeenLastCalledWith('op_data.group_min_mood("自动化")')
    editor.update_group('感知')
    await nextTick()
    expect(update).toHaveBeenLastCalledWith('op_data.group_min_mood("感知")')
    editor.update_group_mood_mode('max')
    await nextTick()
    expect(update).toHaveBeenLastCalledWith('op_data.group_max_mood("感知")')
    plan.plan.central.plans[0].group_bindings.push({ group: 'A"组', replacement: ['砾'] })
    await nextTick()
    expect(plan.all_groups.filter((value) => value === 'A"组')).toHaveLength(1)
    editor.update_group('A"组')
    await nextTick()
    expect(update).toHaveBeenLastCalledWith('op_data.group_max_mood("A\\"组")')
  })

  it('切换编辑表或修改候选名单不重写已保存条件', async () => {
    const { plan, provide } = setup()
    const update = vi.fn()
    const editor = mount(provide, 'op_data.group_max_mood("感知")', update)
    for (const selected of ['main', 0, 1]) {
      plan.sub_plan = selected
      await nextTick()
      expect(plan.all_groups).toContain('感知')
    }
    plan.plan.central.plans[0].group_bindings = []
    await nextTick()
    expect(update).not.toHaveBeenCalled()
    expect(editor.data).toBe('op_data.group_max_mood("感知")')
  })
})
