import { describe, expect, it } from 'vitest'
import {
  createState,
  insertTask,
  moveTask,
  nextBase,
  nextRun,
  removeTask,
  simulateDay
} from './data'
import { cadenceLabel } from './shared'

describe('taskflow prototype editing', () => {
  it.each([null, 0, -1, NaN, Infinity])('keeps previews bounded for MAA interval %s', (gap) => {
    const state = createState()
    state.globals.maaGap = gap
    expect(simulateDay(state).some((run) => run.section === 'maa')).toBe(false)
    expect(nextRun(state, 'maa-fight')).toBe('—')
    expect(nextBase(state)).toMatchObject({ id: 'clue', at: '15:18', gap: 54, open: true })
    state.globals.maaGap = 6
    expect(simulateDay(state).filter((run) => run.id === 'maa-fight')).toHaveLength(4)
  })

  it.each([
    ['drone', 'drone_interval', 6],
    ['trust', 'trust_rotation_interval', 6],
    ['recruit', 'recruit_gap', 6]
  ])('uses the edited interval for %s in the preview and description', (id, key, hours) => {
    const state = createState()
    const task = state.tasks.find((t) => t.id === id)
    task.fields.find((f) => f.key === key).value = hours
    expect(
      simulateDay(state)
        .filter((run) => run.id === id)
        .map((run) => run.hour)
    ).toEqual([4.3, 10.3, 16.3, 22.3])
    expect(nextRun(state, id)).toBe('16:18')
    expect(cadenceLabel(state, task)).toBe('每 6 小时')
    task.fields.find((f) => f.key === key).value = null
    expect(nextRun(state, id)).toBe('—')
  })

  it('keeps an appended MAA task ahead of long tasks', () => {
    const state = createState()
    insertTask(state, 'maa-recruit', 'maa')
    expect(state.tasks.slice(-3).map((task) => task.id)).toEqual([
      'maa-award',
      'maa-recruit',
      'rogue'
    ])
  })

  it('restores an empty section before the following section', () => {
    const state = createState()
    for (const task of [...state.tasks].filter((task) => task.section === 'maa')) {
      removeTask(state, task.id)
    }
    insertTask(state, 'maa-fight', 'maa')
    expect(state.tasks.slice(-2).map((task) => task.id)).toEqual(['maa-fight', 'rogue'])
  })

  it('inserts a daily task at its fixed position and ignores reordering of base and daily tasks', () => {
    const state = createState()
    insertTask(state, 'mastery', 'daily', 0)
    expect(state.tasks.filter((task) => task.section === 'daily').map((task) => task.id)).toEqual([
      'trust',
      'visit',
      'report',
      'skland',
      'mail',
      'recruit',
      'depot',
      'mastery',
      'stage'
    ])
    const before = state.tasks.map((task) => task.id)
    moveTask(state, 'visit', -1)
    moveTask(state, 'shift', 1)
    moveTask(state, 'missing', 1)
    expect(state.tasks.map((task) => task.id)).toEqual(before)
    moveTask(state, 'maa-fight', 1)
    expect(state.tasks.filter((task) => task.section === 'maa').map((task) => task.id)).toEqual([
      'maa-mall',
      'maa-fight',
      'maa-award'
    ])
  })

  it('limits a long-task preview to the active window when the pause crosses midnight', () => {
    const state = createState()
    state.globals.longPause = [23, 7]
    expect(simulateDay(state).find((run) => run.id === 'rogue')).toEqual({
      id: 'rogue',
      section: 'long',
      hour: 7.5,
      span: 15
    })
    state.globals.longPause = [0, 24]
    expect(nextRun(state, 'rogue')).toBe('—')
  })
})
