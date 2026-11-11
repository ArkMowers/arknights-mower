import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { effectScope, reactive, nextTick } from 'vue'
import Dialog from './PlanIncomeDialog.vue'
import { loadIncomeArchive, saveIncomeArchive } from '@/riic/incomeArchive'
import { renderIncomeImage, downloadIncomeImage } from '@/riic/incomeImage'
import { INCOME_PREFERENCES_KEY } from '@/riic/incomePreferences'
vi.mock('@/riic/incomeArchive', () => ({
  loadIncomeArchive: vi.fn(async () => null),
  saveIncomeArchive: vi.fn(async () => {})
}))
vi.mock('@/riic/vendor/components/workbench/ScheduleTimelineGantt.vue', () => ({
  default: { render: () => null }
}))
vi.mock('@/riic/incomeImage', async (original) => ({
  ...(await original()),
  renderIncomeImage: vi.fn(async () => new Blob(['image'])),
  downloadIncomeImage: vi.fn()
}))
const io = vi.hoisted(() => ({ client: null, cleanup: null, warning: vi.fn() }))
vi.mock('naive-ui', () => ({ useMessage: () => ({ warning: io.warning }) }))
vi.mock('vue', async (original) => ({
  ...(await original()),
  useSSRContext: () => ({ modules: new Set() }),
  inject: () => io.client,
  onMounted: vi.fn(),
  onBeforeUnmount: (fn) => {
    io.cleanup = fn
  }
}))
const valuation = (algorithm = 2) => ({
  base_algorithm: algorithm,
  ratios: { experience: 0.9568, gold: 0.76544, order: 0.23456, efficiency: 1.7 }
})
const cache = () => ({
  has_roster: true,
  operators: [{ name: '阿米娅', owned: true, phase: 2, level: 80 }],
  has_inventory: true,
  inventory: { gold: 10, fragment: 0, orirock: 1, device: 0, lmd: 42, exp: 1000 },
  observed_at: 1234
})
let page, scope, workers, props
beforeEach(async () => {
  vi.clearAllMocks()
  const saved = new Map()
  vi.stubGlobal('localStorage', {
    getItem: vi.fn((key) => saved.get(key) ?? null),
    setItem: vi.fn((key, value) => saved.set(key, value)),
    removeItem: vi.fn((key) => saved.delete(key))
  })
  loadIncomeArchive.mockResolvedValue(null)
  saveIncomeArchive.mockResolvedValue(undefined)
  io.client = {
    get: vi.fn(async (url) => ({ data: url.includes('income-cache') ? cache() : valuation() })),
    put: vi.fn(),
    post: vi.fn(async () => ({ data: { success: true, status: 'passed' } }))
  }
  workers = []
  vi.stubGlobal(
    'Worker',
    class {
      constructor() {
        this.postMessage = vi.fn()
        this.terminate = vi.fn()
        workers.push(this)
      }
    }
  )
  scope = effectScope()
  props = reactive({
    snapshot: {
      image: new Blob(['original']),
      theme: 'light',
      roomBounds: { room_1_1: { x: 42 } },
      label: '原排班',
      plan: {
        default: 'plan1',
        conf: {},
        advanced_settings: { drone_room: 'room_1_1' },
        backup_plans: [],
        plan1: { room_1_1: { name: '制造站', product: 'gold', plans: [] } }
      }
    }
  })
  page = scope.run(() => Dialog.setup(props, { expose: vi.fn(), emit: vi.fn() }))
  await page.restoreResult()
})
afterEach(() => {
  io.cleanup()
  scope.stop()
  vi.unstubAllGlobals()
})
function reopenDialog() {
  io.cleanup()
  scope.stop()
  scope = effectScope()
  page = scope.run(() => Dialog.setup(props, { expose: vi.fn(), emit: vi.fn() }))
}
it('remembers edited parameters across dialog recreation before any calculation', () => {
  Object.assign(page.settings, {
    warmupDays: 1,
    sampleDays: 7,
    expectationMode: false,
    operatorMode: 'custom',
    operatorText: '阿米娅,2,80',
    inventorySource: 'manual',
    allowMaterialDebt: false,
    dailyExternalResources: { gold: 12.5, orirock: 3 },
    jayeElite0: true,
    weightMode: 'custom'
  })
  page.settings.initialInventory.gold = 123
  page.settings.productionWeights.exp = 2
  reopenDialog()
  expect(page.settings).toMatchObject({
    warmupDays: 1,
    sampleDays: 7,
    expectationMode: false,
    operatorMode: 'custom',
    operatorText: '阿米娅,2,80',
    inventorySource: 'manual',
    initialInventory: { gold: 123 },
    productionWeights: { exp: 2 },
    allowMaterialDebt: false,
    dailyExternalResources: { gold: 12.5, orirock: 3 },
    jayeElite0: true,
    weightMode: 'custom'
  })
  expect(io.client.put).not.toHaveBeenCalled()
  expect(io.client.post).not.toHaveBeenCalled()
  expect(workers).toHaveLength(0)
})
it('preserves edited cached quantities while reading fresh untouched resources', async () => {
  await page.readCache()
  page.settings.cachedInventory.gold = 222
  reopenDialog()
  const fresh = cache()
  fresh.inventory.gold = 20
  fresh.inventory.lmd = 99
  io.client.get.mockResolvedValueOnce({ data: fresh })
  await page.readCache({ preserveOverrides: true })
  expect(page.settings.cachedInventory).toMatchObject({ gold: 222, lmd: 99 })
  await page.readCache()
  expect(page.settings.cachedInventory.gold).toBe(10)
  reopenDialog()
  await page.readCache({ preserveOverrides: true })
  expect(page.settings.cachedInventory.gold).toBe(10)
})
it('keeps an inventory override when a fresh cache temporarily matches the edited value', async () => {
  await page.readCache()
  page.settings.cachedInventory.gold = 222
  reopenDialog()
  const matching = cache()
  matching.inventory.gold = 222
  io.client.get.mockResolvedValueOnce({ data: matching })
  await page.readCache({ preserveOverrides: true })
  await page.readWeights()
  reopenDialog()
  await page.readCache({ preserveOverrides: true })
  expect(page.settings.cachedInventory.gold).toBe(222)
})
it('restores defaults without changing shared settings or the retained result', async () => {
  await page.readCache()
  await page.readWeights()
  const result = { success: true, marker: 'existing result' }
  page.state.result = result
  page.settings.sampleDays = 5
  page.settings.cachedInventory.gold = 777
  page.settings.weightMode = 'custom'
  page.settings.productionWeights.exp = 5
  page.resetSettings()
  expect(page.settings).toMatchObject({
    warmupDays: 3,
    sampleDays: 28,
    expectationMode: true,
    operatorMode: 'cache',
    inventorySource: 'cache',
    weightMode: 'mower',
    cachedInventory: { gold: 10 },
    productionWeights: { exp: 1 },
    mowerAlgorithm: 2
  })
  expect(page.settings.mowerWeights.exp).toBe(0.9568)
  expect(page.state.result).toEqual(result)
  expect(localStorage.getItem(INCOME_PREFERENCES_KEY)).toBeNull()
  expect(io.client.put).not.toHaveBeenCalled()
  reopenDialog()
  expect(page.settings.sampleDays).toBe(28)
})
it('retains reset defaults after a pending initial cache read', async () => {
  await page.readCache()
  page.settings.cachedInventory.gold = 777
  reopenDialog()
  let resolve
  io.client.get.mockReturnValueOnce(
    new Promise((done) => {
      resolve = done
    })
  )
  const loading = page.readCache({ preserveOverrides: true })
  page.resetSettings()
  resolve({ data: cache() })
  await loading
  expect(page.settings.cachedInventory.gold).toBe(10)
})
it('keeps active parameters when browser storage rejects writes', () => {
  localStorage.setItem.mockImplementation(() => {
    throw new Error('quota')
  })
  page.settings.sampleDays = 7
  expect(page.settings.sampleDays).toBe(7)
  expect(page.preferencesError.value).toContain('未能保存')
  vi.restoreAllMocks()
})
it('does not reset a calculation while it is running', () => {
  page.settings.sampleDays = 7
  page.state.running = true
  page.resetSettings()
  expect(page.settings.sampleDays).toBe(7)
})
it.each(['room_3_3', ''])('ignores the remembered drone target %s', async (droneRoom) => {
  props.snapshot.plan.plan1.room_3_3 = { name: '制造站', product: 'exp', plans: [] }
  localStorage.setItem(
    INCOME_PREFERENCES_KEY,
    JSON.stringify({ version: 1, settings: { droneRoom, sampleDays: 7 } })
  )
  reopenDialog()
  expect(page.settings).not.toHaveProperty('droneRoom')
  expect(page.settings.sampleDays).toBe(7)
  await page.readCache()
  await page.restoreResult()
  await page.start()
  const input = workers[0].postMessage.mock.calls[0][0]
  expect(input.settings.droneRoom).toBe('room_1_1')
  expect(input.plan.advanced_settings.drone_room).toBe('room_1_1')
  expect(JSON.parse(localStorage.getItem(INCOME_PREFERENCES_KEY)).settings).not.toHaveProperty(
    'droneRoom'
  )
})
it.each([false, true])(
  'uses advanced settings when snapshot capture finishes, cache first: %s',
  async (cacheFirst) => {
    const snapshot = props.snapshot
    props.snapshot = null
    reopenDialog()
    page.settings.sampleDays = 7
    if (cacheFirst) await page.readCache({ preserveOverrides: true })
    props.snapshot = snapshot
    await nextTick()
    if (!cacheFirst) await page.readCache({ preserveOverrides: true })
    await page.restoreResult()
    await page.start()
    expect(workers[0].postMessage.mock.calls[0][0].settings.droneRoom).toBe('room_1_1')
    expect(page.settings.sampleDays).toBe(7)
    expect(page.settings).not.toHaveProperty('droneRoom')
  }
)
it('reads cached ownership and stock without writing configuration', async () => {
  expect(page.settings.expectationMode).toBe(true)
  expect(page.settings).not.toHaveProperty('seed')
  await page.readCache()
  await page.readWeights()
  expect(page.settings.cachedOperators).toEqual([{ operator: '阿米娅', elitePhase: 2, level: 80 }])
  expect(page.settings.cachedInventory.gold).toBe(10)
  expect(page.settings.mowerWeights).toMatchObject({ exp: 0.9568, gold: 0.76544, orders: 0.23456 })
  expect(io.client.put).not.toHaveBeenCalled()
})
it.each(['primary', 'active-backup', 'maintenance-backup'])(
  'starts a theoretical run with a tailor in %s',
  async (kind) => {
    Object.assign(page.settings, {
      operatorMode: 'maximum',
      inventorySource: 'manual',
      finiteInventory: false,
      weightMode: 'custom'
    })
    props.snapshot.plan.plan1.room_1_1 = {
      name: '贸易站',
      product: 'lmd',
      plans: [{ agent: kind === 'primary' ? '柏喙' : '芬' }]
    }
    if (kind !== 'primary')
      props.snapshot.plan.backup_plans = [
        {
          name: '裁缝副表',
          trigger:
            kind === 'active-backup'
              ? 'True'
              : {
                  left: 'op_data.major_maintenance_remaining_hours()',
                  operator: '<',
                  right: '4'
                },
          task: { room_1_1: ['柏喙'] }
        }
      ]
    await nextTick()
    await page.start()
    expect(workers).toHaveLength(1)
    const input = workers[0].postMessage.mock.calls[0][0]
    expect(input.settings.expectationMode).toBe(true)
    expect(input.settings).not.toHaveProperty('seed')
  }
)
it('saves the selected shared algorithm and preserves recycling efficiency', async () => {
  await page.readWeights()
  io.client.put.mockImplementation(async (_, value) => ({ data: value }))
  await page.selectAlgorithm(0)
  expect(io.client.put.mock.calls[0][1]).toEqual({
    base_algorithm: 0,
    ratios: { experience: 1, gold: 0.8, order: 0.2, efficiency: 1.7 }
  })
  expect(page.settings.mowerWeights.exp).toBe(1)
})
it('retains the settings request failure as the cause of the displayed error', async () => {
  const failure = new Error('offline')
  io.client.get.mockRejectedValueOnce(failure)

  await expect(page.readWeights()).rejects.toMatchObject({
    message: 'Mower 收益设置读取失败，可重试或选择自定义权重',
    cause: failure
  })
  expect(page.weightsError.value).toBe('Mower 收益设置读取失败，可重试或选择自定义权重')
  expect(page.weightsBusy.value).toBe(false)
  expect(workers).toHaveLength(0)
})
it('rereads Mower settings before starting and freezes the worker input', async () => {
  await page.readCache()
  await page.readWeights()
  io.client.get.mockResolvedValueOnce({
    data: { base_algorithm: -1, ratios: { experience: 2, gold: 0.5, order: 0.3, efficiency: 1 } }
  })
  await page.start()
  expect(workers).toHaveLength(1)
  const sent = workers[0].postMessage.mock.calls[0][0]
  expect(sent.settings.mowerWeights).toMatchObject({ exp: 2, gold: 0.5, orders: 0.3 })
  page.settings.cachedInventory.gold = 999
  expect(sent.settings.cachedInventory.gold).toBe(10)
})
it('uses zero for unreported cached quantities without changing growth mode', async () => {
  const missing = cache()
  missing.inventory.gold = null
  delete missing.inventory.fragment
  io.client.get.mockResolvedValueOnce({ data: missing })
  await page.readCache()
  await page.start()
  expect(workers).toHaveLength(1)
  const sent = workers[0].postMessage.mock.calls[0][0]
  expect(sent.settings.cachedInventory).toMatchObject({ gold: 0, fragment: 0, lmd: 42 })
  expect(sent.settings.operatorMode).toBe('cache')
})
it('closing during settings fetch does not create a worker from a late response', async () => {
  await page.readCache()
  let resolve
  io.client.get.mockImplementationOnce(
    () =>
      new Promise((done) => {
        resolve = done
      })
  )
  const start = page.start()
  page.close()
  resolve({ data: valuation() })
  await start
  expect(workers).toHaveLength(0)
})
it('keeps successful results on screen and exports only on request with frozen inputs', async () => {
  await page.readCache()
  await page.start()
  workers[0].onmessage({
    data: {
      type: 'complete',
      result: {
        success: true,
        diagnostics: [],
        summary: { totalScore82: 103475 },
        observedHours: 672
      }
    }
  })
  expect(page.activeTab.value).toBe('results')
  expect(renderIncomeImage).not.toHaveBeenCalled()
  expect(downloadIncomeImage).not.toHaveBeenCalled()
  props.snapshot = {
    ...props.snapshot,
    plan: { ...props.snapshot.plan, advanced_settings: { drone_room: '' } }
  }
  page.exportName.value = '我的排班'
  await page.exportImage()
  expect(renderIncomeImage).toHaveBeenCalledOnce()
  expect(renderIncomeImage.mock.calls[0][2].droneRoom).toBe('room_1_1')
  expect(renderIncomeImage.mock.calls[0][3].advanced_settings.drone_room).toBe('room_1_1')
  expect(downloadIncomeImage).toHaveBeenCalledOnce()
  expect(downloadIncomeImage.mock.calls[0][1]).toBe('我的排班_日均收益103475_28天.jpg')
})
it('retains bounded progress logs without triggering image rendering', async () => {
  await page.readCache()
  await page.start()
  for (let i = 0; i < 220; i++) {
    workers[0].onmessage({
      data: { type: 'progress', progress: { label: `统计 ${i} 小时`, fraction: 0.5 } }
    })
  }
  expect(page.progressLog.value).toHaveLength(200)
  expect(page.progressLog.value[0]).toBe('统计 20 小时')
  expect(page.activeTab.value).toBe('logs')
  page.session.cancel()
  expect(renderIncomeImage).not.toHaveBeenCalled()
})

