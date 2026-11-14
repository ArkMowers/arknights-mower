import '@/styles/drag.css'

function copyAppearance(source, copy, view) {
  const appearance = view.getComputedStyle(source)
  for (const property of Array.from(appearance)) {
    copy.style.setProperty(property, appearance.getPropertyValue(property))
  }
  copy.style.setProperty('transition', 'none')
  copy.style.setProperty('animation', 'none')
  copy.removeAttribute('id')
  copy.removeAttribute('draggable')
  if (source.tagName === 'CANVAS') {
    copy.width = source.width
    copy.height = source.height
    if (source.width > 0 && source.height > 0) {
      copy.getContext('2d')?.drawImage(source, 0, 0)
    }
  }
  for (let index = 0; index < source.children.length; index += 1) {
    copyAppearance(source.children[index], copy.children[index], view)
  }
}

export function createDragPreview() {
  let preview = null
  let cleanupTimer = null
  let previewWindow = null

  function clear() {
    if (cleanupTimer !== null) previewWindow.clearTimeout(cleanupTimer)
    preview?.remove()
    preview = null
    cleanupTimer = null
    previewWindow = null
  }

  function start(event, element = event.currentTarget) {
    clear()
    if (!element || typeof event.dataTransfer?.setDragImage !== 'function') return
    try {
      const rect = element.getBoundingClientRect()
      if (!rect.width || !rect.height) return
      const document = element.ownerDocument
      const view = document.defaultView
      const configuredZoom = Number(document.documentElement?.style.zoom)
      const zoom = Number.isFinite(configuredZoom) && configuredZoom > 0 ? configuredZoom : 1
      const width = rect.width / zoom
      const height = rect.height / zoom
      const copy = element.cloneNode(true)
      copyAppearance(element, copy, view)
      copy.classList.add('mower-drag-preview')
      Object.assign(copy.style, {
        width: `${width}px`,
        height: `${height}px`,
        boxSizing: 'border-box',
        margin: '0',
        transform: 'none'
      })
      const padding = 12
      preview = document.createElement('div')
      previewWindow = view
      preview.setAttribute('aria-hidden', 'true')
      preview.inert = true
      Object.assign(preview.style, {
        position: 'fixed',
        left: '-10000px',
        top: '0',
        width: `${width}px`,
        height: `${height}px`,
        padding: `${padding}px`,
        boxSizing: 'content-box',
        pointerEvents: 'none'
      })
      preview.append(copy)
      document.body.append(preview)
      const x = Math.max(0, Math.min(rect.width, event.clientX - rect.left))
      const y = Math.max(0, Math.min(rect.height, event.clientY - rect.top))
      event.dataTransfer.setDragImage(preview, x + padding * zoom, y + padding * zoom)
      cleanupTimer = view.setTimeout(clear, 0)
    } catch {
      clear()
    }
  }

  return { start, clear }
}
