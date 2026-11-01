import { renderToString } from '@vue/server-renderer'
import { createSSRApp, h, ref } from 'vue'
import { createPinia } from 'pinia'
import { afterEach, expect, it, vi } from 'vitest'
import PlanAdvancedSettings from './PlanAdvancedSettings.vue'
import { useConfigStore } from '@/stores/config'
import { usePlanStore } from '@/stores/plan'

let selectProps, updateSelection
const sliderProps = []
vi.mock('naive-ui', async (importOriginal) => ({
  ...(await importOriginal()),
  NSlider: {
    props: { value: Number, min: Number, max: Number },
    setup(props) {
      sliderProps.push({ ...props })
      return () => h('input')
    }
  },
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
vi.mock('./MowerInputNumber.vue', () => ({
  default: {
    props: ['value', 'min'],
    setup: (props) => () => h('input', { value: props.value, min: props.min })
  }
}))
vi.mock('./SlickOperatorSelect.vue', () => ({ default: { render: () => h('select') } }))
vi.mock('./HelpText.vue', () => ({ default: { render: () => h('span') } }))

const stores = []
afterEach(() => {
  stores.forEach((store) => store.$dispose())
  stores.length = 0
  sliderProps.length = 0
})

it.each([0, 19, 20, 100])('无人机使用阈值最小为 20，保留已读取的值 %s', async (limit) => {
  const app = createSSRApp(PlanAdvancedSettings)
  app.use(createPinia())
  app.provide('loaded', ref(false))
  app.provide('mobile', ref(false))
  const config = app.runWithContext(() => useConfigStore())
  const plan = app.runWithContext(() => usePlanStore())
  stores.push(config, plan)
  expect(config.drone_count_limit).toBe(100)
  config.drone_count_limit = limit
  expect(await renderToString(app)).toContain(`<input value="${limit}" min="20"`)
  expect(config.drone_count_limit).toBe(limit)
  expect(config.build_advanced_settings().drone_count_limit).toBe(limit)
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
  config.resting_threshold = 35
  plan.plan = {
    meeting: { plans: [{ agent: 'A', group: '主表组', group_bindings: [{ group: '多绑组' }] }] }
  }
  plan.backup_plans = [{ plan: { meeting: { plans: [{ agent: 'B', group: '副表组' }] } } }]
  const html = await renderToString(app)
  expect(html).toContain('实时心情计算调控')
  expect(sliderProps).toContainEqual({ value: 35, min: 35, max: 80 })
  expect(html).toContain('各组心情阈值')
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
