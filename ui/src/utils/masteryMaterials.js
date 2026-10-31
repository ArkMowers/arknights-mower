export function materialStatus(summary) {
  if (!summary) return '待计算'
  if (summary.available) return '材料充足'
  return summary.craftable ? '可合成' : '材料不足'
}

export function materialStatusType(summary) {
  if (!summary) return undefined
  if (summary.available) return 'success'
  return summary.craftable ? 'warning' : 'error'
}

export function materialQuantityType(material) {
  if (material.owned >= material.required) return undefined
  return material.craftable ? 'warning' : 'error'
}

const exactNumber = new Intl.NumberFormat('zh-CN')
const WAN = 10000
const YI = 100000000

function trimTrailingZeros(text) {
  return text.includes('.') ? text.replace(/\.?0+$/, '') : text
}

function yiLabel(amount) {
  return trimTrailingZeros((amount / YI).toFixed(2)) + '亿'
}

// 库存与需求数量：万/亿紧凑显示，精确值由调用方保留在 title 提示里。
export function formatMaterialAmount(value) {
  const amount = Number(value)
  if (!Number.isFinite(amount)) return '0'
  const rounded = Math.round(amount)
  const magnitude = Math.abs(rounded)
  if (magnitude >= YI) return yiLabel(rounded)
  if (magnitude >= WAN) {
    const wan = rounded / WAN
    // 四舍五入后达到 10000 万时进位到亿，避免出现「10000万」这类边界写法。
    if (Math.round(wan * 10) / 10 >= 10000) return yiLabel(rounded)
    return trimTrailingZeros(wan.toFixed(1)) + '万'
  }
  return exactNumber.format(rounded)
}
