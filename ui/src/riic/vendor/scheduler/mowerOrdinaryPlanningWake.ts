import { MowerTask } from './mowerTaskQueue'

function samePlanningWakeState(task: MowerTask, fresh: MowerTask): boolean {
  const keys = Reflect.ownKeys(fresh)
  return (
    Object.getPrototypeOf(task) === Object.getPrototypeOf(fresh) &&
    Reflect.ownKeys(task).length === keys.length &&
    keys.every((key) => {
      if (!Object.hasOwn(task, key)) return false
      if (key === 'timeMicros') return true
      const value = Reflect.get(task, key),
        expected = Reflect.get(fresh, key)
      if (value === expected) return true
      if (
        expected === null ||
        typeof expected !== 'object' ||
        value === null ||
        typeof value !== 'object' ||
        Object.getPrototypeOf(value) !== Object.getPrototypeOf(expected)
      )
        return false
      if (Array.isArray(expected))
        return Array.isArray(value) && !value.length && Reflect.ownKeys(value).length === 1
      if (expected instanceof Set)
        return value instanceof Set && !value.size && !Reflect.ownKeys(value).length
      return !Reflect.ownKeys(expected).length && !Reflect.ownKeys(value).length
    })
  )
}

export function hasMowerPlanningWake(
  tasks: readonly MowerTask[],
  fresh: MowerTask,
  current?: MowerTask
): boolean {
  return tasks.some(
    (task) =>
      task !== current && task.timeMicros <= fresh.timeMicros && samePlanningWakeState(task, fresh)
  )
}
