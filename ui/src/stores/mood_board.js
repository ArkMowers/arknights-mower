import { i18n } from '@/i18n'
import { defineStore } from 'pinia'
import { ref } from 'vue'
import axios from 'axios'
import {
  normalizeMoodPreferences,
  readMoodPreferences,
  saveMoodPreferences
} from '@/utils/mood_order'
import {
  MAX_MOOD_VIEWS,
  normalizeMoodViews,
  orderedBoardNames,
  readMoodViews,
  saveMoodViews
} from '@/utils/mood_observation'

export const useMoodBoardStore = defineStore('mood-board', () => {
  const initialized = ref(false)
  const groupOrder = ref([])
  const hiddenLines = ref({})
  const hiddenGroups = ref([])
  const defaultOperators = ref({})
  const views = ref([])
  const saveError = ref('')
  const url = `${import.meta.env.VITE_HTTP_URL || ''}/ui-state/mood-board`
  const requestOptions = { timeout: 5000 }
  const editedFields = new Set()
  const pendingFields = new Set()
  let loadRequest
  let saveRequest = Promise.resolve()

  function storage() {
    try {
      return window.localStorage
    } catch {
      return null
    }
  }

  const fields = { groupOrder, hiddenLines, hiddenGroups, defaultOperators, views }

  function snapshot() {
    return JSON.parse(
      JSON.stringify(
        Object.fromEntries(Object.entries(fields).map(([key, field]) => [key, field.value]))
      )
    )
  }

  function saveLocal() {
    // Old pinned rules have been retired from the main UI; migrate the former
    // manual order but do not let old pinned values silently override dragging.
    saveMoodPreferences(storage(), snapshot())
    saveMoodViews(storage(), views.value)
  }

  function apply(preferences, preserveEdits = false) {
    const normalized = {
      ...normalizeMoodPreferences(preferences),
      views: normalizeMoodViews(preferences?.views)
    }
    for (const [key, field] of Object.entries(fields)) {
      if (!preserveEdits || !editedFields.has(key)) field.value = normalized[key]
    }
  }

  function load() {
    if (loadRequest) return loadRequest
    apply({ ...readMoodPreferences(storage()), views: readMoodViews(storage()) })
    loadRequest = (async () => {
      try {
        let { data } = await axios.get(url, requestOptions)
        if (!data || !Object.hasOwn(data, 'preferences')) throw new Error('Invalid preferences')
        if (data.preferences === null) {
          data = (await axios.post(url, snapshot(), requestOptions)).data
        }
        if (!data?.preferences) throw new Error('Invalid preferences')
        apply(data.preferences, true)
        saveLocal()
        saveError.value = ''
        return true
      } catch {
        loadRequest = undefined
        saveError.value = i18n.global.t('reports.moralePreferencesFailed')
        return false
      } finally {
        initialized.value = true
      }
    })()
    return loadRequest
  }

  function persistPreferences(...keys) {
    keys.forEach((key) => {
      editedFields.add(key)
      pendingFields.add(key)
    })
    saveLocal()
    saveRequest = saveRequest.then(async () => {
      if (!(await load())) return
      const current = snapshot()
      const patch = Object.fromEntries([...pendingFields].map((key) => [key, current[key]]))
      if (!Object.keys(patch).length) return
      try {
        await axios.patch(url, patch, requestOptions)
        for (const [key, value] of Object.entries(patch)) {
          if (JSON.stringify(fields[key].value) === JSON.stringify(value)) pendingFields.delete(key)
        }
        saveError.value = ''
      } catch {
        saveError.value = i18n.global.t('reports.moralePreferencesFailed')
      }
    })
  }

  async function flushSaves() {
    await load()
    let pending
    do {
      pending = saveRequest
      await pending
    } while (pending !== saveRequest)
  }

  function setHiddenLines(key, names) {
    hiddenLines.value = normalizeMoodPreferences({
      hiddenLines: { ...hiddenLines.value, [key]: names }
    }).hiddenLines
    persistPreferences('hiddenLines')
  }

  function hideGroup(key) {
    hiddenGroups.value = [...new Set([...hiddenGroups.value, key])]
    persistPreferences('hiddenGroups')
  }

  function restoreGroups() {
    hiddenGroups.value = []
    persistPreferences('hiddenGroups')
  }

  function setDefaultOperator(key, name) {
    defaultOperators.value = normalizeMoodPreferences({
      defaultOperators: { ...defaultOperators.value, [key]: name }
    }).defaultOperators
    persistPreferences('defaultOperators')
  }

  function reorder(visibleGroups, sourceKey, targetKey) {
    const keys = visibleGroups.map((group) => group.boardKey || group.groupName)
    if (sourceKey === targetKey || !keys.includes(sourceKey) || !keys.includes(targetKey)) {
      return false
    }
    groupOrder.value = orderedBoardNames(groupOrder.value, keys, sourceKey, targetKey)
    persistPreferences('groupOrder')
    return true
  }

  function upsertView(data, id) {
    const name = typeof data?.name === 'string' ? data.name.trim() : ''
    const operators = Array.isArray(data?.operators) ? data.operators : []
    if (!name || name.length > 30 || operators.length > 16) return false
    if (views.value.some((view) => view.name === name && view.id !== id)) return false
    const identifier =
      id ||
      (typeof crypto !== 'undefined' && crypto.randomUUID
        ? crypto.randomUUID()
        : 'view-' + Date.now().toString(36) + Math.random().toString(36).slice(2, 8))
    if (!id && views.value.length >= MAX_MOOD_VIEWS) return false
    const next = normalizeMoodViews([
      ...views.value.filter((view) => view.id !== identifier),
      { id: identifier, name, operators }
    ])
    if (next.length !== views.value.length + (id ? 0 : 1)) return false
    views.value = next
    if (!id) {
      groupOrder.value = ['custom:' + identifier, ...groupOrder.value]
    }
    persistPreferences(...(id ? ['views'] : ['views', 'groupOrder']))
    return identifier
  }

  function removeView(id) {
    if (!views.value.some((view) => view.id === id)) return
    views.value = views.value.filter((view) => view.id !== id)
    groupOrder.value = groupOrder.value.filter((name) => name !== 'custom:' + id)
    hiddenGroups.value = hiddenGroups.value.filter((name) => name !== 'custom:' + id)
    const remaining = { ...hiddenLines.value }
    delete remaining['custom:' + id]
    hiddenLines.value = remaining
    const defaults = { ...defaultOperators.value }
    delete defaults['custom:' + id]
    defaultOperators.value = defaults
    persistPreferences('views', 'groupOrder', 'hiddenLines', 'hiddenGroups', 'defaultOperators')
  }

  return {
    initialized,
    groupOrder,
    hiddenLines,
    hiddenGroups,
    defaultOperators,
    views,
    saveError,
    load,
    flushSaves,
    reorder,
    setHiddenLines,
    hideGroup,
    restoreGroups,
    setDefaultOperator,
    upsertView,
    removeView
  }
})
