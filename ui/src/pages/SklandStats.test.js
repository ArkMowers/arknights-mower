import { renderToString } from 'vue/server-renderer'
import { createSSRApp } from 'vue'
import { createPinia } from 'pinia'
import { createMemoryHistory, createRouter } from 'vue-router'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { DEFAULT_SKLAND_PREFERENCES } from '@/stores/sklandPreferences'
import SklandStats from './SklandStats.vue'

vi.mock('@/components/HelpText.vue', () => ({ default: { render: () => null } }))
vi.mock('naive-ui', () => {
  const wrapper = {
    inheritAttrs: false,
    setup:
      (_, { slots }) =>
      () =>
        slots.default?.()
  }
  return Object.fromEntries(
    ['NButton', 'NDatePicker', 'NIcon', 'NInput', 'NSelect'].map((name) => [name, wrapper])
  )
})

const firstAccount = '138****8000'
const secondAccount = '139****9000'
const arknights = '明日方舟官服'
const bilibili = '明日方舟bilibili服'
const endfield = '终末地官服'

function pair(account, game, overrides = {}) {
  return {
    key: `${account}::${game}`,
    account,
    game,
    game_group: game.startsWith('明日方舟') ? '明日方舟' : '终末地',
    channel: game === bilibili ? 'bilibili服' : '官服',
    first_date: '2026-10-31',
    last_date: '2026-11-03',
    current_streak: 2,
    longest_streak: 2,
    last_outcome: 'signed',
    ...overrides
  }
}

function record(date, entry, overrides = {}) {
  return {
    date,
    account: entry.account,
    game: entry.game,
    game_group: entry.game_group,
    channel: entry.channel,
    pair: entry.key,
    outcome: 'signed',
    reward: '龙门币×1000',
    item: '龙门币',
    count: 1000,
    ...overrides
  }
}

function history() {
  const main = pair(firstAccount, arknights)
  const otherGame = pair(firstAccount, endfield, {
    first_date: '2026-11-03',
    current_streak: 1,
    longest_streak: 1,
    last_outcome: 'repeated'
  })
  const otherAccount = pair(secondAccount, bilibili, {
    first_date: '2026-11-02',
    last_date: '2026-11-02',
    current_streak: 1,
    longest_streak: 1
  })
  return {
    today: { date: '2026-11-03' },
    accounts: [firstAccount, secondAccount],
    games: [arknights, bilibili, endfield],
    pairs: [main, otherGame, otherAccount],
    records: [
      record('2026-11-03', main),
      record('2026-11-03', otherGame, {
        outcome: 'repeated',
        reward: '请勿重复签到！',
        item: null,
        count: 0
      }),
      record('2026-11-02', main),
      record('2026-11-02', otherAccount),
      record('2026-11-01', main, { outcome: 'failed', reward: '网络错误', item: null, count: 0 }),
      record('2026-10-31', main)
    ]
  }
}

function monthResponse(payload, { startDate, endDate }) {
  return {
    data: {
      ...payload,
      range: { start: startDate, end: endDate },
      records: payload.records.filter((row) => row.date >= startDate && row.date <= endDate),
      ...(payload.account_failures && {
        account_failures: payload.account_failures.filter(
          ({ date }) => date >= startDate && date <= endDate
        )
      })
    }
  }
}

async function render({
  payload = history(),
  rewards,
  cachedRewards,
  pastRewards,
  preferences,
  interact,
  initialOnly = false,
  failure,
  taskResult = '添加任务成功！'
} = {}) {
  const emptyRewards = (month) => ({ month, cached: false, pairs: [], warnings: [] })
  let saved = { ...DEFAULT_SKLAND_PREFERENCES, ...preferences }
  const axios = {
    get: vi.fn(async (url, { params } = {}) => {
      if (url.endsWith('/gui/skland')) return { data: { skland: { ...saved } } }
      if (url.endsWith('/skland/rewards')) {
        return {
          data:
            [cachedRewards, pastRewards].find((entry) => entry?.month === params.month) ??
            emptyRewards(params.month)
        }
      }
      if (failure) {
        const original = failure
        failure = null
        throw original
      }
      return monthResponse(payload, params)
    }),
    put: vi.fn(async (_url, { skland }) => {
      saved = { ...saved, ...skland }
      return { data: { skland: { ...saved } } }
    }),
    post: vi.fn(async (url) =>
      url.endsWith('/task')
        ? { data: taskResult }
        : { data: rewards ?? emptyRewards(payload.today.date.slice(0, 7)) }
    )
  }
  let page
  const app = createSSRApp({
    ...SklandStats,
    async setup(props, context) {
      page = SklandStats.setup(props, context)
      if (!initialOnly) await page.initialize()
      await interact?.(page, axios)
      return page
    }
  })
  const router = createRouter({
    history: createMemoryHistory(),
    routes: ['/', '/settings'].map((path) => ({
      path,
      component: { render: () => null }
    }))
  })
  await router.push('/?token=session-token')
  app.use(router)
  app.use(createPinia())
  app.provide('axios', axios)
  const html = await renderToString(app)
  const dayDetail = html.split('aria-label="签到详情"')[1]?.split('</section>')[0]
  return { html, dayDetail, page, axios }
}

function slotCell(html, index) {
  return html.split(`data-slot="${index}"`)[1]?.split('</button>')[0] ?? ''
}

function reportSummary(html) {
  return html.split('class="reward-report__summary"')[1]?.split('</p>')[0] ?? ''
}

function slotTag(html, index) {
  return html.match(new RegExp(`<button[^>]*data-slot="${index}"[^>]*>`))?.[0] ?? ''
}

function slotClass(html, index) {
  return (slotTag(html, index).match(/class="([^"]*)"/)?.[1] ?? '').split(' ')
}

/** 主账号 1 日失败，2 日和 3 日签到。 */
function thirtySlots() {
  return {
    month: '2026-11',
    cached: true,
    pairs: [
      {
        account: firstAccount,
        game: arknights,
        role_index: 1,
        progress_date: '2026-11-03',
        signed_today: true,
        signed_dates: ['2026-11-02', '2026-11-03'],
        reward_slots: Array.from({ length: 30 }, (_, index) => ({
          done: index < 2,
          rewards: [{ item: index % 2 ? '赤金' : '龙门币', count: index % 2 ? 2 : 500 }]
        }))
      }
    ],
    warnings: []
  }
}

function historyWithMissedFirstDay() {
  const payload = history()
  for (const row of payload.records) {
    if (row.pair !== payload.pairs[0].key) continue
    if (row.date === '2026-11-02') Object.assign(row, { reward: '龙门币×500', count: 500 })
    if (row.date === '2026-11-03') Object.assign(row, { reward: '赤金×2', item: '赤金', count: 2 })
  }
  return payload
}

function statisticsReads(axios) {
  return axios.get.mock.calls.filter(([url]) => url.endsWith('/skland/statistics'))
}

