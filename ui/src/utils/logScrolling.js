import { logLayoutZoom } from './logLayout'

const rowsOf = (container) => Array.from(container?.querySelectorAll?.('[data-log-anchor]') ?? [])
const keyOf = (row) => row.getAttribute('data-log-anchor')

export function logScrollEnd(container) {
  return Math.max(0, container.scrollHeight - container.clientHeight)
}

export function isLogAtBottom(container) {
  return logScrollEnd(container) - container.scrollTop <= 3
}

export function captureLogScroll(container) {
  if (!container) return null
  const top = container.getBoundingClientRect().top
  const rows = rowsOf(container)
  let first = rows.findIndex((row) => row.getBoundingClientRect().bottom > top)
  if (first < 0) first = rows.length
  return {
    scrollTop: container.scrollTop,
    atBottom: isLogAtBottom(container),
    anchors: rows.slice(first).map((row) => ({
      key: keyOf(row),
      offset: row.getBoundingClientRect().top - top
    }))
  }
}

export function scrollLogToBottom(container) {
  if (!container) return
  const target = logScrollEnd(container)
  if (Math.abs(container.scrollTop - target) > 0.5) container.scrollTop = target
}

export function restoreLogScroll(container, snapshot, autoScroll = true) {
  if (!container || !snapshot) return
  if (autoScroll && snapshot.atBottom) {
    scrollLogToBottom(container)
    return
  }
  const byKey = new Map(rowsOf(container).map((row) => [keyOf(row), row]))
  const anchor = snapshot.anchors.find((entry) => byKey.has(entry.key))
  const top = container.getBoundingClientRect().top
  const target = anchor
    ? container.scrollTop +
      (byKey.get(anchor.key).getBoundingClientRect().top - top - anchor.offset) /
        logLayoutZoom(container)
    : snapshot.scrollTop
  const bounded = Math.min(Math.max(0, target), logScrollEnd(container))
  if (Math.abs(container.scrollTop - bounded) > 0.5) container.scrollTop = bounded
}
