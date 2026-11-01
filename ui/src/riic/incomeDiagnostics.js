import { getOperatorName, getRoomDisplayName } from './vendor/workbench/operatorHelpers'

const failureCodes = new Set([
  'SIMULATION_EVENT_LIMIT',
  'SIMULATION_SAME_TIME_ACTION',
  'SIMULATION_STALLED',
  'MOWER_PENDING_TASK_FAILURE',
  'BACKUP_EXECUTION_FAILED',
  'INVALID_RUNTIME',
  'INVENTORY_INVALID',
  'SKILL_STAGE_UNSUPPORTED',
  'OPERATION_DURATION_UNSUPPORTED'
])
const format = (value) => Number(value.toFixed(1)).toLocaleString('zh-CN')
const roomName = (id) => getRoomDisplayName(id) || id

export function incomeDiagnosticMessage({ code, message = '' }) {
  let text = message.replace(/^演算曾报告：/, '')
  if (code === 'SIMULATION_EVENT_LIMIT') {
    const limit = /达到 (\d+) 个积分区间/.exec(text)?.[1]
    return `已达到本次演算的计算次数上限${limit ? `（${Number(limit).toLocaleString('zh-CN')} 次）` : ''}，尚未算完。可缩短统计天数后重试；这条记录不能确定演算变慢的原因。`
  }
  text = text.replace(
    /\b(group|slot):(.+?): insufficient available candidates or beds; original occupants retained/g,
    (_, kind, key) => {
      const slot = /^(.*)_(\d+)$/.exec(key)
      const target =
        kind === 'group'
          ? `绑组“${key}”`
          : slot
            ? `${roomName(slot[1])}第 ${Number(slot[2]) + 1} 个岗位`
            : `岗位“${key}”`
      return `${target}曾因可用替班或宿舍床位不足而保留原在岗安排`
    }
  )
  return text
    .replace(/\bchar_\d+_[a-zA-Z0-9_]+\b/g, getOperatorName)
    .replace(
      /\b(?:room_\d+_\d+|dormitory_\d+|factory|train|recycle|contact|meeting|central)\b/g,
      roomName
    )
}

export function incomeDiagnosticGroups(diagnostics = []) {
  const groups = { failures: [], records: [], assumptions: [] }
  const seen = new Set()
  for (const diagnostic of diagnostics) {
    const message = incomeDiagnosticMessage(diagnostic)
    const key = `${diagnostic.code}\0${message}`
    if (seen.has(key)) continue
    seen.add(key)
    const group =
      failureCodes.has(diagnostic.code) || diagnostic.severity === 'error'
        ? 'failures'
        : /_(?:MODEL|ASSUMPTION)$/.test(diagnostic.code) ||
            diagnostic.code === 'PASSIVE_AUXILIARY_OCCUPANCY'
          ? 'assumptions'
          : 'records'
    groups[group].push({ ...diagnostic, message })
  }
  return groups
}

export function incomeFailureMessage(result, diagnostics, settings) {
  const simulation = result.simulationReport
  const failures = incomeDiagnosticGroups(diagnostics).failures
  const reason =
    failures[0]?.message ||
    (simulation ? '未取得完整的生产报告，请查看演算日志。' : result.error) ||
    '演算未完成，请查看演算日志。'
  if (!simulation) return reason
  const warmup = settings.warmupDays * 24
  const progress =
    simulation.elapsedHours < warmup
      ? `预热已算 ${format(simulation.elapsedHours)} / ${format(warmup)} 小时`
      : `统计已算 ${format(simulation.observedHours)} / ${format(settings.sampleDays * 24)} 小时`
  return `演算未完成：${progress}。${reason}`
}
