import { describe, expect, it } from 'vitest'
import { factory_product_ids, factory_product_options } from './base_products'

describe('制造站产物选项', () => {
  it('旧源石碎片值保留并显示为固源岩配方', () => {
    expect(factory_product_options.find(({ value }) => value === 'orirock')).toEqual({
      label: '源石碎片（固源岩）',
      value: 'orirock',
      icon: 'orirock'
    })
  })

  it('装置配方使用独立值', () => {
    expect(factory_product_options).toContainEqual({
      label: '源石碎片（装置）',
      value: 'orirock_device',
      icon: 'orirock'
    })
    expect(factory_product_ids).toContain('orirock_device')
  })
})
