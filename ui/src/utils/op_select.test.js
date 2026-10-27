import { afterEach, expect, it } from 'vitest'
import { i18n } from '@/i18n'
import { render_op_label, filterOperatorOption } from './op_select'

afterEach(() => {
  i18n.global.locale.value = 'zh-CN'
})

it.each([
  ['zh-CN', '能天使', '自由位置（Free）', '保持当前干员（Current）'],
  ['en-US', 'Exusiai', 'Flexible slot (Free)', 'Keep current operator (Current)'],
  ['ja-JP', 'エクシア', '自由枠（Free）', '現在のオペレーターを維持（Current）'],
  ['zh-TW', '能天使', '自由位置（Free）', '保留目前幹員（Current）']
])(
  'shows operator and special-slot labels in %s while preserving values and asset paths',
  (locale, operator, free, current) => {
    const options = [
      { value: '能天使', label: '能天使' },
      { value: 'Free', label: 'Free' },
      { value: 'Current', label: 'Current' }
    ]
    const original = structuredClone(options)
    i18n.global.locale.value = locale
    expect(options.map((option) => render_op_label(option).children.at(-1))).toEqual([
      operator,
      free,
      current
    ])
    expect(render_op_label(options[0]).children[0].props.src).toBe('avatar/能天使.webp')
    expect(filterOperatorOption(free, options[1])).toBe(true)
    expect(filterOperatorOption('nengtianshi', options[0])).toBe(true)
    expect(
      render_op_label({ value: 'extension-id', label: '用户自定义标签' }).children.at(-1)
    ).toBe('用户自定义标签')
    expect(options).toEqual(original)
  }
)
