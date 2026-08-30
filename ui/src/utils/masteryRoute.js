function normalizeMatch(value) {
  if (value === true) return 'yes'
  if (value === false) return 'no'
  return value
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
        : Boolean(route.half_off),
    legacyControlCenter: wrapped?.controlCenter || wrapped?.control_center || null
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
