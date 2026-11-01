const iconFiles = import.meta.glob('../assets/growth/*.png', {
  eager: true,
  query: '?url&no-inline',
  import: 'default'
})

export function moduleIconKey(value) {
  return String(value ?? '')
    .trim()
    .toLowerCase()
    .replace(/[δ∆]/g, 'd')
}

export function moduleIconLabel(value) {
  const type = String(value ?? '').trim()
  return type.split('-').at(-1) || '模组'
}

export function growthGameIcon(kind, value) {
  let filename
  if (kind === 'profession') filename = 'profession-' + String(value ?? '').toLowerCase()
  if (kind === 'elite') filename = 'elite-elite_' + (value ?? 0)
  if (kind === 'mastery') filename = 'specialized-specialized_tiny_' + (value ?? 0)
  if (kind === 'module') filename = 'module-' + moduleIconKey(value)
  return {
    src: iconFiles['../assets/growth/' + filename + '.png'] || null,
    fallback: kind === 'module' ? moduleIconLabel(value) : ''
  }
}
