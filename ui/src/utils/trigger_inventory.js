import { i18n } from '@/i18n'
import { planDisplayName } from '@/i18n/plans'

export const inventory_options = [
  { label: '赤金', value: '赤金', icon: '赤金' },
  { label: '源石碎片', value: '源石碎片', icon: '源石碎片' },
  { label: '固源岩', value: '固源岩', icon: '固源岩' },
  { label: '装置', value: '装置', icon: '装置' },
  { label: '龙门币', value: '龙门币', icon: '龙门币' },
  { label: '全部经验（计算）', value: '全部经验（计算）', icon: 'EXP' }
]

export function inventory_options_with_counts(inventory, state = 'loaded') {
  return inventory_options.map((option) => {
    let count = i18n.global.t('plans.loadingInventory')
    if (state === 'error') {
      count = i18n.global.t('plans.unknown')
    } else if (state === 'loaded') {
      count = new Intl.NumberFormat(i18n.global.locale.value).format(
        Number(inventory[option.value] ?? 0)
      )
    }
    return {
      ...option,
      name: planDisplayName(option.label),
      inventoryText: count,
      label: i18n.global.t('plans.inventoryOption', { name: planDisplayName(option.label), count })
    }
  })
}

export function extract_inventory_counts(response) {
  const result = {}
  const categories = response?.depot?.[0] || {}
  for (const items of Object.values(categories)) {
    for (const [name, item] of Object.entries(items || {})) {
      result[name] = Number(item?.number ?? 0)
    }
  }
  return result
}

export function inventory_expression(item) {
  return `op_data.inventory_count('${item}')`
}

export function parse_inventory_expression(value) {
  const match = value.match(/^op_data\.inventory_count\('(.+)'\)$/)
  return match?.[1]
}
