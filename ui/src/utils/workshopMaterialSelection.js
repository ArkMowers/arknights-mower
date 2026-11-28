import { pinyin_match } from './common'

export function selectedMaterials(item, tiers) {
  return [...tiers.filter((rarity) => item.material_rarities?.includes(rarity)), ...item.item_names]
}

export function updateSelectedMaterials(item, selection) {
  item.material_rarities = selection.filter((value) => typeof value === 'number')
  item.item_names = selection.filter((value) => typeof value === 'string')
}

export function materialFallback(value) {
  return { value, label: typeof value === 'number' ? `T${value} 材料` : value }
}

export const normalizeTierSearch = (text) => text.replace(/\s+/g, '').toLowerCase()

export function filterMaterial(pattern, option) {
  if (typeof option.value === 'number') {
    return normalizeTierSearch(option.label).includes(normalizeTierSearch(pattern))
  }
  return pinyin_match(option.label, pattern)
}
