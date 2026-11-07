// group 取值来自后端结构化日志（Web 访问子系统说明的 Live Log Records）：
// 默认对应子系统说明文件名；clue、credit-shop 是基建内的线索与信用商店业务组。
export const LOG_GROUPS = {
  'base-scheduler': '基建排班',
  clue: '线索',
  'credit-shop': '信用商店购物',
  'local-operation': 'Mower日常',
  recognition: '场景识别',
  'device-control': '设备连接',
  recruitment: '公开招募',
  'depot-recognition': '仓库识别',
  'resource-update': '资源更新',
  'software-update': '软件更新',
  'maa-runtime': 'MAA 运行',
  'maa-integration': 'MAA日常',
  'web-access': 'Web 访问',
  'ai-assistant': 'AI 助手',
  'config-backup': '配置备份',
  'config-profiles': '配置档案',
  'growth-planning': '养成规划',
  'plan-editor': '排班编辑',
  'weekly-plan-editor': '周计划',
  'process-recovery': '进程恢复',
  'desktop-window': '桌面窗口'
}

export function groupMeta(group) {
  if (!group) return null
  return { label: LOG_GROUPS[group] ?? group }
}
