import { operatorDisplayName } from '@/i18n/gameNames'
import { i18n } from '@/i18n'
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
    ? i18n.global.t('growth.supportHelper.isAssignedOutsideTheTrainingRoomMastery', {
        value0: operatorDisplayName(name)
      })
    : ''
}

export function masteryFormWarning(charIds) {
  const forms = {
    char_002_amiya: 'CASTER',
    char_1001_amiya2: 'WARRIOR',
    char_1037_amiya3: 'MEDIC'
  }
  const selected = Object.keys(forms).filter((id) => charIds.includes(id))
  if (!selected.length) return ''
  return i18n.global.t('growth.supportHelper.masteryPlansIncludeSFormsSklandData', {
    value0: selected
      .map((id) => i18n.global.t(`growth.format.profession${forms[id]}`))
      .join(i18n.global.locale.value === 'en-US' ? ', ' : '、')
  })
}
import { planReplacements } from './plan_bindings'
