import { toRaw } from 'vue'

const DATABASE = 'mower-income-results'
const STORE = 'results'
const KEY = 'latest'
const VERSION = 1
let pending = Promise.resolve()

function openDatabase() {
  return new Promise((resolve, reject) => {
    const request = indexedDB.open(DATABASE, 1)
    let settled = false
    const timer = setTimeout(() => fail(new Error('收益记录存储等待超时')), 5000)
    function fail(error) {
      if (settled) return
      settled = true
      clearTimeout(timer)
      reject(error)
    }
    request.onupgradeneeded = () => {
      if (!request.result.objectStoreNames.contains(STORE)) request.result.createObjectStore(STORE)
    }
    request.onerror = () => fail(request.error)
    request.onblocked = () => fail(new Error('收益记录存储被其他窗口占用'))
    request.onsuccess = () => {
      if (settled) return request.result.close()
      settled = true
      clearTimeout(timer)
      resolve(request.result)
    }
  })
}
function access(mode, action) {
  const task = pending
    .catch(() => {})
    .then(async () => {
      const db = await openDatabase()
      try {
        return await new Promise((resolve, reject) => {
          const tx = db.transaction(STORE, mode)
          const request = action(tx.objectStore(STORE))
          tx.oncomplete = () => resolve(request.result)
          tx.onabort = () => reject(tx.error || new Error('收益记录存储已中止'))
          tx.onerror = () => reject(tx.error)
        })
      } finally {
        db.close()
      }
    })
  pending = task
  return task
}
export async function loadIncomeArchive() {
  const record = await access('readonly', (store) => store.get(KEY))
  if (!record) return null
  if (
    record.version !== VERSION ||
    !record.result?.success ||
    !record.input?.plan ||
    !record.input?.settings ||
    !(record.snapshot?.image instanceof Blob) ||
    !record.snapshot?.plan ||
    !Array.isArray(record.progressLog)
  )
    throw new Error('已保存的收益记录格式不兼容')
  return record
}
export function saveIncomeArchive(record) {
  // IndexedDB commits the result and its original image/plan in one transaction.
  const plain = detachArchive({ ...record, version: VERSION })
  return access('readwrite', (store) => {
    const current = store.get(KEY)
    current.onsuccess = () => {
      // Closing an older result in another tab must not replace a newer completed run.
      if (current.result?.savedAt > plain.savedAt) return
      store.put(plain, KEY)
    }
    return current
  })
}
// Remove nested Vue proxies without expanding shared simulation data into a JSON string.
function detachArchive(value, seen = new WeakMap()) {
  if (value === null || typeof value !== 'object') return value
  const raw = toRaw(value)
  if (raw instanceof Blob) return raw
  if (seen.has(raw)) return seen.get(raw)
  const copy = Array.isArray(raw) ? [] : {}
  seen.set(raw, copy)
  for (const key of Object.keys(raw)) copy[key] = detachArchive(raw[key], seen)
  return copy
}
