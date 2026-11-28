import { describe, expect, it } from 'vitest'
import { createSSRApp, h } from 'vue'
import { renderToString } from 'vue/server-renderer'
import LoadingSkeleton from './LoadingSkeleton.vue'

function render(props, shapes) {
  return renderToString(createSSRApp({ render: () => h(LoadingSkeleton, props, () => shapes) }))
}

describe('loading skeleton', () => {
  it('announces the label and makes the placeholder shapes inert', async () => {
    const html = await render({ label: '正在读取仓库数据', class: 'tier-groups-list' }, [
      h('span', { class: 'skeleton-bone skeleton-line' })
    ])
    // 页面给的布局 class 落在外壳上，占位块直接按页面的布局排列。
    expect(html).toMatch(
      /^<div class="loading-skeleton tier-groups-list" role="status" aria-busy="true">/
    )
    expect(html).toContain('<span class="loading-skeleton__label">正在读取仓库数据</span>')
    // 插槽内容在渲染结果里带有片段注释，比较前去掉。
    expect(html.replace(/<!--[[\]]-->/g, '')).toContain(
      '<div class="loading-skeleton__shapes" inert><span class="skeleton-bone skeleton-line"></span></div>'
    )
  })
})
