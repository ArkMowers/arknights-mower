const ignored = new Set(['', 'Free', 'Current'])
const boosters = new Set(['阿斯卡纶', '烛煌', '斩业星熊'])

export function masteryScheduleContext(primary, backups = []) {
  const blocked = new Set()
  const scheduled = new Set()
  let centralBonus = 0
  for (const table of [primary, ...backups.map((b) => b.plan)]) {
    for (const [room, facility] of Object.entries(table || {})) {
      for (const slot of facility?.plans || []) {
        for (const name of [slot.agent, ...(slot.replacement || [])]) {
          if (!name || ignored.has(name)) continue
          scheduled.add(name)
          if (room === 'train') continue
          blocked.add(name)
          if (room === 'central' && boosters.has(name)) centralBonus = 5
        }
      }
    }
  }
  return { blocked, scheduled, centralBonus }
}

export function supportEditableAfter(plan) {
  if (['idle', 'failed'].includes(plan?.status)) return 0
  if (plan?.status === 'training') return plan.support_runtime?.level ?? plan.target_level
  return plan?.target_level ?? 3
}

export function masteryTraineeWarning(name, scheduledOperators) {
  return name && scheduledOperators.has(name)
    ? `${name} 出现在非训练室排班中，专精期间可能影响排班，请留意。`
    : ''
}
