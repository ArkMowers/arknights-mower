import { logLayoutZoom } from './logLayout'

const rowsOf = (container) =>
  Array.from(
    container?.querySelectorAll?.(
      '.log-line[data-log-key]:not(.log-line--source-only), .log-facility-heading[data-log-key], .log-recruit-slot[data-log-key]'
    ) ?? []
  )
const keyOf = (row) => row.getAttribute('data-log-key')

export function captureLogScroll(container) {
  if (!container) return null
  const top = container.getBoundingClientRect().top
  const rows = rowsOf(container)
  let first = rows.findIndex((row) => row.getBoundingClientRect().bottom > top)
  if (first < 0) first = rows.length
  return {
    scrollTop: container.scrollTop,
    atBottom: container.scrollHeight - container.clientHeight - container.scrollTop <= 3,
    lastKey: rows.length ? keyOf(rows.at(-1)) : null,
    anchors: rows.slice(first).map((row) => ({
      key: keyOf(row),
      offset: row.getBoundingClientRect().top - top
    }))
  }
}

export function scrollLogToBottom(container) {
  if (!container) return
  const target = Math.max(0, container.scrollHeight - container.clientHeight)
  if (Math.abs(container.scrollTop - target) > 0.5) container.scrollTop = target
}

export function restoreLogScroll(container, snapshot, autoScroll = true) {
  if (!container || !snapshot) return
  const rows = rowsOf(container)
  if (autoScroll && snapshot.atBottom) {
    scrollLogToBottom(container)
    return
  }
  const byKey = new Map(rows.map((row) => [keyOf(row), row]))
  const anchor = snapshot.anchors.find((entry) => byKey.has(entry.key))
  const top = container.getBoundingClientRect().top
  const target = anchor
    ? container.scrollTop +
      (byKey.get(anchor.key).getBoundingClientRect().top - top - anchor.offset) /
        logLayoutZoom(container)
    : snapshot.scrollTop
  const bounded = Math.max(0, Math.min(target, container.scrollHeight - container.clientHeight))
  if (Math.abs(container.scrollTop - bounded) > 0.5) container.scrollTop = bounded
}
