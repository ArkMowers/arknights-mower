import { afterEach, expect, it, vi } from 'vitest'
import { createSSRApp, defineComponent, effectScope, h } from 'vue'
import { renderToString } from 'vue/server-renderer'
import { i18n } from '@/i18n'
import catalog from '../../../arknights_mower/data/building_skill.json'
import { annotateBasementSkills } from '@/utils/basementSkills'
import { useBasementSkill } from '@/stores/basementSkill'
import SkillRows from './buffer.vue'
import SkillTerms from './bufferinfo.vue'

vi.mock('vue', async (original) => ({
  ...(await original()),
  useSSRContext: () => ({ modules: new Set() })
}))
afterEach(() => {
  i18n.global.locale.value = 'zh-CN'
})

const uiSlot = defineComponent({
  setup:
    (_, { slots }) =>
    () =>
      h('span', slots.default?.())
})
async function render(item) {
  const app = createSSRApp(SkillRows, { item })
  for (const name of ['NAvatar', 'NTag', 'NModal', 'NCard']) app.component(name, uiSlot)
  return renderToString(app)
}

it('renders the official name and effect description in skill rows without replacing the original skill data', async () => {
  const item = annotateBasementSkills(
    [catalog.find((operator) => operator.name === '能天使')],
    null
  )[0]
  const original = JSON.stringify(item)
  expect(await render(item)).toContain('物流专家')
  i18n.global.locale.value = 'en-US'
  const html = await render(item)
  expect(html).toContain('Logistics Expert')
  expect(html).toContain('order acquisition efficiency')
  expect(html).toContain('+35%')
  expect(JSON.stringify(item)).toBe(original)
})

it('keeps the effect dialog open and translates its linked explanations without changing source term IDs', () => {
  const scope = effectScope()
  try {
    const props = { des: '', isbuffer: true, buffer: ['cc_bd_a1'] }
    const original = JSON.stringify(useBasementSkill().buffer.value.cc_bd_a1)
    const component = scope.run(() => SkillTerms.setup(props, { expose: vi.fn() }))
    component.handleTermClick({
      composedPath: () => [{ classList: { contains: (name) => name === 'riic-term' } }]
    })
    expect(component.showModal.value).toBe(true)
    i18n.global.locale.value = 'en-US'
    expect(component.displayedTerms.value[0].termName).toBe('Perception Information')
    expect(component.displayedTerms.value[0].description).toContain('Soundless Resonance')
    i18n.global.locale.value = 'ja-JP'
    expect(component.displayedTerms.value[0].termName).toBe('知覚情報')
    expect(component.showModal.value).toBe(true)
    expect(props.buffer).toEqual(['cc_bd_a1'])
    expect(JSON.stringify(useBasementSkill().buffer.value.cc_bd_a1)).toBe(original)
  } finally {
    scope.stop()
  }
})
