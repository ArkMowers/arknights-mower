import { onBeforeUnmount, onMounted, shallowRef, useId, watch } from 'vue'

function measureLines(element) {
  const bounds = element.getBoundingClientRect?.()
  const document = element.ownerDocument
  if (!bounds?.width || !bounds.height || !document?.createRange) return []
  const range = document.createRange()
  const fragments = []
  const collect = (node) => {
    if (node.nodeType === 3) {
      if (!node.textContent?.trim()) return
      range.selectNodeContents(node)
      fragments.push(...range.getClientRects())
    } else if (['IMG', 'SVG', 'CANVAS'].includes(node.tagName?.toUpperCase())) {
      fragments.push(node.getBoundingClientRect())
    } else {
      for (const child of node.childNodes ?? []) collect(child)
    }
  }
  collect(element)
  const rows = []
  for (const rect of fragments
    .filter((rect) => rect.width > 0 && rect.height > 0)
    .sort((a, b) => a.top - b.top || a.left - b.left)) {
    const row = rows.find(
      (row) =>
        Math.min(row.bottom, rect.bottom) - Math.max(row.top, rect.top) >=
        Math.min(row.bottom - row.top, rect.height) / 2
    )
    if (row) {
      row.left = Math.min(row.left, rect.left)
      row.right = Math.max(row.right, rect.right)
      row.top = Math.min(row.top, rect.top)
      row.bottom = Math.max(row.bottom, rect.bottom)
    } else rows.push({ left: rect.left, right: rect.right, top: rect.top, bottom: rect.bottom })
  }
  const totalWidth = rows.reduce((sum, row) => sum + row.right - row.left, 0)
  let consumedWidth = 0
  const number = (value) => Number(value.toFixed(6))
  return rows.map((row, index) => {
    const width = (row.right - row.left) / bounds.width
    const left = (row.left - bounds.left) / bounds.width
    const top = index ? (rows[index - 1].bottom + row.top) / 2 : bounds.top
    const bottom = index + 1 < rows.length ? (row.bottom + rows[index + 1].top) / 2 : bounds.bottom
    const start = number((consumedWidth / totalWidth) * 0.8)
    consumedWidth += row.right - row.left
    const end = number((consumedWidth / totalWidth) * 0.8)
    const from = number(left - width * 0.56)
    const to = number(left + width * 1.12)
    const y = number((top - bounds.top) / bounds.height)
    return {
      yValues: start ? `-2;${y};-2;-2` : `${y};-2;-2`,
      height: number((bottom - top) / bounds.height),
      width: number(width * 0.48),
      from,
      values: start ? `${from};${from};${to};${to}` : `${from};${to};${to}`,
      keyTimes: start ? `0;${start};${end};1` : `0;${end};1`
    }
  })
}

export function useLogSheen(root) {
  const filters = shallowRef([])
  const prefix = `log-sheen-${useId()}`
  const entries = new Map()
  let nextId = 0
  let frame = null
  let observer = null
  let mutations = null
  let observedRoot = null
  let fonts = null
  let stopped = false

  function update() {
    frame = null
    if (stopped) return
    const active = new Set(root.value?.querySelectorAll?.('.log-lifecycle-active') ?? [])
    const beganAt = root.value?.querySelector?.('.log-sheen-filter')?.getCurrentTime?.() ?? 0
    for (const [element] of entries) {
      if (!active.has(element)) {
        element.style.removeProperty('--log-sheen-filter')
        entries.delete(element)
      }
    }
    for (const element of active) {
      const lines = measureLines(element)
      if (!lines.length) {
        element.style?.removeProperty('--log-sheen-filter')
        entries.delete(element)
        continue
      }
      const signature = JSON.stringify(lines)
      let entry = entries.get(element)
      if (entry?.signature === signature) continue
      entry = {
        id: entry?.id ?? `${prefix}-${++nextId}`,
        lines,
        signature,
        begin: `${beganAt}s`
      }
      entries.set(element, entry)
      element.style.setProperty('--log-sheen-filter', `url(#${entry.id})`)
    }
    const next = [...entries.values()]
    if (next.length !== filters.value.length || next.some((entry, i) => entry !== filters.value[i]))
      filters.value = next
  }

  function refresh() {
    if (stopped || frame !== null || !globalThis.requestAnimationFrame) return
    frame = requestAnimationFrame(update)
  }

  function bind() {
    if (observedRoot === root.value) return
    observer?.disconnect()
    mutations?.disconnect()
    observedRoot = root.value
    if (root.value?.ownerDocument?.createRange && globalThis.ResizeObserver) {
      observer = new ResizeObserver(refresh)
      observer.observe(root.value)
    }
    const lines = root.value?.querySelector?.('.log-output__lines')
    if (lines && globalThis.MutationObserver) {
      mutations = new MutationObserver(refresh)
      mutations.observe(lines, { childList: true, characterData: true, subtree: true })
    }
    refresh()
  }

  onMounted(() => {
    fonts = root.value?.ownerDocument?.fonts
    fonts?.addEventListener?.('loadingdone', refresh)
    bind()
  })
  watch(root, bind, { flush: 'post' })
  onBeforeUnmount(() => {
    stopped = true
    observer?.disconnect()
    mutations?.disconnect()
    fonts?.removeEventListener?.('loadingdone', refresh)
    if (frame !== null) cancelAnimationFrame(frame)
    for (const [element] of entries) element.style.removeProperty('--log-sheen-filter')
    entries.clear()
  })
  return { filters, refresh }
}
