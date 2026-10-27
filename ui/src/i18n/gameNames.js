import { i18n } from '@/i18n'
import names from './data/gameNames.json'

const itemNamesByOriginal = new Map(Object.values(names.items).map((item) => [item['zh-CN'], item]))

export function operatorDisplayName(name) {
  return names.operators[name]?.[i18n.global.locale.value] || name
}

export function itemDisplayName(id, original) {
  const item = names.items[id] || itemNamesByOriginal.get(original ?? id)
  return item?.[i18n.global.locale.value] || original || id
}

export function skillDisplayName(name) {
  if (typeof name !== 'string' || i18n.global.locale.value === 'zh-CN') return name
  const match = /^([一二三])技能[·・](.+)$/.exec(name)
  const skill = match ? match[2] : name
  const translated = names.skills[skill]?.[i18n.global.locale.value] || skill
  if (!match) return translated
  const number = '一二三'.indexOf(match[1]) + 1
  const prefix =
    i18n.global.locale.value === 'ja-JP'
      ? `スキル${number}`
      : i18n.global.locale.value === 'zh-TW'
        ? `${match[1]}技能`
        : `S${number}`
  return `${prefix} · ${translated}`
}
