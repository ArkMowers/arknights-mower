import { describe, expect, it, vi } from 'vitest'
import { createSSRApp, effectScope } from 'vue'
import { renderToString } from 'vue/server-renderer'
import { setup as setupCssRenderSsr } from '@css-render/vue3-ssr'
import GrowthHero from './GrowthHero.vue'

vi.mock('vue', async (original) => ({
  ...(await original()),
  useSSRContext: () => ({ modules: new Set() })
}))

describe('当前训练真实状态', () => {
  it.each([
    ['arranging', '安排中', '正在安排'],
    ['training', '训练中', '正在训练'],
    ['waiting_collect', '待收取', '本阶段训练已完成，等待收取']
  ])('%s 保留对应状态和说明', (status, label, text) => {
    const scope = effectScope()
    const component = scope.run(() =>
      GrowthHero.setup(
        {
          operators: [],
          training: {
            entry: { status },
            op: { name: '测试干员' },
            rec: { skill_name: '测试技能', current_level: 1 },
            target: 3
          }
        },
        { expose: vi.fn(), emit: vi.fn() }
      )
    )
    expect(component.trainingStatusLabel.value).toBe(label)
    expect(component.stateLine.value).toContain(text)
    if (status !== 'training') expect(component.stateLine.value).not.toContain('正在训练')
    scope.stop()
  })
})

describe('养成自动化开关', () => {
  it.each([false, true])('自动合成为 %s 时控制两项依赖开关', async (autoCrafting) => {
    const app = createSSRApp(GrowthHero, { autoCrafting })
    setupCssRenderSsr(app)
    const html = await renderToString(app)
    const switches = [
      ...html.matchAll(/<[^>]*aria-label="(?:自动合成|自动专精|MAA 干员培养)"[^>]*>/g)
    ].map(([tag]) => tag)
    expect(switches).toHaveLength(3)
    expect(switches[0]).toContain('aria-label="自动合成"')
    expect(switches[0]).not.toContain('n-switch--disabled')
    for (const [index, label] of ['自动专精', 'MAA 干员培养'].entries()) {
      expect(switches[index + 1]).toContain(`aria-label="${label}"`)
      expect(switches[index + 1].includes('n-switch--disabled')).toBe(!autoCrafting)
    }
  })
})
