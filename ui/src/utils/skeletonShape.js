// 只缓存页面声明的布局字段。行数在分配数组或交给 v-for 前就要有上限。
const PREFIX = 'mower_skeleton_shape:'
const MAX_RECORD_LENGTH = 16384

export function skeletonCount(limit, fallback = 0) {
  return (value) => (Number.isInteger(value) && value >= 0 ? Math.min(value, limit) : fallback)
}

export function skeletonList(limit, item, fallback = []) {
  return (value) => {
    if (!Array.isArray(value)) return fallback
    const rows = value.slice(0, limit).map(item)
    return rows.includes(undefined) ? fallback : rows
  }
}

export function createSkeletonShape(key, fields) {
  const storageKey = PREFIX + key
  function normalize(value) {
    const record = value && typeof value === 'object' && !Array.isArray(value) ? value : {}
    const shape = {}
    for (const [name, rule] of Object.entries(fields)) {
      const field = record[name]
      if (typeof rule === 'function') shape[name] = rule(field)
      else shape[name] = typeof field === 'boolean' ? field : rule
    }
    return shape
  }

  function save(value) {
    try {
      localStorage.setItem(storageKey, JSON.stringify(normalize(value)))
    } catch {
      // 浏览器禁用存储或空间不足时仍可使用当前页面。
    }
  }

  function read() {
    try {
      const raw = localStorage.getItem(storageKey)
      if (raw && raw.length <= MAX_RECORD_LENGTH) {
        const shape = normalize(JSON.parse(raw))
        // 访问旧缓存时一并清除已停用的字段，包括旧版基建技能记录里的干员名。
        if (JSON.stringify(shape) !== raw) save(shape)
        return shape
      }
      if (raw) localStorage.removeItem(storageKey)
    } catch {
      // 无法读取或解析旧记录时，用默认布局替换它。
      save(null)
    }
    return normalize(null)
  }

  return { read, save }
}