it.each(['room_1_1', ''])(
  'follows the advanced drone target %s without writing configuration',
  async (droneRoom) => {
    props.snapshot.plan.advanced_settings.drone_room = droneRoom
    page.resetSettings()
    await page.readCache()
    await page.start()
    expect(workers[0].postMessage.mock.calls[0][0].settings.droneRoom).toBe(droneRoom)
    expect(props.snapshot.plan.advanced_settings.drone_room).toBe(droneRoom)
    expect(io.client.put).not.toHaveBeenCalled()
  }
)

const success = () => ({
  success: true,
  diagnostics: [],
  summary: { totalScore82: 100 },
  observedHours: 672
})
it('restores the last result with its original plan image after reopening with a different schedule', async () => {
  await page.readCache()
  await page.start()
  workers[0].onmessage({ data: { type: 'complete', result: success() } })
  const saved = saveIncomeArchive.mock.calls.at(-1)[0]
  expect(saved.input.plan).toEqual(props.snapshot.plan)
  expect(saved.snapshot.image).toBe(props.snapshot.image)
  io.cleanup()
  scope.stop()
  props.snapshot = {
    ...props.snapshot,
    label: '新排班',
    image: new Blob(['new']),
    theme: 'dark',
    roomBounds: {}
  }
  props.snapshot.plan = { ...props.snapshot.plan, facility_levels: { contact: 1 } }
  loadIncomeArchive.mockResolvedValue(saved)
  scope = effectScope()
  page = scope.run(() => Dialog.setup(props, { expose: vi.fn(), emit: vi.fn() }))
  page.settings.sampleDays = 7
  await page.restoreResult()
  await page.exportImage()
  expect(page.settings.sampleDays).toBe(7)
  expect(page.activeTab.value).toBe('results')
  expect(renderIncomeImage.mock.calls.at(-1)).toEqual([
    saved.snapshot.image,
    saved.result,
    saved.input.settings,
    saved.input.plan,
    'light',
    { room_1_1: { x: 42 } },
    { author: '', remarks: '' }
  ])
  expect(downloadIncomeImage.mock.calls.at(-1)[1]).toContain('原排班_')
  expect(page.state.input.plan.facility_levels).toBeUndefined()
  expect(props.snapshot.plan.facility_levels).toEqual({ contact: 1 })
})
it('saves editable image annotations separately from calculation inputs and restores them', async () => {
  await page.readCache()
  await page.start()
  workers[0].onmessage({ data: { type: 'complete', result: success() } })
  const original = JSON.parse(JSON.stringify(page.state.input))
  page.exportDetails.author = '排班作者'
  page.exportDetails.remarks = '满练，经验站加速\n菲亚梅塔防呆关闭'
  page.saveName()
  const saved = saveIncomeArchive.mock.calls.at(-1)[0]
  expect(saved.exportDetails).toEqual({
    author: '排班作者',
    remarks: '满练，经验站加速\n菲亚梅塔防呆关闭'
  })
  await page.exportImage()
  expect(renderIncomeImage.mock.calls.at(-1)[6]).toEqual(saved.exportDetails)
  page.exportDetails.author = '修改后的作者'
  expect(saved.exportDetails.author).toBe('排班作者')
  expect(renderIncomeImage.mock.calls.at(-1)[6].author).toBe('排班作者')
  expect(page.state.input).toEqual(original)
  expect(workers).toHaveLength(1)
  loadIncomeArchive.mockResolvedValue(saved)
  await page.restoreResult()
  expect(page.exportDetails).toEqual(saved.exportDetails)
  delete saved.exportDetails
  await page.restoreResult()
  expect(page.exportDetails).toEqual({ author: '', remarks: '' })
})
it('keeps the previous success through cancellation and replaces it only after a new success', async () => {
  await page.readCache()
  await page.start()
  workers[0].onmessage({ data: { type: 'complete', result: success() } })
  const previous = page.state.input
  props.snapshot.plan.facility_levels = { contact: 1 }
  await page.start()
  expect(page.state.input).toBe(previous)
  page.session.cancel()
  expect(page.state.result.success).toBe(true)
  expect(saveIncomeArchive).toHaveBeenCalledTimes(1)
  await page.start()
  workers[2].onmessage({ data: { type: 'complete', result: success() } })
  expect(page.state.input.plan.facility_levels).toEqual({ contact: 1 })
  expect(saveIncomeArchive).toHaveBeenCalledTimes(2)
})
it('reports storage failure while keeping the completed result exportable', async () => {
  saveIncomeArchive.mockRejectedValue(new Error('quota'))
  await page.readCache()
  await page.start()
  workers[0].onmessage({ data: { type: 'complete', result: success() } })
  await nextTick()
  expect(page.archiveError.value).toContain('quota')
  expect(page.state.result.success).toBe(true)
  await page.exportImage()
  expect(downloadIncomeImage).toHaveBeenCalledOnce()
})
it('shows failed-attempt diagnostics separately from the retained successful result', async () => {
  await page.readCache()
  await page.start()
  const saved = { ...success(), diagnostics: [{ code: 'OLD_MODEL', message: '旧结果模型说明' }] }
  workers[0].onmessage({ data: { type: 'complete', result: saved } })
  await page.start()
  const diagnostics = [
    { code: 'SIMULATION_EVENT_LIMIT', message: '达到 200000 个积分区间，结果未完成' }
  ]
  workers[1].onmessage({
    data: { type: 'complete', result: { success: false, error: '演算未完成', diagnostics } }
  })
  expect(page.state.result.diagnostics).toEqual(saved.diagnostics)
  expect(page.attemptDetails.value).toEqual(diagnostics)
  expect(page.outcomeLabel.value).toBe('演算未完成')
  expect(page.activeTab.value).toBe('logs')
  expect(saveIncomeArchive).toHaveBeenCalledTimes(1)
})
it('does not let a late archive read replace a new calculation or a closed dialog', async () => {
  let done
  loadIncomeArchive.mockImplementationOnce(
    () =>
      new Promise((resolve) => {
        done = resolve
      })
  )
  page.archiveLoading.value = true
  const restore = page.restoreResult()
  await page.start()
  expect(workers).toHaveLength(0)
  page.close()
  done({ result: success(), input: {}, snapshot: {}, progressLog: [] })
  await restore
  expect(page.state.result).toBeNull()
})

