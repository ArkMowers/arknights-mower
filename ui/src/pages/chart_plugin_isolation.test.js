import { readFileSync } from 'node:fs'
import { describe, expect, it } from 'vitest'

// Cross-route regression: a globally registered ChartDataLabels instance
// paints every raw point in densely sampled mood-line charts as text.
describe('mood chart data-label plugin isolation', () => {
  for (const file of ['RecordPie.vue', 'record.vue']) {
    it(file + ' keeps percentage labels local to Pie charts', () => {
      const vue = readFileSync(new URL('./' + file, import.meta.url), 'utf8')
      const registrations = [...vue.matchAll(/ChartJS\.register\(([\s\S]*?)\)/g)]
      expect(registrations.length).toBe(1)
      expect(registrations[0][1]).not.toContain('ChartDataLabels')
      expect(vue).toMatch(/<Pie[^>]*:plugins="\[ChartDataLabels\]"/)
    })
  }

  it('dense mood lines disable plugin labels even if registered elsewhere', () => {
    const vue = readFileSync(new URL('./RecordLine.vue', import.meta.url), 'utf8')
    expect(vue).toMatch(
      /const chartOptions = \{[\s\S]*?plugins:\s*\{[\s\S]*?datalabels:\s*\{\s*display:\s*false\s*\}/
    )
  })
})
