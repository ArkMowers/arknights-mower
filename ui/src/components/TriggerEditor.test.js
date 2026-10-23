import { renderToString } from '@vue/server-renderer'
import { createRenderer, createSSRApp, h, nextTick, ssrContextKey } from 'vue'
import { afterEach, describe, expect, it, vi } from 'vitest'
import TriggerEditor from './TriggerEditor.vue'
import { maintenance_trigger } from '@/utils/trigger_maintenance'
import { new_expression } from '@/utils/trigger_function'

vi.mock('./TriggerString.vue', () => ({
  default: {
    props: ['data'],
    emits: ['update'],
    setup:
      (props, { emit }) =>
      () =>
        h('input', {
          value: props.data,
          onInput: (value) => emit('update', value)
        })
  }
}))
vi.mock('naive-ui', async (importOriginal) => {
  const { h } = await import('vue')
  return {
    ...(await importOriginal()),
    NTable: {
      setup:
        (_, { slots }) =>
        () =>
          h('table', slots.default?.())
    },
    NSelect: {
      props: ['value', 'options', 'onUpdate:value'],
      setup: (props) => () =>
        h(
          'select',
          {
            value: props.value,
            onChange: props['onUpdate:value']
          },
          props.options.map(({ label, value }) => h('option', { value }, label))
        )
    },
    NAutoComplete: {
      props: ['value'],
      setup: (props) => () => h('input', { value: props.value })
    },
    NButton: {
      setup:
        (_, { slots }) =>
        () =>
          h('button', slots.default?.())
    },
    NInputNumber: {
      props: ['value'],
      setup: (props) => () => h('input', { value: props.value })
    }
  }
})

async function render(data) {
  return renderToString(createSSRApp(TriggerEditor, { data }))
}

const cleanups = []
afterEach(() => cleanups.splice(0).forEach((cleanup) => cleanup()))

function mount(data) {
  const renderer = createRenderer({
    createElement: (type) => ({ type, props: {}, children: [] }),
    createText: (text) => ({ text }),
    createComment: (text) => ({ text }),
    insert(node, parent, anchor) {
      if (node.parent) node.parent.children.splice(node.parent.children.indexOf(node), 1)
      node.parent = parent
      const index = anchor ? parent.children.indexOf(anchor) : -1
      if (index < 0) parent.children.push(node)
      else parent.children.splice(index, 0, node)
    },
    remove(node) {
      node.parent.children.splice(node.parent.children.indexOf(node), 1)
    },
    setText(node, text) {
      node.text = text
    },
    setElementText(node, text) {
      node.text = text
      node.children = []
    },
    patchProp(node, key, _prev, value) {
      node.props[key] = value
    },
    parentNode: (node) => node.parent,
    nextSibling: (node) => node.parent?.children[node.parent.children.indexOf(node) + 1]
  })
  const update = vi.fn()
  const root = { children: [] }
  const app = renderer.createApp(
    { ...TriggerEditor, render: () => h('div') },
    { data, onUpdate: update }
  )
  app.provide(ssrContextKey, {})
  app.mount(root)
  cleanups.push(() => app.unmount())
  return { state: app._instance.setupState, update }
}

describe('维护副表条件编辑', () => {
  it('renders a complete timing condition in one row', async () => {
    const html = await render(maintenance_trigger())
    expect(html.match(/<tr(?:\s[^>]*)?>/g)).toHaveLength(1)
    expect(html).toContain('定时条件')
    expect(html).toContain('停服大更新提前小时数')
    expect(html).toContain('小时内生效')
    expect(html).not.toContain('运算符')
  })

  it('preserves the saved advance value', async () => {
    const html = await render(maintenance_trigger(12))
    expect(html).toContain('value="12"')
  })

  it('preserves ordinary and nested conditions', async () => {
    const ordinary = { left: '1', operator: '==', right: '1' }
    expect(await render(ordinary)).toContain('运算符')
    const html = await render({ left: maintenance_trigger(), operator: 'and', right: ordinary })
    expect(html).toContain('定时条件')
    expect(html).toContain('运算符')
  })
})

describe('多参数函数条件编辑', () => {
  it('groups all function names under one expression type', async () => {
    const ordinary = await render({ left: '1', operator: '>', right: '0' })
    expect(ordinary).toContain('<option value="function">函数</option>')
    expect(ordinary).not.toContain('<option value="max">')
    const functions = await render({
      function: 'max',
      args: ['1', { function: 'min', args: ['2', '3'] }]
    })
    for (const name of ['max', 'min', 'sum', 'any', 'all', 'abs']) {
      expect(functions).toContain(`<option value="${name}">`)
    }
    expect(functions).toContain('value="function" aria-label="第 2 项类型"')
  })
  it.each(['max', 'min', 'sum', 'any', 'all'])(
    'renders %s with one right-side add button and removes only later arguments',
    async (name) => {
      const html = await render({ function: name, args: ['1', '2', '3'] })
      expect(html).not.toContain('运算符')
      expect(html).not.toContain('<span>第 1 项</span>')
      expect(html.match(/aria-label="新增项"/g)).toHaveLength(1)
      expect(html).not.toContain('aria-label="删除第 1 项"')
      expect(html).toContain('aria-label="删除第 2 项"')
      expect(html.indexOf('aria-label="新增项"')).toBeLessThan(
        html.indexOf('aria-label="第 2 项类型"')
      )
    }
  )

  it.each(['max', 'min', 'sum', 'any', 'all', 'abs'])(
    'opens a saved single %s argument',
    async (name) => {
      const html = await render({ function: name, args: ['7'] })
      expect(html).toContain('value="7"')
      expect(html).not.toContain('删除第')
      expect(html.includes('aria-label="新增项"')).toBe(name !== 'abs')
    }
  )

  it('selects a function, adds and removes arguments, and restores the saved expression', async () => {
    const editor = mount({ left: '1', operator: '>', right: '0' })
    editor.state.left = new_expression('function')
    await nextTick()
    expect(editor.update).toHaveBeenLastCalledWith({
      left: { function: 'max', args: [''] },
      operator: '>',
      right: '0'
    })
    const child = mount(editor.update.mock.lastCall[0].left)
    child.state.add_argument()
    child.state.add_argument()
    await nextTick()
    child.state.args[2].value = '17'
    await nextTick()
    expect(child.update.mock.lastCall[0].args).toEqual(['', '', '17'])
    child.state.args.splice(1, 1)
    await nextTick()
    const saved = child.update.mock.lastCall[0]
    expect(saved.args).toEqual(['', '17'])
    const reopened = mount(JSON.parse(JSON.stringify(saved)))
    expect(reopened.state.args.map((arg) => arg.value)).toEqual(['', '17'])
    expect(await render(saved)).not.toContain('aria-label="删除第 1 项"')
    expect(reopened.update).not.toHaveBeenCalled()
  })

  it('retains nested arguments and enforces the single abs argument when switching functions', async () => {
    const nested = { left: '3', operator: '+', right: '4' }
    const data = { function: 'sum', args: [nested, '8'] }
    const editor = mount(data)
    editor.state.update_function('abs')
    await nextTick()
    expect(editor.update).toHaveBeenLastCalledWith({ function: 'abs', args: [nested] })
    expect(await render(editor.update.mock.lastCall[0])).not.toContain('aria-label="新增项"')
    editor.state.update_function('min')
    await nextTick()
    expect(editor.update).toHaveBeenLastCalledWith({ function: 'min', args: [nested] })
    expect(data.args).toEqual([nested, '8'])
  })
})
