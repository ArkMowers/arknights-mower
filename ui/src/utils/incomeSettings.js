import { i18n } from '@/i18n'
const { t } = i18n.global
export const incomeSettingsUrl = `${import.meta.env.VITE_HTTP_URL}/report/recycling_settings`
export const incomeAlgorithms = [
  {
    value: 0,
    get label() {
      return t('tasks.income82')
    },
    ratios: { experience: 1, gold: 0.8, order: 0.2 }
  },
  {
    value: 1,
    get label() {
      return t('tasks.income0245')
    },
    ratios: { experience: 1, gold: 0.8, order: 733 / 2990 }
  },
  {
    value: 2,
    get label() {
      return t('tasks.income023456')
    },
    ratios: { experience: 0.9568, gold: 0.76544, order: 0.23456 }
  },
  {
    value: -1,
    get label() {
      return t('tasks.customProductRatios')
    }
  }
]
export function incomeAlgorithmLabel(value) {
  return incomeAlgorithms.find((row) => row.value === value)?.label || t('tasks.notLoaded')
}
export async function loadIncomeSettings(client, storage = globalThis.localStorage) {
  let value = (await client.get(incomeSettingsUrl)).data
  if (value.base_algorithm_saved || !storage) return value
  let legacy
  try {
    legacy = JSON.parse(storage.getItem('earning_algorithm_config'))
  } catch {
    return value
  }
  if (!legacy) return value
  const option = incomeAlgorithms.find((row) => row.value === legacy.using)
  if (!option) return value
  const ratios = option.ratios || {
    experience: legacy.custom?.exp,
    gold: legacy.custom?.gold,
    order: legacy.custom?.lmb
  }
  if (
    !Object.values(ratios).every((v) => Number.isFinite(v) && v >= 0 && v <= 1000) ||
    ratios.experience < 0.000001
  )
    return value
  value = (
    await client.put(incomeSettingsUrl, {
      base_algorithm: option.value,
      ratios: { ...ratios, efficiency: value.ratios.efficiency }
    })
  ).data
  storage.removeItem('earning_algorithm_config')
  return value
}
