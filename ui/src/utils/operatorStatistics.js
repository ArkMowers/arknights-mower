const countKeys = [
  'owned',
  'available',
  'elite2',
  'max_level',
  'module_level',
  'sanity',
  'consumed_lmd',
  'consumed_exp',
  'module_blocks',
  'skill_book_equivalent'
]

export function sumPersonalStatistics(statistics, rarities) {
  const result = Object.fromEntries(countKeys.map((key) => [key, 0]))
  result.skills = { 1: 0, 2: 0, 3: 0 }
  result.modules = { 1: 0, 2: 0, 3: 0 }
  result.incomplete = []
  result.ranking = []
  const materials = new Map()
  for (const rarity of rarities) {
    const row = statistics?.rarities?.[rarity]
    if (!row) continue
    for (const key of countKeys) result[key] += row[key] || 0
    for (const level of [1, 2, 3]) {
      result.skills[level] += row.skills?.[level] || 0
      result.modules[level] += row.modules?.[level] || 0
    }
    result.incomplete.push(...(row.incomplete || []))
    result.ranking.push(...(row.ranking || []))
    for (const item of row.materials || []) {
      const current = materials.get(item.id)
      materials.set(item.id, {
        ...item,
        count: (current?.count || 0) + item.count,
        sanity:
          item.sanity === null || current?.sanity === null
            ? null
            : (current?.sanity || 0) + item.sanity
      })
    }
  }
  result.materials = [...materials.values()].sort(
    (a, b) =>
      Number(a.sanity === null) - Number(b.sanity === null) ||
      (b.sanity || 0) - (a.sanity || 0) ||
      a.id.localeCompare(b.id)
  )
  result.ranking.sort((a, b) => b.sanity - a.sanity || a.char_id.localeCompare(b.char_id))
  return result
}

export function personalStatisticsRows(statistics, rarities) {
  return [
    { key: 'all', label: '全部所选', ...sumPersonalStatistics(statistics, rarities) },
    ...[6, 5, 4, 3, 2, 1]
      .filter((rarity) => rarities.includes(rarity))
      .map((rarity) => ({ key: rarity, label: `${rarity} 星`, ...statistics?.rarities?.[rarity] }))
  ]
}
