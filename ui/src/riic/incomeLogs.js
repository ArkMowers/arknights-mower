import { OPERATOR_MAP } from './vendor/domain/operators'

const labels = {
  'shift-off': '下班休息',
  'shift-on': '上班',
  fiammetta: '菲亚梅塔充能',
  'backup-plan': '副表切换',
  'backup-task': '副表任务',
  'rest-limit-release': '离开宿舍',
  'rest-bed-takeover': '宿舍换人',
  'exhaust-support': '用尽支援',
  'order-completed': '订单完成',
  'order-collected': '交付订单',
  'product-switched': '切换产物',
  'product-switch-drone': '切产物使用无人机',
  'trade-drone': '贸易加速',
  'manufacture-drone': '制造加速',
  'native-trade-drone': '贸易加速',
  'native-manufacture-drone': '制造加速',
  'recycle-collected': '回收站收取'
}
export function incomeEventLog(simulation, limit = 5000) {
  const events = [
    ...simulation.events,
    ...(simulation.production?.events ?? []).filter((e) => labels[e.type] && e.roomId)
  ]
    .filter((e) => e.time >= simulation.assumptions.warmupHours)
    .sort((a, b) => b.time - a.time)
  return {
    total: events.length,
    entries: events.slice(0, limit).map((e) => ({
      hours: e.time - simulation.assumptions.warmupHours,
      type: labels[e.type] ?? e.type,
      room: e.roomId ?? '',
      detail: [
        (e.operators ?? e.operatorIds ?? [])
          .map((id) => OPERATOR_MAP.get(id)?.name ?? id)
          .join('、'),
        e.backupName &&
          `${e.backupName}${e.active === undefined ? '' : e.active ? '（启用）' : '（退出）'}`,
        e.toProduct && `${e.fromProduct} → ${e.toProduct}`,
        e.amount !== undefined && `数量 ${Number(e.amount.toFixed(2))}`,
        e.order &&
          `龙门币 ${e.order.lmdReward ?? 0} · 赤金消耗 ${e.order.goldCost ?? 0} · 合成玉 ${e.order.orundumReward ?? 0}`
      ]
        .filter(Boolean)
        .join('；')
    }))
  }
}
export function incomeLogTime(hours) {
  const minutes = Math.round(hours * 60)
  return `第 ${Math.floor(minutes / 1440) + 1} 天 ${String(Math.floor(minutes / 60) % 24).padStart(2, '0')}:${String(minutes % 60).padStart(2, '0')}`
}
