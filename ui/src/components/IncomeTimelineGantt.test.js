import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { nextTick } from 'vue'
import ScheduleTimelineGantt from '@/riic/vendor/components/workbench/ScheduleTimelineGantt.vue'

const hooks = vi.hoisted(() => ({}))
vi.mock('vue', async (original) => ({
  ...(await original()),
  useSSRContext: () => ({ modules: new Set() }),
  onBeforeUnmount: (callback) => (hooks.unmount = callback)
}))
let chart, browser
const mouse = (x, y = 0) => ({
  button: 0,
  clientX: x,
  clientY: y,
  stopPropagation: vi.fn(),
  preventDefault: vi.fn()
})
const move = (x) => {
  const event = new Event('mousemove')
  Object.assign(event, { clientX: x })
  browser.dispatchEvent(event)
}
beforeEach(() => {
  browser = Object.assign(new EventTarget(), { innerWidth: 662, innerHeight: 827 })
  vi.stubGlobal('window', browser)
  chart = ScheduleTimelineGantt.setup(
    { report: { observedHours: 672 }, initialWindowHours: 24, initiallyCollapsed: false },
    { expose: vi.fn(), emit: vi.fn() }
  )
  chart.overviewTrackRef.value = { getBoundingClientRect: () => ({ left: 10, width: 840 }) }
})
afterEach(() => {
  hooks.unmount()
  vi.unstubAllGlobals()
})

it('drags a 24-hour window through the full 28-day period at CSS zoom 1.25', () => {
  chart.handleOverviewThumbMouseDown(mouse(10))
  move(40)
  expect(chart.customWindowStart.value).toBe(24)
  expect(chart.customWindowEnd.value).toBe(48)
  browser.dispatchEvent(new Event('mouseup'))
  move(70)
  expect(chart.customWindowStart.value).toBe(24)
})
it('clicks to the middle and clamps dragging to both ends without changing duration', () => {
  chart.handleOverviewTrackMouseDown(mouse(430))
  expect(chart.customWindowStart.value).toBe(324)
  expect(chart.customWindowEnd.value).toBe(348)
  move(2000)
  expect(chart.customWindowStart.value).toBe(648)
  expect(chart.customWindowEnd.value).toBe(672)
  move(-2000)
  expect(chart.customWindowStart.value).toBe(0)
  expect(chart.customWindowEnd.value).toBe(24)
})
it('shares the navigation range with existing duration and boundary controls', () => {
  chart.jumpToEnd()
  expect(chart.customWindowStart.value).toBe(648)
  chart.setWindowDuration(72)
  expect(chart.windowDuration.value).toBe(72)
  expect(chart.customWindowEnd.value).toBeLessThanOrEqual(672)
  chart.jumpToStart()
  expect(chart.customWindowStart.value).toBe(0)
  expect(chart.customWindowEnd.value).toBe(72)
})
it('stops active dragging on collapse and unmount', async () => {
  chart.handleOverviewThumbMouseDown(mouse(10))
  chart.isTimelineExpanded.value = false
  await nextTick()
  move(40)
  expect(chart.customWindowStart.value).toBe(0)
  chart.isTimelineExpanded.value = true
  chart.handleOverviewThumbMouseDown(mouse(10))
  hooks.unmount()
  move(40)
  expect(chart.customWindowStart.value).toBe(0)
})
it.each([1, 1.25, 2])(
  'keeps hovered operator details inside the viewport at zoom %s',
  async (zoom) => {
    chart.intervalTooltipRef.value = {
      offsetWidth: 200,
      getBoundingClientRect: () => ({ width: 200 * zoom, height: 120 * zoom })
    }
    chart.handleIntervalHover({ operatorName: '芬' }, mouse(650, 800))
    await nextTick()
    expect(chart.tooltipX.value * zoom).toBe(650 - 200 * zoom - 12)
    expect(chart.tooltipY.value * zoom).toBe(800 - 120 * zoom - 12)
    chart.handleMouseMove({ ...mouse(100, 200), currentTarget: chart.overviewTrackRef.value })
    await nextTick()
    expect(chart.tooltipX.value * zoom).toBe(112)
    expect(chart.tooltipY.value * zoom).toBe(212)
  }
)
it('positions event details with the same viewport bounds', async () => {
  chart.eventTooltipRef.value = {
    offsetWidth: 200,
    getBoundingClientRect: () => ({ width: 250, height: 150 })
  }
  chart.handleEventHover({ label: '换班' }, mouse(650, 800))
  await nextTick()
  expect(chart.tooltipX.value * 1.25).toBe(388)
  expect(chart.tooltipY.value * 1.25).toBe(638)
})
