// Survey counts are a fixed reference, not measured incremental refresh outcomes.
// https://ark.yituliu.cn/survey/maarecruitdata (2026-11-14)
const recruitCounts = { 3: 593407671, 4: 108025329, 5: 3878075, 6: 1511907 }
const recruitTotal = Object.values(recruitCounts).reduce((sum, value) => sum + value, 0)
export const recruitmentProbabilities = Object.fromEntries(
  Object.entries(recruitCounts).map(([star, count]) => [star, count / recruitTotal])
)

export const potentialPresets = [
  { value: 'default', label: '默认：四星 1、五星 5、六星 10 黄票' },
  { value: 'skland', label: '当前森空岛数据估算' },
  { value: 'full', label: '满潜：四星 1、五星 13、六星 25 黄票' }
]
export const yellowValuePresets = [
  { value: 'vouchers', label: '抽卡券：258 黄票换 38 抽' },
  { value: 'royal_token', label: '通用信物：六星皇家信物' }
]

function operatorRewards(operator) {
  if (operator.owned === false) return { yellow: 1, green: 0 }
  if (
    operator.owned !== true ||
    !Number.isInteger(operator.potential) ||
    operator.potential < 1 ||
    operator.potential > 6
  )
    return null
  const full = operator.potential === 6
  switch (operator.stars) {
    case 3:
      return { yellow: 0, green: full ? 10 : 5 }
    case 4:
      return { yellow: full ? 1 : 0, green: 30 }
    case 5:
      return { yellow: full ? 13 : 5, green: 0 }
    case 6:
      return { yellow: full ? 25 : 10, green: 0 }
    default:
      return null
  }
}

export function certificateRewards(preset, roster) {
  if (preset === 'default' || preset === 'full')
    return {
      3: { yellow: 0, green: 10 },
      4: { yellow: 1, green: 30 },
      5: { yellow: preset === 'full' ? 13 : 5, green: 0 },
      6: { yellow: preset === 'full' ? 25 : 10, green: 0 }
    }
  if (preset !== 'skland' || !Array.isArray(roster)) return null
  const result = {}
  for (const star of [3, 4, 5, 6]) {
    const group = roster.filter((operator) => operator.stars === star)
    if (!group.length) return null
    const rewards = group.map(operatorRewards)
    if (rewards.some((reward) => reward === null)) return null
    result[star] = {
      yellow: rewards.reduce((sum, reward) => sum + reward.yellow, 0) / group.length,
      green: rewards.reduce((sum, reward) => sum + reward.green, 0) / group.length
    }
  }
  return result
}

const value = (candidate) =>
  typeof candidate === 'number' && Number.isFinite(candidate) && candidate >= 0 ? candidate : null

export function createCertificateValuation(valuation, roster) {
  const options = valuation?.income_options ?? {}
  const overrides = valuation?.income_unit_values ?? {}
  const potentialPreset = options.potential_preset ?? 'default'
  const yellowPreset = options.yellow_preset ?? 'vouchers'
  const rewards = certificateRewards(potentialPreset, roster)
  const refresh = rewards
    ? Object.fromEntries(
        ['yellow', 'green'].map((currency) => [
          currency,
          Object.entries(recruitmentProbabilities).reduce(
            (sum, [star, probability]) =>
              sum + probability * (rewards[star][currency] - rewards[3][currency]),
            0
          )
        ])
      )
    : null
  const orundum = value(valuation?.prices?.['合成玉'])
  const redCertificate = value(valuation?.prices?.['采购凭证'])
  const yellow =
    value(overrides.yellow_certificate) ??
    (yellowPreset === 'royal_token'
      ? redCertificate === null
        ? null
        : (720 / 135) * redCertificate
      : orundum === null
        ? null
        : ((38 * 600) / 258) * orundum)
  const green =
    value(overrides.green_certificate) ?? (orundum === null ? null : (30 / 50) * orundum)
  const refreshYellow = value(overrides.recruitment_certificates) ?? refresh?.yellow ?? null
  const refreshGreen = refresh?.green ?? null
  const component = (quantity, price) =>
    quantity === 0 || price === 0
      ? 0
      : quantity === null || price === null
        ? null
        : quantity * price
  const yellowIncome = component(refreshYellow, yellow)
  const greenIncome = component(refreshGreen, green)
  return {
    potentialPreset,
    yellowPreset,
    rewards,
    redCertificate,
    orundum,
    yellow,
    green,
    refreshYellow,
    refreshGreen,
    recruitmentValue:
      yellowIncome === null || greenIncome === null ? null : yellowIncome + greenIncome
  }
}
