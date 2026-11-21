import { expect, it, vi } from 'vitest'
import { createSSRApp, h } from 'vue'
import { renderToString } from 'vue/server-renderer'
import IncomeDiagnostics from './IncomeDiagnostics.vue'

vi.mock('vue', async (original) => ({
  ...(await original()),
  useSSRContext: () => ({ modules: new Set() })
}))

it('shows failures and historical issues while omitting model explanations', async () => {
  const html = await renderToString(
    createSSRApp({
      render: () =>
        h(IncomeDiagnostics, {
          diagnostics: [
            { code: 'SIMULATION_EVENT_LIMIT', message: '达到 200000 个积分区间，结果未完成' },
            { code: 'FINITE_INVENTORY_MODEL', message: '库存从预热开始连续扣料' },
            {
              code: 'group-blocked',
              message:
                'group:深海: insufficient available candidates or beds; original occupants retained'
            }
          ]
        })
    })
  )
  expect(html).toContain('未完成的原因')
  expect(html).toContain('计算次数上限（200,000 次）')
  expect(html).not.toContain('模型说明')
  expect(html).toContain('调度与校验记录（1 条）')
  expect(html).not.toContain('库存从预热开始连续扣料')
  expect(html).not.toContain('insufficient available candidates')
  expect(html).toContain('绑组“深海”曾因可用替班或宿舍床位不足')
})
