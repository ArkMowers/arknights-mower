export function planBindings(slot) {
  return [slot, ...(slot.group_bindings || [])]
}

export function planReplacements(slot) {
  return [...new Set(planBindings(slot).flatMap((binding) => binding.replacement || []))]
}

export function addPlanBinding(slot) {
  ;(slot.group_bindings ||= []).push({ group: '', replacement: [] })
}

export function removePlanBinding(slot, index) {
  if (index === 0) {
    const next = slot.group_bindings?.shift()
    if (!next) return
    slot.group = next.group
    slot.replacement = next.replacement
  } else {
    slot.group_bindings?.splice(index - 1, 1)
  }
  if (!slot.group_bindings?.length) delete slot.group_bindings
}

export function bindingColorStyle(slot, colors) {
  const bindings = planBindings(slot)
  if (bindings.length === 1) {
    return { borderBottom: slot.group ? `5px solid ${colors[slot.group]}` : 'none' }
  }
  const stops = bindings.flatMap((binding, index) => {
    const color = colors[binding.group] || 'transparent'
    return [
      `${color} ${(index * 100) / bindings.length}%`,
      `${color} ${((index + 1) * 100) / bindings.length}%`
    ]
  })
  return {
    paddingBottom: '5px',
    backgroundImage: `linear-gradient(to right, ${stops.join(', ')})`,
    backgroundSize: '100% 5px',
    backgroundPosition: 'left bottom',
    backgroundRepeat: 'no-repeat'
  }
}
