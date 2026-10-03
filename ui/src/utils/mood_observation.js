export const MOOD_VIEWS_KEY = 'mowerMoodCustomViews:v1'
export const MAX_MOOD_VIEWS = 12
export const MAX_MOOD_VIEW_OPERATORS = 16

function cleanNames(input, max = MAX_MOOD_VIEW_OPERATORS) {
  if (!Array.isArray(input)) return []
  return [...new Set(input.filter((name) => typeof name === 'string').map((s) => s.trim()))]
    .filter((name) => name.length > 0 && name.length <= 40)
    .slice(0, max)
}

export function normalizeMoodViews(value) {
  if (!Array.isArray(value)) return []
  const ids = new Set()
  const views = []
  for (const view of value) {
    if (
      typeof view?.id !== 'string' ||
      !/^[\w-]{4,80}$/.test(view.id) ||
      ids.has(view.id) ||
      typeof view.name !== 'string' ||
      !view.name.trim() ||
      view.name.trim().length > 30
    ) {
      continue
    }
    ids.add(view.id)
    views.push({
      id: view.id,
      name: view.name.trim(),
      operators: cleanNames(view.operators)
    })
    if (views.length >= MAX_MOOD_VIEWS) break
  }
  return views
}

export function readMoodViews(storage) {
  try {
    return normalizeMoodViews(JSON.parse(storage?.getItem(MOOD_VIEWS_KEY) || '[]'))
  } catch {
    return []
  }
}

export function saveMoodViews(storage, views) {
  try {
    storage?.setItem(MOOD_VIEWS_KEY, JSON.stringify(normalizeMoodViews(views)))
    return typeof storage?.setItem === 'function'
  } catch {
    return false
  }
}

export function mergeOperatorCatalog(apiCatalog, groups) {
  const merged = new Map()
  for (const item of Array.isArray(apiCatalog) ? apiCatalog : []) {
    if (typeof item?.name === 'string' && item.name.trim()) {
      merged.set(item.name, {
        name: item.name,
        sampleCount: Number.isFinite(item.sampleCount) ? item.sampleCount : null,
        lastRecordedAt: item.lastRecordedAt || null
      })
    }
  }
  for (const group of Array.isArray(groups) ? groups : []) {
    for (const dataset of group.moodData?.datasets || []) {
      if (!merged.has(dataset.label)) {
        merged.set(dataset.label, {
          name: dataset.label,
          sampleCount: Array.isArray(dataset.data) ? dataset.data.length : 0,
          lastRecordedAt: dataset.data?.at(-1)?.x || null
        })
      }
    }
  }
  return [...merged.values()]
}

export function buildObservationGroups(views, reportGroups, series = []) {
  const byName = new Map()
  for (const group of Array.isArray(reportGroups) ? reportGroups : []) {
    for (const dataset of group.moodData?.datasets || []) {
      if (typeof dataset?.label === 'string' && !byName.has(dataset.label)) {
        byName.set(dataset.label, dataset)
      }
    }
  }
  for (const item of Array.isArray(series) ? series : []) {
    if (typeof item?.name !== 'string' || !Array.isArray(item.data)) continue
    // A database series supersedes the short, filtered default report series.
    byName.set(item.name, { label: item.name, data: item.data })
  }

  return normalizeMoodViews(views).map((view) => {
    const datasets = view.operators
      .filter((name) => (byName.get(name)?.data?.length || 0) > 0)
      .map((name) => ({ ...byName.get(name), label: name, data: [...byName.get(name).data] }))
    return {
      groupName: view.name,
      boardKey: 'custom:' + view.id,
      isCustom: true,
      customId: view.id,
      operators: view.operators,
      missing: view.operators.filter((name) => !(byName.get(name)?.data?.length > 0)),
      moodData: { datasets }
    }
  })
}

export function orderedBoardNames(existing, visible, dragged, target) {
  const all = [...new Set([...(Array.isArray(existing) ? existing : []), ...visible])]
  const start = all.indexOf(dragged)
  const destination = all.indexOf(target)
  if (start < 0 || destination < 0 || start === destination) return all
  all.splice(destination, 0, all.splice(start, 1)[0])
  return all
}
