const equivalentTerms = [
  ['深色', '暗色'],
  ['浅色', '亮色'],
  ['公招', '公开招募'],
  ['肉鸽', '集成战略'],
  ['触摸', '触控']
]

function normalize(value) {
  let normalized = String(value ?? '')
    .normalize('NFKC')
    .toLowerCase()
    .replace(/\s+/g, '')
  for (const [alias, term] of equivalentTerms) normalized = normalized.replaceAll(alias, term)
  return normalized
}

export function matchesSettingsSearch(query, ...sources) {
  const words = String(query ?? '')
    .normalize('NFKC')
    .trim()
    .split(/\s+/)
    .filter(Boolean)
  const haystack = normalize(sources.flat().join(' '))
  return words.every((word) => haystack.includes(normalize(word)))
}

// 只收集标签、说明和选项名称，避免把用户输入的账号、密钥等配置值加入索引。
export function settingsElementKeywords(element) {
  if (!element) return ''
  const labels =
    element.querySelectorAll?.(
      '[data-settings-keywords], [data-settings-label], .n-form-item-label, .n-radio__label, .n-checkbox__label, .settings-segmented-choice, .settings-row-description'
    ) ?? []
  return [
    element.getAttribute?.('data-settings-keywords'),
    ...Array.from(
      labels,
      (node) =>
        node.getAttribute?.('data-settings-keywords') ||
        node.getAttribute?.('data-settings-label') ||
        node.textContent
    )
  ]
    .filter(Boolean)
    .join(' ')
}
