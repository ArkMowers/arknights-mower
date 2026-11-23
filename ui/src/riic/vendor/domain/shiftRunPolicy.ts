import { OPERATOR_MAP } from './operators'

export const TRADE_RUN_ORDER_NAMES = ['但书', '龙舌兰', '佩佩', '可露希尔'] as const
const tradeRunners = new Set<string>(TRADE_RUN_ORDER_NAMES)

export function isTradeRunOrderOperator(idOrName: string): boolean {
  return tradeRunners.has(OPERATOR_MAP.get(idOrName)?.name ?? idOrName)
}

export function orundumRunOrderError(room: string, slotIndex: number, candidates: readonly string[]): string | undefined {
  const runner = candidates.find(isTradeRunOrderOperator)
  if (runner) return `${room} 的第 ${slotIndex + 1} 个工位卖玉时不能安排跑单干员${OPERATOR_MAP.get(runner)?.name ?? runner}`
}