it('starts with no training-plan option and strips retired state before freezing a new run', async () => {
  expect(page.settings).not.toHaveProperty('masteryPlanPresent')
  page.settings.masteryPlanPresent = true
  await page.readCache()
  await page.start()
  expect(workers).toHaveLength(1)
  expect(workers[0].postMessage.mock.calls[0][0].settings).not.toHaveProperty('masteryPlanPresent')
  expect(page.state.input.settings).not.toHaveProperty('masteryPlanPresent')
})

it('shows conditional backup warnings before running without changing the captured schedule', async () => {
  const { backupWarningPlan } = await import('@/riic/backupWarningFixture')
  props.snapshot.plan = backupWarningPlan()
  await nextTick()
  const before = structuredClone(JSON.parse(JSON.stringify(props.snapshot.plan)))
  const warnings = page.planIssues.value.filter((issue) => issue.code === 'CONFLICTING_REPLACEMENT')
  expect(warnings).toHaveLength(3)
  for (const name of ['斯卡蒂', '幽灵鲨', '结城理'])
    expect(
      warnings.some((issue) => issue.message.includes(name) && issue.message.includes('鸿雪下班'))
    ).toBe(true)
  expect(warnings.every((issue) => issue.severity === 'warning')).toBe(true)
  expect(workers).toHaveLength(0)
  expect(props.snapshot.plan).toEqual(before)
})

