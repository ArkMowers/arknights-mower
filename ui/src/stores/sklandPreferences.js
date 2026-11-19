import { defineStore } from 'pinia'
import { computed, ref, shallowRef } from 'vue'
import axios from 'axios'

const endpoint = `${import.meta.env.VITE_HTTP_URL || ''}/gui/skland`
const requestOptions = { timeout: 5000 }
const rangeFields = ['statsPreset', 'statsRange']

export const DEFAULT_SKLAND_PREFERENCES = Object.freeze({
  account: null,
  game: null,
  detailView: 'day',
  statsAccount: null,
  statsGame: null,
  statsPreset: 'month',
  statsRange: null
})

function validDate(value) {
  if (typeof value !== 'string' || !/^\d{4}-\d{2}-\d{2}$/.test(value)) return false
  const date = new Date(`${value}T00:00:00Z`)
  return date.getUTCFullYear() > 0 && date.toISOString().slice(0, 10) === value
}

function readPreferences(value) {
  if (!value || typeof value !== 'object' || Array.isArray(value)) throw new TypeError()
  const { account, game, detailView, statsAccount, statsGame, statsPreset, statsRange } = value
  if (
    [account, game, statsAccount, statsGame].some(
      (option) =>
        option !== null && (typeof option !== 'string' || !option.trim() || option.length > 128)
    ) ||
    !['day', 'rewards', 'failures'].includes(detailView) ||
    !['month', 'week', '90', 'year', 'custom'].includes(statsPreset) ||
    (statsPreset === 'custom'
      ? !Array.isArray(statsRange) ||
        statsRange.length !== 2 ||
        !statsRange.every(validDate) ||
        statsRange[0] > statsRange[1] ||
        Date.parse(statsRange[1]) - Date.parse(statsRange[0]) > 365 * 86400000
      : statsRange !== null)
  ) {
    throw new TypeError()
  }
  return {
    account,
    game,
    detailView,
    statsAccount,
    statsGame,
    statsPreset,
    statsRange: statsRange && [...statsRange]
  }
}

export const useSklandPreferencesStore = defineStore('sklandPreferences', () => {
  const preferences = shallowRef({ ...DEFAULT_SKLAND_PREFERENCES })
  const loaded = ref(false)
  const loading = ref(false)
  const saving = ref(false)
  const error = ref('')
  const disabled = computed(() => !loaded.value)
  let loadRequest = null
  let saveRequest = null
  let pending = {}

  function load(client = axios) {
    if (loadRequest) return loadRequest
    if (loaded.value) return Promise.resolve(true)
    loading.value = true
    error.value = ''
    loadRequest = (async () => {
      try {
        const { data } = await client.get(endpoint, requestOptions)
        preferences.value = readPreferences(data?.skland)
        loaded.value = true
        return true
      } catch {
        error.value = '签到偏好读取失败，请重试。'
        return false
      }
    })().finally(() => {
      loadRequest = null
      loading.value = false
    })
    return loadRequest
  }

  function save(client) {
    if (saveRequest) return saveRequest
    if (!Object.keys(pending).length) return Promise.resolve(true)
    saving.value = true
    error.value = ''
    saveRequest = Promise.resolve().then(async () => {
      try {
        while (Object.keys(pending).length) {
          const changes = pending
          pending = {}
          try {
            const { data } = await client.put(endpoint, { skland: changes }, requestOptions)
            const saved = readPreferences(data?.skland)
            const confirmed = Object.entries(changes)
              .filter(([key]) => !Object.hasOwn(pending, key))
              .map(([key]) => [key, saved[key]])
            preferences.value = { ...preferences.value, ...Object.fromEntries(confirmed) }
          } catch {
            pending = { ...changes, ...pending }
            error.value = '签到偏好尚未保存，请重试。'
            return false
          }
        }
        return true
      } finally {
        saveRequest = null
        saving.value = false
      }
    })
    return saveRequest
  }

  function update(changes, client = axios) {
    if (disabled.value || !changes || typeof changes !== 'object') return Promise.resolve(false)
    const keys = Object.keys(changes)
    if (!keys.length || keys.some((key) => !Object.hasOwn(DEFAULT_SKLAND_PREFERENCES, key))) {
      return Promise.resolve(false)
    }
    let next
    try {
      next = readPreferences({ ...preferences.value, ...changes })
    } catch {
      return Promise.resolve(false)
    }
    const edited = keys.filter(
      (key) => JSON.stringify(next[key]) !== JSON.stringify(preferences.value[key])
    )
    if (!edited.length) return Promise.resolve(true)
    const fields = edited.some((key) => rangeFields.includes(key))
      ? [...new Set([...edited, ...rangeFields])]
      : edited
    pending = { ...pending, ...Object.fromEntries(fields.map((key) => [key, next[key]])) }
    preferences.value = next
    return error.value ? Promise.resolve(false) : save(client)
  }

  function retry(client = axios) {
    return loaded.value ? save(client) : load(client)
  }

  return { preferences, loaded, loading, saving, error, disabled, load, update, retry }
})
