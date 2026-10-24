const isObject = (value) => value !== null && typeof value === 'object' && !Array.isArray(value)

export const configSnapshot = (value) => JSON.parse(JSON.stringify(value))

// Match Conf's schema: model fields merge, but this dict is replaced as a whole.
const dictionaryFields = new Set(['rogue.collectible_mode_start_list'])

// Arrays and schema dictionaries are complete replacement values on /conf.
export function configPatch(previous, current, path = '') {
  const patch = {}
  for (const [key, value] of Object.entries(current)) {
    if (JSON.stringify(previous?.[key]) === JSON.stringify(value)) continue
    const fieldPath = path ? `${path}.${key}` : key
    if (isObject(value) && isObject(previous?.[key]) && !dictionaryFields.has(fieldPath)) {
      const nested = configPatch(previous[key], value, fieldPath)
      if (Object.keys(nested).length) patch[key] = nested
    } else {
      patch[key] = value
    }
  }
  return patch
}

// Preserve local edits while applying the server's compatibility fields.
export function reconcileConfig(current, submitted, accepted) {
  if (JSON.stringify(current) === JSON.stringify(submitted)) return configSnapshot(accepted)
  if (!isObject(current) || !isObject(submitted) || !isObject(accepted)) return current
  const result = { ...current }
  for (const [key, value] of Object.entries(accepted)) {
    result[key] = reconcileConfig(current[key], submitted[key], value)
  }
  return result
}
