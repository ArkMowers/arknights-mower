export const factory_product_options = [
  { label: '赤金', value: 'gold' },
  { label: '中级作战记录', value: 'exp3' },
  { label: '源石碎片（固源岩）', value: 'orirock', icon: 'orirock' },
  { label: '源石碎片（装置）', value: 'orirock_device', icon: 'orirock' }
]

export const factory_product_ids = factory_product_options.map(({ value }) => value)

export const trade_product_options = [
  { label: '龙门商法', value: 'lmd' },
  { label: '开采协力', value: 'orundum' }
]

export const facility_product_options = [...factory_product_options, ...trade_product_options]

export const facility_product_labels = Object.fromEntries(
  facility_product_options.map(({ label, value }) => [value, label])
)
