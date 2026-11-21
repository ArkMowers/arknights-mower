import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { createRenderer, createSSRApp, h, nextTick, reactive, ref, ssrContextKey } from 'vue'
import { renderToString } from 'vue/server-renderer'
import DailyMission from './DailyMission.vue'

const state = vi.hoisted(() => ({ config: null, buttons: [] }))
vi.mock('@/stores/config', () => ({ useConfigStore: () => state.config }))
vi.mock('pinia', async () => ({ storeToRefs: (await import('vue')).toRefs }))
vi.mock('naive-ui', async () => {
  const { h } = await import('vue')
  return Object.fromEntries(
    ['NCard', 'NFlex', 'NCheckbox', 'NTabs', 'NTabPane', 'NButton', 'NDivider'].map((name) => [
      name,
      {
        inheritAttrs: false,
        props: ['title', 'checked', 'disabled', 'loading'],
        setup(props, { attrs, slots }) {
          if (name === 'NButton') state.buttons.push({ props, attrs })
          return () =>
            h(name === 'NButton' ? 'button' : 'div', { ...attrs, disabled: props.disabled }, [
              props.title,
              slots.default?.()
            ])
        }
      }
    ])
  )
})
vi.mock('./HelpText.vue', () => ({
  default: {
    props: ['label'],
    setup:
      (props, { slots }) =>
      () =>
        h('aside', { 'aria-label': props.label }, slots.default?.())
  }
}))

let app
const axios = { get: vi.fn() }

beforeEach(() => {
  state.buttons = []
  state.config = reactive({
    check_mail_enable: true,
    event_sign_in_enable: false,
    report_enable: true,
    skland_enable: true,
    skland_info: [
      {
        account: 'example-account',
        password: 'example-password',
        arknights_isCheck: true,
        sign_in_official: true,
        sign_in_bilibili: true,
        endfield_isCheck: true,
        sign_in_endfield_official: true,
        sign_in_endfield_bilibili: true
      }
    ]
  })
})

afterEach(() => {
  app?.unmount()
  app = null
  vi.clearAllMocks()
})

async function render(props = {}) {
  const serverApp = createSSRApp(DailyMission, props)
  serverApp.provide('axios', axios)
  return renderToString(serverApp)
}

function regionTag(html, task) {
  return html.match(new RegExp(`<div\\b[^>]*data-daily-task="${task}"[^>]*>`))?.[0]
}

function mountEditor(selected = ref('skland')) {
  const renderer = createRenderer({
    createElement: (tag) => ({ tag, children: [], props: {}, style: {} }),
    createText: (text) => ({ text }),
    createComment: () => ({}),
    setText: (node, text) => (node.text = text),
    setElementText: (node, text) => (node.text = text),
    parentNode: (node) => node.parent,
    nextSibling: () => null,
    patchProp: (node, key, previous, next) => (node.props[key] = next),
    insert(node, parent) {
      node.parent = parent
      parent.children.push(node)
    },
    remove(node) {
      const siblings = node.parent.children
      siblings.splice(siblings.indexOf(node), 1)
    }
  })
  let component
  let setups = 0
  const Subject = {
    ...DailyMission,
    render: () => null,
    setup(props, context) {
      setups += 1
      component = DailyMission.setup(props, context)
      return component
    }
  }
  app = renderer.createApp({ render: () => h(Subject, { task: selected.value }) })
  app.provide(ssrContextKey, { modules: new Set() })
  app.provide('axios', axios)
  app.mount({ children: [] })
  return {
    get component() {
      return component
    },
    get setups() {
      return setups
    }
  }
}

