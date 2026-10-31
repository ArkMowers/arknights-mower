import { renderToString } from 'vue/server-renderer'
import { createRenderer, createSSRApp, ref, ssrContextKey } from 'vue'
import { createMemoryHistory, createRouter } from 'vue-router'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import RecyclingStats from './RecyclingStats.vue'

const state = vi.hoisted(() => ({ theme: null, page: null, media: null }))
vi.mock('@/stores/config', () => ({ useConfigStore: () => ({ theme: state.theme }) }))
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

beforeEach(() => vi.useFakeTimers())
afterEach(() => {
  vi.clearAllTimers()
  vi.useRealTimers()
})

async function render(calculator, { records = [], client = {}, act } = {}) {
  const response = {
    total: 0,
    materials: [],
    qualities: [],
    records,
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
  const axios = { get: vi.fn().mockResolvedValue({ data: response }), post: vi.fn(), ...client }
  const app = createSSRApp({
    ...RecyclingStats,
    async setup(props, context) {
      const page = RecyclingStats.setup(props, context)
      state.page = page
      await page.load()
      await act?.(page, axios)
      return page
    }
  })
  const router = createRouter({
    history: createMemoryHistory(),
    routes: ['/', '/settings'].map((path) => ({ path, component: { render: () => null } }))
  })
  await router.push('/?token=session-token')
  app.use(router)
  app.provide('axios', axios)
  return renderToString(app)
}

describe('回收站两种机制对照', () => {
  beforeEach(() => {
    state.theme = ref('light')
    const listeners = new Set()
    state.media = {
      matches: false,
      addEventListener: (_type, listener) => listeners.add(listener),
      removeEventListener: (_type, listener) => listeners.delete(listener),
      change(matches) {
        this.matches = matches
        for (const listener of listeners) listener({ matches })
      }
    }
    vi.stubGlobal('window', { matchMedia: () => state.media })
  })
  afterEach(() => vi.unstubAllGlobals())

  const calculator = {
    daily_sanity: 11.972960143201481,
    configured_daily_sanity: 11.972960143201481,
    manufacturing_equivalent: 0.4344981007003046,
    elite0_equivalent: 0.08689962014006092,
    elite2_equivalent: 0.13034943021009138
  }
  it('页面和环图跟随系统主题变化且保留主题偏好', async () => {
    state.theme.value = 'system'
    state.media.matches = true
    const html = await render(calculator)
    expect(html).toContain('recycling-page dark')
    expect(state.page.chart.value.series[0].itemStyle.borderColor).toBe('#252a2f')
    state.media.change(false)
    expect(state.page.theme.value).toBe('light')
    expect(state.page.chart.value.series[0].itemStyle.borderColor).toBe('#ffffff')
    expect(state.theme.value).toBe('system')
    state.theme.value = 'dark'
    expect(state.page.chart.value.series[0].itemStyle.borderColor).toBe('#252a2f')
    state.theme.value = 'light'
    state.media.change(true)
    expect(state.page.chart.value.series[0].itemStyle.borderColor).toBe('#ffffff')
    expect(state.theme.value).toBe('light')
  })
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
    expect(html).toContain('href="/settings?token=session-token#task-accounts"')
  })
  it('旧接口没有对照数据时保留默认结果并隐藏对照区域', async () => {
    const html = await render(calculator)
    expect(html).toContain('11.973')
    expect(html).not.toContain('额外池顶替普通池（对照假设）')
  })
})

