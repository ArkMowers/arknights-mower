import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { effectScope, reactive, nextTick } from 'vue'
import Dialog from './PlanIncomeDialog.vue'
import { loadIncomeArchive, saveIncomeArchive } from '@/riic/incomeArchive'
import { renderIncomeImage, downloadIncomeImage } from '@/riic/incomeImage'
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
const io = vi.hoisted(() => ({ client: null, cleanup: null }))
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
      droneRoom: 'room_1_1',
      image: new Blob(['original']),
      theme: 'light',
      roomBounds: { room_1_1: { x: 42 } },
      label: '原排班',
      plan: {
        default: 'plan1',
        conf: {},
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
it('reads cached ownership and stock without writing configuration', async () => {
  await page.readCache()
  await page.readWeights()
  expect(page.settings.cachedOperators).toEqual([{ operator: '阿米娅', elitePhase: 2, level: 80 }])
  expect(page.settings.cachedInventory.gold).toBe(10)
  expect(page.settings.mowerWeights).toMatchObject({ exp: 0.9568, gold: 0.76544, orders: 0.23456 })
  expect(io.client.put).not.toHaveBeenCalled()
})
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
    message: 'Mower 收益设置读取失败，可重试或选择本次自定义',
    cause: failure
  })
  expect(page.weightsError.value).toBe('Mower 收益设置读取失败，可重试或选择本次自定义')
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
  page.settings.droneRoom = 'room_3_3'
  page.exportName.value = '我的排班'
  await page.exportImage()
  expect(renderIncomeImage).toHaveBeenCalledOnce()
  expect(renderIncomeImage.mock.calls[0][2].droneRoom).toBe('room_1_1')
  expect(renderIncomeImage.mock.calls[0][3]).toEqual(props.snapshot.plan)
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

it('uses the captured Mower drone target without saving temporary changes', async () => {
  expect(page.settings.droneRoom).toBe('room_1_1')
  page.settings.droneRoom = ''
  await page.readCache()
  await page.start()
  expect(workers[0].postMessage.mock.calls[0][0].settings.droneRoom).toBe('')
  expect(props.snapshot.droneRoom).toBe('room_1_1')
  expect(io.client.put).not.toHaveBeenCalled()
})
it('applies the default after asynchronous capture and rejects unavailable facilities', async () => {
  const snapshot = structuredClone(JSON.parse(JSON.stringify(props.snapshot)))
  props.snapshot = null
  await nextTick()
  props.snapshot = { ...snapshot, droneRoom: 'room_3_3' }
  await nextTick()
  expect(page.settings.droneRoom).toBe('')
  props.snapshot = snapshot
  await nextTick()
  expect(page.settings.droneRoom).toBe('room_1_1')
})

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
  await page.restoreResult()
  await page.exportImage()
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