describe('daily task editors', () => {
  it('keeps sign-in accounts available when the task checklist owns the enable switch', async () => {
    const html = await render({ task: 'skland', showEnable: false })
    expect(html).toContain('example-account')
    expect(html).toContain('官服签到')
    expect(html).toContain('测试签到')
    expect(html).toContain('aria-label="森空岛签到说明"')
    expect(html).toContain('检查是否勾选了未绑定的区服/游戏')
    expect(html).toContain('tmp/skland.csv')
    expect(html.replace(/<!--[\s\S]*?-->/g, '')).not.toContain('class="item"')
    expect(state.config.skland_enable).toBe(true)
    expect(state.config.skland_info[0].sign_in_official).toBe(true)
    expect(axios.get).not.toHaveBeenCalled()
  })

  it('offers account setup instead of empty tabs and a disabled test', async () => {
    state.config.skland_info = []
    const configureAccounts = vi.fn()
    const html = await render({
      task: 'skland',
      showEnable: false,
      onConfigureAccounts: configureAccounts
    })

    expect(html).toContain('尚未添加森空岛账号')
    expect(html).toContain('添加森空岛账号')
    expect(html).not.toContain('明日方舟终末地')
    expect(html).not.toContain('测试签到')
    expect(state.buttons).toHaveLength(1)
    state.buttons[0].attrs.onClick()
    expect(configureAccounts).toHaveBeenCalledOnce()
    expect(state.config.skland_info).toEqual([])
    expect(axios.get).not.toHaveBeenCalled()
  })

  it('keeps callers with enable controls free of an unhandled account setup action', async () => {
    state.config.skland_info = []
    const html = await render()

    expect(html).toContain('尚未添加森空岛账号')
    expect(html).not.toContain('>添加森空岛账号<')
    expect(state.buttons).toHaveLength(0)
  })

  it('keeps the existing combined editor as the default', async () => {
    const html = await render()
    expect(html).toContain('每日任务')
    for (const task of ['skland', 'mail', 'event-sign-in', 'report']) {
      expect(regionTag(html, task)).toBeTruthy()
      expect(regionTag(html, task)).not.toContain('display:none')
    }
    expect(html).toContain('测试签到')
    expect(html).toContain('领取邮件')
    expect(html.indexOf('data-daily-task="event-sign-in"')).toBeGreaterThan(
      html.indexOf('data-daily-task="mail"')
    )
    expect(html.indexOf('data-daily-task="event-sign-in"')).toBeLessThan(
      html.indexOf('data-daily-task="report"')
    )
    expect(html).toContain('活动签到说明')
    expect(state.config.event_sign_in_enable).toBe(false)
    expect(html).toContain('读取基报')
    expect(axios.get).not.toHaveBeenCalled()
  })

  it('retains the mail cleanup setting and its searchable editor when the checklist owns enablement', async () => {
    const html = await render({ task: 'mail', showEnable: false })
    expect(html).toContain('跳过清除已读')
    expect(html).not.toContain('无需额外设置')
    expect(regionTag(html, 'mail')).toContain('data-task-editor="mail"')
    expect(state.config.check_mail_enable).toBe(true)
    expect(axios.get).not.toHaveBeenCalled()
  })

  it.each(['skland', 'mail', 'event-sign-in', 'report'])(
    'shows only the %s editor while retaining the other task controls',
    async (selected) => {
      const html = await render({ task: selected })
      for (const task of ['skland', 'mail', 'event-sign-in', 'report']) {
        expect(regionTag(html, task)).toBeTruthy()
        expect(regionTag(html, task).includes('display:none')).toBe(task !== selected)
      }
      expect(html).toContain('example-account')
      expect(html).toContain('测试签到')
      expect(html).toContain('领取邮件')
      expect(html).toContain('读取基报')
      expect(axios.get).not.toHaveBeenCalled()
    }
  )

  it('retains sign-in feedback and account choices when switching task editors', async () => {
    const selected = ref('skland')
    const editor = mountEditor(selected)
    const component = editor.component

    axios.get.mockResolvedValue({ data: '签到完成' })
    await component.test_sign()
    const account = state.config.skland_info[0]
    component.AllCheck(account, false, 'arknights')
    const originalComponent = component

    for (const task of ['mail', 'event-sign-in', 'report', 'skland']) {
      selected.value = task
      await nextTick()
      expect(editor.component).toBe(originalComponent)
      expect(component.sign_msg.value).toBe('签到完成')
      expect(account.sign_in_official).toBe(false)
      expect(account.sign_in_bilibili).toBe(false)
    }
    expect(editor.setups).toBe(1)
    expect(axios.get).toHaveBeenCalledOnce()
  })

  it('allows only one sign-in request until the current request finishes', async () => {
    const { component } = mountEditor()
    let finish
    axios.get.mockReturnValue(new Promise((resolve) => (finish = resolve)))

    const signing = component.test_sign()
    await component.test_sign()
    expect(component.testing.value).toBe(true)
    expect(component.sign_msg.value).toBe('正在测试签到……')
    expect(axios.get).toHaveBeenCalledExactlyOnceWith(expect.stringContaining('/check-skland-sign'))

    finish({ data: ['官服签到成功', 'B服今天已签到'] })
    await signing
    expect(component.testing.value).toBe(false)
    expect(component.sign_error.value).toBe(false)
    expect(component.sign_msg.value).toBe('官服签到成功\nB服今天已签到')
    expect(await render({ task: 'skland', showEnable: false })).toContain('aria-live="polite"')
  })

  it('shows a short request failure and restores the test action for retry', async () => {
    const { component } = mountEditor()
    axios.get.mockRejectedValueOnce(new Error('连接中断'))

    await component.test_sign()
    expect(component.testing.value).toBe(false)
    expect(component.sign_error.value).toBe(true)
    expect(component.sign_msg.value).toBe('测试签到失败，请检查连接后重试')

    axios.get.mockResolvedValueOnce({ data: '签到完成' })
    await component.test_sign()
    expect(component.testing.value).toBe(false)
    expect(component.sign_error.value).toBe(false)
    expect(component.sign_msg.value).toBe('签到完成')
    expect(axios.get).toHaveBeenCalledTimes(2)
  })

  it('does not test an account with missing credentials', async () => {
    state.config.skland_info[0].password = ''
    const { component } = mountEditor()

    await component.test_sign()
    expect(axios.get).not.toHaveBeenCalled()
    expect(component.testing.value).toBe(false)
    const html = await render({ task: 'skland', showEnable: false })
    expect(html).toMatch(/<button\b[^>]*disabled/)
  })
})
