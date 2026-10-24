import { renderToString } from '@vue/server-renderer'
import { createSSRApp, defineComponent, h, reactive, toRefs } from 'vue'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import MaaReward from './MaaReward.vue'
import { createTaskWorkflow, setTaskEnabled } from '@/task-workflow/model'

const state = vi.hoisted(() => ({ config: null, checkboxes: [] }))
vi.mock('@/stores/config', () => ({ useConfigStore: () => state.config }))
vi.mock('pinia', () => ({ storeToRefs: (store) => toRefs(store) }))
vi.mock('naive-ui', () => {
  const wrapper = defineComponent(
    (_, { slots }) =>
      () =>
        h('div', slots.default?.())
  )
  return {
    NCard: defineComponent(
      (_, { slots }) =>
        () =>
          h('section', [h('header', slots.header?.()), slots.default?.()])
    ),
    NFlex: wrapper,
    NDivider: wrapper,
    NCheckbox: defineComponent({
      props: ['checked', 'indeterminate'],
      emits: ['update:checked'],
      setup(props, { slots, emit, attrs }) {
        state.checkboxes.push({
          props,
          label: attrs['aria-label'],
          update: (value) => emit('update:checked', value)
        })
        return () => h('label', slots.default?.())
      }
    })
  }
})

beforeEach(() => {
  state.config = reactive({
    maa_mail: false,
    maa_recruit: true,
    maa_orundum: false,
    maa_mining: false,
    maa_specialaccess: false,
    check_mail_enable: true,
    mail_skip_clear_read: false,
    recruit_enable: false,
    visit_friend_enable: true,
    maa_credit_fight: true,
    stage_plan_enable: true,
    maa_mall_enable: false
  })
  state.checkboxes = []
})

async function renderRewards() {
  state.checkboxes = []
  return renderToString(createSSRApp(MaaReward))
}
function header() {
  return state.checkboxes.find(({ label }) => label === '启用MAA 领取奖励')
}
function expectSelection(checked, indeterminate) {
  expect(header().props).toMatchObject({ checked, indeterminate })
  const workflow = createTaskWorkflow(state.config)
  expect(workflow.statuses.rewards).toBe(checked)
  expect(workflow.tasks.find(({ id }) => id === 'rewards').indeterminate).toBe(indeterminate)
}

describe('MAA reward card aggregate checkbox', () => {
  it('keeps the card title and all five individual choices visible with a partial selection', async () => {
    const html = await renderRewards()
    expect(html).toContain('<header>')
    expect(html.match(/<header>(.*?)<\/header>/s)[1]).toContain('MAA 领取奖励')
    expect(html).toContain('领取赠送月卡奖励')
    expect(state.checkboxes).toHaveLength(6)
    expectSelection(false, true)
  })

  it('selects and clears all reward options from the header while preserving other task choices', async () => {
    await renderRewards()
    const before = { ...state.config }
    header().update(true)
    await renderRewards()
    expectSelection(true, false)
    expect(state.config).toEqual({
      ...before,
      maa_mail: true,
      maa_recruit: true,
      maa_orundum: true,
      maa_mining: true,
      maa_specialaccess: true
    })
    state.checkboxes[1].update(false)
    await renderRewards()
    expectSelection(false, true)
    header().update(false)
    await renderRewards()
    expectSelection(false, false)
    expect(state.config).toEqual({ ...before, maa_recruit: false })
  })

  it('reflects directory toggles and individual reward edits through the same stored fields', async () => {
    setTaskEnabled(state.config, 'rewards', true)
    await renderRewards()
    expectSelection(true, false)
    state.config.maa_specialaccess = false
    await renderRewards()
    expectSelection(false, true)
    setTaskEnabled(state.config, 'rewards', false)
    await renderRewards()
    expectSelection(false, false)
  })
})
