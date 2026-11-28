import { describe, expect, it, vi } from 'vitest'
import { createSSRApp, h, ref } from 'vue'
import { renderToString } from 'vue/server-renderer'
import OperatorStatistics from './OperatorStatistics.vue'

vi.mock('naive-ui', async (original) => {
  const slot = (_props, { slots }) => h('div', slots.default?.())
  return {
    ...(await original()),
    useThemeVars: () => ref({}),
    NTabs: slot,
    NTabPane: slot,
    NSpace: slot,
    NCheckboxGroup: slot,
    NCheckbox: () => null,
    NDataTable: () => null
  }
})

describe('干员统计精二率', () => {
  it.each([
    [
      { 6: { owned: 6, elite2: 3, max_phase: 2 }, 3: { owned: 12, elite2: 0, max_phase: 1 } },
      '50.0%'
    ],
    [{ 3: { owned: 5, elite2: 0, max_phase: 1 } }, '0%'],
    [{}, '0%']
  ])('仅统计可精二的已拥有干员，分母为零时显示零', async (rarities, percentage) => {
    const html = await renderToString(
      createSSRApp(OperatorStatistics, { statistics: { rarities } })
    )
    expect(html.match(/精二干员[\s\S]*?<small[^>]*>([^<]*)<\/small>/)?.[1]).toBe(percentage)
  })
})
