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

async function render(
  calculator,
  { records = [], materials = [], qualities = [], client = {}, act } = {}
) {
  const response = {
    total: 0,
    materials,
    qualities,
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

describe('回收站理论收益换算', () => {
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
    daily_sanity: 11.374512896194027,
    configured_daily_sanity: 11.374512896194027,
    manufacturing_equivalent: 0.4127804812407833,
    ten_percent_equivalent: 0.04127804812407833
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
  it('展示统一的理论日产和每10%回收站效率的制造站换算', async () => {
    const html = await render(calculator)
    expect(html).toContain('回收站理论收益')
    expect(html).toContain('10%回收站效率等效制造站')
    for (const value of ['11.375', '41.28%', '4.13%']) {
      expect(html).toContain(value)
    }
    expect(html).not.toContain('旅骨')
    expect(html).not.toContain('假设')
    expect(html).not.toContain('顶替')
    expect(html).toContain('收益计算')
    expect(html).toContain('生产换算')
    expect(html).toContain('数据来源')
    expect(html).toContain('不使用手填效率')
    expect(html).not.toContain('设定效率理论日产')
    expect(html).toContain('href="/settings?token=session-token#task-accounts"')
  })
  it('缺少计算器结果时保留材料比较说明', async () => {
    const html = await render(undefined)
    expect(html).toContain('收益计算')
    expect(html).toContain('22.7490')
    expect(html).not.toContain('10%回收站效率等效制造站')
  })
})

describe('材料品质悬浮明细', () => {
  function tooltip(page, index, percent) {
    const option = page.chart.value
    const slice = option.series[0].data[index]
    return option.tooltip.formatter({
      name: slice.name,
      value: slice.value,
      percent,
      data: slice
    })
  }

  it('按品质展示范围累计的材料名称和数量，保留总数及占比', async () => {
    const html = await render(undefined, {
      materials: [
        { name: '装置', rarity: 2, count: 9 },
        { name: '聚合剂', rarity: 5, count: 3 },
        { name: '双极纳米片', rarity: 5, count: 1 }
      ],
      qualities: [
        { rarity: 2, count: 9 },
        { rarity: 5, count: 4 }
      ],
      records: [{ id: 'latest', materials: { 聚合剂: 1 }, operators: [], collected_at: 1 }],
      act(page) {
        const gold = tooltip(page, 1, 30.77)
        expect(gold).toContain('金色材料：4 个（30.77%）')
        expect(gold).toContain('<span>聚合剂</span><strong>× 3</strong>')
        expect(gold).toContain('<span>双极纳米片</span><strong>× 1</strong>')
        expect(gold).not.toContain('装置')
        const green = tooltip(page, 0, 69.23)
        expect(green).toContain('绿色材料：9 个（69.23%）')
        expect(green).toContain('<span>装置</span><strong>× 9</strong>')
        expect(green).not.toContain('聚合剂')
        expect(page.chart.value.tooltip).toMatchObject({
          renderMode: 'html',
          confine: true,
          enterable: true
        })
      }
    })
    expect(html).toContain('悬停扇区或下方品质行，查看材料明细')
  })

  it('品质行悬停或聚焦时定位实际扇区，无实际产出的品质不打开浮窗', async () => {
    const dispatchAction = vi.fn()
    const html = await render(undefined, {
      materials: [
        { name: '聚合剂', rarity: 5, count: 1 },
        { name: '装置', rarity: 2, count: 99 }
      ],
      qualities: [
        { rarity: 5, count: 1 },
        { rarity: 2, count: 99 }
      ],
      act(page) {
        page.data.value.comparison.qualities = [{ rarity: 4, probability: 0.1 }]
        page.qualityChart.value = { dispatchAction }
        page.showQualityTooltip(5)
        expect(dispatchAction).toHaveBeenLastCalledWith({
          type: 'showTip',
          seriesIndex: 0,
          dataIndex: 0
        })
        page.showQualityTooltip(2)
        expect(dispatchAction).toHaveBeenLastCalledWith({
          type: 'showTip',
          seriesIndex: 0,
          dataIndex: 1
        })
        page.hideQualityTooltip()
        expect(dispatchAction).toHaveBeenLastCalledWith({ type: 'hideTip' })
        page.showQualityTooltip(4)
        expect(dispatchAction).toHaveBeenCalledTimes(3)
      }
    })
    expect(html.match(/class="quality-row" tabindex="0"/g)).toHaveLength(2)
  })

  it('未知品质的材料仍展示名称和数量，并转义材料名称', async () => {
    await render(undefined, {
      materials: [{ name: '<img src=x onerror="alert(1)"> & 未知', rarity: null, count: 2 }],
      qualities: [{ rarity: null, count: 2 }],
      act(page) {
        const unknown = tooltip(page, 0, 100)
        expect(unknown).toContain('未知品质：2 个（100%）')
        expect(unknown).toContain('&lt;img src=x onerror=&quot;alert(1)&quot;&gt; &amp; 未知')
        expect(unknown).toContain('× 2')
        expect(unknown).not.toContain('<img')
      }
    })
  })

  it('极小扇区在原环图外也能命中，透明区域保留真实数量及占比', async () => {
    await render(undefined, {
      materials: [
        { name: '装置', rarity: 2, count: 9999 },
        { name: '聚合剂', rarity: 5, count: 1 }
      ],
      qualities: [
        { rarity: 2, count: 9999 },
        { rarity: 5, count: 1 }
      ],
      act(page) {
        const { series, tooltip } = page.chart.value
        const api = { getWidth: () => 400, getHeight: () => 200 }
        expect(series[1].renderItem({ dataIndex: 0 }, api)).toBeUndefined()
        const target = series[1].renderItem({ dataIndex: 1 }, api)
        expect(target.type).toBe('sector')
        expect(target.style.fill).toBe('transparent')
        expect(target.shape).toMatchObject({ cx: 200, cy: 100, r0: 61, r: 88 })
        // 点 (205, 15) 位于原环图外，但在金色扇区扩大的范围内。
        const distance = Math.hypot(5, -85)
        const angle = Math.atan2(-85, 5) + Math.PI * 2
        expect(distance).toBeGreaterThan(83)
        expect(distance).toBeLessThan(target.shape.r)
        expect(angle).toBeGreaterThan(target.shape.startAngle)
        expect(angle).toBeLessThan(target.shape.endAngle)
        expect(series[0].radius).toEqual(['66%', '83%'])
        expect(series[0].data.map((row) => row.value)).toEqual([9999, 1])
        expect(
          tooltip.formatter({ name: '金色材料', value: 1, data: series[1].data[1] })
        ).toContain('金色材料：1 个（0.01%）')
      }
    })
  })

  it('相邻的窄扇区在环图首尾交界处也各自保留命中区域', async () => {
    await render(undefined, {
      materials: [
        { name: '装置', rarity: 2, count: 1 },
        { name: '酮凝集组', rarity: 3, count: 998 },
        { name: '聚合剂', rarity: 5, count: 1 }
      ],
      qualities: [
        { rarity: 2, count: 1 },
        { rarity: 3, count: 998 },
        { rarity: 5, count: 1 }
      ],
      act(page) {
        const overlay = page.chart.value.series[1]
        const api = { getWidth: () => 200, getHeight: () => 200 }
        const green = overlay.renderItem({ dataIndex: 0 }, api).shape
        const gold = overlay.renderItem({ dataIndex: 2 }, api).shape
        expect(green.startAngle).toBeCloseTo(-Math.PI / 2)
        expect(gold.endAngle - Math.PI * 2).toBeCloseTo(green.startAngle)
        expect(green.endAngle).toBeGreaterThan(green.startAngle)
        expect(gold.endAngle).toBeGreaterThan(gold.startAngle)
      }
    })
  })

  it('切换日期更新悬浮明细，翻页保持范围累计数量，空结果清空扇区', async () => {
    const initial = {
      total: 60,
      records: [],
      materials: [{ name: '聚合剂', rarity: 5, count: 8 }],
      qualities: [{ rarity: 5, count: 8 }],
      comparison: null
    }
    await render(undefined, {
      client: { get: vi.fn().mockResolvedValue({ data: initial }) },
      async act(page, axios) {
        page.page.value = 2
        await page.load()
        expect(tooltip(page, 0, 100)).toContain('<span>聚合剂</span><strong>× 8</strong>')
        page.range.value = [new Date(2026, 9, 1).getTime(), new Date(2026, 9, 2).getTime()]
        axios.get.mockResolvedValueOnce({
          data: {
            ...initial,
            materials: [{ name: '双极纳米片', rarity: 5, count: 1 }],
            qualities: [{ rarity: 5, count: 1 }]
          }
        })
        page.changeRange()
        await vi.advanceTimersByTimeAsync(0)
        expect(page.page.value).toBe(1)
        expect(axios.get.mock.lastCall[1].params).toEqual({
          startDate: '2026-10-01',
          endDate: '2026-10-02',
          page: 1
        })
        const updated = tooltip(page, 0, 100)
        expect(updated).toContain('金色材料：1 个（100%）')
        expect(updated).toContain('双极纳米片')
        expect(updated).not.toContain('聚合剂')
        axios.get.mockResolvedValueOnce({
          data: { ...initial, total: 0, materials: [], qualities: [] }
        })
        await page.load()
        expect(page.chart.value.series[0].data).toEqual([])
      }
    })
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

  it('切换页码时保留上次的收取记录，失败时标明记录所属页码', async () => {
    const html = await render(undefined, {
      records: [row('shown', 'submitted')],
      act: async (page, axios) => {
        let reject
        axios.get.mockImplementationOnce(
          () =>
            new Promise((_, fail) => {
              reject = fail
            })
        )
        page.page.value = 2
        const refresh = page.load()
        expect(page.loading.value).toBe(true)
        expect(page.data.value.records[0].id).toBe('shown')
        reject(new Error('offline'))
        await refresh
        expect(page.displayedQuery.value.page).toBe(1)
      }
    })
    expect(html).toContain('回收站统计读取失败')
    expect(html).toContain('第 1 页')
    expect(html).toContain('已上传')
    expect(html).not.toContain('正在读取回收站统计')
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
