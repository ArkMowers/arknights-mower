import { renderToString } from '@vue/server-renderer'
import { createSSRApp, defineComponent, getCurrentInstance, h, ref } from 'vue'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import MaaWeekly from './MaaWeekly.vue'
import { CHIP_STAGES } from '@/utils/maa_weekly_plan'

const state = vi.hoisted(() => ({
  config: {},
  editor: null,
  tableProps: null,
  applyChips: null,
  showTable: null
}))
vi.mock('@/stores/config', () => ({ useConfigStore: () => ({}) }))
vi.mock('pinia', () => ({ storeToRefs: () => state.config }))
vi.mock('axios', () => ({ default: { get: vi.fn(async () => ({ data: [] })) } }))
vi.mock('./WeeklyPlanSelector.vue', () => ({ default: defineComponent(() => () => h('div')) }))
vi.mock('./HelpText.vue', () => ({ default: defineComponent(() => () => h('div')) }))
vi.mock('./MowerInputNumber.vue', () => ({ default: defineComponent(() => () => h('div')) }))
vi.mock('./MaaStageInventory.vue', () => ({
  default: defineComponent({
    emits: ['chip-limits-applied'],
    setup(_, { emit }) {
      let parent = getCurrentInstance().parent
      while (parent && !parent.type.__file?.endsWith('/MaaWeekly.vue')) parent = parent.parent
      state.editor = parent
      state.applyChips = () => emit('chip-limits-applied')
      return () => h('button', { onClick: state.applyChips }, '一键芯片上限')
    }
  })
}))
vi.mock('./MaaWeeklyTable.vue', () => ({
  default: defineComponent({
    props: ['stageOrder'],
    setup(props) {
      state.tableProps = props
      return () => h('div')
    }
  })
}))
vi.mock('naive-ui', () => {
  const wrapper = defineComponent({
    setup:
      (_, { slots }) =>
      () =>
        h('div', slots.default?.())
  })
  return {
    ...Object.fromEntries(
      [
        'NA',
        'NButton',
        'NCard',
        'NCheckbox',
        'NCheckboxGroup',
        'NFlex',
        'NForm',
        'NFormItem',
        'NInput',
        'NModal',
        'NRadio',
        'NRadioGroup',
        'NSelect',
        'NSpace',
        'NTabs',
        'NTag'
      ].map((name) => [name, wrapper])
    ),
    NTabPane: defineComponent({
      props: ['name'],
      setup:
        (props, { slots }) =>
        () =>
          h('div', props.name === 'table' && !state.showTable.value ? [] : slots.default?.())
    })
  }
})

describe('周计划芯片按钮排序联动', () => {
  let storage
  beforeEach(() => {
    storage = new Map([
      [
        'maa-weekly-plan-table-stage-order',
        JSON.stringify(['CE-6', 'PR-D-2', '1-7', 'Annihilation'])
      ]
    ])
    vi.stubGlobal('window', {
      localStorage: {
        getItem: (key) => storage.get(key) ?? null,
        setItem: (key, value) => storage.set(key, value)
      }
    })
    state.showTable = ref(false)
    state.tableProps = null
    state.config = Object.fromEntries(
      [
        'stage_plan_enable',
        'stage_plan_runner',
        'medicine_expire_days',
        'expiring_medicine_on_weekend',
        'maa_report_to_yituliu',
        'maa_yituliu_id',
        'maa_penguin_id',
        'ap_fallback'
      ].map((key) => [key, ref('')])
    )
    state.config.maa_weekly_plan = ref([
      { weekday: '周一', stage: ['1-7', 'PR-B-2', 'Annihilation'], medicine: 2 },
      { weekday: '周二', stage: ['1-7', 'PR-D-2', 'CE-6'], sanity_threshold: 50 }
    ])
  })
  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('表格未挂载时按钮仍更新共享排序和每日执行顺序', async () => {
    const app = createSSRApp(MaaWeekly)
    app.provide('mobile', false)
    app.component(
      'mower-input-number',
      defineComponent(() => () => h('div'))
    )
    await renderToString(app)
    expect(state.tableProps).toBeNull()
    state.applyChips()
    expect(state.editor.setupState.tableStageOrder).toEqual([
      'Annihilation',
      ...CHIP_STAGES,
      'CE-6',
      '1-7'
    ])
    expect(state.config.maa_weekly_plan.value).toEqual([
      { weekday: '周一', stage: ['Annihilation', 'PR-B-2', '1-7'], medicine: 2 },
      { weekday: '周二', stage: ['PR-D-2', 'CE-6', '1-7'], sanity_threshold: 50 }
    ])
  })
})
