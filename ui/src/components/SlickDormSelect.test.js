import { renderToString } from '@vue/server-renderer'
import { createSSRApp, defineComponent, h } from 'vue'
import { describe, expect, it, vi } from 'vitest'
import SlickDormSelect from './SlickDormSelect.vue'

const state = vi.hoisted(() => ({ select: null }))
vi.mock('naive-ui', async (original) => ({
  ...(await original()),
  NSelect: defineComponent({
    props: ['value', 'options', 'disabled'],
    setup(props) {
      state.select = props
      return () => h('select', { disabled: props.disabled })
    }
  })
}))
vi.mock('vue-slicksort', () => ({
  SlickList: defineComponent({
    setup:
      (_, { slots }) =>
      () =>
        h('div', slots.default?.())
  }),
  SlickItem: defineComponent({
    setup:
      (_, { slots }) =>
      () =>
        h('span', slots.default?.())
  })
}))

const defaults = [1, 2, 3, 4].map((index) => `dormitory_${index}`)

describe('宿舍高低优位选择', () => {
  it('只选中默认四个宿舍，额外提供四个低优位供手动选择', async () => {
    await renderToString(
      createSSRApp(SlickDormSelect, {
        modelValue: defaults,
        roomOnly: true,
        includeLow: true
      })
    )
    expect(state.select.value).toEqual(defaults)
    expect(state.select.options).toHaveLength(8)
    expect(state.select.options.filter((option) => option.value.endsWith('_low'))).toEqual(
      [1, 2, 3, 4].map((index) => ({
        label: `宿舍 ${index} 低优位`,
        value: `dormitory_${index}_low`
      }))
    )
  })

  it('显示已插入的低优位顺序并保留编辑锁', async () => {
    const chosen = ['dormitory_1', 'dormitory_1_low', ...defaults.slice(1)]
    await renderToString(
      createSSRApp(SlickDormSelect, {
        modelValue: chosen,
        roomOnly: true,
        includeLow: true,
        disabled: true
      })
    )
    expect(state.select.value).toEqual(chosen)
    expect(state.select.disabled).toBe(true)
  })
})
