// PROTOTYPE：E/F/G 三个变体共用的小工具，选定方案后删除。
import { computed } from 'vue'
import { fmt, nextBase, reorderable, taskInterval } from './data'

export const sectionTitle = {
  base: '基建队列',
  daily: '日常',
  maa: 'MAA 日常',
  long: '长任务'
}

export const idleLabel = (state) =>
  state.globals.idle.options.find(([v]) => v === state.globals.idle.value)?.[1]

export const pauseLabel = (state) => {
  const [a, b] = state.globals.longPause
  return `${fmt(a)}–${fmt(b)}`
}

export function cadenceLabel(state, task) {
  if (task.cadence.kind === 'every') {
    const gap = taskInterval(state, task)
    return Number.isFinite(gap) && gap >= 1 ? `每 ${gap} 小时` : '请填写间隔'
  }
  return task.trigger
}

export function useFlow(state) {
  const of = (section) => state.tasks.filter((t) => t.section === section)
  const spareOf = (section) => state.spare.filter((t) => t.section === section)
  const gate = computed(() => nextBase(state))
  return { of, spareOf, gate, reorderable }
}
