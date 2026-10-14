import { expect, it, vi } from 'vitest'
import { effectScope, nextTick, reactive } from 'vue'
import MoodLineChart from './MoodLineChart.vue'
vi.mock('vue-chartjs', () => ({ Line: { render: () => null } }))
vi.mock('vue', async (original) => ({
  ...(await original()),
  useSSRContext: () => ({ modules: new Set() })
}))

function setup(type = 'linear') {
  const points =
    type === 'time'
      ? [
          { x: '2026-10-01T00:00:00Z', y: 24 },
          { x: '2026-10-05T00:00:00Z', y: 12 }
        ]
      : [
          { x: 0, y: 24 },
          { x: 345600000, y: 12 }
        ]
  const props = reactive({
    data: { datasets: [{ label: '芬', data: points }] },
    options: { scales: { x: { type }, y: { min: 0, max: 24 } } },
    plugins: []
  })
  const scope = effectScope()
  const page = scope.run(() => MoodLineChart.setup(props, { expose: vi.fn() }))
  return { props, page, scope }
}
it.each(['linear', 'time'])(
  'zooms and navigates %s time while preserving raw observations and mood scale',
  (type) => {
    const { page, props, scope } = setup(type)
    try {
      const original = JSON.stringify(props)
      const start = type === 'time' ? Date.parse('2026-10-01T00:00:00Z') : 0
      page.zoom(0.5)
      expect(page.options.value.scales.x.min).toBe(start + 86400000)
      expect(page.options.value.scales.x.max).toBe(start + 259200000)
      page.pan(1)
      expect(page.options.value.scales.x.max).toBe(start + 345600000)
      page.pan(1)
      expect(page.range.value).toEqual([50, 100])
      page.selectRange([10, 30])
      expect(page.options.value.scales.x.min).toBe(start + 34560000)
      page.zoom(100)
      expect(page.range.value).toEqual([0, 100])
      page.selectRange([50, 50])
      expect(page.width.value).toBeCloseTo(page.minimum.value)
      page.reset()
      expect(page.range.value).toEqual([0, 100])
      expect(page.options.value.scales.y).toEqual({ min: 0, max: 24 })
      expect(JSON.stringify(props)).toBe(original)
    } finally {
      scope.stop()
    }
  }
)
it('preserves zoom and updates visibility in fullscreen, resetting for new observation arrays', async () => {
  const { page, props, scope } = setup()
  try {
    page.line.value = { chart: { setDatasetVisibility: vi.fn(), update: vi.fn() } }
    page.zoom(0.5)
    props.data = { datasets: [{ ...props.data.datasets[0], hidden: true }] }
    await nextTick()
    expect(page.range.value).toEqual([25, 75])
    expect(page.line.value.chart.setDatasetVisibility).toHaveBeenCalledWith(0, false)
    props.data.datasets[0].data = [{ x: 0, y: 2 }]
    await nextTick()
    expect(page.range.value).toEqual([0, 100])
    expect(page.bounds.value).toBeNull()
    props.data.datasets = []
    await nextTick()
    expect(page.bounds.value).toBeNull()
  } finally {
    scope.stop()
  }
})
it('anchors modified wheel zoom to the pointer and leaves ordinary scrolling alone', () => {
  const { page, scope } = setup()
  try {
    page.line.value = {
      chart: {
        width: 500,
        chartArea: { left: 50, right: 450 },
        canvas: { getBoundingClientRect: () => ({ left: 0, width: 500 }) }
      }
    }
    const event = { clientX: 50, deltaY: -1, preventDefault: vi.fn() }
    page.wheel(event)
    expect(event.preventDefault).not.toHaveBeenCalled()
    page.wheel({ ...event, ctrlKey: true })
    expect(event.preventDefault).toHaveBeenCalledOnce()
    expect(page.range.value).toEqual([0, 80])
  } finally {
    scope.stop()
  }
})
