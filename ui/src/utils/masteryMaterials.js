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
