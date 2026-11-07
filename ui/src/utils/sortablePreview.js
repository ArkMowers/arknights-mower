const preparedPreviews = new WeakMap()

function effectiveZoom(element, view) {
  let zoom = 1
  for (let current = element; current; current = current.parentElement) {
    const value = String(view.getComputedStyle(current).zoom || '1')
    const factor = Number.parseFloat(value) / (value.endsWith('%') ? 100 : 1)
    if (Number.isFinite(factor) && factor > 0) zoom *= factor
  }
  return zoom
}

export function normalizeSortablePreview({ item } = {}) {
  const document = item?.ownerDocument
  const view = document?.defaultView
  const preview = document?.body?.querySelector(':scope > .mower-drag-fallback')
  if (!preview || !view) return null
  if (preparedPreviews.has(preview)) return preparedPreviews.get(preview)
  const sourceZoom = effectiveZoom(item, view)
  const bodyZoom = effectiveZoom(preview.parentElement, view)
  if (Math.abs(sourceZoom - 1) < 0.0001 && Math.abs(bodyZoom - 1) < 0.0001)
    return { preview, content: preview, scale: 1 }

  // Sortable moves its fallback in viewport pixels; ancestor zoom scales those pixels again.
  // Keep the movement shell at viewport scale and restore the original zoom inside it.
  const rect = item.getBoundingClientRect()
  const content = preview.cloneNode(false)
  content.removeAttribute('id')
  content.classList.remove('mower-drag-chosen', 'mower-drag-ghost', 'sortable-drag')
  while (preview.firstChild) content.append(preview.firstChild)
  Object.assign(content.style, {
    position: 'static',
    top: 'auto',
    left: 'auto',
    margin: '0',
    transform: 'none',
    transformOrigin: '0 0',
    font: view.getComputedStyle(item).font,
    width: `${rect.width / sourceZoom}px`,
    height: `${rect.height / sourceZoom}px`,
    zoom: String(sourceZoom)
  })
  for (const [property, value] of Object.entries({
    display: 'block',
    padding: '0',
    border: '0',
    background: 'transparent',
    outline: 'none',
    'box-shadow': 'none',
    'border-radius': '0',
    overflow: 'visible',
    'max-height': 'none',
    'min-height': '0',
    'min-width': '0',
    'max-width': 'none',
    opacity: '1'
  }))
    preview.style.setProperty(property, value, 'important')

  Object.assign(preview.style, {
    zoom: String(1 / bodyZoom),
    width: `${rect.width}px`,
    height: `${rect.height}px`,
    left: `${rect.left}px`,
    top: `${rect.top}px`
  })
  preview.append(content)
  const result = { preview, content, scale: sourceZoom }
  preparedPreviews.set(preview, result)
  return result
}
