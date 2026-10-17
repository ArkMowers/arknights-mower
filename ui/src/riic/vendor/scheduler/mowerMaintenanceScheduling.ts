// Mower 3de2b2ac6f1aeff6513b63faaeea4b2369cf8856 maintenance/daily-reset timing (MIT).
import { MOWER_TASK_TYPES as T, toMowerMicros, type MowerTask } from './mowerTaskQueue'
import type { MowerTaskSchedulingOptions } from './mowerTaskScheduling'

type Window = readonly [startMicros: number, endMicros: number]
const day = toMowerMicros(24)
const second = 1_000_000

/** The caller supplies the first reset relative to the simulation clock; zero has no wall-clock meaning. */
export function nextMowerDailyReset(nowMicros: number, firstDailyResetMicros?: number): number | undefined {
  if (firstDailyResetMicros === undefined) return undefined
  return firstDailyResetMicros + Math.max(0, Math.floor((nowMicros - firstDailyResetMicros) / day) + 1) * day
}

/** Orders retain the existing update window; swaps require the announcement's explicit full end. */
export function mowerMaintenanceWindows(nowMicros: number, options: MowerTaskSchedulingOptions, kind: 'orders' | 'swaps'): Window[] {
  const windows: Window[] = [], reset = nextMowerDailyReset(nowMicros, options.firstDailyResetMicros)
  if (reset !== undefined) windows.push([reset, reset])
  if (options.maintenance && (kind === 'orders' || options.maintenanceEndMicros !== undefined)) {
    windows.push([options.maintenance[0], kind === 'orders' ? options.maintenance[1] : options.maintenanceEndMicros!])
  }
  return windows.sort((a, b) => b[0] - a[0] || (kind === 'orders' ? b[1] - a[1] : 0))
}

export function advanceMowerMaintenanceOrders(tasks: MowerTask[], nowMicros: number, options: MowerTaskSchedulingOptions): void {
  if (options.adjustForRunOrders === false) return
  const gap = toMowerMicros(Math.max((options.runOrderDelayMinutes ?? 5) * 2, 10) / 60)
  for (const [start, end] of mowerMaintenanceWindows(nowMicros, options, 'orders')) {
    const deadline = start - gap
    const affected = tasks.filter(task => task.type === T.RUN_ORDER && deadline < task.timeMicros && task.timeMicros < end + gap).sort((a, b) => a.timeMicros - b.timeMicros)
    affected.forEach((task, index) => { task.timeMicros = deadline - (index + 1) * second; task.adjusted = true })
  }
}

/** Reserve operations backwards from each later boundary before considering earlier windows. */
export function advanceMowerMaintenanceSwaps(tasks: MowerTask[], nowMicros: number, options: MowerTaskSchedulingOptions, durationMicros: (task: MowerTask) => number): void {
  if (options.enableMastery === false) return
  const swaps = tasks.filter(task => task.type === T.SWAP_SUPPORT).sort((a, b) => a.timeMicros - b.timeMicros)
  const gap = toMowerMicros(Math.max((options.runOrderDelayMinutes ?? 5) * 2, 10) / 60)
  for (const [start, end] of mowerMaintenanceWindows(nowMicros, options, 'swaps')) {
    if (nowMicros >= start) continue
    let deadline = start - gap
    const affected = swaps.filter(task => deadline < task.timeMicros && (task.timeMicros < end || task.timeMicros === start && start === end))
    for (const swap of affected.reverse()) {
      swap.timeMicros = Math.min(swap.timeMicros, Math.max(nowMicros, deadline - durationMicros(swap) - second))
      swap.advanceSupportSwap = true
      deadline = swap.timeMicros
    }
  }
}
