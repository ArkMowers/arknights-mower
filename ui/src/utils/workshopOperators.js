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
    ? `${name} 已在合成计划中被选为加工站干员，专精期间可能影响合成，请留意。`
    : ''
}

export async function syncWorkshopOperators(http, baseUrl, minBonus = 80) {
  const synced = await http.get(`${baseUrl}/cultivate-fetch`)
  if (!synced.data?.success) {
    throw new Error(synced.data?.message || '干员数据同步失败，请稍后重试')
  }
  return loadWorkshopOperators(http, baseUrl, minBonus)
}

export async function loadWorkshopOperators(http, baseUrl, minBonus = 80) {
  const { data } = await http.get(`${baseUrl}/workshop-operators/recommendations`, {
    params: { min_bonus: minBonus }
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
    throw new Error('加工站推荐数据不完整，请稍后重试')
  }
  return data
}

export async function loadWorkshopReference(http, baseUrl) {
  const { data } = await http.get(`${baseUrl}/workshop-operators/reference`)
  if (workshopCategories.some((key) => !Array.isArray(data?.recommendations?.[key]))) {
    throw new Error('加工站培养推荐数据不完整，请稍后重试')
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
  const name = unowned ? `${operator.name}（未持有）` : operator.name
  if (operator.causality) return name
  const materials = operator.materials || []
  const bonus = [...new Set(Object.values(operator.bonuses || {}))].sort((a, b) => a - b)
  const amount = bonus.length > 1 ? `${bonus[0]}～${bonus.at(-1)}` : bonus[0]
  const scope =
    operator.name === '休谟斯'
      ? '仅合成 T3 材料'
      : operator.material_scope === 't4'
        ? '仅 T4 材料'
        : operator.specialist
          ? `仅${materials.join('、')}`
          : `${materials.slice(0, 3).join('、')}${materials.length > 3 ? `等 ${materials.length} 种材料` : ''}`
  const extra = operator.name === '蚀清' ? '，副产物固定异铁组（收益仅次于九色鹿）' : ''
  return `${name}：${scope}，副产品概率加成 +${amount}%${extra}`
}
