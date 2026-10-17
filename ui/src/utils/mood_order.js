export const MOOD_ORDER_KEY = 'mowerMoodOrder:v1'
export const LEGACY_MOOD_GROUP_ORDER_KEY = 'reportDataOrder'

function uniqueNames(input) {
  if (!Array.isArray(input)) return []
  const seen = new Set()
  return input.filter((name) => {
    if (typeof name !== 'string' || !name.trim() || seen.has(name)) return false
    seen.add(name)
    return true
  })
}

export function normalizeMoodPreferences(input = {}) {
  return {
    groupOrder: uniqueNames(input?.groupOrder),
    pinnedGroups: uniqueNames(input?.pinnedGroups),
    pinnedOperators: uniqueNames(input?.pinnedOperators)
  }
}

function parseStoredJson(storage, key) {
  try {
    const raw = storage?.getItem(key)
    return raw ? JSON.parse(raw) : null
  } catch {
    return null
  }
}

export function readMoodPreferences(storage) {
  const oldGroupOrder = parseStoredJson(storage, LEGACY_MOOD_GROUP_ORDER_KEY)
  const saved = parseStoredJson(storage, MOOD_ORDER_KEY)
  return normalizeMoodPreferences({
    groupOrder: saved?.groupOrder ?? oldGroupOrder,
    pinnedGroups: saved?.pinnedGroups,
    pinnedOperators: saved?.pinnedOperators
  })
}

export function saveMoodPreferences(storage, input) {
  if (typeof storage?.setItem !== 'function') return false
  const prefs = normalizeMoodPreferences(input)
  try {
    storage?.setItem(MOOD_ORDER_KEY, JSON.stringify(prefs))
    // Keep the existing work/rest chart's ordering compatible with the previous version.
    storage?.setItem(LEGACY_MOOD_GROUP_ORDER_KEY, JSON.stringify(prefs.groupOrder))
    return true
  } catch {
    // Private browsing or disabled storage must not break report rendering.
    return false
  }
}

function ranking(names) {
  return new Map(uniqueNames(names).map((name, index) => [name, index]))
}

export function orderMoodDatasets(datasets, pinnedOperators) {
  const preferred = ranking(pinnedOperators)
  return [...(Array.isArray(datasets) ? datasets : [])].sort((a, b) => {
    const left = preferred.get(a?.label) ?? Infinity
    const right = preferred.get(b?.label) ?? Infinity
    return left - right
  })
}

export function orderMoodGroups(groups, input) {
  const prefs = normalizeMoodPreferences(input)
  const groupRanks = ranking(prefs.pinnedGroups)
  const operatorRanks = ranking(prefs.pinnedOperators)
  const fallbackRanks = ranking(prefs.groupOrder)

  function key(group, originalIndex) {
    const name = group?.groupName
    const groupPriority = groupRanks.get(name)
    if (groupPriority !== undefined) return [0, groupPriority, originalIndex]

    const datasets = group?.moodData?.datasets
    const operatorPriority = Array.isArray(datasets)
      ? Math.min(...datasets.map((dataset) => operatorRanks.get(dataset?.label) ?? Infinity))
      : Infinity
    if (Number.isFinite(operatorPriority)) return [1, operatorPriority, originalIndex]

    // Saved order only affects listed groups. Unlisted and newly added groups stay behind them.
    const fallback = fallbackRanks.get(name)
    return [2, fallback ?? Infinity, originalIndex]
  }

  return [...(Array.isArray(groups) ? groups : [])]
    .map((group, index) => ({ group, key: key(group, index) }))
    .sort((a, b) => {
      for (let i = 0; i < a.key.length; i++) {
        if (a.key[i] !== b.key[i]) return a.key[i] - b.key[i]
      }
      return 0
    })
    .map(({ group }) => ({
      ...group,
      moodData: group?.moodData
        ? {
            ...group.moodData,
            datasets: orderMoodDatasets(group.moodData.datasets, prefs.pinnedOperators)
          }
        : group?.moodData
    }))
}

export function reorderedGroupNames(visibleGroups, draggedName, targetName) {
  const names = uniqueNames(
    (Array.isArray(visibleGroups) ? visibleGroups : []).map((g) => g?.groupName)
  )
  const start = names.indexOf(draggedName)
  const target = names.indexOf(targetName)
  if (start < 0 || target < 0 || start === target) return names
  names.splice(target, 0, names.splice(start, 1)[0])
  return names
}
