import {MOWER_TASK_TYPES as T,type MowerTask} from './mowerTaskQueue'

/** Explicit arrangements finish before startup proposes a new correction. */
export function mowerInitialStaffingBlocked(tasks:readonly MowerTask[],nowMicros:number):boolean {
 return tasks.some(task=>task.backupShiftActive||
  [T.SHIFT_ON,T.SHIFT_OFF,T.SELF_CORRECTION].includes(task.type)&&Object.keys(task.plan).length>0&&task.timeMicros<=nowMicros)
}
