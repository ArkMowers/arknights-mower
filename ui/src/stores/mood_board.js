import { defineStore } from 'pinia'
import { ref } from 'vue'
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
  const views = ref([])

  function storage() {
    try {
      return window.localStorage
    } catch {
      return null
    }
  }

  function load() {
    if (initialized.value) return
    initialized.value = true
    groupOrder.value = readMoodPreferences(storage()).groupOrder
    views.value = readMoodViews(storage())
  }

  function persistOrder() {
    // Old pinned rules have been retired from the main UI; migrate the former
    // manual order but do not let old pinned values silently override dragging.
    saveMoodPreferences(storage(), normalizeMoodPreferences({ groupOrder: groupOrder.value }))
  }

  function reorder(visibleGroups, sourceKey, targetKey) {
    const keys = visibleGroups.map((group) => group.boardKey || group.groupName)
    if (sourceKey === targetKey || !keys.includes(sourceKey) || !keys.includes(targetKey)) {
      return false
    }
    groupOrder.value = orderedBoardNames(groupOrder.value, keys, sourceKey, targetKey)
    persistOrder()
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
      persistOrder()
    }
    saveMoodViews(storage(), next)
    return identifier
  }

  function removeView(id) {
    if (!views.value.some((view) => view.id === id)) return
    views.value = views.value.filter((view) => view.id !== id)
    groupOrder.value = groupOrder.value.filter((name) => name !== 'custom:' + id)
    saveMoodViews(storage(), views.value)
    persistOrder()
  }

  return { initialized, groupOrder, views, load, reorder, upsertView, removeView }
})