describe('森空岛签到统计页面', () => {
  beforeEach(() => {
    vi.useFakeTimers({ toFake: ['Date'] })
    vi.setSystemTime(new Date(2026, 10, 3, 12))
  })

  afterEach(() => {
    vi.useRealTimers()
    vi.unstubAllGlobals()
  })

  it('本机没有记录时等待本月奖励返回再显示空状态', async () => {
    const { html } = await render({
      payload: { ...history(), accounts: [], games: [], pairs: [], records: [] },
      initialOnly: true,
      interact: async (page, axios) => {
        const get = axios.get.getMockImplementation()
        let complete, started
        const requestStarted = new Promise((resolve) => {
          started = resolve
        })
        axios.get.mockImplementation((url, options) => {
          if (!url.endsWith('/skland/rewards')) return get(url, options)
          started()
          return new Promise((resolve) => {
            complete = resolve
          })
        })
        const load = page.initialize()
        await requestStarted
        expect(page.data.value).toBeTruthy()
        expect(page.sklandSkeleton.value).toBe(true)
        complete({ data: { month: '2026-11', cached: true, pairs: [], warnings: [] } })
        await load
        expect(page.sklandSkeleton.value).toBe(false)
      }
    })
    expect(html).toContain('还没有签到记录')
  })

  it('有本机记录时也等本月奖励读完，再按森空岛的格子一次画出日历', async () => {
    const { html } = await render({
      cachedRewards: thirtySlots(),
      initialOnly: true,
      interact: async (page, axios) => {
        const get = axios.get.getMockImplementation()
        let complete, started
        const requestStarted = new Promise((resolve) => {
          started = resolve
        })
        axios.get.mockImplementation((url, options) => {
          if (!url.endsWith('/skland/rewards')) return get(url, options)
          started()
          return new Promise((resolve) => {
            complete = () => resolve(get(url, options))
          })
        })
        const load = page.initialize()
        await requestStarted
        expect(page.data.value.records.length).toBeGreaterThan(0)
        expect(page.selectedChannel.value).toBeTruthy()
        expect(page.sklandSkeleton.value).toBe(true)
        expect(page.signIn.value).toBeNull()
        complete()
        await load
        expect(page.sklandSkeleton.value).toBe(false)
        expect(page.signIn.value.source).toBe('cache')
      }
    })
    expect(html.match(/data-slot="/g)).toHaveLength(30)
    expect(html).not.toContain('正在读取签到记录')
  })

  it('翻月时等该月奖励读完再换掉占位格，期间右栏保留读数占位', async () => {
    const payload = history()
    payload.records.push(record('2026-10-30', payload.pairs[0]))
    const pastRewards = {
      month: '2026-10',
      cached: true,
      pairs: [
        {
          account: firstAccount,
          game: arknights,
          progress_date: '2026-10-31',
          signed_today: true,
          signed_dates: ['2026-10-30', '2026-10-31'],
          reward_slots: [
            { done: true, rewards: [{ item: '招聘许可', count: 1 }] },
            { done: true, rewards: [{ item: '合成玉', count: 40 }] },
            { done: false, rewards: [{ item: '赤金', count: 2 }] }
          ]
        }
      ],
      warnings: []
    }
    const { html } = await render({
      payload,
      cachedRewards: thirtySlots(),
      pastRewards,
      interact: async (page, axios) => {
        const get = axios.get.getMockImplementation()
        let complete, started
        const requestStarted = new Promise((resolve) => {
          started = resolve
        })
        axios.get.mockImplementation((url, options) => {
          if (!url.endsWith('/skland/rewards') || options.params.month !== '2026-10') {
            return get(url, options)
          }
          started()
          return new Promise((resolve) => {
            complete = () => resolve(get(url, options))
          })
        })
        const october = page.selectMonth('2026-10-01')
        await requestStarted
        expect(page.data.value.range.start).toBe('2026-10-01')
        expect(page.monthPending.value).toBe(true)
        expect(page.signIn.value).toBeNull()
        expect(page.readingPlaceholders.value).toEqual({
          progress: ['森空岛已签到', '本机有签到记录'],
          streak: false
        })
        complete()
        await october
        expect(page.monthPending.value).toBe(false)
        expect(page.signIn.value.source).toBe('cache')
      }
    })
    expect(html.match(/data-slot="/g)).toHaveLength(3)
    expect(html).toMatch(/森空岛已签到 <strong[^>]*>2<\/strong> 天/)
  })

  it('翻月时即使本机没有渠道，等待森空岛奖励期间也显示日历占位', async () => {
    const cachedRewards = { ...thirtySlots(), earliest_month: '2026-10' }
    const started = Promise.withResolvers()
    const reply = Promise.withResolvers()
    let october
    const { html } = await render({
      payload: { ...history(), accounts: [], games: [], pairs: [], records: [] },
      cachedRewards,
      interact: async (page, axios) => {
        const get = axios.get.getMockImplementation()
        expect(page.signIn.value.source).toBe('cache')
        axios.get.mockImplementation((url, options) => {
          if (!url.endsWith('/skland/rewards') || options.params.month !== '2026-10') {
            return get(url, options)
          }
          started.resolve()
          return reply.promise
        })
        october = page.selectMonth('2026-10-01')
        await started.promise
        expect(page.selectedChannel.value).toBeNull()
      }
    })
    reply.resolve({ data: { month: '2026-10', cached: true, pairs: [], warnings: [] } })
    await october
    expect(html).toContain('sign-slot is-placeholder')
    expect(html).not.toContain('还没有签到记录')
  })

  it('按上限绘制旧版渠道数和奖励分组，同时保留空布局', async () => {
    let raw = JSON.stringify({ chips: 10, groups: [25, 2], months: 13 })
    vi.stubGlobal('localStorage', {
      getItem: (key) => (key === 'mower_skeleton_shape:skland' ? raw : null),
      setItem: vi.fn()
    })
    try {
      const { html } = await render({ initialOnly: true })
      expect(html.match(/class="channel-chip"/g)).toHaveLength(8)
      expect(html.match(/class="reward-tile"/g)).toHaveLength(26)
      expect(html).toContain('正在读取签到记录')
      raw = JSON.stringify({ calendar: false, stats: false, groups: [], chips: [] })
      const empty = await render({ initialOnly: true })
      expect(empty.html).not.toMatch(/class="channel-chip"|class="reward-tile"|data-slot=/)
    } finally {
      vi.unstubAllGlobals()
    }
  })

  it('通过中转打开时提示使用桌面窗口或直接连接实例的 Web UI', async () => {
    vi.stubGlobal('window', {
      location: { protocol: 'https:', hostname: 'trial.free.mower.work', port: '58000' }
    })

    const { html, axios } = await render()

    expect(html).toContain('当前通过中转访问')
    expect(html).toContain('Mower 桌面窗口或直接连接实例的 Web UI')
    expect(html).not.toContain('正在读取签到记录')
    expect(axios.get).not.toHaveBeenCalled()
    expect(axios.post).not.toHaveBeenCalled()
  })

  it('读取当前月，默认选中第一个渠道并定位到今天领取的格子', async () => {
    const payload = history()
    payload.records.push(record('2026-11-04', payload.pairs[0]))
    const { html, dayDetail, axios, page } = await render({ payload })
    expect(statisticsReads(axios)).toEqual([
      [
        expect.stringContaining('/skland/statistics'),
        {
          params: { startDate: '2026-11-01', endDate: '2026-11-30' }
        }
      ]
    ])
    expect(page.selectedChannel.value.key).toBe(`${firstAccount}::${arknights}::1`)
    expect((html.match(/data-slot="/g) || []).length).toBe(2)
    expect(html).toMatch(/data-slot="2"[^>]+aria-pressed="true"[^>]+aria-current="date"/)
    expect(slotClass(html, 2)).toEqual(expect.arrayContaining(['is-today', 'is-claimed']))
    expect(dayDetail).toContain('本机签到记录')
    expect(dayDetail).toContain('今日已领取')
    expect(dayDetail).toContain('11月3日（今天）签到领取')
    expect(page.records.value.some((row) => row.date === '2026-11-04')).toBe(false)
  })

  it('侧栏按账号列出渠道和今天的状态，提示其他渠道的失败', async () => {
    const payload = history()
    payload.records.push(
      record('2026-11-03', payload.pairs[2], {
        outcome: 'failed',
        reward: '网络错误',
        item: null,
        count: 0
      })
    )
    const { html, page } = await render({
      payload,
      cachedRewards: {
        month: '2026-11',
        cached: true,
        pairs: [
          {
            account: firstAccount,
            game: arknights,
            role_index: 1,
            display_name: '罗德岛博士',
            progress_date: '2026-11-03',
            signed_today: true,
            reward_slots: [{ done: true, rewards: [{ item: '龙门币', count: 1000 }] }]
          }
        ],
        warnings: []
      }
    })
    expect(page.channels.value.map(({ account, game, status }) => [account, game, status])).toEqual(
      [
        [firstAccount, arknights, 'signed'],
        [firstAccount, endfield, 'signed'],
        [secondAccount, bilibili, 'failed']
      ]
    )
    const picker = html.split('class="channel-picker"')[1].split('aria-label="明细视图"')[0]
    expect(picker).not.toContain('今日')
    expect(picker).toMatch(/aria-pressed="true"[^>]*title="罗德岛博士 · 今天已签到"/)
    const chips = picker.split('aria-label="签到渠道"')[1].split('</div>')[0]
    expect(chips).toContain('明日方舟 官服')
    expect(chips).toContain('终末地 官服')
    expect(chips).not.toContain('B服')
    expect(chips).not.toContain('channel-chip__dot')
    expect(picker).toContain('另有 1 个渠道今天签到失败')
    expect(picker).toContain(`查看 ${secondAccount} 明日方舟 B服`)
  })

  it('同区服角色的签到和失败详情各用自己的记录', async () => {
    const payload = history()
    const main = payload.pairs[0]
    payload.records = [
      record('2026-11-03', main, { role_key: 'role-a', event_id: 'a-1' }),
      record('2026-11-03', main, {
        role_key: 'role-b',
        event_id: 'b-1',
        outcome: 'failed',
        reward: '网络错误',
        item: null,
        count: 0
      })
    ]
    const { dayDetail, page } = await render({
      payload,
      interact(page) {
        page.selectFailure(page.failureLog.value.entries[0])
      }
    })
    const roles = page.channels.value.filter((channel) => channel.pairKey === main.key)
    expect(roles.map(({ roleKey, status }) => [roleKey, status])).toEqual([
      ['role-a', 'signed'],
      ['role-b', 'failed']
    ])
    expect(page.selectedChannel.value.roleKey).toBe('role-b')
    expect(dayDetail).toContain('11月3日签到失败')
    expect(dayDetail).toContain('角色 2')
    expect(dayDetail).not.toContain('当天已签到')
    expect(dayDetail).toContain('网络错误')
  })

  it('有角色的奖励读取失败时，使用未被快照占用的编号显示本机角色', async () => {
    const payload = history()
    const [main] = payload.pairs
    payload.records = [record('2026-11-03', main, { role_key: 'role-a' })]
    const cachedRewards = thirtySlots()
    Object.assign(cachedRewards.pairs[0], {
      role_key: 'role-b',
      role_index: 2,
      progress_ambiguous: true
    })

    const { html, page } = await render({ payload, cachedRewards })

    expect(
      page.channels.value
        .filter(({ pairKey }) => pairKey === main.key)
        .map(({ roleKey, role_index }) => [roleKey, role_index])
    ).toEqual([
      ['role-a', 1],
      ['role-b', 2]
    ])
    expect(html).toContain('明日方舟 官服 · 角色 1')
    expect(html).toContain('明日方舟 官服 · 角色 2')
  })

  it('显式刷新当月时，即使已有奖励缓存也读回新的进度', async () => {
    const rewards = thirtySlots()
    const cachedRewards = structuredClone(rewards)
    const cachedPair = cachedRewards.pairs[0]
    cachedPair.progress_date = '2026-11-02'
    cachedPair.signed_dates.pop()
    cachedPair.reward_slots[1].done = false
    const { page, axios } = await render({
      payload: historyWithMissedFirstDay(),
      cachedRewards,
      rewards,
      async interact(page, axios) {
        expect(axios.post).not.toHaveBeenCalled()
        const started = Promise.withResolvers()
        const reply = Promise.withResolvers()
        const post = axios.post.getMockImplementation()
        axios.post.mockImplementationOnce(async (...args) => {
          started.resolve()
          await reply.promise
          return post(...args)
        })
        const refreshing = page.refreshPage()
        await started.promise
        const signInWhileRefreshing = page.signIn.value
        reply.resolve()
        await refreshing
        expect(signInWhileRefreshing.source).toBe('cache')
        expect(signInWhileRefreshing.snapshotDate).toBe('2026-11-02')
      }
    })
    expect(axios.post).toHaveBeenCalledWith(
      expect.stringMatching(/\/skland\/rewards\/refresh$/),
      {}
    )
    expect(page.selectedMonthRewards.value.pairs[0].progress_date).toBe('2026-11-03')
    expect(page.activeSlot.value).toMatchObject({ index: 2, date: '2026-11-03' })
  })

  it('当月更新期间翻到上月再返回，继续使用在途进度请求', async () => {
    const rewards = thirtySlots()
    const cachedRewards = structuredClone(rewards)
    cachedRewards.pairs[0].progress_date = '2026-11-02'
    const { page, axios } = await render({
      cachedRewards,
      async interact(page, axios) {
        let started
        let finish
        const requestStarted = new Promise((resolve) => (started = resolve))
        const response = new Promise((resolve) => (finish = resolve))
        axios.post.mockImplementation(() => {
          started()
          return response
        })
        const refresh = page.refreshPage()
        await requestStarted
        await page.selectMonth('2026-10-01')
        const back = page.selectMonth('2026-11-01')
        finish({ data: rewards })
        await Promise.all([refresh, back])
      }
    })
    expect(axios.post).toHaveBeenCalledTimes(1)
    expect(page.selectedMonthRewards.value).toEqual(rewards)
  })

  it('同一个角色的森空岛记录确认后来已签到时保留失败并收起重试按钮', async () => {
    const payload = history()
    payload.records = [
      record('2026-11-03', payload.pairs[0], {
        role_key: 'role-a',
        event_id: 'failure-a',
        outcome: 'failed',
        item: null,
        count: 0,
        reward: '网络错误'
      })
    ]
    const cachedRewards = thirtySlots()
    cachedRewards.pairs[0].role_key = 'role-a'
    const { dayDetail, page } = await render({
      payload,
      cachedRewards,
      interact(page) {
        page.selectFailure(page.failureLog.value.entries[0])
      }
    })
    expect(page.failureLog.value.entries[0]).toMatchObject({ pending: false, recovered: true })
    expect(dayDetail).toContain('当天已签到')
    expect(dayDetail).toContain('网络错误')
    expect(dayDetail).not.toContain('重新签到')
  })

  it.each(['本机记录', '森空岛快照'])(
    '%s确认唯一角色当天已签到时，旧失败无需重试',
    async (source) => {
      const payload = history()
      const [main] = payload.pairs
      payload.records = [
        record('2026-11-03', main, {
          outcome: 'failed',
          item: null,
          count: 0,
          reward: '网络错误'
        })
      ]
      let cachedRewards
      if (source === '本机记录') {
        payload.records.push(record('2026-11-03', main, { role_key: 'role-a' }))
      } else {
        cachedRewards = thirtySlots()
        cachedRewards.pairs[0].role_key = 'role-a'
      }

      const { dayDetail, page } = await render({
        payload,
        cachedRewards,
        interact: (page) => page.selectFailure(page.failureLog.value.entries[0])
      })

      expect(page.failureLog.value.entries[0]).toMatchObject({
        roleKey: null,
        pending: false,
        recovered: true
      })
      expect(dayDetail).toContain('当天已签到')
      expect(dayDetail).not.toContain('重新签到')
    }
  )

  it.each(['森空岛快照', '本机历史记录'])(
    '%s显示该区服还有其他角色时，旧失败仍待重试',
    async (source) => {
      const payload = history()
      const [main] = payload.pairs
      payload.records = [
        record('2026-11-03', main, {
          outcome: 'failed',
          item: null,
          count: 0,
          reward: '网络错误'
        }),
        record('2026-11-03', main, { role_key: 'role-a' })
      ]
      let cachedRewards
      if (source === '森空岛快照') {
        cachedRewards = thirtySlots()
        Object.assign(cachedRewards.pairs[0], { role_key: 'role-a', progress_ambiguous: true })
      } else {
        main.multiple_roles = true
        payload.records.unshift(record('2026-10-31', main, { role_key: 'role-b' }))
      }

      const { page } = await render({ payload, cachedRewards })

      expect(page.failureLog.value.entries[0]).toMatchObject({
        roleKey: null,
        pending: true,
        recovered: false
      })
    }
  )

  it('一格有多项奖励时并排两项并标出数量，详情列出全部', async () => {
    const payload = history()
    const [main] = payload.pairs
    payload.records.splice(
      1,
      0,
      record('2026-11-03', main, { item: '赤金', count: 2, reward: '赤金×2' }),
      record('2026-11-03', main, { item: '合成玉', count: 60, reward: '合成玉×60' })
    )
    const { html, dayDetail } = await render({ payload })
    const cell = slotCell(html, 2)
    expect(cell).toContain(`/depot/${encodeURIComponent('龙门币')}.webp`)
    expect(cell).toContain(`/depot/${encodeURIComponent('赤金')}.webp`)
    expect(cell).not.toContain(`/depot/${encodeURIComponent('合成玉')}.webp`)
    expect(cell).toMatch(/class="sign-slot__quantity"[^>]*>1,000</)
    expect(cell).toContain('+1')
    expect(html).toMatch(
      /data-slot="2"[^>]+aria-label="本机签到记录，龙门币 ×1,000、赤金 ×2、合成玉 ×60，今日已领取，11月3日签到"/
    )
    expect(dayDetail).toContain('title="合成玉 ×60"')
    expect(dayDetail).toContain('×60')
  })

  it('图标缺失时格子用礼物图标，物品名称在详情显示', async () => {
    const payload = history()
    payload.records = [record('2026-11-03', payload.pairs[1])]
    const { html, dayDetail } = await render({
      payload,
      interact(page) {
        page.selectChannel(`${firstAccount}::${endfield}::1`)
      }
    })
    expect(slotCell(html, 1)).toContain('sign-slot__fallback')
    expect(slotCell(html, 1)).not.toMatch(/>龙门币</)
    expect(dayDetail).toContain('title="龙门币 ×1,000"')
    expect(html).not.toContain('/depot/')
  })

  it('今天签到失败时把今天的格子标成失败，可以加入森空岛签到任务重新签到', async () => {
    const payload = history()
    const otherAccount = payload.pairs[2]
    for (const reward of ['网络错误', '网络错误']) {
      payload.records.push(
        record('2026-11-03', otherAccount, { outcome: 'failed', reward, item: null, count: 0 })
      )
    }
    const { html, dayDetail, page, axios } = await render({
      payload,
      interact: async (page) => {
        page.selectChannel(`${secondAccount}::${bilibili}::1`)
        await page.retrySignIn()
      }
    })
    expect(page.signIn.value).toMatchObject({ claimed: 1, todaySigned: false, todayIndex: 2 })
    expect(slotClass(html, 2)).toEqual(expect.arrayContaining(['is-today', 'is-failed']))
    expect(slotCell(html, 2)).toContain('sign-slot__corner')
    expect(dayDetail).toContain('今日签到失败')
    expect(dayDetail).toContain('失败 2 次 · 网络错误')
    expect(dayDetail).toContain('重新签到')
    expect(dayDetail).toContain('已加入任务队列，签到完成后刷新查看结果')
    expect(dayDetail).not.toContain('森空岛账号')
    const [[url, body]] = axios.post.mock.calls.filter(([url]) => url.endsWith('/task'))
    expect(url).toMatch(/\/task$/)
    expect(body.task).toMatchObject({ plan: {}, task_type: '森空岛签到', meta_data: '' })
    expect(body.task.time).toBeInstanceOf(Date)
  })

  it('Mower 没有运行时显示加入任务失败的原因，登录类失败提示先检查账号', async () => {
    const payload = history()
    payload.records.push(
      record('2026-11-03', payload.pairs[2], {
        outcome: 'failed',
        reward: '登录已过期，请重新登录',
        item: null,
        count: 0
      })
    )
    const { html } = await render({
      payload,
      taskResult: '添加任务失败！！请确保Mower正在运行',
      interact: async (page) => {
        page.detailView.value = 'failures'
        await page.retrySignIn()
      }
    })
    const list = html.split('aria-label="失败记录"')[1]
    expect(list).toContain('今天有 1 项签到失败')
    expect(list).toContain('/settings?token=session-token#task-accounts')
    expect(list).toMatch(/class="is-error"[^>]*>添加任务失败！！请确保Mower正在运行</)
  })

  it('日历侧栏显示连续签到，奖励统计默认按日历所选区服计算记录率', async () => {
    const { html } = await render()
    const toolbar = html.split('class="month-summary"')[1]?.split('</p>')[0] ?? ''
    expect(toolbar).toMatch(/连续签到 <strong[^>]*>2<\/strong> 天/)
    expect(toolbar).not.toContain('签到率')
    const summary = reportSummary(html)
    expect(summary).toMatch(/本机签到记录率 <strong[^>]*>66\.7%</)
    expect(summary).toContain('title="本机有签到记录 2/3 天"')
    expect(summary).toContain('失败 1')
    expect(summary).not.toContain('无记录')
    expect(slotCell(html, 1)).toContain('sign-slot__check')
    expect(slotCell(html, 2)).toContain('sign-slot__check')
    expect(slotClass(html, 1)).toContain('is-near')
    expect(slotClass(html, 2)).not.toContain('is-near')
    expect(slotTag(html, 1)).toMatch(/style="--near-x:\s*1;\s*--near-y:\s*0;?"/)
    expect(slotTag(html, 2)).not.toContain('--near-x')
    expect(html).not.toContain('calendar-day')
  })

  it('翻到历史月份及切换日历渠道时保留明确选择的统计区服和日期范围', async () => {
    const { html, page } = await render({
      preferences: { statsGame: arknights },
      async interact(page) {
        page.selectChannel(`${firstAccount}::${endfield}::1`)
        await page.selectMonth('2026-10-01')
      }
    })
    expect(page.activeStatsGame.value).toBe(arknights)
    expect(page.statsRange.value).toEqual(['2026-11-01', '2026-11-03'])
    expect(html).not.toContain('class="month-summary"')
    const summary = reportSummary(html)
    expect(summary).toMatch(/本机签到记录率 <strong[^>]*>66.7%</)
    expect(summary).toContain('title="本机有签到记录 2/3 天"')
  })

  it.each([null, '全部游戏区服'])('旧统计区服偏好 %s 回退到日历所选区服', async (statsGame) => {
    const { html, page, axios } = await render({
      preferences: { account: firstAccount, game: endfield, statsGame }
    })
    expect(page.activeStatsGame.value).toBe(endfield)
    expect(page.statsGameOptions.value.map((option) => option.value)).toEqual([arknights, endfield])
    expect(reportSummary(html)).toContain('title="本机有签到记录 1/1 天"')
    expect(page.rewardReport.value.items).toEqual([])
    expect(axios.put).not.toHaveBeenCalled()
    expect(statisticsReads(axios)).toHaveLength(1)
  })

  it('所选区服有缺记录的日期时保留签到天数和记录率摘要', async () => {
    const games = [arknights, bilibili, endfield, '终末地bilibili服']
    const pairs = games.map((game) =>
      pair(firstAccount, game, {
        channel: game.endsWith('bilibili服') ? 'bilibili服' : '官服',
        first_date: '2026-11-05',
        last_date: '2026-11-19'
      })
    )
    const dates = Array.from(
      { length: 15 },
      (_, index) => `2026-11-${String(index + 5).padStart(2, '0')}`
    )
    const { html } = await render({
      preferences: { statsGame: arknights },
      payload: {
        today: { date: '2026-11-19' },
        accounts: [firstAccount],
        games,
        pairs,
        records: pairs.flatMap((entry) =>
          dates
            .filter((date) => entry.game !== arknights || date !== '2026-11-14')
            .map((date) => record(date, entry))
        )
      }
    })
    const report = html.split('aria-label="签到奖励统计"')[1]
    expect(report).toMatch(/本机签到记录率 <strong[^>]*>93\.3%/)
    expect(report).toContain('title="本机有签到记录 14/15 天"')
    expect(report).toMatch(/本机记录到 <strong[^>]*>14<\/strong> 天签到/)
    expect(report).not.toContain('无本机记录')
    expect(report).not.toContain('reward-report__missing')
  })

  it.each([
    [arknights, /森空岛已签到 <strong[^>]*>18<\/strong> 天/],
    [endfield, /森空岛已领 <strong[^>]*>18<\/strong> 格奖励/]
  ])('%s 区分森空岛月度进度与本机区服签到记录', async (game, progressText) => {
    const channel = pair(firstAccount, game, {
      first_date: '2026-08-09',
      last_date: '2026-11-19'
    })
    const signedDates = Array.from(
      { length: 19 },
      (_, index) => `2026-11-${String(index + 1).padStart(2, '0')}`
    ).filter((date) => date !== '2026-11-14')
    const { html, dayDetail } = await render({
      payload: {
        today: { date: '2026-11-19' },
        accounts: [firstAccount],
        games: [game],
        pairs: [channel],
        records: signedDates.slice(4).map((date) => record(date, channel))
      },
      cachedRewards: {
        month: '2026-11',
        cached: true,
        pairs: [
          {
            account: firstAccount,
            game,
            role_key: 'a'.repeat(64),
            progress_date: '2026-11-19',
            signed_today: true,
            ...(game === arknights ? { signed_dates: signedDates } : {}),
            reward_slots: Array.from({ length: 30 }, (_, index) => ({
              index: index + 1,
              done: index < 18,
              rewards: [{ item: '示例奖励', count: 1 }]
            }))
          }
        ]
      }
    })
    expect(html).toMatch(progressText)
    expect(html).toMatch(/本机有签到记录 <strong[^>]*>14<\/strong> 天/)
    expect(reportSummary(html)).toContain('title="本机有签到记录 14/19 天"')
    expect(dayDetail).toContain('第 18 格奖励')
  })

  it('切换渠道后月历、汇总和格子都换成该渠道，只使用已读取的月份', async () => {
    const { dayDetail, page, axios } = await render({
      interact(page) {
        page.selectChannel(`${firstAccount}::${endfield}::1`)
      }
    })
    expect(page.summary.value).toMatchObject({ signedPairDays: 1, expectedPairDays: 1 })
    expect(page.signIn.value.slots.map(({ index, date }) => [index, date])).toEqual([
      [1, '2026-11-03']
    ])
    expect(dayDetail).toContain('这次签到没有奖励明细')
    expect(statisticsReads(axios)).toHaveLength(1)
  })

  it('默认展示单个账号本月实际获得的奖励', async () => {
    const { html, page } = await render()
    expect(html).toContain('签到奖励统计')
    const report = html.split('aria-label="签到奖励统计"')[1]
    expect(report).toMatch(/本机记录到 <strong[^>]*>2<\/strong> 天签到/)
    expect(report).toMatch(/class="reward-tile"[^>]*title="龙门币 ×2,000，2 天获得"/)
    expect(report).toMatch(/class="reward-art__count"[^>]*>2,000</)
    expect(report).toContain(`/depot/${encodeURIComponent('龙门币')}.webp`)
    expect(html).not.toContain('class="inventory-card"')
    expect(html).not.toContain('aria-label="奖励获得明细"')
    expect(html).not.toContain('calendar-legend')
    expect(page.rewardReport.value.items).toMatchObject([{ name: '龙门币', count: 2000 }])
    expect(html).not.toContain('class="skland-panel ledger"')
  })

  it('统计默认选中第一种奖励，按真实日期列出它每天的出现情况', async () => {
    const { html, page } = await render({
      interact(page) {
        page.statsItem.value = '明日方舟::不存在的奖励'
      }
    })
    const report = html.split('aria-label="签到奖励统计"')[1]
    expect(report).toMatch(/class="reward-tile__button"[^>]*aria-pressed="true"[^>]*>/)
    const chart = report.split('aria-label="龙门币的出现情况"')[1]
    expect(chart).toMatch(
      /共获得 <strong[^>]*>2,000<\/strong>，出现在\s*<strong[^>]*>2<\/strong> 天/
    )
    expect(chart).toMatch(/<th[^>]*scope="row"[^>]*>11月<\/th>/)
    expect(chart).toMatch(/class="is-failed day-cell"[^>]*aria-label="11月1日：签到失败"/)
    expect(chart).toMatch(/class="is-got day-cell"[^>]*aria-label="11月2日：获得 ×1,000"/)
    expect(chart).toMatch(/class="is-got day-cell"[^>]*aria-label="11月3日：获得 ×1,000"/)
    expect(chart.match(/role="img"/g)).toHaveLength(3)
    expect(page.rewardDistribution.value.months).toHaveLength(1)
  })

  it('恢复实例内保存的签到偏好，只保存用户明确修改的字段', async () => {
    const { page, axios } = await render({
      preferences: {
        account: firstAccount,
        game: endfield,
        detailView: 'rewards',
        statsAccount: secondAccount,
        statsPreset: '90'
      },
      interact: async (page, axios) => {
        expect(page.detailView.value).toBe('rewards')
        expect(page.selectedChannel.value.game).toBe(endfield)
        expect(page.activeStatsAccount.value).toBe(secondAccount)
        expect(page.activeStatsGame.value).toBe(bilibili)
        expect(page.statsRange.value).toEqual(['2026-08-06', '2026-11-03'])
        expect(axios.put).not.toHaveBeenCalled()

        page.selectSlot(1)
        expect(axios.put).not.toHaveBeenCalled()
        await page.selectDetailView('failures')
        await page.selectChannel(`${firstAccount}::${arknights}::1`)
      }
    })
    expect(page.detailView.value).toBe('failures')
    expect(axios.put.mock.calls.map(([url, body]) => [url, body])).toEqual([
      [expect.stringMatching(/\/gui\/skland$/), { skland: { detailView: 'failures' } }],
      [expect.stringMatching(/\/gui\/skland$/), { skland: { game: arknights } }]
    ])
  })

  it('按账号统计跨月奖励，翻动日历和切换账号复用已读取的记录', async () => {
    const { page, dayDetail, axios } = await render({
      interact: async (page) => {
        await page.selectStatsRange([
          new Date(2026, 9, 31).getTime(),
          new Date(2026, 10, 3).getTime()
        ])
        const item = page.rewardReport.value.items[0]
        expect(item).toMatchObject({ name: '龙门币', count: 3000 })
        await page.selectMonth('2026-10-01')
        expect(page.rewardReport.value.items[0].count).toBe(3000)
        page.selectStatsAccount(secondAccount)
        expect(page.rewardReport.value.items[0].count).toBe(1000)
        page.selectStatsAccount(firstAccount)
        page.statsGame.value = endfield
        expect(page.rewardReport.value.items).toEqual([])
      }
    })
    expect(dayDetail).toContain('10月31日')
    expect(page.statsRange.value).toEqual(['2026-10-31', '2026-11-03'])
    expect(statisticsReads(axios).map(([, { params }]) => params)).toEqual([
      { startDate: '2026-11-01', endDate: '2026-11-30' },
      { startDate: '2026-10-31', endDate: '2026-11-03' },
      { startDate: '2026-10-01', endDate: '2026-10-31' }
    ])
  })

  it('本年可以查看无记录的上一年', async () => {
    const { html, axios, page } = await render({
      preferences: { statsPreset: 'year' },
      interact: (page) => page.pageStats(-1)
    })
    expect(page.statsRange.value).toEqual(['2025-01-01', '2025-12-31'])
    expect(page.canPageStatsBack.value).toBe(false)
    expect(page.canPageStatsForward.value).toBe(true)
    expect(statisticsReads(axios).map(([, { params }]) => params)).toContainEqual({
      startDate: '2025-01-01',
      endDate: '2025-12-31'
    })
    expect(html).toContain('所选范围没有奖励记录')
  })

  it('按自然月翻页，保持区服、日历所在月和保存的快捷周期', async () => {
    const { page, axios } = await render({
      interact: async (page) => {
        await page.pageStats(-1)
        expect(page.statsRange.value).toEqual(['2026-10-01', '2026-10-31'])
        expect(page.month.value).toBe('2026-11-01')
        expect(page.activeStatsGame.value).toBe(arknights)
        expect(page.rewardReport.value.items[0]).toMatchObject({ count: 1000 })
        expect(page.canPageStatsBack.value).toBe(false)
        expect(page.canPageStatsForward.value).toBe(true)
        await page.pageStats(-1)
        expect(page.statsRange.value).toEqual(['2026-10-01', '2026-10-31'])
        await page.pageStats(1)
      }
    })
    expect(page.statsRange.value).toEqual(['2026-11-01', '2026-11-03'])
    expect(page.canPageStatsForward.value).toBe(false)
    expect(statisticsReads(axios).map(([, { params }]) => params)).toEqual([
      { startDate: '2026-11-01', endDate: '2026-11-30' },
      { startDate: '2026-10-01', endDate: '2026-10-31' }
    ])
    expect(axios.put).not.toHaveBeenCalled()
  })

  it('用同一个按钮循环切换统计跨度，切换时显示当前周期', async () => {
    const { page, axios } = await render({
      async interact(page) {
        expect(page.statsModeLabel.value).toBe('按月')
        await page.pageStats(-1)
        expect(page.statsRange.value).toEqual(['2026-10-01', '2026-10-31'])

        await page.cycleStatsPreset()
        expect(page.statsModeLabel.value).toBe('按周')
        expect(page.statsRange.value).toEqual(['2026-11-02', '2026-11-03'])
        expect(page.canPageStatsForward.value).toBe(false)
        await page.pageStats(-1)
        expect(page.statsRange.value).toEqual(['2026-10-26', '2026-11-01'])
        expect(page.canPageStatsBack.value).toBe(false)
        await page.pageStats(1)
        expect(page.statsRange.value).toEqual(['2026-11-02', '2026-11-03'])

        await page.cycleStatsPreset()
        expect(page.statsRange.value).toEqual(['2026-08-06', '2026-11-03'])
        await page.cycleStatsPreset()
        expect(page.statsRange.value).toEqual(['2026-01-01', '2026-11-03'])
        await page.cycleStatsPreset()
      }
    })
    expect(page.statsRange.value).toEqual(['2026-11-01', '2026-11-03'])
    expect(axios.put.mock.calls.map(([, { skland }]) => skland)).toEqual(
      ['week', '90', 'year', 'month'].map((statsPreset) => ({ statsPreset, statsRange: null }))
    )
    expect(statisticsReads(axios).map(([, { params }]) => params)).toContainEqual({
      startDate: '2026-10-26',
      endDate: '2026-11-01'
    })
  })

  it('按年翻页会读取完整闰年，回到本年只统计到今天', async () => {
    vi.setSystemTime(new Date(2025, 2, 1, 12))
    const main = pair(firstAccount, arknights, {
      first_date: '2024-02-29',
      last_date: '2025-03-01'
    })
    const { page, axios } = await render({
      payload: {
        today: { date: '2025-03-01' },
        accounts: [firstAccount],
        games: [arknights],
        pairs: [main],
        records: [record('2025-03-01', main), record('2024-02-29', main)]
      },
      preferences: { statsPreset: 'year' },
      interact: async (page) => {
        await page.pageStats(-1)
        expect(page.statsRange.value).toEqual(['2024-01-01', '2024-12-31'])
        expect(page.rewardReport.value.signedDays).toBe(1)
        expect(page.canPageStatsBack.value).toBe(false)
        await page.pageStats(1)
      }
    })
    expect(page.statsRange.value).toEqual(['2025-01-01', '2025-03-01'])
    expect(page.canPageStatsForward.value).toBe(false)
    expect(statisticsReads(axios).map(([, { params }]) => params)).toContainEqual({
      startDate: '2024-01-01',
      endDate: '2024-12-31'
    })
    expect(axios.put).not.toHaveBeenCalled()
  })

  it('近 90 天按相邻的 90 天翻页', async () => {
    const payload = history()
    payload.pairs[0] = { ...payload.pairs[0], first_date: '2026-06-01' }
    const { page, axios } = await render({
      payload,
      preferences: { statsPreset: '90' },
      interact: async (page) => {
        await page.pageStats(-1)
        expect(page.canPageStatsBack.value).toBe(false)
      }
    })
    expect(page.statsRange.value).toEqual(['2026-05-08', '2026-08-05'])
    expect(statisticsReads(axios).at(-1)?.[1].params).toEqual({
      startDate: '2026-05-08',
      endDate: '2026-08-05'
    })
    expect(axios.put).not.toHaveBeenCalled()
  })

  it('自定义周期按包含首尾的天数翻页，末页截至今天且可回翻', async () => {
    const payload = history()
    payload.pairs[0] = { ...payload.pairs[0], first_date: '2026-10-20' }
    const { page, axios } = await render({
      payload,
      preferences: { statsPreset: 'custom', statsRange: ['2026-10-28', '2026-10-30'] },
      interact: async (page) => {
        await page.pageStats(-1)
        expect(page.statsRange.value).toEqual(['2026-10-25', '2026-10-27'])
        await page.pageStats(1)
        await page.pageStats(1)
        expect(page.statsRange.value).toEqual(['2026-10-31', '2026-11-02'])
        await page.pageStats(1)
        expect(page.statsRange.value).toEqual(['2026-11-03', '2026-11-03'])
        expect(page.canPageStatsForward.value).toBe(false)
        await page.pageStats(-1)
      }
    })
    expect(page.statsRange.value).toEqual(['2026-10-31', '2026-11-02'])
    expect(axios.put).not.toHaveBeenCalled()
  })

  it('保留已保存日期的年份，翻页到公元元年的起点时停止', async () => {
    const { page } = await render({
      preferences: { statsPreset: 'custom', statsRange: ['0001-01-03', '0001-01-05'] },
      async interact(page) {
        expect(page.statsRange.value).toEqual(['0001-01-03', '0001-01-05'])
        await page.pageStats(-1)
        expect(page.statsRange.value).toEqual(['0001-01-01', '0001-01-02'])
        expect(page.canPageStatsBack.value).toBe(false)
        await page.pageStats(1)
      }
    })
    expect(page.statsRange.value).toEqual(['0001-01-03', '0001-01-05'])
  })

  it('在日历侧栏切换月度奖励和失败记录，点击失败打开原日期的详情', async () => {
    const rewards = await render({
      interact(page) {
        page.detailView.value = 'rewards'
      }
    })
    const monthly = rewards.html.split('aria-label="月度奖励"')[1]
    expect(monthly).toMatch(/title="龙门币 ×2,000，签到 2 次获得"/)
    expect(monthly).toMatch(/class="reward-art__count"[^>]*>2,000</)
    expect(rewards.dayDetail).toBeUndefined()

    const failures = await render({
      interact(page) {
        page.detailView.value = 'failures'
      }
    })
    const list = failures.html.split('aria-label="失败记录"')[1]
    expect(list).toContain('网络错误')
    expect(list).toContain('11月1日')
    expect(list).not.toContain('当天未签到成功')
    expect(list).not.toContain('顺延')
    const opened = await render({
      interact(page) {
        page.selectFailure(page.failureLog.value.entries[0])
      }
    })
    expect(opened.page.detailView.value).toBe('day')
    expect(opened.page.activeSlot.value).toBeNull()
    expect(opened.dayDetail).toContain('11月1日签到失败')
    expect(opened.dayDetail).toContain('网络错误')
    expect(opened.dayDetail).not.toContain('11月2日')
  })

  it('同一天多次失败合并为一条，重试成功后标明已签到', async () => {
    const payload = history()
    const [main, , otherAccount] = payload.pairs
    payload.records.push(
      record('2026-11-01', main, { outcome: 'failed', reward: '请求超时', item: null, count: 0 }),
      record('2026-11-02', otherAccount, {
        outcome: 'failed',
        reward: '网络错误',
        item: null,
        count: 0
      })
    )
    const { html, page } = await render({
      payload,
      interact(page) {
        page.detailView.value = 'failures'
      }
    })
    const list = html.split('aria-label="失败记录"')[1]
    expect(page.failureLog.value).toMatchObject({ attempts: 3, recovered: 1 })
    expect(page.failureLog.value.entries.map((entry) => entry.date)).toEqual([
      '2026-11-02',
      '2026-11-01'
    ])
    expect(list).toMatch(/<strong[^>]*>2<\/strong> 天出现签到失败/)
    expect(list).toContain('当天已签到')
    expect(list).toContain('失败 2 次 · 网络错误、请求超时')
    expect(list).toMatch(/aria-label="常见失败原因"[\s\S]*网络错误[\s\S]*<strong[^>]*>2</)
    expect(html).toMatch(/失败记录 <span[^>]*>2<\/span>/)
  })

  it('只标出有证据判定月底领不到的格子，日历和详情都省略推测说明', async () => {
    const { html, dayDetail, page } = await render({
      payload: historyWithMissedFirstDay(),
      cachedRewards: thirtySlots(),
      interact(page) {
        page.selectSlot(30)
      }
    })
    expect(page.signIn.value).toMatchObject({ claimed: 2, total: 30, lag: 1, todayIndex: 2 })
    expect(page.signIn.value.slots[0].date).toBe('2026-11-02')
    expect(slotClass(html, 3)).toContain('is-upcoming')
    expect(slotClass(html, 30)).toContain('is-unreachable')
    expect(slotTag(html, 30)).toContain('本月领不到')
    expect(slotCell(html, 30)).not.toContain('sign-slot__tag')
    expect(dayDetail).toContain('第 30 格奖励')
    expect(dayDetail).not.toContain('本月剩下的天数不够，到月底也轮不到这一格。')
    expect(dayDetail).not.toContain('进度以')
    expect(dayDetail).not.toContain('待确认')
    expect(slotClass(html, 22)).toContain('is-near')
    expect(slotClass(html, 29)).toContain('is-near')
    expect(slotClass(html, 21)).not.toContain('is-near')
  })

  it('月度奖励按已领取、月底前可领取和本月领不到分组，不附说明文字', async () => {
    const { html, page } = await render({
      payload: historyWithMissedFirstDay(),
      cachedRewards: thirtySlots(),
      interact(page) {
        page.detailView.value = 'rewards'
      }
    })
    const monthly = html.split('aria-label="月度奖励"')[1]
    expect(monthly).toMatch(/<h3[^>]*>已领取<\/h3>/)
    const upcoming = monthly.split('aria-label="月底前可领取"')[1].split('</section>')[0]
    const lost = monthly.split('aria-label="本月领不到"')[1].split('</section>')[0]
    // 11 月 1 日失败、2 日和 3 日签到：剩余 28 格只剩 27 天，最后一格排不下。
    expect(page.upcomingRewards.value).toEqual([
      { name: '龙门币', game_group: '明日方舟', count: 7000, days: 14 },
      { name: '赤金', game_group: '明日方舟', count: 26, days: 13 }
    ])
    expect(upcoming).toMatch(/title="龙门币 ×7,000"/)
    expect(lost).toMatch(/title="赤金 ×2"/)
    expect(lost).not.toContain('龙门币')
    expect(monthly).not.toContain('class="reward-note"')
    expect(monthly).not.toMatch(/<h3[^>]*>[^<]*<small/)
  })

  it('翻月读取该月，切回本月定位到今天', async () => {
    const { dayDetail, axios } = await render({
      interact: async (page) => {
        await page.selectMonth('2026-10-01')
        expect(page.activeSlot.value).toMatchObject({ index: 1, date: '2026-10-31' })
        expect(page.records.value.map((row) => row.date)).toEqual(['2026-10-31'])
        await page.selectMonth('2026-11-01')
      }
    })
    expect(
      statisticsReads(axios)
        .slice(1)
        .map(([, options]) => options.params)
    ).toEqual([
      { startDate: '2026-10-01', endDate: '2026-10-31' },
      { startDate: '2026-11-01', endDate: '2026-11-30' }
    ])
    expect(dayDetail).toContain('11月3日')
  })

  it('翻到历史月份读取该月奖励缓存，按快照排出格子和领取日期', async () => {
    const payload = history()
    payload.records.push(
      record('2026-10-30', payload.pairs[0], { outcome: 'repeated', item: null })
    )
    payload.pairs[0].first_date = '2026-10-30'
    const { dayDetail, html, axios } = await render({
      payload,
      cachedRewards: { month: '2026-11', cached: true, pairs: [], warnings: [] },
      pastRewards: {
        month: '2026-10',
        cached: true,
        pairs: [
          {
            account: firstAccount,
            game: arknights,
            progress_date: '2026-10-31',
            signed_today: true,
            reward_slots: [
              { done: true, rewards: [{ item: '招聘许可', count: 1 }] },
              { done: true, rewards: [{ item: '合成玉', count: 40 }] },
              { done: false, rewards: [{ item: '赤金', count: 2 }] }
            ]
          }
        ],
        warnings: []
      },
      interact: (page) => page.selectMonth('2026-10-01', '2026-10-30')
    })
    expect(axios.post).not.toHaveBeenCalled()
    expect(axios.get).toHaveBeenLastCalledWith(expect.stringMatching(/\/skland\/rewards$/), {
      params: { month: '2026-10' }
    })
    expect(slotCell(html, 2)).toContain(encodeURIComponent('合成玉'))
    expect(slotClass(html, 3)).toContain('is-unclaimed')
    expect(slotTag(html, 3)).toContain('月底未领取')
    expect(dayDetail).toContain('第 1 格奖励')
    expect(dayDetail).toContain('10月30日签到领取，当天已在其他地方签到')
  })

  it('切回本月时，忽略晚到的历史奖励缓存', async () => {
    const payload = history()
    const cachedRewards = { month: '2026-11', cached: true, pairs: [], warnings: [] }
    const { page, html, axios } = await render({
      payload,
      cachedRewards,
      interact: async (page, axios) => {
        let startHistory
        let finishHistory
        const historyStarted = new Promise((resolve) => {
          startHistory = resolve
        })
        const get = axios.get.getMockImplementation()
        axios.get.mockImplementation((url, options) => {
          if (url.endsWith('/skland/rewards') && options.params.month === '2026-10') {
            return new Promise((resolve) => {
              finishHistory = resolve
              startHistory()
            })
          }
          return get(url, options)
        })
        const october = page.selectMonth('2026-10-01')
        await historyStarted
        await page.selectMonth('2026-11-01')
        finishHistory({ data: { ...cachedRewards, month: '2026-10', warnings: ['十月提示'] } })
        await october
      }
    })
    expect(axios.post).not.toHaveBeenCalled()
    expect(page.selectedMonthRewards.value).toEqual(cachedRewards)
    expect(html).not.toContain('十月提示')
  })

  it('没有本机历史记录时仍可翻到保存过奖励的月份', async () => {
    const { page, html, axios } = await render({
      payload: { ...history(), pairs: [], accounts: [], games: [], records: [] },
      cachedRewards: {
        month: '2026-11',
        cached: true,
        pairs: [],
        warnings: [],
        earliest_month: '2026-10'
      },
      pastRewards: {
        month: '2026-10',
        cached: true,
        pairs: [
          {
            account: firstAccount,
            game: arknights,
            progress_date: '2026-10-01',
            signed_today: false,
            reward_slots: [{ done: false, rewards: [{ item: '招聘许可', count: 1 }] }]
          }
        ],
        warnings: [],
        earliest_month: '2026-10'
      },
      interact: (page) => page.selectMonth('2026-10-01')
    })
    expect(page.month.value).toBe('2026-10-01')
    expect(axios.post).not.toHaveBeenCalled()
    expect(slotCell(html, 1)).toContain(encodeURIComponent('招聘许可'))
    expect(slotTag(html, 1)).toContain('aria-label="第 1 格奖励，招聘许可 ×1"')
    expect(slotClass(html, 1)).toContain('is-unknown')
  })

  it('客户端和后端跨月时使用后端日期定位今天', async () => {
    vi.setSystemTime(new Date(2026, 9, 31, 23))
    const { dayDetail, axios } = await render()
    expect(statisticsReads(axios).map(([, options]) => options.params.startDate)).toEqual([
      '2026-10-01',
      '2026-11-01'
    ])
    expect(dayDetail).toContain('11月3日')
  })

  it('月份选择器允许跳到历史年份，并限制在有记录的月份范围内', async () => {
    const payload = history()
    payload.pairs[0].first_date = '2025-12-31'
    payload.records.push(record('2025-12-31', payload.pairs[0]))
    const { dayDetail, page, axios } = await render({
      payload,
      interact: async (page) => {
        await page.pickMonth(new Date(2025, 10, 1).getTime())
        await page.pickMonth(new Date(2026, 11, 1).getTime())
        await page.pickMonth(new Date(2025, 11, 1).getTime())
      }
    })
    expect(page.yearRange.value).toEqual([2025, 2027])
    expect(statisticsReads(axios).map(([, options]) => options.params.startDate)).toEqual([
      '2026-11-01',
      '2025-12-01'
    ])
    expect(dayDetail).toContain('2025/12/31签到领取')
  })

  it('快速翻月时忽略晚到的其他月份响应', async () => {
    const payload = history()
    const { dayDetail, page } = await render({
      payload,
      interact: async (page, axios) => {
        let finishOctober
        axios.get.mockImplementationOnce(
          () =>
            new Promise((resolve) => {
              finishOctober = resolve
            })
        )
        const october = page.selectMonth('2026-10-01')
        await page.selectMonth('2026-11-01')
        finishOctober(monthResponse(payload, { startDate: '2026-10-01', endDate: '2026-10-31' }))
        await october
      }
    })
    expect(page.month.value).toBe('2026-11-01')
    expect(dayDetail).toContain('11月3日')
    expect(page.records.value).toHaveLength(5)
  })

  it('快速翻回原月时等这一次的月度奖励，晚到的上月响应不撤下占位', async () => {
    const octoberStarted = Promise.withResolvers()
    const novemberStarted = Promise.withResolvers()
    const octoberReply = Promise.withResolvers()
    const novemberReply = Promise.withResolvers()
    const { html } = await render({
      cachedRewards: { month: '2026-11', cached: true, pairs: [], warnings: [] },
      interact: async (page, axios) => {
        expect(page.signIn.value.source).toBe('local')
        const get = axios.get.getMockImplementation()
        axios.get.mockImplementation((url, options) => {
          if (!url.endsWith('/skland/rewards')) return get(url, options)
          if (options.params.month === '2026-10') {
            octoberStarted.resolve()
            return octoberReply.promise
          }
          novemberStarted.resolve()
          return novemberReply.promise
        })
        const october = page.selectMonth('2026-10-01')
        await octoberStarted.promise
        const november = page.selectMonth('2026-11-01')
        await novemberStarted.promise
        const waitingForNovember = {
          month: page.data.value.range.start,
          pending: page.monthPending.value,
          signIn: page.signIn.value,
          fullPageSkeleton: page.sklandSkeleton.value
        }
        octoberReply.resolve({ data: { month: '2026-10', cached: true, pairs: [], warnings: [] } })
        await october
        const pendingAfterOctober = page.monthPending.value
        novemberReply.resolve({ data: thirtySlots() })
        await november

        expect(waitingForNovember).toEqual({
          month: '2026-11-01',
          pending: true,
          signIn: null,
          fullPageSkeleton: false
        })
        expect(pendingAfterOctober).toBe(true)
        expect(page.signIn.value.source).toBe('cache')
      }
    })
    expect(html.match(/data-slot="/g)).toHaveLength(30)
  })

  it('当前月没有记录时可以跳到最近有记录的日期', async () => {
    const entry = pair(firstAccount, arknights, {
      first_date: '2026-10-20',
      last_date: '2026-10-22'
    })
    const payload = { ...history(), pairs: [entry], records: [record('2026-10-22', entry)] }
    const { html, page, axios } = await render({ payload })
    expect(html).toContain('这个月没有签到记录')
    expect(html).toContain('查看最近记录')
    await page.showLatest()
    expect(page.activeSlot.value).toMatchObject({ index: 1, date: '2026-10-22' })
    expect(statisticsReads(axios).at(-1)[1].params.startDate).toBe('2026-10-01')
  })

  it('最近的签到记录属于同区服的第二个角色时打开该角色的签到详情', async () => {
    const entry = pair(firstAccount, arknights, {
      first_date: '2026-10-21',
      last_date: '2026-10-22'
    })
    const dates = ['2026-10-21', '2026-10-22']
    const { dayDetail, page } = await render({
      payload: {
        ...history(),
        pairs: [entry],
        records: dates.map((date, index) => record(date, entry, { role_key: `role-${index + 1}` }))
      },
      pastRewards: {
        month: '2026-10',
        cached: true,
        pairs: dates.map((date, index) => ({
          account: firstAccount,
          game: arknights,
          role_index: index + 1,
          role_key: `role-${index + 1}`,
          progress_date: '2026-10-31',
          signed_today: false,
          signed_dates: [date],
          reward_slots: [{ done: true, rewards: [{ item: '龙门币', count: 1000 }] }]
        })),
        warnings: []
      },
      interact: (page) => page.showLatest()
    })
    expect(page.selectedChannel.value.roleKey).toBe('role-2')
    expect(dayDetail).toContain('10月22日签到领取')
  })

  it('今天有最新记录时把七天没有更新的渠道标为近期无记录', async () => {
    const payload = history()
    payload.pairs[2].first_date = '2026-10-01'
    payload.pairs[2].last_date = '2026-10-01'
    payload.records = payload.records.filter((row) => row.account !== secondAccount)
    const { page } = await render({ payload })
    expect(page.channels.value.map((channel) => channel.status)).toEqual([
      'signed',
      'signed',
      'stale'
    ])
  })

  it('没有历史时提供账号管理入口', async () => {
    const { html } = await render({
      payload: { ...history(), pairs: [], accounts: [], games: [], records: [] }
    })
    expect(html).toContain('还没有签到记录')
    expect(html).toContain('/settings?token=session-token#task-accounts')
  })

  it('未读取到角色时仍显示当天账号失败并可提交签到任务', async () => {
    const failure = {
      date: '2026-11-03',
      account: firstAccount,
      attempts: 1,
      messages: ['森空岛登录失败，请检查账号设置或网络连接'],
      resolved: false
    }
    const { html, page, axios } = await render({
      payload: {
        ...history(),
        pairs: [],
        accounts: [],
        games: [],
        records: [],
        account_failures: [failure]
      },
      interact: (page) => page.retrySignIn()
    })

    expect(page.channels.value).toEqual([])
    expect(html).toContain('今天有 1 项签到失败')
    expect(html).toContain(failure.messages[0])
    expect(html).toContain('重新签到')
    expect(html).toContain('/settings?token=session-token#task-accounts')
    expect(axios.post).toHaveBeenCalledWith(
      expect.stringMatching(/\/task$/),
      { task: expect.objectContaining({ task_type: '森空岛签到' }) },
      expect.any(Object)
    )
  })

  it('账号当天恢复读取签到角色后，账号失败详情与角色签到结果独立显示', async () => {
    const payload = history()
    payload.account_failures = [
      {
        date: '2026-11-03',
        account: firstAccount,
        attempts: 2,
        messages: ['森空岛登录失败，请检查账号设置或网络连接'],
        resolved: true
      }
    ]
    const { page, dayDetail } = await render({
      payload,
      interact: (page) => page.selectFailure(page.failureLog.value.entries[0])
    })

    expect(page.failureLog.value.entries[0]).toMatchObject({ pending: false, recovered: true })
    expect(dayDetail).toContain('当天已读到签到角色')
    expect(dayDetail).not.toContain('当天已签到')
    expect(dayDetail).not.toContain('重新签到')
  })

  it('只有账号级失败记录时也可以选择历史月份查看', async () => {
    const date = '2026-10-22'
    const { html, page } = await render({
      payload: {
        ...history(),
        pairs: [],
        accounts: [],
        games: [],
        records: [],
        first_account_failure_date: date,
        account_failures: [
          {
            date,
            account: firstAccount,
            attempts: 1,
            messages: ['没有可签到的已启用角色'],
            resolved: false
          }
        ]
      },
      interact: (page) => page.selectMonth('2026-10-01')
    })

    expect(page.month.value).toBe('2026-10-01')
    expect(html).toContain('没有可签到的已启用角色')
    expect(html).not.toContain('重新签到')
  })

  it('没有历史且奖励读取失败时仍显示原因', async () => {
    const { html } = await render({
      payload: { ...history(), pairs: [], accounts: [], games: [], records: [] },
      rewards: {
        month: '2026-11',
        cached: false,
        pairs: [],
        warnings: ['森空岛账号登录失败，请检查账号设置']
      }
    })
    expect(html).toContain('还没有签到记录')
    expect(html).toContain('森空岛账号登录失败，请检查账号设置')
  })

  it('提示同名遮盖账号未统计本机记录，同时显示森空岛角色进度', async () => {
    const { html } = await render({
      payload: {
        ...history(),
        accounts: [],
        games: [],
        pairs: [],
        records: [],
        ambiguous_accounts: [firstAccount]
      },
      cachedRewards: thirtySlots()
    })

    expect(html).toContain(`账号隐藏部分字符后显示为相同的标识（${firstAccount}）`)
    expect(html).toContain('这些账号的本机签到记录无法区分，未纳入统计')
    expect(html).toContain('森空岛已签到')
    expect(html).not.toContain('本机有签到记录')
    expect(slotClass(html, 2)).toContain('is-claimed')
  })

  it('没有本机历史时用奖励缓存排出本月签到日历', async () => {
    const rewards = {
      month: '2026-11',
      cached: true,
      pairs: [
        {
          account: firstAccount,
          game: arknights,
          display_name: '罗德岛博士',
          progress_date: '2026-11-03',
          signed_today: false,
          reward_slots: [
            { index: 1, done: true, rewards: [{ item: '龙门币', count: 1000 }] },
            { index: 2, done: false, rewards: [{ item: '招聘许可', count: 1 }] }
          ]
        }
      ],
      warnings: []
    }
    const { html, dayDetail, axios } = await render({
      payload: { ...history(), pairs: [], accounts: [], games: [], records: [] },
      cachedRewards: rewards,
      interact: (page) => page.selectSlot(1)
    })
    expect(axios.get).toHaveBeenLastCalledWith(expect.stringMatching(/\/skland\/rewards$/), {
      params: { month: '2026-11' }
    })
    expect(axios.post).not.toHaveBeenCalled()
    expect(slotClass(html, 1)).toContain('is-claimed')
    expect(slotClass(html, 2)).toContain('is-today')
    expect(slotCell(html, 2)).toContain(encodeURIComponent('招聘许可'))
    expect(dayDetail).toContain('已领取')
    expect(dayDetail).not.toContain('slot-detail__date')
    expect(html).toContain('罗德岛博士')
    expect(html).not.toContain('读取预计奖励')
  })

  it('首次自动读取奖励，并展示所选渠道的格子', async () => {
    const rewards = {
      month: '2026-11',
      cached: true,
      pairs: [
        {
          account: firstAccount,
          game: arknights,
          progress_date: '2026-11-03',
          signed_today: false,
          reward_slots: [{ index: 1, done: false, rewards: [{ item: '合成玉', count: 40 }] }]
        },
        {
          account: firstAccount,
          game: endfield,
          progress_date: '2026-11-03',
          signed_today: true,
          reward_slots: [
            {
              index: 1,
              done: true,
              rewards: [
                { item: '折金票', count: 1000 },
                { item: '中级作战记录', count: 6 }
              ]
            },
            {
              index: 2,
              done: false,
              rewards: [
                { item: '武库配额', count: 200 },
                { item: '武器检查装置', count: 5 }
              ]
            }
          ]
        }
      ],
      warnings: ['一个绑定角色的本月奖励读取失败']
    }
    const { html, dayDetail, axios, page } = await render({
      rewards,
      interact: (page) => {
        page.selectChannel(`${firstAccount}::${endfield}::1`)
        page.selectSlot(2)
      }
    })
    expect(axios.post).toHaveBeenCalledExactlyOnceWith(
      expect.stringMatching(/\/skland\/rewards\/refresh$/),
      {}
    )
    expect(page.signIn.value.slots.map(({ index, state, date }) => [index, state, date])).toEqual([
      [1, 'today', '2026-11-03'],
      [2, 'upcoming', '2026-11-04']
    ])
    expect(slotCell(html, 1)).toContain('折金票')
    expect(slotCell(html, 1)).toContain('/skland-icons/endfield/item_gold.webp')
    expect(slotCell(html, 1)).toContain('/skland-icons/endfield/item_expcard_stage1_mid.webp')
    expect(slotCell(html, 2)).toContain('/skland-icons/endfield/item_weapon_expcard_mid.webp')
    expect(slotCell(html, 2)).toContain('sign-slot__fallback')
    expect(dayDetail).toContain('武库配额')
    expect(dayDetail).toContain('/skland-icons/endfield/item_weapon_expcard_mid.webp')
    expect(dayDetail).toContain('预计 11月4日 领取')
    expect(html).not.toContain('合成玉')
    expect(html).toContain('一个绑定角色的本月奖励读取失败')
  })

  it('跨日复用本月缓存，并根据本机签到记录推进签到日历', async () => {
    const payload = history()
    Object.assign(payload.records[0], { item: '招聘许可', count: 1, reward: '招聘许可×1' })
    const { html, axios, page } = await render({
      payload,
      cachedRewards: {
        month: '2026-11',
        cached: true,
        pairs: [
          {
            account: firstAccount,
            game: arknights,
            progress_date: '2026-11-02',
            signed_today: true,
            reward_slots: [
              { index: 1, done: true, rewards: [{ item: '龙门币', count: 1000 }] },
              { index: 2, done: false, rewards: [{ item: '招聘许可', count: 1 }] },
              { index: 3, done: false, rewards: [{ item: '赤金', count: 2 }] }
            ]
          }
        ],
        warnings: []
      }
    })
    expect(axios.post).not.toHaveBeenCalled()
    expect(page.signIn.value.slots.map(({ state, date }) => [state, date])).toEqual([
      ['claimed', '2026-11-02'],
      ['today', '2026-11-03'],
      ['upcoming', '2026-11-04']
    ])
    expect(slotCell(html, 3)).toContain(encodeURIComponent('赤金'))
  })

  it('保存的渠道不存在时回到该账号的第一个渠道', async () => {
    const { page } = await render({
      preferences: { account: secondAccount, game: endfield }
    })
    expect(page.selectedChannel.value).toMatchObject({ account: secondAccount, game: bilibili })
  })

  it('读取失败时展示接口错误，重试后恢复', async () => {
    const { html, page } = await render({
      failure: { response: { data: { error: 'skland.csv 正在被其他程序占用，请关闭后刷新' } } }
    })
    expect(html).toContain('skland.csv 正在被其他程序占用')
    expect(html).toContain('重试')
    await page.load()
    expect(page.error.value).toBe('')
    expect(page.records.value).toHaveLength(5)
  })
})
