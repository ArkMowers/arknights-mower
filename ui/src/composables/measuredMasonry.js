import { onActivated, onDeactivated, onScopeDispose, watch } from 'vue'

export function useMeasuredMasonry(root, enabled) {
  let observer
  let target
  let frame = null
  let active = true
  let cards = []

  function update() {
    if (!observer || !enabled.value || !active) return
    target.setAttribute('data-masonry-ready', '')
    // Measure natural content in CSS pixels so desktop zoom does not enlarge the row spans.
    for (const { section, content } of cards) {
      const span = Math.ceil(content.offsetHeight) + 10
      section.style.setProperty('--task-card-span', String(span))
    }
  }

  function schedule() {
    if (frame !== null) return
    frame = requestAnimationFrame(() => {
      frame = null
      update()
    })
  }

  function stop() {
    observer?.disconnect()
    observer = undefined
    if (frame !== null) cancelAnimationFrame(frame)
    frame = null
    target?.removeAttribute('data-masonry-ready')
    for (const { section } of cards) section.style.removeProperty('--task-card-span')
    cards = []
    target = undefined
  }

  function start() {
    stop()
    if (
      !enabled.value ||
      !active ||
      !root.value ||
      typeof ResizeObserver === 'undefined' ||
      typeof requestAnimationFrame === 'undefined'
    )
      return
    target = root.value
    cards = Array.from(target.children)
      .filter((section) => section.hasAttribute('data-task-editor'))
      .map((section) => ({ section, content: section.firstElementChild }))
      .filter(({ content }) => content)
    observer = new ResizeObserver(schedule)
    for (const { content } of cards) observer.observe(content)
    update()
  }

  watch([root, enabled], start, { flush: 'post' })
  onActivated(() => {
    active = true
    start()
  })
  onDeactivated(() => {
    active = false
    stop()
  })
  onScopeDispose(stop)
  return update
}
