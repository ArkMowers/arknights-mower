import { OPERATOR_MAP } from './operators'

export const TRADE_RUN_ORDER_NAMES = ['但书', '龙舌兰', '佩佩', '可露希尔', 'U-Official'] as const
const tradeRunners = new Set<string>(TRADE_RUN_ORDER_NAMES)

/** Trade replacement candidates; U-Official extends the pinned Mower list for this app. */
export function isTradeRunOrderOperator(idOrName: string): boolean {
  return tradeRunners.has(OPERATOR_MAP.get(idOrName)?.name ?? idOrName)
}
