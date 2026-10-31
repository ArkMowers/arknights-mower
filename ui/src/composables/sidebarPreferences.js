import { computed, readonly, ref } from 'vue'
import axios from 'axios'
import { navigationSections, sidebarNavigationItems } from '@/navigation'

export const SIDEBAR_STORAGE_KEY = 'mower.sidebar-preferences.v1'
const MAX_GROUPS = 20
const REQUEST_TIMEOUT = 10000
const fixedItemKeys = new Set(
  sidebarNavigationItems.filter((item) => item.footer).map((item) => item.key)
)
const editableItems = sidebarNavigationItems.filter((item) => !item.footer)
const editableKeys = new Set(editableItems.map((item) => item.key))
const MAX_PLACEMENTS = editableItems.length * (MAX_GROUPS + 2)

const defaultGroups = navigationSections
  .filter((section) => section.items.some((item) => editableKeys.has(item.key)))
  .map((section) => ({ key: section.key, title: section.title || '', collapsed: false }))
const dailyGroup = defaultGroups.find((group) => group.key === 'daily')
const defaultPlacements = navigationSections.flatMap((section) =>
  section.items
    .filter((item) => editableKeys.has(item.key))
    .map((item) => ({
      key: item.key,
      group: item.footer ? 'footer' : section.key,
      visible: true,
      pinned: false
    }))
)
defaultPlacements.push({ key: 'chat', group: 'footer', visible: true, pinned: false })
defaultPlacements.sort(
  (left, right) => Number(fixedItemKeys.has(left.key)) - Number(fixedItemKeys.has(right.key))
)

const validKey = (key) => typeof key === 'string' && /^[a-zA-Z0-9_-]{1,100}$/.test(key)
const cleanTitle = (title) => (typeof title === 'string' ? title.trim().slice(0, 80) : '')
let idSequence = 0

function newKey(prefix) {
  return `${prefix}-${Date.now().toString(36)}-${(++idSequence).toString(36)}`
}

function defaults() {
  return {
    version: 3,
    knownKeys: [...editableKeys],
    groups: defaultGroups.map((group) => ({ ...group })),
    placements: defaultPlacements.map((item) => ({ ...item, id: item.key }))
  }
}

function normalize(saved) {
  if (!saved || ![1, 2, 3].includes(saved.version) || Array.isArray(saved)) return defaults()
  const legacy = saved.version === 1
  const knownKeys = new Set(Array.isArray(saved.knownKeys) ? saved.knownKeys : editableKeys)

  const groups = []
  const groupKeys = new Set()
  const savedGroups = Array.isArray(saved.groups) ? saved.groups : defaultGroups
  for (const group of savedGroups.slice(0, MAX_GROUPS)) {
    if (!validKey(group?.key) || ['footer', 'pinned', 'ungrouped'].includes(group.key)) continue
    if (groupKeys.has(group.key)) continue
    const savedTitle = cleanTitle(group.title)
    const title =
      saved.version < 3 && group.key === 'daily' && savedTitle === '日常任务'
        ? dailyGroup.title
        : savedTitle || (group.key === 'daily' ? dailyGroup.title : '')
    if (!title) continue
    groups.push({ key: group.key, title, collapsed: group.collapsed === true })
    groupKeys.add(group.key)
  }
  const placements = []
  const placedKeys = new Set()
  const placedIds = new Set(fixedItemKeys)
  const occupied = new Set()
  for (const placement of Array.isArray(saved.placements) ? saved.placements : []) {
    if (!placement || !editableKeys.has(placement.key)) continue
    const id = legacy ? placement.key : placement.id
    if (!validKey(id) || placedIds.has(id)) continue
    if (legacy && placedKeys.has(placement.key)) continue
    const fallback = defaultPlacements.find((item) => item.key === placement.key)?.group
    const group =
      placement.group === 'ungrouped' || groupKeys.has(placement.group)
        ? placement.group
        : groupKeys.has(fallback)
          ? fallback
          : 'ungrouped'
    const pinned = placement.pinned === true
    const area = `${pinned ? 'pinned' : group}:${placement.key}`
    if (occupied.has(area) || placements.length >= MAX_PLACEMENTS) continue
    placements.push({
      id,
      key: placement.key,
      group,
      visible: placement.visible !== false,
      pinned
    })
    placedKeys.add(placement.key)
    placedIds.add(id)
    occupied.add(area)
  }
  for (const item of defaultPlacements) {
    if (fixedItemKeys.has(item.key)) {
      placements.push({ ...item, id: item.key })
      continue
    }
    if (placedKeys.has(item.key) || (!legacy && knownKeys.has(item.key))) continue
    const id = placedIds.has(item.key) ? newKey('entry') : item.key
    const logPlacements =
      item.key === 'task-settings' && !groupKeys.has(item.group)
        ? placements.filter((entry) => entry.key === 'log' && !entry.pinned)
        : []
    const group = groupKeys.has(item.group)
      ? item.group
      : logPlacements.length === 1
        ? logPlacements[0].group
        : 'ungrouped'
    const precedingKeys = defaultPlacements
      .slice(0, defaultPlacements.indexOf(item))
      .filter((entry) => entry.group === item.group)
      .map((entry) => entry.key)
      .reverse()
    const previous = precedingKeys
      .map((key) =>
        placements.findIndex((entry) => entry.key === key && entry.group === group && !entry.pinned)
      )
      .find((index) => index >= 0)
    placements.splice(previous === undefined ? placements.length : previous + 1, 0, {
      id,
      key: item.key,
      group,
      visible: true,
      pinned: false
    })
    placedKeys.add(item.key)
    placedIds.add(id)
  }
  return { version: 3, knownKeys: [...editableKeys], groups, placements }
}