describe('回收站上传状态与手动重试', () => {
  const row = (id, upload_status) => ({
    id,
    upload_status,
    collected_at: 1759400000,
    materials: { 装置: 1 },
    operators: null
  })
  const response = (records) => ({
    data: { total: records.length, records, materials: [], qualities: [], comparison: null }
  })

  it('在记录后展示持久化状态，仅失败记录提供重试入口', async () => {
    const html = await render(undefined, {
      records: [
        row('done', 'submitted'),
        row('failed', 'failed'),
        row('pending', 'pending'),
        row('skip', 'skipped')
      ]
    })
    expect(html).toContain('已上传')
    expect(html).toContain('请求已提交，接口不提供入库确认')
    expect(html).toContain('上传失败')
    expect(html).toContain('待上传')
    expect(html).toContain('未上传（材料未识别）')
    expect(html.match(/重试上传/g)).toHaveLength(1)
  })

  it('重试只提交当前记录，阻止重复点击并刷新后台完成状态', async () => {
    const failed = row('event/a', 'failed')
    let accept
    const post = vi.fn().mockImplementation(
      () =>
        new Promise((resolve) => {
          accept = resolve
        })
    )
    const html = await render(undefined, {
      records: [failed],
      client: { post },
      act: async (page, axios) => {
        axios.get.mockResolvedValueOnce(response([row(failed.id, 'pending')]))
        axios.get.mockResolvedValueOnce(response([row(failed.id, 'submitted')]))
        const retry = page.retryUpload(failed)
        expect(page.retrying.value).toBe(failed.id)
        await page.retryUpload(failed)
        expect(post).toHaveBeenCalledTimes(1)
        expect(post).toHaveBeenCalledWith(
          expect.stringContaining('/report/recycling_history/event%2Fa/retry')
        )
        accept({ data: { upload_status: 'pending' } })
        await retry
        expect(page.retrying.value).toBe('')
        expect(page.data.value.records[0].upload_status).toBe('pending')
        await vi.advanceTimersByTimeAsync(2000)
        expect(page.data.value.records[0].upload_status).toBe('submitted')
        expect(vi.getTimerCount()).toBe(0)
      }
    })
    expect(html).toContain('已上传')
    expect(html).not.toContain('重试上传')
  })

  it('手动请求失败保留失败状态、错误提示和再次点击入口', async () => {
    const failed = row('failed', 'failed')
    const html = await render(undefined, {
      records: [failed],
      client: { post: vi.fn().mockRejectedValue(new Error('offline')) },
      act: (page) => page.retryUpload(failed)
    })
    expect(html).toContain('重试上传未能启动，请稍后再试')
    expect(html).toContain('上传失败')
    expect(html).toContain('重试上传')
  })

  it('待上传记录的状态刷新有次数上限，不重复触发上传', async () => {
    const html = await render(undefined, {
      records: [row('pending', 'pending')],
      act: async (page, axios) => {
        await page.retryUpload(row('pending', 'pending'))
        await page.retryUpload(row('done', 'submitted'))
        await vi.advanceTimersByTimeAsync(180000)
        expect(axios.get).toHaveBeenCalledTimes(61)
        expect(axios.post).not.toHaveBeenCalled()
        expect(vi.getTimerCount()).toBe(0)
      }
    })
    expect(html).toContain('待上传')
  })

  it('切换查询后旧的状态响应不覆盖新记录', async () => {
    let resolveOld
    await render(undefined, {
      records: [row('pending', 'pending')],
      act: async (page, axios) => {
        axios.get.mockImplementationOnce(
          () =>
            new Promise((resolve) => {
              resolveOld = resolve
            })
        )
        const oldLoad = page.load(false)
        axios.get.mockResolvedValueOnce(response([row('new', 'submitted')]))
        await page.load()
        resolveOld(response([row('pending', 'failed')]))
        await oldLoad
        expect(page.data.value.records[0].id).toBe('new')
        expect(page.data.value.records[0].upload_status).toBe('submitted')
        expect(vi.getTimerCount()).toBe(0)
      }
    })
  })

  it('离开页面后取消刷新并忽略未完成的请求', async () => {
    const renderer = createRenderer({
      createElement: () => ({}),
      createText: () => ({}),
      createComment: () => ({}),
      setText() {},
      setElementText() {},
      patchProp() {},
      insert() {},
      remove() {},
      parentNode: () => null,
      nextSibling: () => null
    })
    const axios = {
      get: vi.fn().mockResolvedValue(response([row('pending', 'pending')])),
      post: vi.fn()
    }
    let page
    let resolveLate
    const app = renderer.createApp({
      setup(props, context) {
        page = RecyclingStats.setup(props, context)
        return page
      },
      render: () => null
    })
    app.provide(ssrContextKey, { modules: new Set() })
    app.provide('axios', axios)
    app.mount({})
    try {
      await vi.advanceTimersByTimeAsync(0)
      expect(vi.getTimerCount()).toBe(1)
      axios.get.mockImplementationOnce(
        () =>
          new Promise((resolve) => {
            resolveLate = resolve
          })
      )
      const late = page.load(false)
      expect(vi.getTimerCount()).toBe(0)
      app.unmount()
      resolveLate(response([row('late', 'pending')]))
      await late
      await page.load()
      await page.retryUpload(row('failed', 'failed'))
      await vi.advanceTimersByTimeAsync(10000)
      expect(page.data.value.records[0].id).toBe('pending')
      expect(axios.get).toHaveBeenCalledTimes(2)
      expect(axios.post).not.toHaveBeenCalled()
      expect(vi.getTimerCount()).toBe(0)
    } finally {
      app.unmount()
    }
  })
})
