export const workshopCategories = ['fodder_operators', 't5_operators', 'book_operators']

export async function loadWorkshopOperators(http, baseUrl) {
  const { data } = await http.get(`${baseUrl}/workshop-operators/recommendations`)
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

export function workshopRecommendationText(operator) {
  if (operator.causality) return `${operator.name}：非 T5 材料，因果垫刀合成`
  const materials = operator.materials || []
  const bonus = [...new Set(Object.values(operator.bonuses || {}))].sort((a, b) => a - b)
  const amount = bonus.length > 1 ? `${bonus[0]}～${bonus.at(-1)}` : bonus[0]
  return `${operator.name}：${materials.slice(0, 3).join('、')}${materials.length > 3 ? `等 ${materials.length} 种材料` : ''}，副产品概率加成 +${amount}%`
}
