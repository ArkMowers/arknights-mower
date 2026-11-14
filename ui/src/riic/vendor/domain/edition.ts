import type { SpecialOrder } from './types'

export interface CalculatorEdition {
  id: 'standard' | 'shift-run'
  label: string
  description: string
  storageNamespace: string
  allowShiftRun: boolean
  importLegacyConfig: boolean
  defaultSpecialOrder: SpecialOrder
}

export const EDITION: CalculatorEdition = {
  id: 'shift-run',
  label: '跑单排班版',
  description: '按理想跑单模型，计算贸易站已配置候补的特殊订单收益。',
  storageNamespace: 'shift-run',
  allowShiftRun: true,
  importLegacyConfig: false,
  defaultSpecialOrder: 'shiftRun',
}
