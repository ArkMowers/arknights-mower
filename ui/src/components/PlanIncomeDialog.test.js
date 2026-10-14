import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { effectScope, reactive, nextTick } from 'vue'
import Dialog from './PlanIncomeDialog.vue'
import { loadIncomeArchive, saveIncomeArchive } from '@/riic/incomeArchive'
import { renderIncomeImage, downloadIncomeImage } from '@/riic/incomeImage'
vi.mock('@/riic/incomeArchive', () => ({
  loadIncomeArchive: vi.fn(async () => null),
  saveIncomeArchive: vi.fn(async () => {})
}))
vi.mock('./IncomeMoraleChart.vue', () => ({ default: { render: () => null } }))
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
    put: vi.fn()
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
it('missing cache values require explicit input instead of falling back to maximum or zero', async () => {
  const missing = cache()
  missing.inventory.gold = null
  io.client.get.mockResolvedValueOnce({ data: missing })
  await page.readCache()
  await page.start()
  expect(workers).toHaveLength(0)
  expect(page.state.error).toContain('赤金')
  expect(page.settings.operatorMode).toBe('cache')
  page.settings.inventorySource = 'manual'
  await page.start()
  expect(workers).toHaveLength(1)
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
    { room_1_1: { x: 42 } }
  ])
  expect(downloadIncomeImage.mock.calls.at(-1)[1]).toContain('原排班_')
  expect(page.state.input.plan.facility_levels).toBeUndefined()
  expect(props.snapshot.plan.facility_levels).toEqual({ contact: 1 })
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
