import { operatorDisplayName, itemDisplayName } from '@/i18n/gameNames'
import { i18n } from '@/i18n'
import { operatorSyncMessage } from '@/i18n/operatorSync'
export const workshopCategories = ['fodder_operators', 't5_operators', 'book_operators']

export function selectedWorkshopOperators(settings = {}) {
  const names = workshopCategories.flatMap((key) => settings[key] || [])
  for (const entry of [
    ...(settings.workshop_settings || []),
    ...(settings.workshop_manual_settings || [])
  ]) {
    if (entry?.enabled !== false) names.push(entry?.operator)
  }
  return new Set(names.filter((name) => name && name !== 'Free' && name !== 'Current'))
}

export function workshopTraineeWarning(name, operators) {
  return name && operators.has(name)
    ? i18n.global.t('growth.workshopHelper.isSelectedAsAWorkshopOperatorIn', {
        value0: operatorDisplayName(name)
      })
    : ''
}

export async function syncWorkshopOperators(http, baseUrl, minBonus = 80) {
  const synced = await http.get(`${baseUrl}/cultivate-fetch`)
  if (!synced.data?.success) {
    throw new Error(
      operatorSyncMessage(synced.data?.message) ||
        i18n.global.t('growth.workshopHelper.operatorSynchronizationFailedPleaseTryAgainLater')
    )
  }
  const data = await loadWorkshopOperators(http, baseUrl, minBonus)
  const defaults = { ...data.defaults }
  for (const key of workshopCategories) {
    let threshold = minBonus
    while (threshold > 0 && !defaults[key].length) {
      threshold = Math.max(0, threshold - 5)
      const fallback = await loadWorkshopOperators(http, baseUrl, minBonus, { [key]: threshold })
      defaults[key] = fallback.defaults[key]
    }
  }
  return { ...data, defaults }
}

export async function loadWorkshopOperators(http, baseUrl, minBonus = 80, categoryMinBonus = {}) {
  const params = { min_bonus: minBonus }
  for (const [key, threshold] of Object.entries(categoryMinBonus)) {
    params[key.replace('_operators', '_min_bonus')] = threshold
  }
  const { data } = await http.get(`${baseUrl}/workshop-operators/recommendations`, {
    params
  })
  if (
    !data?.defaults ||
    !data?.recommendations ||
    workshopCategories.some(
      (key) =>
        !Array.isArray(data.defaults[key]) ||
        !Array.isArray(data.recommendations[key]) ||
        data.defaults[key].some((name) => typeof name !== 'string' || !name)
    )
  ) {
    throw new Error(
      i18n.global.t('growth.workshopHelper.workshopRecommendationsAreIncompletePleaseTryAgain')
    )
  }
  return data
}

export async function loadWorkshopReference(http, baseUrl) {
  const { data } = await http.get(`${baseUrl}/workshop-operators/reference`)
  if (workshopCategories.some((key) => !Array.isArray(data?.recommendations?.[key]))) {
    throw new Error(
      i18n.global.t('growth.workshopHelper.workshopGrowthRecommendationsAreIncompletePleaseTry')
    )
  }
  return data.recommendations
}

export function usesLegacyWorkshopDefaults(settings) {
  const legacy = {
    fodder_operators: ['九色鹿'],
    t5_operators: ['年'],
    book_operators: ['司霆惊蛰']
  }
  return workshopCategories.every(
    (key) => JSON.stringify(settings[key]) === JSON.stringify(legacy[key])
  )
}

export function workshopRecommendationText(operator, unowned = false) {
  const name = unowned
    ? i18n.global.t('growth.workshopHelper.notOwned', {
        value0: operatorDisplayName(operator.name)
      })
    : operatorDisplayName(operator.name)
  if (operator.causality) return name
  const materials = (operator.materials || []).map((name) => itemDisplayName(name))
  const bonus = [...new Set(Object.values(operator.bonuses || {}))].sort((a, b) => a - b)
  const amount = bonus.length > 1 ? `${bonus[0]}～${bonus.at(-1)}` : bonus[0]
  const scope =
    operator.name === '休谟斯'
      ? i18n.global.t('growth.workshopHelper.craftsT3MaterialsOnly')
      : operator.material_scope === 't4'
        ? i18n.global.t('growth.workshopHelper.t4MaterialsOnly')
        : operator.specialist
          ? i18n.global.t('growth.workshopHelper.only', { value0: materials.join('、') })
          : i18n.global.t('growth.workshopHelper.text', {
              value0: materials.slice(0, 3).join('、'),
              value1:
                materials.length > 3
                  ? i18n.global.t('growth.workshopHelper.andOtherMaterialsTypesTotal', {
                      value0: materials.length
                    })
                  : ''
            })
  const extra =
    operator.name === '蚀清'
      ? i18n.global.t('growth.workshopHelper.theByproductIsAlwaysReturnsSecondOnly')
      : ''
  return i18n.global.t('growth.workshopHelper.byproductProbabilityBonus', {
    value0: name,
    value1: scope,
    value2: amount,
    value3: extra
  })
}
