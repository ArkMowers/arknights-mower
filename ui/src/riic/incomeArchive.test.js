import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { reactive } from 'vue'
import { loadIncomeArchive, saveIncomeArchive } from './incomeArchive'

let stored, failWrite
beforeEach(() => {
  stored = undefined
  failWrite = false
  // Controlled IndexedDB boundary: commit only once all requests in a transaction finish.
  const db = {
    close: vi.fn(),
    transaction() {
      let active = 0
      let next = stored
      let aborted = false
      const tx = { error: null }
      const request = (action) => {
        active++
        const result = {}
        queueMicrotask(() => {
          if (aborted) return
          try {
            result.result = action()
            result.onsuccess?.()
          } catch (error) {
            aborted = true
            tx.error = error
            tx.onabort?.()
          }
          if (!--active && !aborted) {
            stored = next
            tx.oncomplete?.()
          }
        })
        return result
      }
      tx.objectStore = () => ({
        get: () => request(() => structuredClone(stored)),
        put: (value) =>
          request(() => {
            if (failWrite) throw new Error('quota')
            next = structuredClone(value)
          })
      })
      return tx
    }
  }
  vi.stubGlobal('indexedDB', {
    open() {
      const request = { result: db }
      queueMicrotask(() => request.onsuccess())
      return request
    }
  })
})
afterEach(() => {
  vi.unstubAllGlobals()
  vi.restoreAllMocks()
})
function record(savedAt = 1) {
  return {
    savedAt,
    result: {
      success: true,
      timelineData: { operatorTracks: [{ operatorName: '芬', workHours: 42 }] }
    },
    input: { plan: { conf: { rest: '芬' } }, settings: { sampleDays: 28 } },
    snapshot: {
      plan: { conf: { rest: '芬' } },
      image: new Blob(['original image']),
      theme: 'light'
    },
    progressLog: ['完成'],
    exportName: '排班'
  }
}
it('stores the image, inputs and result together and detaches later mutations', async () => {
  const data = record()
  const saving = saveIncomeArchive(data)
  data.input.settings.sampleDays = 1
  data.result.timelineData.operatorTracks[0].workHours = 100
  await saving
  const loaded = await loadIncomeArchive()
  expect(loaded.input.settings.sampleDays).toBe(28)
  expect(loaded.result.timelineData.operatorTracks[0].workHours).toBe(42)
  expect(await loaded.snapshot.image.text()).toBe('original image')
  expect(loaded.snapshot.plan).toEqual(loaded.input.plan)
})
it('retains the previous result if a replacement transaction fails', async () => {
  await saveIncomeArchive(record(1))
  failWrite = true
  await expect(saveIncomeArchive(record(2))).rejects.toThrow('quota')
  expect((await loadIncomeArchive()).savedAt).toBe(1)
})
it('saves shared report graphs and nested Vue state without JSON string expansion', async () => {
  const data = record()
  let shared = { roomId: 'room_1_1' }
  for (let i = 0; i < 30; i++) shared = { left: shared, right: shared }
  data.result.simulationReport = shared
  data.result.timelineData.report = shared
  data.input.settings = reactive({ sampleDays: 28, inventory: reactive({ gold: 42 }) })
  const stringify = vi.spyOn(JSON, 'stringify').mockImplementation(() => {
    throw new RangeError('Invalid string length')
  })
  const saving = saveIncomeArchive(data)
  data.input.settings.inventory.gold = 99
  await saving
  const loaded = await loadIncomeArchive()
  expect(stringify).not.toHaveBeenCalled()
  expect(loaded.result.simulationReport).toBe(loaded.result.timelineData.report)
  expect(loaded.result.simulationReport.left).toBe(loaded.result.simulationReport.right)
  expect(loaded.input.settings.inventory.gold).toBe(42)
  expect(await loaded.snapshot.image.text()).toBe('original image')
})
it('rejects a stale tab save while allowing renaming the current result', async () => {
  await saveIncomeArchive(record(2))
  await saveIncomeArchive({ ...record(1), exportName: '旧窗口' })
  expect((await loadIncomeArchive()).savedAt).toBe(2)
  await saveIncomeArchive({ ...record(2), exportName: '新名称' })
  expect((await loadIncomeArchive()).exportName).toBe('新名称')
})
it('returns no result for empty storage and reports incompatible data', async () => {
  expect(await loadIncomeArchive()).toBeNull()
  stored = { ...record(), version: 99 }
  await expect(loadIncomeArchive()).rejects.toThrow('格式不兼容')
})
it('preserves signed valuation without changing the completed product quantities or legacy scores', async () => {
  const data = record()
  data.result.summary = {
    totalScore82: 75,
    exp: 1000,
    valuation: {
      completedScore: { daily: 100, total: 2800 },
      opening: { amounts: { exp: 500 }, score: { daily: 50, total: 1400 } },
      closing: { amounts: { exp: 250 }, score: { daily: 25, total: 700 } },
      adjustment: { amounts: { exp: -250 }, score: { daily: -25, total: -700 } }
    }
  }
  await saveIncomeArchive(data)
  const restored = await loadIncomeArchive()
  expect(restored.result.summary).toEqual(data.result.summary)
  delete restored.result.summary.valuation
  await saveIncomeArchive(restored)
  expect((await loadIncomeArchive()).result.summary).toEqual({ totalScore82: 75, exp: 1000 })
})
