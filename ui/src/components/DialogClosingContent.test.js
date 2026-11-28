import { describe, expect, it, vi } from 'vitest'
import { createSSRApp, defineComponent, getCurrentInstance, h } from 'vue'
import { renderToString } from 'vue/server-renderer'
import HelpDialog from './HelpDialog.vue'

vi.mock('virtual:mower-changelog', () => ({
  default: '# CHANGELOG\n\n## 1.0.0\n\n- 新的版本说明'
}))

// n-modal 的 show 变为 false 后，弹窗还要淡出一段时间才移除。替身无论 show 是什么都画出标题和
// 正文，并记下 show 和正文高度，用来检查淡出期间弹窗里显示的内容。
vi.mock('naive-ui', async (original) => {
  const library = await original()
  const modal = defineComponent({
    props: ['show', 'title', 'contentStyle'],
    setup(props, { slots }) {
      return () =>
        h(
          'dialog',
          { 'data-show': String(props.show), 'data-height': props.contentStyle?.height },
          [h('header', props.title), h('main', slots.default?.())]
        )
    }
  })
  const passThrough = defineComponent({
    setup:
      (_, { slots }) =>
      () =>
        slots.default?.()
  })
  return {
    ...library,
    ...Object.fromEntries(
      Object.keys(library)
        .filter((name) => /^N[A-Z]/.test(name))
        .map((name) => [name, passThrough])
    ),
    NModal: modal
  }
})

/** 先按 props 完成组件的 setup，再执行 close 清空打开弹窗的状态，画出此时（淡出期间）的弹窗。 */
async function renderWhileClosing(component, props, close) {
  const app = createSSRApp(
    {
      ...component,
      async setup(_props, context) {
        const instance = getCurrentInstance()
        const bindings = component.setup(instance.props, context)
        await close(instance.props)
        return bindings
      }
    },
    props
  )
  const html = await renderToString(app)
  const dialog = html.match(/<dialog[^>]*>[\s\S]*?<\/dialog>/)[0]
  const part = (tag) => dialog.match(new RegExp(`<${tag}>([\\s\\S]*?)</${tag}>`))?.[1] ?? ''
  return {
    show: dialog.match(/data-show="([^"]*)"/)[1],
    height: dialog.match(/data-height="([^"]*)"/)?.[1],
    title: part('header'),
    content: part('main')
  }
}

describe('弹窗关闭时淡出期间保留关闭前的内容', () => {
  it('关于 Mower 淡出时仍显示标题和版本信息', async () => {
    const dialog = await renderWhileClosing(
      HelpDialog,
      { section: 'about', version: '4.1.6' },
      (props) => {
        props.section = ''
      }
    )
    expect(dialog.show).toBe('false')
    expect(dialog.title).toBe('关于 Mower')
    expect(dialog.content).toContain('4.1.6')
  })

  it('更新日志读取中占用与读完后同样的高度', async () => {
    const dialog = await renderWhileClosing(HelpDialog, { section: 'changelog' }, () => {})
    expect(dialog.show).toBe('true')
    expect(dialog.height).toBe('65dvh')
    expect(dialog.content).toContain('正在加载更新日志')
    expect(dialog.content).toContain('skeleton-bone')
  })

  it('更新日志读完后淡出时不会换成关于 Mower，高度不变', async () => {
    const dialog = await renderWhileClosing(HelpDialog, { section: 'changelog' }, async (props) => {
      await vi.dynamicImportSettled()
      props.section = ''
    })
    expect(dialog.show).toBe('false')
    expect(dialog.height).toBe('65dvh')
    expect(dialog.title).toBe('更新日志')
    expect(dialog.content).toContain('新的版本说明')
    expect(dialog.content).not.toContain('正在加载更新日志')
  })
})
