import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { createSSRApp, effectScope, h } from 'vue'
import { renderToString } from 'vue/server-renderer'
import MetroVariant from './MetroVariant.vue'
import LoopVariant from './LoopVariant.vue'
import SchematicVariant from './SchematicVariant.vue'
import ScoreVariant from './ScoreVariant.vue'
import { createState, removeTask } from './data'

vi.mock('vue', async (original) => ({
  ...(await original()),
  useSSRContext: () => ({ modules: new Set() })
}))
vi.mock('naive-ui', () => ({
  ...Object.fromEntries(
    [
      'NSpace',
      'NSwitch',
      'NInputNumber',
      'NRadioGroup',
      'NRadio',
      'NSelect',
      'NInput',
      'NSlider'
    ].map((name) => [
      name,
      {
        setup:
          (_, { slots }) =>
          () =>
            h('div', slots.default?.())
      }
    ])
  ),
  NButton: {
    setup:
      (_, { slots }) =>
      () =>
        h('button', slots.default?.())
  }
}))

const scopes = []
function setup(Component, state) {
  const scope = effectScope()
  scopes.push(scope)
  return scope.run(() => Component.setup({ state }, { expose: vi.fn() }))
}

beforeEach(() => {
  vi.stubGlobal('window', { matchMedia: () => ({ matches: true }) })
})
afterEach(() => {
  for (const scope of scopes.splice(0)) scope.stop()
  vi.unstubAllGlobals()
})

describe.each([
  ['Metro', MetroVariant],
  ['Loop', LoopVariant]
])('%s task reinsertion', (name, Component) => {
  it.each(
    [['base'], ['daily'], ['maa'], ['long'], ['maa', 'long'], ['base', 'daily', 'maa', 'long']].map(
      (sections) => [sections]
    )
  )('keeps cleared sections %j insertable', (sections) => {
    const state = createState()
    for (const task of [...state.tasks]) {
      if (sections.includes(task.section)) removeTask(state, task.id)
    }
    const page = setup(Component, state)
    const slots = () => (name === 'Metro' ? page.layout.value.slots : page.slots.value)
    const sectionOf = (slot) => slot.section ?? slot.key

    for (const section of sections) {
      expect(slots().some((slot) => sectionOf(slot) === section)).toBe(true)
    }
    for (const slot of slots()) {
      expect(Number.isFinite(slot.x)).toBe(true)
      expect(Number.isFinite(slot.y)).toBe(true)
    }

    for (const section of sections) {
      const slot = slots().find((entry) => sectionOf(entry) === section)
      const task = state.spare.find((entry) => entry.section === section)
      if (name === 'Metro') page.openInsert(slot)
      else page.inserting.value = slot
      page.doInsert(task.id)

      expect(state.tasks.some((entry) => entry.id === task.id)).toBe(true)
      expect(state.selected).toBe(task.id)
      const displayed =
        name === 'Metro'
          ? page.layout.value.stations.map((station) => station.task.id)
          : [...page.leftStops.value, ...page.rightStops.value].map((station) => station.item.id)
      expect(displayed).toContain(task.id)
    }
  })
})

it('keeps the Metro MAA insertion control when only one MAA task remains', () => {
  const state = createState()
  for (const id of ['maa-mall', 'maa-award']) removeTask(state, id)
  const page = setup(MetroVariant, state)
  const slot = page.layout.value.slots.find((entry) => entry.section === 'maa')
  expect(slot).toBeDefined()
  page.openInsert(slot)
  page.doInsert('maa-mall')
  expect(page.layout.value.stations.some((station) => station.task.id === 'maa-mall')).toBe(true)
})

it.each(['shift', 'maa-fight', 'rogue'])(
  'closes the Schematic inspector after removing %s',
  (id) => {
    const state = createState()
    const page = setup(SchematicVariant, state)
    page.pick(id)
    expect(page.task.value.id).toBe(id)

    page.removeSelectedTask()

    expect(page.sel.value).toBeNull()
    expect(page.task.value).toBeUndefined()
    expect(state.tasks.some((task) => task.id === id)).toBe(false)
    expect(state.spare.some((task) => task.id === id)).toBe(true)
  }
)

describe.each([
  ['Metro', MetroVariant, '前移一站'],
  ['Score', ScoreVariant, '← 前移']
])('%s task order controls', (_, Component, moveLabel) => {
  it.each([
    ['shift', false],
    ['trust', false],
    ['maa-fight', true]
  ])('shows move controls for %s: %s', async (id, reorderable) => {
    const state = createState()
    state.selected = id
    const html = await renderToString(createSSRApp(Component, { state }))
    if (reorderable) expect(html).toContain(moveLabel)
    else expect(html).not.toContain(moveLabel)
  })
})
