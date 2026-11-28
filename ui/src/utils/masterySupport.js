const ignored = new Set(['', 'Free', 'Current'])
const boosters = new Set(['阿斯卡纶', '烛煌', '斩业星熊'])

export function masteryScheduleContext(primary, backups = []) {
  const blocked = new Set()
  const scheduled = new Set()
  let centralBonus = 0
  for (const table of [primary, ...backups.map((b) => b.plan)]) {
    for (const [room, facility] of Object.entries(table || {})) {
      for (const slot of facility?.plans || []) {
        for (const name of [slot.agent, ...planReplacements(slot)]) {
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

export function masteryFormWarning(charIds) {
  const forms = {
    char_002_amiya: '术师',
    char_1001_amiya2: '近卫',
    char_1037_amiya3: '医疗'
  }
  const selected = Object.keys(forms).filter((id) => charIds.includes(id))
  if (!selected.length) return ''
  return `已选择阿米娅的${selected.map((id) => forms[id]).join('、')}形态专精，请在训练前确认当前形态与计划一致。`
}
import { planReplacements } from './plan_bindings'
