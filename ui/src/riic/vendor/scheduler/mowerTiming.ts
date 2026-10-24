/** Deterministic policy time, excluding device-operation lead times. */
export function mowerReturnDelay(members: { hours: number; full?: boolean }[], powerCount: number, rescue: number): number {
  const full = members.filter(m => m.full)
  if (full.length) return Math.max(...full.map(m => m.hours))
  const first = members[0]?.hours ?? Infinity
  if (members.length > 1 && members.some(m => first - m.hours > (powerCount === 2 ? 1.5 : 1))) return first
  return Math.min(...members.map(m => m.hours), rescue)
}
/** operators.py:predict_exhaust and scheduler_task.py:plan_metadata. */
export function mowerRescueDelay(workers: { morale: number; lower: number; rate: number; ignore?: boolean }[]): number {
  return Math.min(...workers.map(w => Math.max(.5, w.ignore || w.rate <= 0 ? 24 : (w.morale - w.lower) / w.rate - .5)))
}
