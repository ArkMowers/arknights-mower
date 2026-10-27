import { i18n } from '@/i18n'
import names from './data/moduleNames.json'

const byOriginal = new Map()
const ambiguous = new Set()
for (const entry of Object.values(names.modules)) {
  const original = entry['zh-CN']
  if (
    byOriginal.has(original) &&
    JSON.stringify(byOriginal.get(original)) !== JSON.stringify(entry)
  ) {
    ambiguous.add(original)
  }
  byOriginal.set(original, entry)
}
for (const original of ambiguous) byOriginal.delete(original)

export function moduleDisplayName(id, original) {
  const entry = names.modules[id] || byOriginal.get(original ?? id)
  return entry?.[i18n.global.locale.value] || original || id
}
