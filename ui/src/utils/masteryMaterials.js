export function materialStatus(summary) {
  if (!summary) return '待计算'
  if (summary.available) return '材料充足'
  return summary.craftable ? '可合成' : '材料不足'
}
