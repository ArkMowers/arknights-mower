import { describe, expect, it, vi } from 'vitest'
import { readFileSync } from 'node:fs'
import { parse } from '@vue/compiler-sfc'
import {
  compile,
  createRenderer,
  effectScope,
  h,
  nextTick,
  reactive,
  ref,
  ssrContextKey
} from 'vue'
import GroupRestingThresholds from './GroupRestingThresholds.vue'
import { i18n } from '@/i18n'

vi.mock('vue', async (original) => {
  const vue = await original()
  return {
    ...vue,
    useSSRContext: () => ({ modules: new Set() }),
    useModel: (props, key) =>
      vue.getCurrentInstance()
        ? vue.useModel(props, key)
        : vue.computed({ get: () => props[key], set: (value) => (props[key] = value) })
  }
})

function edit(run) {
  const props = reactive({
    modelValue: {},
    groups: ['主表组', '副表组'],
    defaultThreshold: 65,
    disabled: false
  })
  const scope = effectScope()
  const editor = scope.run(() => GroupRestingThresholds.setup(props, { expose: () => {} }))
  try {
    run(editor, props)
  } finally {
    scope.stop()
  }
}

describe('各组心情阈值', () => {
  it('updates the mounted labels in every language while preserving group names, selection and stored ratios', async () => {
    const { descriptor } = parse(
      readFileSync(new URL('./GroupRestingThresholds.vue', import.meta.url), 'utf8')
    )
    const Input = {
      props: ['value'],
      emits: ['update:value'],
      setup:
        (props, { attrs, emit }) =>
        () =>
          h('input', {
            ...attrs,
            value: props.value,
            onInput: (value) => emit('update:value', value)
          })
    }
    const Select = {
      props: ['value', 'options'],
      emits: ['update:value'],
      setup:
        (props, { attrs, emit }) =>
        () =>
          h(
            'select',
            { ...attrs, value: props.value, onChange: (value) => emit('update:value', value) },
            props.options.map((option) => h('option', { value: option.value }, option.label))
          )
    }
    const Button = {
      setup:
        (_, { attrs, slots }) =>
        () =>
          h('button', attrs, slots.default?.())
    }
    const Client = {
      ...GroupRestingThresholds,
      components: { NSelect: Select, NButton: Button, MowerInputNumber: Input },
      render: compile(descriptor.template.content),
      setup: (props, context) => ({ ...GroupRestingThresholds.setup(props, context) })
    }
    const node = (tag, text = '') => ({ tag, text, props: {}, children: [], parent: null })
    const remove = (child) => {
      if (child.parent)
        child.parent.children = child.parent.children.filter((sibling) => sibling !== child)
      child.parent = null
    }
    const renderer = createRenderer({
      createElement: node,
      createText: (text) => node('#text', text),
      createComment: () => node('#comment'),
      setText: (child, text) => (child.text = text),
      setElementText: (child, text) => {
        child.text = text
        child.children = []
      },
      patchProp: (child, key, _old, value) => (child.props[key] = value),
      parentNode: (child) => child.parent,
      nextSibling: () => null,
      insert: (child, parent, anchor) => {
        remove(child)
        child.parent = parent
        const index = anchor ? parent.children.indexOf(anchor) : -1
        parent.children.splice(index < 0 ? parent.children.length : index, 0, child)
      },
      remove
    })
    const all = (element) => [element, ...element.children.flatMap(all)]
    const text = (element) => element.text + element.children.map(text).join('')
    const ratios = ref({ 我的中文组: 0.355 })
    const saved = JSON.stringify(ratios.value)
    const onUpdate = vi.fn((value) => (ratios.value = value))
    const app = renderer.createApp({
      render: () =>
        h(Client, {
          modelValue: ratios.value,
          groups: ['我的中文组', '副表组'],
          defaultThreshold: 35,
          'onUpdate:modelValue': onUpdate
        })
    })
    app.provide(ssrContextKey, { modules: new Set() })
    const root = node('root')
    app.mount(root)
    try {
      all(root)
        .find((element) => element.tag === 'select')
        .props.onChange('副表组')
      await nextTick()
      for (const [locale, removeLabel, addLabel, thresholdLabel, placeholder] of [
        ['zh-CN', '移除', '添加', '我的中文组心情阈值', '选择单独设置的绑组'],
        [
          'en-US',
          'Remove',
          'Add',
          '我的中文组 morale threshold',
          'Select a group to set separately'
        ],
        ['ja-JP', '削除', '追加', '我的中文组の体力閾値', '個別に設定するグループを選択'],
        ['zh-TW', '移除', '新增', '我的中文组心情閾值', '選擇單獨設定的綁組']
      ]) {
        i18n.global.locale.value = locale
        await nextTick()
        const elements = all(root)
        expect(text(root)).toContain('我的中文组')
        expect(elements.filter((element) => element.tag === 'button').map(text)).toEqual([
          removeLabel,
          addLabel
        ])
        expect(elements.find((element) => element.tag === 'input').props).toMatchObject({
          value: 35.5,
          min: 35,
          max: 100,
          'aria-label': thresholdLabel
        })
        expect(elements.find((element) => element.tag === 'select').props).toMatchObject({
          value: '副表组',
          placeholder
        })
        expect(elements.filter((element) => element.tag === 'option').map(text)).toEqual(['副表组'])
        expect(JSON.stringify(ratios.value)).toBe(saved)
        expect(onUpdate).not.toHaveBeenCalled()
      }
      all(root)
        .filter((element) => element.tag === 'button')[1]
        .props.onClick()
      await nextTick()
      expect(ratios.value).toEqual({ 我的中文组: 0.355, 副表组: 0.35 })
      all(root)
        .find((element) => element.tag === 'input')
        .props.onInput(75.5)
      await nextTick()
      expect(ratios.value).toEqual({ 我的中文组: 0.755, 副表组: 0.35 })
      all(root)
        .find((element) => element.tag === 'button')
        .props.onClick()
      await nextTick()
      expect(ratios.value).toEqual({ 副表组: 0.35 })
    } finally {
      app.unmount()
      i18n.global.locale.value = 'zh-CN'
    }
  })

  it('添加时使用全局值，各组独立修改，移除后恢复继承', () =>
    edit((editor, props) => {
      editor.selected.value = '主表组'
      editor.add()
      editor.selected.value = '副表组'
      editor.add()
      editor.update('主表组', 35)
      expect(props.modelValue).toEqual({ 主表组: 0.35, 副表组: 0.65 })
      expect(editor.choices.value).toEqual([])
      editor.remove('主表组')
      expect(props.modelValue).toEqual({ 副表组: 0.65 })
      expect(editor.choices.value).toEqual([{ label: '主表组', value: '主表组' }])
    }))
  it('最低允许 35%，拒绝无效输入并保留旧组名供移除', () =>
    edit((editor, props) => {
      props.modelValue = { 旧组: 0.35 }
      for (const value of [null, NaN, Infinity, 34, 101]) editor.update('旧组', value)
      expect(props.modelValue).toEqual({ 旧组: 0.35 })
      editor.update('旧组', 35.5)
      expect(props.modelValue.旧组).toBe(0.355)
      editor.remove('旧组')
      expect(props.modelValue).toEqual({})
    }))
  it('编辑锁阻止增删改', () =>
    edit((editor, props) => {
      props.modelValue = { 主表组: 0.65 }
      props.disabled = true
      editor.update('主表组', 35)
      editor.remove('主表组')
      editor.selected.value = '副表组'
      editor.add()
      expect(props.modelValue).toEqual({ 主表组: 0.65 })
    }))
})
