import moduleColors from '../assets/growth/module-colors.json'

const iconFiles = import.meta.glob('../assets/growth/*.png', {
  eager: true,
  query: '?url&no-inline',
  import: 'default'
})

export function moduleBadge(value, moduleId) {
  const type = String(value ?? '')
    .trim()
    .toUpperCase()
  const suffix = type.split('-').at(-1)
  const label = !type
    ? '模组'
    : type === 'ORIGINAL'
      ? '基础'
      : { D: 'Δ', '∆': 'Δ', A: 'α', Α: 'α', B: 'β', Β: 'β', Γ: 'γ' }[suffix] || suffix
  // 相同型号在不同干员上可能有不同颜色，不能由 X/Y 等字母推断。
  const colorName = moduleColors.colors[moduleId] || 'grey'
  return { label, color: moduleColors.palette[colorName] || moduleColors.palette.grey }
}

export function growthGameIcon(kind, value) {
  let filename
  if (kind === 'profession') filename = 'profession-' + String(value ?? '').toLowerCase()
  if (kind === 'elite') filename = 'elite-elite_' + (value ?? 0)
  if (kind === 'mastery') filename = 'mastery-' + (value ?? 0)
  return {
    src: iconFiles['../assets/growth/' + filename + '.png'] || null,
    fallback: ''
  }
}
