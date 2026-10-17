import { renderToString } from '@vue/server-renderer'
import { createSSRApp, defineComponent, h, ref } from 'vue'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import PlanOperatorSelect from './PlanOperatorSelect.vue'

const state = vi.hoisted(() => ({ selects: [] }))
vi.mock('./SlickOperatorSelect.vue', () => ({
  default: defineComponent({
    props: ['modelValue', 'disabled', 'select_placeholder'],
    emits: ['update:modelValue'],
    setup(props, { emit }) {
      state.selects.push({ props, update: (value) => emit('update:modelValue', value) })
      return () => h('select', { disabled: props.disabled, 'aria-label': props.select_placeholder })
    }
  })
}))

beforeEach(() => {
  state.selects = []
})

async function render(backup, disabled = false) {
  const added = ref(['陈'])
  const removed = ref(['红'])
  const app = createSSRApp({
    render: () =>
      h(PlanOperatorSelect, {
        backup,
        disabled,
        modelValue: added.value,
        removed: removed.value,
        'onUpdate:modelValue': (value) => {
          added.value = value
        },
        'onUpdate:removed': (value) => {
          removed.value = value
        }
      })
  })
  const html = await renderToString(app)
  return { added, removed, html }
}

describe('副表选项增减编辑', () => {
  it('主表只显示原名单，副表显示增和减', async () => {
    const main = await render(false)
    expect(state.selects).toHaveLength(1)
    expect(main.html).not.toContain('operation-label')
    state.selects = []
    const backup = await render(true)
    expect(state.selects).toHaveLength(2)
    expect(backup.html).toContain('增')
    expect(backup.html).toContain('减')
    expect(state.selects[1].props.modelValue).toEqual(['红'])
    expect(state.selects.every(({ props }) => !props.select_placeholder)).toBe(true)
  })

  it('选择移除取消同副表的增加', async () => {
    const { added, removed } = await render(true)
    state.selects[1].update(['陈', '红'])
    expect(added.value).toEqual([])
    expect(removed.value).toEqual(['陈', '红'])
  })

  it('选择增加取消同副表的移除', async () => {
    const { added, removed } = await render(true)
    state.selects[0].update(['陈', '红'])
    expect(added.value).toEqual(['陈', '红'])
    expect(removed.value).toEqual([])
  })

  it('清空移除名单保留增加名单', async () => {
    const { added, removed } = await render(true)
    state.selects[1].update([])
    expect(added.value).toEqual(['陈'])
    expect(removed.value).toEqual([])
  })

  it('编辑锁同时阻止增减', async () => {
    const { added, removed } = await render(true, true)
    expect(state.selects.every(({ props }) => props.disabled)).toBe(true)
    state.selects[0].update(['初雪'])
    state.selects[1].update(['陈'])
    expect(added.value).toEqual(['陈'])
    expect(removed.value).toEqual(['红'])
  })
})
