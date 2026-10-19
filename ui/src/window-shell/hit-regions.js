import { nextTick } from 'vue'

const REGION_SELECTOR = '[data-window-drag-region], [data-window-resize-edge]'
const RESIZE_EDGES = new Set([
  'left',
  'right',
  'top',
  'bottom',
  'top-left',
  'top-right',
  'bottom-left',
  'bottom-right'
])
const MAX_REGIONS = 128

function subtractRectangle(region, occupied) {
  const left = Math.max(region.x, occupied.x)
  const top = Math.max(region.y, occupied.y)
  const right = Math.min(region.x + region.width, occupied.x + occupied.width)
  const bottom = Math.min(region.y + region.height, occupied.y + occupied.height)
  if (left >= right || top >= bottom) return [region]
  return [
    { ...region, height: top - region.y },
    { ...region, y: bottom, height: region.y + region.height - bottom },
    { ...region, y: top, width: left - region.x, height: bottom - top },
    {
      ...region,
      x: right,
      y: top,
      width: region.x + region.width - right,
      height: bottom - top
    }
  ].filter(({ width, height }) => width > 0 && height > 0)
}

export function collectWindowHitRegions(windowObject) {
  const documentObject = windowObject?.document
  const width = documentObject?.documentElement?.clientWidth || windowObject?.innerWidth || 0
  const height = documentObject?.documentElement?.clientHeight || windowObject?.innerHeight || 0
  const elements = Array.from(documentObject?.querySelectorAll?.(REGION_SELECTOR) || []).slice(
    0,
    MAX_REGIONS
  )
  const candidates = elements.flatMap((element) => {
    const edge = element.getAttribute('data-window-resize-edge')
    if (edge !== null && !RESIZE_EDGES.has(edge)) return []
    const rect = element.getBoundingClientRect()
    if (![rect.left, rect.top, rect.width, rect.height].every(Number.isFinite)) return []
    const x = Math.max(0, rect.left)
    const y = Math.max(0, rect.top)
    const right = Math.min(width, rect.left + rect.width)
    const bottom = Math.min(height, rect.top + rect.height)
    if (right <= x || bottom <= y) return []
    return [
      {
        kind: edge === null ? 'move' : 'resize',
        ...(edge === null ? {} : { edge }),
        x,
        y,
        width: right - x,
        height: bottom - y
      }
    ]
  })
  candidates.sort((a, b) => {
    const priority = ({ kind, edge }) => (kind === 'move' ? 2 : edge.includes('-') ? 0 : 1)
    return priority(a) - priority(b)
  })
  const regions = []
  for (const candidate of candidates) {
    let remaining = [candidate]
    for (const occupied of regions) {
      remaining = remaining.flatMap((region) => subtractRectangle(region, occupied))
      if (remaining.length + regions.length > MAX_REGIONS) {
        remaining = []
        break
      }
    }
    regions.push(...remaining.slice(0, MAX_REGIONS - regions.length))
    if (regions.length === MAX_REGIONS) break
  }
  return { payload: { width, height, regions }, elements }
}

export function createWindowHitRegionSync({ windowObject, send }) {
  let enabled = false
  let disposed = false
  let queued = false
  let sending = false
  let observer = null
  let observed = new Set()
  let lastPayload = null
  let lastDimensions = null
  let pendingPayload = null

  async function drain() {
    sending = true
    try {
      while (pendingPayload && !disposed) {
        const payload = pendingPayload
        pendingPayload = null
        const serialized = JSON.stringify(payload)
        if (serialized === lastPayload) continue
        try {
          if ((await send(payload)) === true && !disposed) lastPayload = serialized
        } catch {
          lastPayload = null
        }
      }
    } finally {
      sending = false
    }
  }

  function submit(payload) {
    pendingPayload = payload
    if (!sending) void drain()
  }

  async function flush() {
    await nextTick()
    if (!enabled || disposed) {
      queued = false
      return
    }
    queued = false
    const { payload, elements } = collectWindowHitRegions(windowObject)
    const targets = new Set([windowObject?.document?.documentElement, ...elements].filter(Boolean))
    for (const target of observed) {
      if (!targets.has(target)) observer?.unobserve(target)
    }
    for (const target of targets) {
      if (!observed.has(target)) observer?.observe(target)
    }
    observed = targets
    if (payload.width <= 0 || payload.height <= 0) return
    lastDimensions = { width: payload.width, height: payload.height }
    submit(payload)
  }

  function schedule() {
    if (!enabled || disposed || queued) return
    queued = true
    void flush()
  }

  function stopObserving() {
    windowObject?.removeEventListener?.('resize', schedule)
    observer?.disconnect()
    observer = null
    observed.clear()
  }

  function setEnabled(value) {
    if (disposed || enabled === value) return
    enabled = value
    if (enabled) {
      if (windowObject?.ResizeObserver) observer = new windowObject.ResizeObserver(schedule)
      windowObject?.addEventListener?.('resize', schedule)
      schedule()
    } else {
      stopObserving()
      if (lastDimensions) submit({ ...lastDimensions, regions: [] })
    }
  }

  function dispose() {
    disposed = true
    enabled = false
    pendingPayload = null
    stopObserving()
  }

  return { schedule, setEnabled, dispose }
}
