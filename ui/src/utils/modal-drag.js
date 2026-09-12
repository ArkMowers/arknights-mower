// Makes naive-ui modals draggable by their header so the panel can be moved
// freely inside the desktop shell instead of staying pinned to the window centre.
//
// The panel is centred by its container in normal flow, so on the first drag we
// convert it to fixed screen coordinates (matching its current on-screen rect)
// and then track the pointer to reposition it. This keeps the modal's own CSS
// intact — we only take over once the user actually starts a drag.
//
// Install with `installModalDragging()`; returns a disposable.

const DRAG_HANDLE_SELECTOR = '.n-card-header, .n-dialog__title'
// Elements the user may need to click rather than drag on.
const INTERACTIVE =
  'button, a, input, textarea, select, [contenteditable], [role="button"], .n-card-header__close'

let active = null

function onHandlePointerDown(event) {
  if (event.button !== 0) return
  if (active) return // one drag at a time
  if (event.target.closest(INTERACTIVE)) return

  const handle = event.target.closest(DRAG_HANDLE_SELECTOR)
  if (!handle) return

  // Only drag the main modal panel, never something nested inside it.
  const panel = handle.closest('.n-modal')
  if (!panel) return

  const rect = panel.getBoundingClientRect()
  const startX = event.clientX
  const startY = event.clientY

  const pointerId = event.pointerId
  const onPointerMove = (moveEvent) => {
    if (!active || moveEvent.pointerId !== pointerId) return
    const dx = moveEvent.clientX - startX
    const dy = moveEvent.clientY - startY
    if (!active.moved && Math.hypot(dx, dy) < 3) return
    active.moved = true
    panel.style.left = `${active.left + dx}px`
    panel.style.top = `${active.top + dy}px`
  }

  const onPointerUp = () => {
    window.removeEventListener('pointermove', onPointerMove)
    window.removeEventListener('pointerup', onPointerUp)
    window.removeEventListener('pointercancel', onPointerUp)
    active = null
  }

  window.addEventListener('pointermove', onPointerMove)
  window.addEventListener('pointerup', onPointerUp)
  window.addEventListener('pointercancel', onPointerUp)

  active = {
    panel,
    left: rect.left,
    top: rect.top,
    moved: false
  }

  // Take the panel out of the container's centering flow and pin it to the
  // position it currently occupies, then the pointer handler moves it.
  panel.style.position = 'fixed'
  panel.style.left = `${rect.left}px`
  panel.style.top = `${rect.top}px`
  panel.style.right = 'auto'
  panel.style.bottom = 'auto'
  panel.style.margin = '0'
  panel.style.transform = 'none'
}

export function installModalDragging() {
  document.addEventListener('pointerdown', onHandlePointerDown, true)
  return function dispose() {
    document.removeEventListener('pointerdown', onHandlePointerDown, true)
    active = null
  }
}
