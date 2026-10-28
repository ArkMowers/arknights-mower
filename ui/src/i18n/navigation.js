import { DEFAULT_LOCALE, i18n } from '@/i18n'
import { navigationSections } from '@/navigation'

const defaultGroupTitles = new Map([
  ...navigationSections.map(({ key, title }) => [key, title]),
  ['pinned', '置顶']
])
const hasTranslation = (key) => i18n.global.te(key) || i18n.global.te(key, DEFAULT_LOCALE)

export function navigationLabel(item, short = false) {
  const key = `navigation.pages.${item.key}`
  if (short && hasTranslation(`${key}.shortLabel`)) return i18n.global.t(`${key}.shortLabel`)
  if (hasTranslation(`${key}.label`)) return i18n.global.t(`${key}.label`)
  return (short && item.shortLabel) || item.label || item.title || ''
}

export function navigationGroupTitle(group) {
  const key = `navigation.groups.${group.key}`
  if (defaultGroupTitles.get(group.key) === group.title && hasTranslation(key))
    return i18n.global.t(key)
  return group.title || ''
}
