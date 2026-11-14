import recyclingModel from '../../../arknights_mower/data/recycling_model.json'
import { simulationOutputOrders } from './vendor/simulator/productionScore'

export const sanityItems = [
  { key: 'exp', label: '经验', unit: '经验值' },
  { key: 'gold', label: '赤金净产出', unit: '个' },
  { key: 'lmd', label: '龙门币净产出', unit: '龙门币' },
  { key: 'fragment', label: '源石碎片净产出', unit: '个' },
  { key: 'orundum', label: '合成玉', unit: '个' },
  { key: 'orirock', label: '固源岩消耗', unit: '个' },
  { key: 'device', label: '装置消耗', unit: '个' },
  { key: 'recycle', label: '回收站产出', unit: '次' },
  { key: 'recruitment', label: '公招刷新', unit: '次' },
  { key: 'clue', label: '线索搜集与赠送', unit: '个' },
  { key: 'exchange', label: '连续线索交流', unit: '天' }
]

const valueOrNull = (value) =>
  typeof value === 'number' && Number.isFinite(value) && value >= 0 ? value : null

export function recyclingIncomeValue(prices, model = recyclingModel) {
  const average = (pool, pick) => {
    const total = pool.reduce((sum, item) => sum + item.weight, 0)
    if (!(total > 0)) return null
    let result = 0
    for (const item of pool) {
      const value = valueOrNull(pick(item))
      if (value === null) return null
      result += (item.weight / total) * value
    }
    return result
  }
  const ordinary = average(model.ordinary, (item) => prices?.[item.name])
  const extra = average(model.extra, (item) => prices?.[item.name])
  const points = average(model.ordinary, (item) => item.points)
  if (ordinary === null || extra === null || points === null || !(model.point_threshold > 0))
    return null
  // The existing timer counts ordinary production cycles; extra rewards add long-run value.
  return ordinary + (points / model.point_threshold) * extra
}

export function createIncomeSanityValuation(valuation) {
  const price = (name) => valueOrNull(valuation?.prices?.[name])
  const overrides = valuation?.income_unit_values ?? {}
  const lmd = valueOrNull(valuation?.lmd_sanity)
  const record = price('中级作战记录')
  const orundum = price('合成玉')
  const certificates = valueOrNull(overrides.recruitment_certificates) ?? 0.2
  const yellowCertificateValue =
    valueOrNull(overrides.yellow_certificate) ?? (38 / 258) * 600 * (135 / 180)
  const creditValue =
    valueOrNull(overrides.credit) ?? valueOrNull(valuation?.credit_shop_value_threshold)
  return {
    version: 1,
    source: valuation?.source ?? '',
    recruitmentCertificates: certificates,
    yellowCertificateValue,
    creditValue,
    creditDailyLimit: valueOrNull(overrides.credit_daily_limit),
    unitValues: {
      exp: record === null ? null : record / 1000,
      gold: price('赤金'),
      lmd,
      fragment: valueOrNull(overrides.fragment),
      orundum,
      orirock: price('固源岩'),
      device: price('装置'),
      recycle: valueOrNull(overrides.recycle) ?? recyclingIncomeValue(valuation?.prices),
      recruitment: certificates * yellowCertificateValue,
      clue: creditValue === null ? null : 40 * creditValue,
      exchange: creditValue === null ? null : 210 * creditValue
    }
  }
}

export function validateIncomeSanityValuation(valuation) {
  if (valuation?.version !== 1 || !valuation.unitValues)
    throw new Error('理智算法的材料价值尚未读取，请重新读取 Mower 设置')
  for (const { key } of sanityItems) {
    const value = valuation.unitValues[key]
    if (value !== null && valueOrNull(value) === null)
      throw new Error('理智算法的单价必须是有限的非负数，未估值项目请留空')
  }
  if (valuation.creditDailyLimit !== null && valueOrNull(valuation.creditDailyLimit) === null)
    throw new Error('每日有效信用额度必须是有限的非负数，或留空不设上限')
  return valuation
}

export function calculateIncomeSanity(summary, valuation, simulation) {
  validateIncomeSanityValuation(valuation)
  const days = simulation.observedHours / 24
  if (!(days > 0) || !Number.isFinite(days)) throw new Error('理智算法的统计时长无效')
  const production = simulation.production
  const expected = production.assumptions.expectationMode && production.expected
  const orders = expected ? [] : simulationOutputOrders(simulation)
  const consumed = (resource, orderKey) =>
    expected
      ? (expected.costs[resource] ?? 0) / days
      : orders.reduce((sum, order) => sum + order[orderKey], 0) / days
  const quantities = {
    exp: summary.exp,
    gold: summary.goldCount - consumed('gold', 'goldCost'),
    lmd: summary.orderLmd - summary.lmdConsumed,
    fragment: summary.fragments - consumed('fragment', 'fragmentCost'),
    orundum: summary.orundum,
    orirock: -summary.orirockConsumed,
    device: -summary.deviceConsumed,
    recycle: summary.recycleCount,
    recruitment: summary.recruitmentCount,
    clue: summary.clueCount,
    exchange: simulation.inputs?.schedule?.rooms?.some(
      (room) => room.type === 'meeting' && room.level > 0
    )
      ? 1
      : 0
  }
  const creditLimit = valuation.creditDailyLimit ?? Infinity
  const exchangeCredits = Math.min(210 * quantities.exchange, creditLimit)
  const clueCredits = Math.min(40 * quantities.clue, Math.max(0, creditLimit - exchangeCredits))
  const parts = sanityItems.map((item) => {
    const quantity = quantities[item.key]
    if (!Number.isFinite(quantity)) throw new Error(`理智算法缺少${item.label}数量`)
    let unitValue = valuation.unitValues[item.key]
    if (item.key === 'exchange' && quantity > 0)
      unitValue =
        exchangeCredits === 0
          ? 0
          : unitValue === null
            ? null
            : (unitValue * exchangeCredits) / (210 * quantity)
    if (item.key === 'clue' && quantity > 0)
      unitValue =
        clueCredits === 0
          ? 0
          : unitValue === null
            ? null
            : (unitValue * clueCredits) / (40 * quantity)
    return { ...item, quantity, unitValue, value: unitValue === null ? null : quantity * unitValue }
  })
  const unpriced = parts.filter((part) => part.unitValue === null && Math.abs(part.quantity) > 1e-9)
  const total = parts.reduce((sum, part) => sum + (part.value ?? 0), 0)
  if (!Number.isFinite(total)) throw new Error('理智算法的收益超出有效数值范围')
  return {
    total,
    credits: {
      produced: 40 * quantities.clue + 210 * quantities.exchange,
      valued: exchangeCredits + clueCredits
    },
    partial: unpriced.length > 0,
    unpriced: unpriced.map((part) => part.label),
    parts
  }
}

export function incomeScore(result) {
  return result.summary.sanity?.total ?? result.summary.totalScore82
}

export function incomeScoreLabel(result) {
  return result.summary.sanity
    ? `日均理智收益${result.summary.sanity.partial ? '（部分）' : ''}`
    : '日均加权收益'
}
