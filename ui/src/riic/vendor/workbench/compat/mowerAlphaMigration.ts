/** Document migrations from Mower alpha ab0a4e5; unknown fields remain intact. */
const record = (value: unknown): value is Record<string, unknown> => !!value && typeof value === 'object' && !Array.isArray(value)
import { effectiveMowerDormOrder, MOWER_DEFAULT_DORM_ORDER as defaultDormOrder } from '../../domain/mowerDormOrder'

export function normalizeMowerDormOrder(value: string): string {
  return effectiveMowerDormOrder(value.split(',')).join(',')
}

/** Recognizes direct calls in ordinary Python expressions without evaluating them.
 * String literals/comments are opaque. This is deliberately not a Python interpreter.
 */
export function containsRetiredRescueCondition(value: unknown): boolean {
  if (record(value)) return Object.values(value).some(containsRetiredRescueCondition)
  if (typeof value !== 'string') return false
  const tokens = value.match(/(?:[rRuUbBfF]{0,2})?(?:'''[\s\S]*?'''|"""[\s\S]*?"""|'(?:\\[\s\S]|[^'\\])*'|"(?:\\[\s\S]|[^"\\])*")|#[^\n]*|[A-Za-z_]\w*|[^\s]/g) ?? []
  // Incomplete strings/delimiters are not callable expressions. Preserve them
  // for the normal condition validator instead of silently retiring a backup.
  const stack: string[] = []
  for (const token of tokens) {
    if (token === "'" || token === '"') return false
    if (['(', '[', '{'].includes(token)) stack.push(token)
    else if ([')', ']', '}'].includes(token) && stack.pop() !== ({ ')': '(', ']': '[', '}': '{' }[token])) return false
  }
  if (stack.length) return false
  return tokens.some((token, index) => token === 'op_data' && tokens[index - 1] !== '.' && tokens[index + 1] === '.' && tokens[index + 2] === 'rescue_needed' && tokens[index + 3] === '(')
}

export function migrateMowerAlphaDocument(input: Record<string, unknown>): {
  document: Record<string, unknown>; retiredBackupPlans: unknown[]; warnings: string[]
} {
  const document = structuredClone(input)
  const warnings: string[] = [], retiredBackupPlans: unknown[] = []
  if (record(document.advanced_settings)) {
    const settings = document.advanced_settings
    const legacyOrder = settings.dorm_order
    if (typeof legacyOrder === 'string' && legacyOrder) {
      const conf = record(document.conf) ? document.conf : {}
      if (!conf.dorm_order) conf.dorm_order = legacyOrder
      document.conf = conf
    }
    for (const key of ['dorm_order', 'reload_room', 'experimental_dorm_logic', 'refresh_backup_plan_after_mood', 'workshop_low_priority_rest']) {
      if (key in settings) { delete settings[key]; warnings.push(`已按 Mower alpha 迁移退役设置 advanced_settings.${key}`) }
    }
  }
  if (record(document.conf) && typeof document.conf.dorm_order === 'string' && document.conf.dorm_order) {
    document.conf.dorm_order = normalizeMowerDormOrder(document.conf.dorm_order)
  }
  if (Array.isArray(document.backup_plans)) {
    document.backup_plans = document.backup_plans.filter(backup => {
      if (!record(backup)) return true
      if (containsRetiredRescueCondition(backup.trigger)) {
        retiredBackupPlans.push(backup)
        warnings.push(`已停用退役救急副表「${typeof backup.name === 'string' ? backup.name : '未命名'}」；原始内容保留在本地兼容数据中`)
        return false
      }
      for (const key of ['trigger_timing', 'exit_trigger_timing']) {
        if (key in backup) { delete backup[key]; warnings.push(`已移除副表退役选项 ${key}`) }
      }
      if (record(backup.conf)) {
        const conf = backup.conf
        const rawOrder = typeof conf.dorm_order === 'string' ? conf.dorm_order : ''
        if (conf.dorm_order_override != null || rawOrder) {
          const normalized = rawOrder ? normalizeMowerDormOrder(rawOrder) : ''
          const override = conf.dorm_order_override == null
            ? !!normalized && normalized !== defaultDormOrder.join(',') : !!conf.dorm_order_override
          conf.dorm_order = override ? normalized : ''
          conf.dorm_order_override = override
        }
      }
      return true
    })
  }
  return { document, retiredBackupPlans, warnings }
}
