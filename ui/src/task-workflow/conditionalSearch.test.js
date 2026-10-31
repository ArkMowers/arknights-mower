import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { createSSRApp, h, ref } from 'vue'
import { renderToString } from 'vue/server-renderer'
import { createPinia } from 'pinia'
import axios from 'axios'
import { useConfigStore } from '@/stores/config'
import Clue from '@/components/Clue.vue'
import Recruit from '@/components/Recruit.vue'
import LongTasks from '@/components/LongTasks.vue'
import MaaWeekly from '@/components/MaaWeekly.vue'
import { matchesSettingsSearch } from '@/utils/settingsSearch'
import { createTaskWorkflow } from './model'

vi.mock('axios', () => ({ default: { get: vi.fn(), post: vi.fn(), patch: vi.fn() } }))
vi.mock('vue', async (original) => ({
  ...(await original()),
  useSSRContext: () => ({ modules: new Set() })
}))
vi.mock('naive-ui', async (original) => {
  const library = await original()
  const wrapper = (name) => ({
    inheritAttrs: false,
    props: ['value', 'label', 'title', 'show'],
    setup(props, { slots }) {
      return () => {
        if (name === 'NModal' && !props.show) return null
        return h('div', [
          props.title,
          props.label,
          slots.trigger?.(),
          slots.header?.(),
          slots.label?.(),
          slots.default?.()
        ])
      }
    }
  })
  return {
    ...library,
    ...Object.fromEntries(
      Object.keys(library)
        .filter((name) => /^N[A-Z]/.test(name))
        .map((name) => [name, wrapper(name)])
    ),
    useMessage: () => ({}),
    useDialog: () => ({})
  }
})

let config

beforeEach(() => {
  const storage = { getItem: vi.fn(() => null), setItem: vi.fn(), removeItem: vi.fn() }
  vi.stubGlobal('sessionStorage', storage)
  vi.stubGlobal('localStorage', storage)
  vi.stubGlobal('window', { sessionStorage: storage, localStorage: storage })
})

afterEach(() => {
  config?.$dispose()
  vi.clearAllMocks()
  vi.unstubAllGlobals()
})

function setup(Component, overrides = {}, props = {}) {
  const app = createSSRApp(Component, props)
  app.use(createPinia())
  app.provide('axios', axios)
  app.provide('mobile', ref(false))
  app.provide('loaded', ref(false))
  app.provide('token', 'search-test-token')
  config = app.runWithContext(() => useConfigStore())
  Object.assign(config, {
    runtime_platform: 'windows',
    maa_long_task_type: 'sf',
    ...overrides
  })
  return app
}

function matchingTasks(query) {
  return createTaskWorkflow(config)
    .tasks.filter((task) =>
      matchesSettingsSearch(query, task.title, task.description, task.searchKeywords)
    )
    .map(({ id }) => id)
}

describe('task search before conditional controls render', () => {
  it.each([
    [Clue, { maa_mall_mode: 'mower' }, { task: 'shop', showEnable: false }, '按需领取信用'],
    [Recruit, { recruit_auto_5: 2 }, { showEnable: false }, '五星词条组合唯一时自动选择']
  ])(
    'renders an available conditional label from the real component',
    async (Component, values, props, label) => {
      expect(await renderToString(setup(Component, values, props))).toContain(label)
    }
  )

  it.each([
    ['base', 'maa', '按需领取信用'],
    ['base', 'mower', '按性价比购物'],
    ['shop', 'maa', '按需领取信用'],
    ['shop', 'mower', '只购买折扣物品'],
    ['shop', 'maa', '购物性价比阈值']
  ])(
    'finds shopping control %s/%s/%s without opening or changing its mode',
    async (task, mode, query) => {
      const app = setup(Clue, { maa_mall_mode: mode }, { task, showEnable: false })
      const before = JSON.stringify(config.$state)
      const html = await renderToString(app)
      expect(html).not.toContain(query)
      expect(matchingTasks(query)).toEqual(['shop'])
      expect(JSON.stringify(config.$state)).toBe(before)
      expect(axios.post).not.toHaveBeenCalled()
      expect(axios.patch).not.toHaveBeenCalled()
    }
  )

  it('finds the manual recruitment condition while automatic recruitment is selected', async () => {
    const query = '五星词条组合唯一时自动选择'
    const app = setup(Recruit, { recruit_auto_5: 1 }, { showEnable: false })
    const before = JSON.stringify(config.$state)
    expect(await renderToString(app)).not.toContain(query)
    expect(matchingTasks(query)).toEqual(['recruit'])
    expect(JSON.stringify(config.$state)).toBe(before)
  })

  it.each(['支援道具名称', '单次最大组装轮数', '导能单元', '坍缩范式', '烧水分队'])(
    'finds long-task field %s while the Secret Front controls are rendered',
    async (query) => {
      const app = setup(LongTasks, {}, { showEnable: false })
      const before = JSON.stringify(config.$state)
      expect(await renderToString(app)).not.toContain(query)
      expect(matchingTasks(query)).toEqual(['long'])
      expect(JSON.stringify(config.$state)).toBe(before)
    }
  )

  it('finds the local stage sanity fallback while MAA is selected', async () => {
    const query = '关卡体力默认值'
    const app = setup(MaaWeekly, { stage_plan_runner: 'maa' }, { showEnable: false })
    const before = JSON.stringify(config.$state)
    expect(await renderToString(app)).not.toContain(query)
    expect(matchingTasks(query)).toEqual(['stage-plan'])
    expect(JSON.stringify(config.$state)).toBe(before)
  })
})
