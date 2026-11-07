import { describe, expect, it } from 'vitest'
import { captureLogScroll, restoreLogScroll } from './logScrolling'

function viewport(ids = Array.from({ length: 100 }, (_, index) => index + 1)) {
  let position = 100
  const writes = []
  const state = { ids, height: 20, leading: 0, trailing: 0, zoom: 1 }
  const container = {
    clientHeight: 200,
    ownerDocument: {
      documentElement: {
        style: {
          get zoom() {
            return state.zoom
          }
        }
      }
    },
    get scrollHeight() {
      return state.ids.length * state.height + state.leading + state.trailing
    },
    get scrollTop() {
      return position
    },
    set scrollTop(value) {
      position = value
      writes.push(value)
    },
    getBoundingClientRect: () => ({ top: 40 }),
    querySelectorAll: () =>
      state.ids.map((id, index) => ({
        getAttribute: () => `id:${id}`,
        getBoundingClientRect: () => ({
          top: 40 + (state.leading + index * state.height - position) * state.zoom,
          bottom: 40 + (state.leading + (index + 1) * state.height - position) * state.zoom
        })
      }))
  }
  return {
    container,
    state,
    writes,
    scroll: (value) => {
      position = value
    }
  }
}

describe('log reading position', () => {
  it.each(['log-facility-heading', 'log-recruit-slot'])(
    'anchors visible %s summaries and excludes their hidden source records',
    (className) => {
      let summaryTop = 30
      const heading = {
        getAttribute: () => 'facility:1',
        getBoundingClientRect: () => ({ top: summaryTop, bottom: summaryTop + 38 })
      }
      const hidden = {
        getAttribute: () => 'terminal:1',
        getBoundingClientRect: () => ({ top: 40, bottom: 41 })
      }
      const page = viewport()
      page.container.querySelectorAll = (selector) => {
        const rows = selector.includes(className) ? [heading] : []
        if (!selector.includes(':not(.log-line--source-only)')) rows.push(hidden)
        return rows
      }
      const snapshot = captureLogScroll(page.container)
      expect(snapshot.anchors).toEqual([{ key: 'facility:1', offset: -10 }])
      expect(snapshot.lastKey).toBe('facility:1')
      summaryTop = 54
      restoreLogScroll(page.container, snapshot)
      expect(page.container.scrollTop).toBe(124)
    }
  )
  it('keeps following the bottom when an in-place summary changes height without a new visible key', () => {
    const page = viewport()
    page.scroll(1800)
    const snapshot = captureLogScroll(page.container)
    page.state.trailing = 24
    restoreLogScroll(page.container, snapshot)
    expect(page.container.scrollTop).toBe(1824)
  })
  it('does not write scrollTop for an equivalent task or line refresh', () => {
    const page = viewport()
    const snapshot = captureLogScroll(page.container)
    page.state.ids = [...page.state.ids]
    restoreLogScroll(page.container, snapshot)
    expect(page.container.scrollTop).toBe(100)
    expect(page.writes).toEqual([])
  })

  it.each([1, 0.8, 1.25])('keeps the reading anchor through eviction at zoom %s', (zoom) => {
    const page = viewport()
    page.state.zoom = zoom
    page.scroll(107)
    const snapshot = captureLogScroll(page.container)
    expect(snapshot.anchors[0].key).toBe('id:6')
    expect(snapshot.anchors[0].offset).toBeCloseTo(-7 * zoom)
    page.state.ids = [...page.state.ids.slice(2), 101, 102]
    restoreLogScroll(page.container, snapshot)
    expect(page.container.scrollTop).toBeCloseTo(67)
    expect(captureLogScroll(page.container).anchors[0].offset).toBeCloseTo(-7 * zoom)
  })

  it('preserves the reading anchor when row heights or group dividers change', () => {
    const page = viewport()
    page.scroll(107)
    const snapshot = captureLogScroll(page.container)
    page.state.height = 30
    page.state.leading = 24
    restoreLogScroll(page.container, snapshot)
    expect(page.container.scrollTop).toBe(181)
    expect(captureLogScroll(page.container).anchors[0]).toEqual({ key: 'id:6', offset: -7 })
  })

  it('follows appended logs only when enabled and previously at the bottom', () => {
    const page = viewport()
    page.scroll(1800)
    let snapshot = captureLogScroll(page.container)
    page.state.ids.push(101)
    restoreLogScroll(page.container, snapshot)
    expect(page.container.scrollTop).toBe(1820)

    snapshot = captureLogScroll(page.container)
    page.state.ids.push(102)
    restoreLogScroll(page.container, snapshot, false)
    expect(page.container.scrollTop).toBe(1820)

    page.scroll(100)
    snapshot = captureLogScroll(page.container)
    page.state.ids.push(103)
    restoreLogScroll(page.container, snapshot)
    expect(page.container.scrollTop).toBe(100)

    page.scroll(1860)
    snapshot = captureLogScroll(page.container)
    page.state.ids.push(104)
    restoreLogScroll(page.container, snapshot)
    expect(page.container.scrollTop).toBe(1880)
  })
})
