import { defineStore } from 'pinia'
import { computed, ref } from 'vue'
import axios from 'axios'
import {
  DEFAULT_BASELINE_CONFIG,
  DEFAULT_VIEW_PREFS,
  loadBaselineConfig,
  loadFavorites,
  loadViewPrefs,
  normalizeBaselineConfig,
  normalizeFavorites,
  normalizeViewPrefs
} from '@/utils/depot_inventory'

const endpoint = `${import.meta.env.VITE_HTTP_URL || ''}/gui/depot`
const groups = ['favorites', 'view', 'baseline']
const clone = (value) => JSON.parse(JSON.stringify(value))
const isObject = (value) => value && typeof value === 'object' && !Array.isArray(value)

function normalizeGroup(key, value) {
  if (key === 'favorites') return normalizeFavorites(value)
  if (key === 'view') return normalizeViewPrefs(value)
  return normalizeBaselineConfig(value)
}

function parsePreferences(value) {
  if (!isObject(value) || !Array.isArray(value.favorites)) throw new Error()
  if (!isObject(value.view) || !isObject(value.baseline)) throw new Error()
  const normalized = Object.fromEntries(groups.map((key) => [key, normalizeGroup(key, value[key])]))
  for (const key of groups) {
    if (key === 'favorites') {
      if (JSON.stringify(value[key]) !== JSON.stringify(normalized[key])) throw new Error()
    } else {
      for (const [field, item] of Object.entries(normalized[key])) {
        if (JSON.stringify(value[key][field]) !== JSON.stringify(item)) throw new Error()
      }
    }
  }
  return normalized
}

function legacyPreferences() {
  let storage = null
  try {
    storage = typeof localStorage === 'undefined' ? null : localStorage
  } catch {
    // 浏览器禁止访问本地存储时，从默认偏好开始。
  }
  return {
    favorites: normalizeFavorites(loadFavorites(storage)),
    view: loadViewPrefs(storage),
    baseline: loadBaselineConfig(storage)
  }
}

export const useDepotPreferencesStore = defineStore('depotPreferences', () => {
  const favorites = ref([])
  const view = ref({ ...DEFAULT_VIEW_PREFS })
  const baseline = ref({ ...DEFAULT_BASELINE_CONFIG })
  const loaded = ref(false)
  const loading = ref(false)
  const saving = ref(false)
  const error = ref('')
  const disabled = computed(() => !loaded.value || loading.value)
  const state = { favorites, view, baseline }
  let loadRequest = null
  let saveRequest = null
  let pending = {}

  function apply(preferences, except = {}) {
    for (const key of groups) {
      if (!(key in except)) state[key].value = clone(preferences[key])
    }
  }

  function load() {
    if (loadRequest) return loadRequest
    if (loaded.value) return Promise.resolve(true)
    loading.value = true
    error.value = ''
    let migrating = false
    loadRequest = (async () => {
      try {
        let { data } = await axios.get(endpoint, { timeout: 5000 })
        if (data?.depot === null) {
          migrating = true
          ;({ data } = await axios.put(
            endpoint,
            { depot: legacyPreferences(), migrate: true },
            { timeout: 5000 }
          ))
        }
        apply(parsePreferences(data?.depot))
        loaded.value = true
        return true
      } catch {
        error.value = migrating ? '仓库偏好迁移失败，请重试。' : '仓库偏好读取失败，请重试。'
        return false
      } finally {
        loading.value = false
      }
    })().finally(() => {
      loadRequest = null
    })
    return loadRequest
  }

  function saveRemote() {
    if (saveRequest) return saveRequest
    if (!Object.keys(pending).length) return Promise.resolve(true)
    saving.value = true
    error.value = ''
    saveRequest = (async () => {
      while (Object.keys(pending).length) {
        const changes = pending
        pending = {}
        try {
          const { data } = await axios.put(endpoint, { depot: changes }, { timeout: 5000 })
          apply(parsePreferences(data?.depot), pending)
        } catch {
          pending = { ...changes, ...pending }
          error.value = '仓库偏好保存失败，当前修改尚未保存，请重试。'
          return false
        }
      }
      return true
    })().finally(() => {
      saving.value = false
      saveRequest = null
    })
    return saveRequest
  }

  function update(changes) {
    if (
      disabled.value ||
      !isObject(changes) ||
      !Object.keys(changes).length ||
      Object.keys(changes).some((key) => !groups.includes(key))
    )
      return Promise.resolve(false)
    const values = Object.fromEntries(
      Object.entries(changes).map(([key, value]) => [key, clone(normalizeGroup(key, value))])
    )
    for (const [key, value] of Object.entries(values)) state[key].value = clone(value)
    pending = { ...pending, ...values }
    return error.value ? Promise.resolve(false) : saveRemote()
  }

  function toggleFavorite(name) {
    if (typeof name !== 'string' || !name) return Promise.resolve(false)
    return update({
      favorites: favorites.value.includes(name)
        ? favorites.value.filter((item) => item !== name)
        : [...favorites.value, name]
    })
  }

  function retry() {
    return loaded.value ? saveRemote() : load()
  }

  return {
    favorites,
    view,
    baseline,
    loaded,
    loading,
    saving,
    error,
    disabled,
    load,
    update,
    toggleFavorite,
    retry
  }
})
