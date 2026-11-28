import { expect, it, vi } from 'vitest'
import { createSSRApp } from 'vue'
import { renderToString } from 'vue/server-renderer'
import WaitingSceneEditor from './WaitingSceneEditor.vue'

vi.mock('vue', async (original) => ({
  ...(await original()),
  useSSRContext: () => ({ modules: new Set() })
}))

function setup() {
  const props = {
    field: {
      kind: 'waiting_scene',
      label: '页面等待参数',
      scenes: [
        ['CONNECTING', '正在提交反馈至神经'],
        ['UNKNOWN', '未知'],
        ['LOADING', '加载中'],
        ['LOGIN_LOADING', '场景跳转时的等待界面'],
        ['LOGIN_MAIN_NOENTRY', '登录页面（无按钮入口）'],
        ['OPERATOR_ONGOING', '代理作战']
      ]
    },
    value: {
      CONNECTING: [1, 10],
      UNKNOWN: [1, 10],
      LOADING: [2, 30],
      LOGIN_LOADING: [3, 10],
      LOGIN_MAIN_NOENTRY: [3, 10],
      OPERATOR_ONGOING: [10, 30]
    }
  }
  const emit = vi.fn()
  const component = WaitingSceneEditor.setup(props, { expose() {}, emit })
  return { props, emit, component }
}

it('renders the six scene rows and twelve labelled integer inputs', async () => {
  const { props } = setup()
  const html = await renderToString(createSSRApp(WaitingSceneEditor, props))
  for (const [, label] of props.field.scenes) {
    expect(html).toContain(label)
    expect(html).toContain(`${label}截图间隔（秒）`)
    expect(html).toContain(`${label}等待次数`)
  }
  expect(html.match(/<input\b/g)).toHaveLength(12)
  expect(html.match(/<tr\b/g)).toHaveLength(7)
})

it('emits one copied cell change while retaining every other value', () => {
  const { props, emit, component } = setup()
  component.edit('LOADING', 1, 25)
  expect(emit).toHaveBeenCalledExactlyOnceWith('update:value', {
    ...props.value,
    LOADING: [2, 25]
  })
  expect(props.value.LOADING).toEqual([2, 30])
})

it.each(['disabled', 'read_only'])('does not change the table while %s', (condition) => {
  const { props, emit, component } = setup()
  if (condition === 'disabled') props.disabled = true
  else props.field.read_only = true
  component.edit('LOADING', 0, 4)
  expect(emit).not.toHaveBeenCalled()
})

it('accepts original integer semantics without new bounds and rejects non-integer edits', () => {
  const { emit, component } = setup()
  for (const value of [null, '4', true, 0.5]) component.edit('LOADING', 0, value)
  expect(emit).not.toHaveBeenCalled()
  component.edit('LOADING', 0, -1)
  expect(emit.mock.lastCall[1].LOADING).toEqual([-1, 30])
  component.edit('LOADING', 1, 100000)
  expect(emit.mock.lastCall[1].LOADING).toEqual([2, 100000])
})