function browserStorage() {
  try {
    return typeof window === 'undefined' ? null : window.localStorage
  } catch {
    return null
  }
}

export function createSidebarPreferences({
  storage = browserStorage(),
  key = SIDEBAR_STORAGE_KEY,
  transport = null,
  endpoint = `${import.meta.env.VITE_HTTP_URL || ''}/gui/sidebar`
} = {}) {
  const persistenceError = ref(false)
  const initialized = ref(!transport)
  let loading = null
  let pendingSave = null
  let saving = null

  function readLocal() {
    try {
      const saved = storage?.getItem(key)
      if (!saved) return null
      const parsed = JSON.parse(saved)
      return parsed && [1, 2, 3].includes(parsed.version) ? normalize(parsed) : null
    } catch {
      persistenceError.value = true
      return null
    }
  }
  const state = ref(transport ? defaults() : readLocal() || defaults())
  const catalog = computed(() => editableItems)
  const itemMap = computed(() => new Map(sidebarNavigationItems.map((item) => [item.key, item])))
  const itemsWhere = (predicate) =>
    state.value.placements
      .filter((item) => item.visible && predicate(item))
      .map((item) => ({ ...itemMap.value.get(item.key), id: item.id }))
      .filter(Boolean)
  const visibleSections = computed(() =>
    state.value.groups.map((group) => ({
      ...group,
      items: itemsWhere((item) => item.group === group.key && !item.pinned)
    }))
  )
  const pinnedItems = computed(() => itemsWhere((item) => item.pinned))
  const standaloneItems = computed(() =>
    itemsWhere((item) => item.group === 'ungrouped' && !item.pinned)
  )
  const footerItems = computed(() =>
    defaultPlacements
      .filter((item) => fixedItemKeys.has(item.key))
      .map((item) => ({ ...itemMap.value.get(item.key), id: item.key }))
  )

  function saveRemote() {
    if (!initialized.value) return
    pendingSave = JSON.stringify(state.value)
    if (saving) return
    saving = (async () => {
      while (pendingSave !== null) {
        const snapshot = pendingSave
        pendingSave = null
        try {
          await transport.put(
            endpoint,
            { sidebar: JSON.parse(snapshot) },
            { timeout: REQUEST_TIMEOUT }
          )
          persistenceError.value = false
        } catch {
          persistenceError.value = true
        }
      }
    })().finally(() => {
      saving = null
      if (pendingSave !== null) saveRemote()
    })
  }

  async function initialize() {
    if (initialized.value) return true
    if (loading) return loading
    loading = (async () => {
      try {
        const { data } = await transport.get(endpoint, { timeout: REQUEST_TIMEOUT })
        if (!data || !Object.hasOwn(data, 'sidebar')) throw new Error('Invalid sidebar response')
        if (data.sidebar !== null && (!data.sidebar || ![1, 2, 3].includes(data.sidebar.version)))
          throw new Error('Unsupported sidebar layout')
        const migrated = data.sidebar === null ? readLocal() : null
        state.value = normalize(data.sidebar ?? migrated)
        initialized.value = true
        persistenceError.value = false
        if (migrated || (data.sidebar !== null && data.sidebar.version !== 3)) saveRemote()
        return true
      } catch {
        persistenceError.value = true
        return false
      }
    })().finally(() => {
      loading = null
    })
    return loading
  }

  async function flush() {
    if (loading) await loading
    while (saving) await saving
  }

  async function retrySave() {
    if (!initialized.value) return initialize()
    save()
    await flush()
    return !persistenceError.value
  }

  function save() {
    if (transport) {
      saveRemote()
      return
    }
    try {
      if (!storage) throw new Error('Storage unavailable')
      storage.setItem(key, JSON.stringify(state.value))
      persistenceError.value = false
    } catch {
      persistenceError.value = true
    }
  }

  function updateItem(itemId, changes) {
    if (!initialized.value) return false
    const placement = state.value.placements.find((item) => item.id === itemId)
    if (!placement || fixedItemKeys.has(placement.key)) return false
    Object.assign(placement, changes)
    save()
    return true
  }

  function reorderItem(itemId, beforeId = null) {
    if (!initialized.value) return false
    if (fixedItemKeys.has(itemId) || fixedItemKeys.has(beforeId)) return false
    const placements = state.value.placements
    const index = placements.findIndex((item) => item.id === itemId)
    if (index < 0 || itemId === beforeId) return false
    const [item] = placements.splice(index, 1)
    const target = placements.findIndex((entry) => entry.id === beforeId)
    const fixedStart = placements.findIndex((entry) => fixedItemKeys.has(entry.key))
    placements.splice(
      target < 0 ? (fixedStart < 0 ? placements.length : fixedStart) : target,
      0,
      item
    )
    save()
    return true
  }

  function moveItem(itemId, groupKey, beforeId = null) {
    if (!initialized.value) return false
    if (fixedItemKeys.has(itemId) || fixedItemKeys.has(beforeId) || groupKey === 'footer')
      return false
    const placement = state.value.placements.find((item) => item.id === itemId)
    if (!placement || itemId === beforeId) return false
    if (
      state.value.placements.some(
        (item) =>
          item.id !== itemId &&
          item.key === placement.key &&
          (groupKey === 'pinned' ? item.pinned : item.group === groupKey && !item.pinned)
      )
    )
      return false
    if (groupKey === 'pinned') {
      placement.pinned = true
    } else {
      if (groupKey !== 'ungrouped' && !state.value.groups.some((group) => group.key === groupKey)) {
        return false
      }
      placement.group = groupKey
      placement.pinned = false
    }
    return reorderItem(itemId, beforeId)
  }

  function addEntry(itemKey, groupKey) {
    if (!initialized.value) return false
    if (fixedItemKeys.has(itemKey) || !itemMap.value.has(itemKey)) return false
    if (
      !['pinned', 'ungrouped'].includes(groupKey) &&
      !state.value.groups.some((group) => group.key === groupKey)
    ) {
      return false
    }
    const existing = state.value.placements.find(
      (item) =>
        item.key === itemKey &&
        (groupKey === 'pinned' ? item.pinned : item.group === groupKey && !item.pinned)
    )
    if (existing) {
      if (!existing.visible) return updateItem(existing.id, { visible: true })
      return true
    }
    if (
      state.value.placements.filter((item) => !fixedItemKeys.has(item.key)).length >= MAX_PLACEMENTS
    )
      return false
    const fallback = defaultPlacements.find((item) => item.key === itemKey).group
    const group =
      groupKey === 'pinned'
        ? state.value.groups.some((item) => item.key === fallback)
          ? fallback
          : 'ungrouped'
        : groupKey
    const id = newKey('entry')
    const fixedStart = state.value.placements.findIndex((item) => fixedItemKeys.has(item.key))
    state.value.placements.splice(fixedStart < 0 ? state.value.placements.length : fixedStart, 0, {
      id,
      key: itemKey,
      group,
      visible: true,
      pinned: groupKey === 'pinned'
    })
    save()
    return true
  }

  function removeEntry(itemId) {
    if (!initialized.value) return false
    const index = state.value.placements.findIndex((item) => item.id === itemId)
    if (index < 0 || fixedItemKeys.has(state.value.placements[index].key)) return false
    state.value.placements.splice(index, 1)
    save()
    return true
  }

  function setPinned(itemId, pinned) {
    if (!initialized.value) return false
    const placement = state.value.placements.find((item) => item.id === itemId)
    if (!placement || fixedItemKeys.has(placement.key)) return false
    if (placement.pinned === Boolean(pinned)) return true
    if (
      state.value.placements.some(
        (item) =>
          item.id !== itemId &&
          item.key === placement.key &&
          (pinned ? item.pinned : item.group === placement.group && !item.pinned)
      )
    )
      return false
    return updateItem(itemId, { pinned: Boolean(pinned) })
  }

  function toggleGroup(groupKey) {
    if (!initialized.value) return false
    const group = state.value.groups.find((entry) => entry.key === groupKey)
    if (!group) return false
    group.collapsed = !group.collapsed
    save()
    return true
  }

  function addGroup(title) {
    if (!initialized.value) return null
    title = cleanTitle(title)
    if (!title || state.value.groups.length >= MAX_GROUPS) return null
    const groupKey = newKey('group')
    state.value.groups.push({ key: groupKey, title, collapsed: false })
    save()
    return groupKey
  }

  function renameGroup(groupKey, title) {
    if (!initialized.value) return false
    title = cleanTitle(title)
    const group = state.value.groups.find((entry) => entry.key === groupKey)
    if (!group || !title) return false
    group.title = title
    save()
    return true
  }

  function removeGroup(groupKey) {
    if (!initialized.value) return false
    const index = state.value.groups.findIndex((group) => group.key === groupKey)
    if (index < 0) return false
    state.value.groups.splice(index, 1)
    const standaloneKeys = new Set(
      state.value.placements
        .filter((item) => item.group === 'ungrouped' && !item.pinned)
        .map((item) => item.key)
    )
    state.value.placements = state.value.placements.filter((item) => {
      if (item.group !== groupKey) return true
      if (!item.pinned && standaloneKeys.has(item.key)) return false
      item.group = 'ungrouped'
      if (!item.pinned) standaloneKeys.add(item.key)
      return true
    })
    save()
    return true
  }

  function moveGroup(groupKey, beforeKey = null) {
    if (!initialized.value) return false
    const groups = state.value.groups
    const index = groups.findIndex((group) => group.key === groupKey)
    if (index < 0 || groupKey === beforeKey) return false
    const [group] = groups.splice(index, 1)
    const target = groups.findIndex((entry) => entry.key === beforeKey)
    groups.splice(target < 0 ? groups.length : target, 0, group)
    save()
    return true
  }

  function reset() {
    if (!initialized.value) return false
    state.value = defaults()
    save()
    return true
  }

  return {
    state: readonly(state),
    catalog,
    visibleSections,
    pinnedItems,
    standaloneItems,
    footerItems,
    initialized: readonly(initialized),
    persistenceError: readonly(persistenceError),
    initialize,
    flush,
    retrySave,
    toggleGroup,
    setVisible: (itemId, visible) => updateItem(itemId, { visible: Boolean(visible) }),
    setPinned,
    addEntry,
    removeEntry,
    moveItem,
    reorderItem,
    addGroup,
    renameGroup,
    removeGroup,
    moveGroup,
    reset
  }
}

let sharedPreferences

export function useSidebarPreferences() {
  sharedPreferences ??= createSidebarPreferences({ transport: axios })
  return sharedPreferences
}
