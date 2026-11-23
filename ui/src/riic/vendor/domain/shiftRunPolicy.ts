import { OPERATOR_MAP } from './operators'

export const TRADE_RUN_ORDER_NAMES = ['但书', '龙舌兰', '佩佩', '可露希尔'] as const
const tradeRunners = new Set<string>(TRADE_RUN_ORDER_NAMES)

export function isTradeRunOrderOperator(idOrName: string): boolean {
  return tradeRunners.has(OPERATOR_MAP.get(idOrName)?.name ?? idOrName)
}
