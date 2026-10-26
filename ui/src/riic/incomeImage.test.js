import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { renderIncomeImage } from './incomeImage'

let canvases
beforeEach(() => {
  canvases = []
  vi.stubGlobal(
    'Image',
    class {
      naturalWidth = 490
      naturalHeight = 300
      decode = vi.fn(async () => {})
    }
  )
  vi.stubGlobal('document', {
    createElement: () => {
      const canvas = { width: 0, height: 0 }
      const context = {
        font: '',
        drawImage: vi.fn(),
        fillRect: vi.fn(),
        fillText: vi.fn(),
        measureText: (text) => ({
          width: Array.from(text).length * Number(context.font.match(/([\d.]+)px/)?.[1] ?? 10) * 0.6
        }),
        getImageData: () => ({ data: new Uint8ClampedArray(canvas.width * canvas.height * 4) })
      }
      canvas.getContext = () => context
      canvas.context = context
      canvas.toBlob = (done) => done(new Blob(['image'], { type: 'image/jpeg' }))
      canvases.push(canvas)
      return canvas
    }
  })
  vi.spyOn(URL, 'createObjectURL').mockReturnValue('blob:test')
  vi.spyOn(URL, 'revokeObjectURL').mockImplementation(() => {})
})
afterEach(() => {
  vi.unstubAllGlobals()
  vi.restoreAllMocks()
})
const plan = {
  default: 'plan1',
  conf: {},
  backup_plans: [],
  plan1: { room_1_1: { name: '制造站', product: 'exp', plans: [] } }
}
const settings = { weightMode: 'mower', mowerAlgorithm: 0, droneRoom: '' }
const result = () => ({
  observedHours: 48,
  summary: {
    totalScore82: 75,
    exp: 1000,
    valuation: {
      completedScore: { daily: 100, total: 200 },
      opening: { amounts: { exp: 500 }, score: { daily: 75, total: 150 } },
      closing: { amounts: { exp: 250 }, score: { daily: 50, total: 100 } },
      adjustment: { amounts: { exp: -250 }, score: { daily: -25, total: -50 } }
    }
  }
})
it('renders the saved valuation and signed contribution while keeping actual output badges', async () => {
  const saved = result(),
    before = structuredClone(saved)
  const image = await renderIncomeImage(new Blob(['original']), saved, settings, plan)
  expect(image.type).toBe('image/jpeg')
  const text = canvases[0].context.fillText.mock.calls.map(([text]) => text)
  expect(text).toContain('日均加权收益（含在制品估值）')
  expect(text).toContain('75')
  expect(text).toContain('1k')
  expect(text.join('')).toContain('估值净调整（日均）-25')
  expect(saved).toEqual(before)
})
it('grows the header for wrapped valuation and long remarks without crossing the resource column', async () => {
  await renderIncomeImage(new Blob(['original']), result(), settings, plan)
  const shortHeight = canvases[0].height
  await renderIncomeImage(
    new Blob(['original']),
    result(),
    settings,
    plan,
    'dark',
    {},
    { author: '作者'.repeat(20), remarks: '很长的排班适用条件与说明'.repeat(25) }
  )
  const long = canvases[2]
  expect(long.height).toBeGreaterThan(shortHeight)
  const annotations = long.context.fillText.mock.calls.filter(([, x, y]) => x === 14 && y >= 50)
  expect(annotations.length).toBeGreaterThan(3)
  expect(annotations.map(([text]) => text).join('')).toContain('含在制品估值')
  expect(annotations.every(([text]) => long.context.measureText(text).width <= 258)).toBe(true)
})
it('exports a legacy score without inventing valuation or changing output', async () => {
  const saved = result()
  delete saved.summary.valuation
  await renderIncomeImage(new Blob(['original']), saved, settings, plan)
  const text = canvases[0].context.fillText.mock.calls.map(([text]) => text)
  expect(text).toContain('日均加权收益')
  expect(text).toContain('75')
  expect(text).toContain('1k')
  expect(text.join('')).not.toContain('在制品')
  expect(saved.summary).not.toHaveProperty('valuation')
})