it.each(['failed', 'incomplete'])(
  'automatically blocks calculation when schedule validation is %s',
  async (status) => {
    await page.readCache()
    io.client.post.mockResolvedValueOnce({
      data: { success: false, status, message: '副表组合验证失败（鸿雪下班）：斯卡蒂缺少共同绑组' }
    })
    await page.start()
    expect(io.client.post).toHaveBeenCalledWith(
      `${import.meta.env.VITE_HTTP_URL}/validate-plan`,
      { plan: props.snapshot.plan, operatorMode: 'cache' },
      expect.objectContaining({ timeout: 0, signal: expect.any(AbortSignal) })
    )
    expect(workers).toHaveLength(0)
    expect(page.state.error).toContain('鸿雪下班')
    expect(page.state.error).toContain('斯卡蒂')
    expect(page.submitting.value).toBe(false)
  }
)
it('maximum development validates the schedule without requiring Skland cache', async () => {
  page.settings.operatorMode = 'maximum'
  page.settings.inventorySource = 'manual'
  await page.start()
  expect(io.client.post.mock.calls[0][1].operatorMode).toBe('maximum')
  expect(workers).toHaveLength(1)
})
it('calculation uses the same frozen schedule and parameters that passed automatic validation', async () => {
  await page.readCache()
  let finishValidation
  io.client.post.mockImplementationOnce(
    () =>
      new Promise((resolve) => {
        finishValidation = resolve
      })
  )
  const captured = structuredClone(JSON.parse(JSON.stringify(props.snapshot.plan)))
  const start = page.start()
  await vi.waitFor(() => expect(io.client.post).toHaveBeenCalledOnce())
  expect(workers).toHaveLength(0)
  expect(page.validating.value).toBe(true)
  props.snapshot.plan.conf.workaholic = '阿米娅'
  page.settings.sampleDays = 7
  finishValidation({ data: { success: true, status: 'passed' } })
  await start
  const input = workers[0].postMessage.mock.calls[0][0]
  expect(page.validating.value).toBe(false)
  expect(io.client.post.mock.calls[0][1].plan).toEqual(captured)
  expect(input.plan).toEqual(captured)
  expect(input.settings.sampleDays).toBe(28)
})
it('does not start on network failure or a validation response received after closing', async () => {
  await page.readCache()
  io.client.post.mockRejectedValueOnce(new Error('校验请求失败'))
  await page.start()
  expect(workers).toHaveLength(0)
  expect(page.state.error).toBe('校验请求失败')
  let finishValidation
  io.client.post.mockImplementationOnce(
    () =>
      new Promise((resolve) => {
        finishValidation = resolve
      })
  )
  const start = page.start()
  await vi.waitFor(() => expect(io.client.post).toHaveBeenCalledTimes(2))
  page.close()
  finishValidation({ data: { success: true, status: 'passed' } })
  await start
  expect(workers).toHaveLength(0)
})

