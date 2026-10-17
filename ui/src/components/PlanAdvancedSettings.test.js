import { renderToString } from '@vue/server-renderer'
import { createSSRApp, h, ref } from 'vue'
import { createPinia } from 'pinia'
import { afterEach, expect, it, vi } from 'vitest'
import PlanAdvancedSettings from './PlanAdvancedSettings.vue'
import { useConfigStore } from '@/stores/config'
import { usePlanStore } from '@/stores/plan'

let selectProps, updateSelection
vi.mock('naive-ui', async (importOriginal) => ({
  ...(await importOriginal()),
  NSlider: { render: () => h('input') },
  NSelect: {
    props: { value: Array, options: Array, multiple: Boolean, filterable: Boolean, tag: Boolean },
    emits: ['update:value'],
    setup(props, { emit }) {
      selectProps = props
      updateSelection = (value) => emit('update:value', value)
      return () => h('select')
    }
  }
}))
vi.mock('./MowerInputNumber.vue', () => ({ default: { render: () => h('input') } }))
vi.mock('./SlickOperatorSelect.vue', () => ({ default: { render: () => h('select') } }))
vi.mock('./HelpText.vue', () => ({ default: { render: () => h('span') } }))

const stores = []
afterEach(() => {
  stores.forEach((store) => store.$dispose())
  stores.length = 0
})

it('从主副表及多绑组提供多选，保留已保存的组名并绑定配置', async () => {
  const app = createSSRApp(PlanAdvancedSettings)
  app.use(createPinia())
  app.provide('loaded', ref(false))
  app.provide('mobile', ref(false))
  const config = app.runWithContext(() => useConfigStore())
  const plan = app.runWithContext(() => usePlanStore())
  stores.push(config, plan)
  config.group_mood_gap_exclusions = ['暂未使用组']
  plan.plan = {
    meeting: { plans: [{ agent: 'A', group: '主表组', group_bindings: [{ group: '多绑组' }] }] }
  }
  plan.backup_plans = [{ plan: { meeting: { plans: [{ agent: 'B', group: '副表组' }] } } }]
  const html = await renderToString(app)
  expect(html).toContain('延后回班排除组')
  expect(selectProps.options.map((option) => option.value)).toEqual([
    '主表组',
    '多绑组',
    '副表组',
    '暂未使用组'
  ])
  expect(selectProps).toMatchObject({
    multiple: true,
    filterable: true,
    tag: true,
    value: ['暂未使用组']
  })
  updateSelection(['主表组', '副表组'])
  expect(config.build_advanced_settings().group_mood_gap_exclusions).toEqual(['主表组', '副表组'])
  updateSelection([])
  expect(config.group_mood_gap_exclusions).toEqual([])
})
