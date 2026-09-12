export const DEFAULT_MASTERY_SWAP_BUFFERS = Object.freeze({
  no_central: 10,
  central: 15,
  central_unhalved_m2: 30
})

export function normalizeMasterySwapBuffers(settings = {}) {
  const configured = settings.mastery_swap_buffers
  const legacy = settings.mastery_swap_buffer
  return Object.fromEntries(
    Object.entries(DEFAULT_MASTERY_SWAP_BUFFERS).map(([key, fallback]) => {
      const value = configured && typeof configured === 'object' ? configured[key] : legacy
      return [key, Number.isInteger(value) && value >= 0 ? value : fallback]
    })
  )
}

function normalizeMatch(value) {
  if (value === true) return 'yes'
  if (value === false) return 'no'
  return value
}

export async function syncMasteryRouteDefaults(http, baseUrl) {
  const synced = await http.get(`${baseUrl}/cultivate-fetch`)
  if (!synced.data?.success) {
    throw new Error(synced.data?.message || '干员数据同步失败，请稍后重试')
  }
  const { data } = await http.get(`${baseUrl}/mastery-route`)
  if (data?.defaults_error) throw new Error(data.defaults_error)
  if (!data?.defaults) throw new Error('未获取到专精路线，请稍后重试')
  return data
}

function normalizeSupports(supports) {
  if (!Array.isArray(supports)) return []
  return supports.filter(Boolean).map((support) => ({
    ...support,
    match: normalizeMatch(support.match)
  }))
}

function parseJson(value) {
  if (typeof value !== 'string') return value
  try {
    return JSON.parse(value)
  } catch {
    return null
  }
}

function legacyLevelSupports(route) {
  if (!route || typeof route !== 'object' || Array.isArray(route)) return []
  const supports = []
  for (let level = 1; level <= 3; level += 1) {
    const entry = route[`level_${level}`]
    if (!entry) continue
    supports.push({
      name: entry.operator || '',
      skill_level: level,
      efficiency: entry.efficiency ?? 60,
      swap: Boolean(entry.swap_target),
      swap_name: entry.swap_target || '',
      match: normalizeMatch(Boolean(entry.job_match))
    })
  }
  return supports
}

export function buildMasteryRoutePayload(profession, route) {
  const supports = normalizeSupports(route?.supports).map((support) => ({
    ...support,
    match: support.match === 'yes' || support.match === true
  }))
  return {
    profession,
    supports: JSON.stringify(supports),
    optimal: Boolean(route?.optimal),
    half_off: route?.half_off !== false
  }
}

export function parseMasteryRoute(route) {
  const parsed = parseJson(route?.supports)
  const wrapped = parsed && typeof parsed === 'object' && !Array.isArray(parsed) ? parsed : null
  const supports = normalizeSupports(
    Array.isArray(parsed) ? parsed : wrapped?.supports || legacyLevelSupports(wrapped)
  )
  const hasLegacyOptimal = wrapped && Object.hasOwn(wrapped, 'optimal')
  const hasLegacyHalfOff = wrapped && Object.hasOwn(wrapped, 'half_off')

  return {
    profession: route?.profession || '',
    supports,
    optimal: hasLegacyOptimal ? Boolean(wrapped.optimal) : Boolean(route?.optimal),
    half_off: hasLegacyHalfOff
      ? Boolean(wrapped.half_off)
      : route?.half_off === undefined
        ? true
        : Boolean(route.half_off)
  }
}

export function normalizeMasteryRouteDefaults(defaults) {
  const entries = Array.isArray(defaults)
    ? defaults.map((entry) => [entry.profession, entry])
    : Object.entries(defaults || {})
  const result = {}

  for (const [profession, value] of entries) {
    if (!profession) continue
    const parsed = parseJson(value?.supports)
    let supports
    if (Array.isArray(parsed)) {
      supports = parsed
    } else if (parsed && typeof parsed === 'object') {
      supports = parsed.supports || legacyLevelSupports(parsed)
    } else if (Array.isArray(value?.supports)) {
      supports = value.supports
    } else {
      supports = legacyLevelSupports(value)
    }
    result[profession] = normalizeSupports(supports)
  }

  return result
}

// Saved manual choices take priority. Unsaved personal defaults are persisted only
// when the user explicitly saves, even if they have not edited an individual row.
export function prepareMasteryRoutes(routes, defaults, professions) {
  const merged = {
    _defaultFlags: defaults,
    _jsonDefaults: normalizeMasteryRouteDefaults(defaults)
  }
  const suggestedProfessions = []
  for (const route of routes) {
    const parsed = parseMasteryRoute(route)
    if (professions.includes(parsed.profession)) merged[parsed.profession] = parsed
  }
  for (const profession of professions) {
    if (merged[profession] || !merged._jsonDefaults[profession]?.length) continue
    merged[profession] = {
      profession,
      supports: merged._jsonDefaults[profession].map((support) => ({ ...support })),
      optimal: false,
      half_off: !!defaults[profession]?.half_off
    }
    suggestedProfessions.push(profession)
  }
  return { routes: merged, suggestedProfessions }
}

export function completeMasterySupports(supports, defaults = []) {
  const rows = normalizeSupports(supports)
  const fallback = normalizeSupports(defaults)
  return [1, 2, 3].map((level) => ({
    name: '',
    skill_level: level,
    efficiency: 0,
    swap: false,
    swap_name: '',
    match: 'no',
    ...(rows.find((row) => row.skill_level === level && row.name) ||
      fallback.find((row) => row.skill_level === level))
  }))
}