it.each([
  [false, null],
  [false, 0],
  [false, 77],
  [true, null],
  [true, 0],
  [true, 77]
])('freezes one shared seed before validation (tailor=%s, fixed=%s)', async (tailor, fixedSeed) => {
  page.settings.operatorMode = 'maximum'
  page.settings.inventorySource = 'manual'
  page.settings.finiteInventory = false
  page.settings.weightMode = 'custom'
  page.settings.expectationMode = false
  page.settings.fixedSeed = fixedSeed
  if (tailor)
    props.snapshot.plan.plan1.room_1_1 = {
      name: '贸易站',
      product: 'lmd',
      plans: [{ agent: '柏喙' }]
    }
  const random = vi.spyOn(crypto, 'getRandomValues').mockImplementation((array) => {
    array[0] = 123
    return array
  })
  try {
    await page.start()
    expect(workers).toHaveLength(1)
    const input = workers[0].postMessage.mock.calls[0][0]
    expect(input.settings).toMatchObject({
      expectationMode: false,
      fixedSeed,
      seed: fixedSeed ?? 123
    })
    expect(page.settings).not.toHaveProperty('seed')
    expect(random).toHaveBeenCalledTimes(fixedSeed === null ? 1 : 0)
  } finally {
    random.mockRestore()
  }
})

it('shows roster warnings without blocking or archiving them', async () => {
  await page.readCache()
  io.client.post.mockResolvedValueOnce({ data: { success: true, warnings: ['未持有干员'] } })
  await page.start()
  expect(io.warning).toHaveBeenCalledWith('未持有干员', { duration: 0, closable: true })
  expect(workers).toHaveLength(1)
  expect(saveIncomeArchive).not.toHaveBeenCalled()
})
