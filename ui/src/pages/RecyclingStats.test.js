import { renderToString } from 'vue/server-renderer'
import { createSSRApp, ref } from 'vue'
import { createMemoryHistory, createRouter } from 'vue-router'
import { describe, expect, it, vi } from 'vitest'
import RecyclingStats from './RecyclingStats.vue'

vi.mock('@/stores/config', () => ({ useConfigStore: () => ({ theme: ref('light') }) }))
vi.mock('pinia', () => ({ storeToRefs: (store) => store }))
vi.mock('vue-echarts', () => ({ default: { render: () => null } }))
vi.mock('naive-ui', () => {
  const wrapper = {
    inheritAttrs: false,
    setup:
      (_, { slots }) =>
      () =>
        slots.default?.()
  }
  return Object.fromEntries(
    [
      'NAlert',
      'NButton',
      'NCollapse',
      'NCollapseItem',
      'NDatePicker',
      'NEmpty',
      'NIcon',
      'NPagination',
      'NScrollbar',
      'NSpin'
    ].map((name) => [name, wrapper])
  )
})

async function render(calculator) {
  const response = {
    total: 0,
    materials: [],
    qualities: [],
    records: [],
    comparison: {
      actual_sanity: 0,
      expected_sanity: 0,
      difference: 0,
      per_material: 22.749025792388053,
      extra_rate: 0.052613,
      unknown_materials: [],
      unmodeled_materials: [],
      source: { source: '计算表', sheet: '计算表', ranges: [] },
      calculator
    }
  }
  const app = createSSRApp({
    ...RecyclingStats,
    async setup(props, context) {
      const page = RecyclingStats.setup(props, context)
      await page.load()
      return page
    }
  })
  const router = createRouter({
    history: createMemoryHistory(),
    routes: ['/', '/mowersettings'].map((path) => ({ path, component: { render: () => null } }))
  })
  await router.push('/?token=session-token')
  app.use(router)
  app.provide('axios', { get: vi.fn().mockResolvedValue({ data: response }) })
  return renderToString(app)
}

describe('回收站两种机制对照', () => {
  const calculator = {
    daily_sanity: 11.972960143201481,
    configured_daily_sanity: 11.972960143201481,
    manufacturing_equivalent: 0.4344981007003046,
    elite0_equivalent: 0.08689962014006092,
    elite2_equivalent: 0.13034943021009138
  }
  it('渲染默认和顶替假设各自的日产与旅骨效率', async () => {
    const html = await render({
      ...calculator,
      replacement: {
        daily_sanity: 11.374512896194027,
        configured_daily_sanity: 11.374512896194027,
        manufacturing_equivalent: 0.4127804812407833,
        elite0_equivalent: 0.08255609624815666,
        elite2_equivalent: 0.123834144372235
      }
    })
    expect(html).toContain('普通池和额外池各产一次（默认假设）')
    expect(html).toContain('额外池顶替普通池（对照假设）')
    for (const value of ['11.973', '11.375', '8.69%', '13.03%', '8.26%', '12.38%']) {
      expect(html).toContain(value)
    }
    expect(html).toContain('实际机制尚未确认')
    expect(html).toContain('href="/mowersettings?token=session-token"')
  })
  it('旧接口没有对照数据时保留默认结果并隐藏对照区域', async () => {
    const html = await render(calculator)
    expect(html).toContain('11.973')
    expect(html).not.toContain('额外池顶替普通池（对照假设）')
  })
})
