import { describe, expect, it, vi } from 'vitest'
import { effectScope, reactive } from 'vue'
import GroupRestingThresholds from './GroupRestingThresholds.vue'

vi.mock('vue', async (original) => {
  const vue = await original()
  return {
    ...vue,
    useSSRContext: () => ({ modules: new Set() }),
    useModel: (props, key) =>
      vue.computed({ get: () => props[key], set: (value) => (props[key] = value) })
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
