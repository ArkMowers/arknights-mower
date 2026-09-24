import { describe, expect, it, vi } from 'vitest'
import { effectScope, reactive } from 'vue'
import MoodLimitsEditor from './MoodLimitsEditor.vue'

vi.mock('vue', async (original) => {
  const vue = await original()
  return {
    ...vue,
    useSSRContext: () => ({ modules: new Set() }),
    useModel: (props, key) =>
      vue.computed({
        get: () => props[key],
        set: (value) => {
          props[key] = value
        }
      })
  }
})

function edit(run) {
  const props = reactive({
    defaults: null,
    overrides: {},
    disabled: false,
    isBackup: false,
    operators: [{ label: '令', value: '令' }]
  })
  const scope = effectScope()
  const editor = scope.run(() => MoodLimitsEditor.setup(props, { expose: () => {} }))
  try {
    run(editor, props)
  } finally {
    scope.stop()
  }
}

describe('心情上下限编辑', () => {
  it('校验范围并保留小数，不保存非法中间状态', () =>
    edit((editor, props) => {
      editor.enableDefaults(true)
      editor.updateRange(null, 'upper', 12)
      editor.updateRange(null, 'lower', 4.5)
      expect(props.defaults).toEqual({ lower: 4.5, upper: 12 })
      for (const value of [4.5, 0, 25, null, NaN]) editor.updateRange(null, 'upper', value)
      expect(props.defaults).toEqual({ lower: 4.5, upper: 12 })
    }))
  it('单独设置独立于全体，移除后恢复继承', () =>
    edit((editor, props) => {
      editor.enableDefaults(true)
      editor.selected.value = '令'
      editor.addOperator()
      editor.updateRange('令', 'upper', 12)
      expect(props.overrides.令.upper).toBe(12)
      expect(props.defaults.upper).toBe(24)
      expect(editor.choices.value).toEqual([])
      editor.removeOperator('令')
      expect(props.overrides).toEqual({})
      editor.enableDefaults(false)
      expect(props.defaults).toBeNull()
    }))
  it('编辑锁阻止所有修改入口', () =>
    edit((editor, props) => {
      props.defaults = { lower: 0, upper: 24 }
      props.overrides = { 令: { lower: 0, upper: 12 } }
      props.disabled = true
      editor.enableDefaults(false)
      editor.updateRange('令', 'upper', 20)
      editor.removeOperator('令')
      editor.selected.value = '夕'
      editor.addOperator()
      expect(props.defaults.upper).toBe(24)
      expect(props.overrides).toEqual({ 令: { lower: 0, upper: 12 } })
    }))
})
