<script setup>
import { i18n } from '@/i18n'
const { t } = i18n.global
defineOptions({ name: 'MowerPlanPage' })

import { useConfigStore } from '@/stores/config'
import { useResolvedTheme } from '@/composables/theme'
import { usePlanStore, useRescuePlanStore } from '@/stores/plan'
import { useMowerStore } from '@/stores/mower'
import PlanFacilityLevels from '@/components/PlanFacilityLevels.vue'
import PlanAdvancedSettings from '@/components/PlanAdvancedSettings.vue'
import PlanOperatorSelect from '@/components/PlanOperatorSelect.vue'
import DropDown from '@/components/DropDown.vue'
import { storeToRefs } from 'pinia'
import { useRouter } from 'vue-router'
import { swap } from '@/utils/common'
import {
  OPERATOR_CONF_FIELDS,
  apply_operator_replace,
  collect_plan_operators
} from '@/utils/plan_edit'
import { createSaveCoordinator, drainConfigurationSaves } from '@/utils/configPersistence'
import { CONFIG_GENERATION_HEADER } from '@/composables/configProfiles'

const router = useRouter()
const config_store = useConfigStore()
const { free_blacklist: normal_free_blacklist, theme: themePreference } = storeToRefs(config_store)
const theme = useResolvedTheme(themePreference)

const { rescue = false } = defineProps({ rescue: Boolean })
const plan_store = rescue ? useRescuePlanStore() : usePlanStore()
provide('planStore', plan_store)
const rescue_ready = ref(!rescue)
const mower_store = useMowerStore()
const { running } = storeToRefs(mower_store)
const import_saves = createSaveCoordinator(config_store, plan_store)
const {
  ling_xi,
  mood_limits,
  operator_mood_limits,
  resting_priority,
  resting_priority_replacement,
  free_room_exclusions,
  resting_standby,
  exhaust_require,
  rest_in_full,
  workaholic,
  backup_plans,
  sub_plan,
  refresh_trading,
  refresh_drained,
  ope_resting_priority,
  dorm_order,
  operators,
  plan
} = storeToRefs(plan_store)
const free_blacklist = rescue
  ? storeToRefs(plan_store).rescue_free_blacklist
  : normal_free_blacklist
const { load_plan, fill_empty } = plan_store

import {
  computed,
  defineAsyncComponent,
  inject,
  nextTick,
  onMounted,
  onUnmounted,
  provide,
  ref,
  shallowRef,
  watch,
  watchEffect
} from 'vue'
const axios = inject('axios')

const facility = ref('')
provide('facility', facility)
const preparing_income = ref(false)
const edit_locked = computed(() => import_saves.paused.value || preparing_income.value)
provide('planEditLocked', edit_locked)

import { useDialog, useMessage, NAlert } from 'naive-ui'

const plan_editor = ref(null)
const show_advanced_settings_dialog = ref(false)

const generating_image = ref(false)
const show_mood_limits_dialog = ref(false)

const message = useMessage()
const dialog = useDialog()

function requireEditing() {
  if (edit_locked.value) {
    message.warning(t('plans.busy'))
    return false
  }
  return true
}

const restoring_running_plan = ref(false)

async function restoreRunningPlan() {
  if (rescue || !running.value || restoring_running_plan.value || edit_locked.value) return
  restoring_running_plan.value = true
  let keepPaused = false
  try {
    await import_saves.pauseAndDrain()
    await axios.post(`${import.meta.env.VITE_HTTP_URL}/plan/restore-running`)
    keepPaused = true
    sub_plan.value = 'main'
    await config_store.load_config()
    await load_plan()
    keepPaused = false
    message.success(t('plans.restored'))
  } catch (error) {
    const detail = error.response?.data?.error || error.message || t('plans.restoreFailed')
    message.error(keepPaused ? t('plans.restoreReloadFailed', { detail }) : detail)
  } finally {
    if (!keepPaused) import_saves.resume()
    restoring_running_plan.value = false
  }
}

async function importMainPlan() {
  if (!rescue || !requireEditing()) return
  try {
    await import_saves.pauseAndDrain()
    await plan_store.import_main_plan()
    await plan_store.save_plan()
    message.success(t('plans.copiedMain'))
  } catch (error) {
    message.error(error.response?.data?.error || error.message || t('plans.importMainFailed'))
  } finally {
    import_saves.resume()
  }
}

async function clearRescueBindings() {
  if (!rescue || !requireEditing()) return
  try {
    await import_saves.pauseAndDrain()
    plan_store.clear_rescue_bindings()
    await plan_store.save_plan()
    message.success(t('plans.clearedBindings'))
  } catch (error) {
    message.error(error.response?.data?.error || error.message || t('plans.clearFailed'))
  } finally {
    import_saves.resume()
  }
}

async function returnToSettings() {
  if (!requireEditing()) return
  try {
    await drainConfigurationSaves(config_store, plan_store)
    await router.push('/maasettings')
  } catch (error) {
    message.error(error.message || t('plans.saveFailed'))
  }
}

async function beforeImport() {
  if (!requireEditing()) return false
  try {
    await import_saves.pauseAndDrain()
    return true
  } catch (error) {
    message.error(error.message || t('plans.preImportSaveFailed'))
    return false
  }
}

// Select menus teleport to body; consider the toolbar controls and the popup "inside".
const sub_plan_dropdown_open = ref(false)
let running_status_timer

async function refreshRunningStatus() {
  try {
    await mower_store.get_running()
  } catch {
    running.value = false
  }
}

function onSubPlanShowUpdate(show) {
  // Naive UI closes single-select before emitting its value. Ignore that close.
  if (show) sub_plan_dropdown_open.value = true
}

function onSubPlanSelected() {
  sub_plan_dropdown_open.value = true
}

function onSubPlanOutsidePointer(event) {
  const target = event.target
  if (
    target instanceof Element &&
    target.closest('.mower-sub-plan-controls, .mower-sub-plan-menu')
  ) {
    return
  }
  sub_plan_dropdown_open.value = false
}

function onSubPlanKeydown(event) {
  if (event.key === 'Escape') sub_plan_dropdown_open.value = false
}

onMounted(async () => {
  if (rescue) {
    try {
      await Promise.all([load_plan(), plan_store.load_operators()])
      rescue_ready.value = true
    } catch (error) {
      message.error(t('plans.rescueLoadFailed', { detail: error.message }))
    }
  }
  void refreshRunningStatus()
  running_status_timer = setInterval(refreshRunningStatus, 5000)
  document.addEventListener('pointerdown', onSubPlanOutsidePointer, true)
  document.addEventListener('keydown', onSubPlanKeydown, true)
})
onUnmounted(() => {
  clearInterval(running_status_timer)
  document.removeEventListener('pointerdown', onSubPlanOutsidePointer, true)
  document.removeEventListener('keydown', onSubPlanKeydown, true)
})

import { sleep } from '@/utils/sleep'
import { toBlob } from 'html-to-image'
import { useLoadingBar } from 'naive-ui'

const loading_bar = useLoadingBar()

import Bowser from 'bowser'

import { render_op_option, render_op_label, filterOperatorOption } from '@/utils/op_select'

async function save() {
  await drainConfigurationSaves(config_store, plan_store)
  await plan_store.save_plan()
  generating_image.value = true
  loading_bar.start()
  if (facility.value != '') {
    facility.value = ''
    await sleep(500)
  }
  const browser = Bowser.getParser(window.navigator.userAgent)
  if (browser.getEngine().name == 'WebKit') {
    await toBlob(plan_editor.value.outer)
  }
  const imageTheme = theme.value
  const blob = await toBlob(plan_editor.value.outer, {
    pixelRatio: 3,
    backgroundColor: imageTheme == 'light' ? '#ffffff' : '#000000',
    style: { margin: 0, padding: '8px 0' }
  })
  generating_image.value = false
  loading_bar.finish()
  const form_data = new FormData()
  form_data.append('img', blob)
  form_data.append('theme', imageTheme)
  const { data } = await axios.post(
    `${import.meta.env.VITE_HTTP_URL}/dialog/save/img${rescue ? '?rescue=1' : ''}`,
    form_data,
    {
      responseType: 'blob'
    }
  )
  const url = window.URL.createObjectURL(data)
  const link = document.createElement('a')
  link.href = url
  link.setAttribute('download', 'plan.jpg')
  document.body.appendChild(link)
  link.click()
  document.body.removeChild(link)
  window.URL.revokeObjectURL(url)
}

const mobile = inject('mobile')

const sub_plan_options = computed(() => {
  const result = [
    {
      label: t('plans.mainPlan'),
      value: 'main'
    }
  ]
  for (let i = 0; i < backup_plans.value.length; i++) {
    result.push({
      label: backup_plans.value[i].name,
      value: i
    })
  }
  return result
})

function create_sub_plan() {
  if (!requireEditing()) return
  backup_plans.value.push({
    group_ids: ['default'],
    type: 'global',
    conf: {
      exhaust_require: [],
      free_blacklist: [],
      ling_xi: ling_xi.value,
      mood_limits: null,
      operator_mood_limits: {},
      rest_in_full: [],
      resting_priority: [],
      resting_priority_replacement: [],
      free_room_exclusions: [],
      resting_standby: [],
      workaholic: [],
      refresh_trading: [],
      refresh_drained: [],
      ope_resting_priority: [],
      dorm_order: [],
      dorm_order_override: false,
      removed_operators: Object.fromEntries(OPERATOR_CONF_FIELDS.map((field) => [field, []]))
    },
    plan: fill_empty({}),
    trigger: {
      left: '',
      operator: '',
      right: ''
    },
    task: {},
    name: `plan${backup_plans.value.length}`
  })
  sub_plan.value = backup_plans.value.length - 1
}

function delete_sub_plan() {
  if (!requireEditing()) return
  backup_plans.value.splice(sub_plan.value, 1)
  sub_plan.value = 'main'
}

function update_dorm_order_override(value) {
  if (edit_locked.value) return
  if (sub_plan.value !== 'main') {
    current_conf.value.dorm_order_override = value.length > 0
  }
}

const current_conf = ref({
  ling_xi: ling_xi.value,
  mood_limits: mood_limits.value,
  operator_mood_limits: operator_mood_limits.value,
  rest_in_full: rest_in_full.value,
  resting_priority: resting_priority.value,
  resting_priority_replacement: resting_priority_replacement.value,
  free_room_exclusions: free_room_exclusions.value,
  resting_standby: resting_standby.value,
  workaholic: workaholic.value,
  exhaust_require: exhaust_require.value,
  refresh_trading: refresh_trading.value,
  dorm_order: dorm_order.value
})

const current_removed = computed(() => current_conf.value.removed_operators ?? {})

watchEffect(() => {
  if (sub_plan.value == 'main') {
    current_conf.value = {
      ling_xi: ling_xi.value,
      mood_limits: mood_limits.value,
      operator_mood_limits: operator_mood_limits.value,
      rest_in_full: rest_in_full.value,
      resting_priority: resting_priority.value,
      resting_priority_replacement: resting_priority_replacement.value,
      free_room_exclusions: free_room_exclusions.value,
      resting_standby: resting_standby.value,
      workaholic: workaholic.value,
      exhaust_require: exhaust_require.value,
      refresh_trading: refresh_trading.value,
      free_blacklist: free_blacklist.value,
      refresh_drained: refresh_drained.value,
      ope_resting_priority: ope_resting_priority.value,
      dorm_order: dorm_order.value
    }
  } else {
    current_conf.value = backup_plans.value[sub_plan.value].conf
  }
})

watchEffect(() => {
  if (sub_plan.value == 'main') {
    ling_xi.value = current_conf.value.ling_xi
    mood_limits.value = current_conf.value.mood_limits
    operator_mood_limits.value = current_conf.value.operator_mood_limits
    rest_in_full.value = current_conf.value.rest_in_full
    exhaust_require.value = current_conf.value.exhaust_require
    resting_priority.value = current_conf.value.resting_priority
    resting_priority_replacement.value = current_conf.value.resting_priority_replacement
    free_room_exclusions.value = current_conf.value.free_room_exclusions
    resting_standby.value = current_conf.value.resting_standby
    workaholic.value = current_conf.value.workaholic
    refresh_trading.value = current_conf.value.refresh_trading
    free_blacklist.value = current_conf.value.free_blacklist
    refresh_drained.value = current_conf.value.refresh_drained
    ope_resting_priority.value = current_conf.value.ope_resting_priority
    dorm_order.value = current_conf.value.dorm_order
  } else {
    backup_plans.value[sub_plan.value].conf = current_conf.value
  }
})

const show_trigger_editor = ref(false)
provide('show_trigger_editor', show_trigger_editor)

const show_name_editor = ref(false)
provide('show_name_editor', show_name_editor)

const show_replace_dialog = ref(false)
provide('show_replace_dialog', show_replace_dialog)

const show_task = ref(false)
provide('show_task', show_task)

const add_task = ref(false)
provide('add_task', add_task)

watch(edit_locked, (locked) => {
  if (!locked) return
  show_trigger_editor.value = false
  show_name_editor.value = false
  show_replace_dialog.value = false
  show_task.value = false
})

const replace_source = ref('')
const replace_target = ref('')

// 弹窗关闭（应用或取消）时清空选择，避免重开时旧 target 已进排班 → 误报重复守卫
watch(show_replace_dialog, (open) => {
  if (!open) {
    replace_source.value = ''
    replace_target.value = ''
  }
})

const validating_plan = ref(false)

async function validate_plan() {
  if (validating_plan.value) return
  validating_plan.value = true
  try {
    await nextTick()
    await plan_store.save_plan()
    await plan_store.wait_for_plan_save()
    const { data } = await axios.post(
      `${import.meta.env.VITE_HTTP_URL}/${rescue ? 'rescue-plan/validate' : 'validate-plan'}`,
      {},
      {
        headers: { token: token }
      }
    )
    if (data.status === 'incomplete') {
      message.warning(data.message, { duration: 10000 })
    } else if (data.success) {
      message.success(data.message)
    } else {
      message.error(data.message)
    }
  } catch (error) {
    message.error(t('plans.validationError', { detail: error.message }))
  } finally {
    validating_plan.value = false
  }
}

function replace_main_conf() {
  return {
    rest_in_full: rest_in_full.value,
    exhaust_require: exhaust_require.value,
    workaholic: workaholic.value,
    resting_priority: resting_priority.value,
    resting_priority_replacement: resting_priority_replacement.value,
    free_room_exclusions: free_room_exclusions.value,
    resting_standby: resting_standby.value,
    refresh_trading: refresh_trading.value,
    refresh_drained: refresh_drained.value,
    free_blacklist: free_blacklist.value,
    ope_resting_priority: ope_resting_priority.value,
    operator_mood_limits: operator_mood_limits.value
  }
}

const replace_plan_state = () => ({
  main_plan: plan.value,
  main_conf: replace_main_conf(),
  backup_plans: backup_plans.value
})

// 被替换侧只列排班里出现过的干员（防选了个不在排班里的干员变 no-op）
const replace_source_options = computed(() =>
  collect_plan_operators(replace_plan_state()).map((name) => ({ value: name, label: name }))
)

// 目标干员已在排班 → 提示（不硬禁：重复替换是合理需求，见 #168 修订）
const target_already_in_plan = computed(() => {
  const target = replace_target.value
  if (!target) return false
  return collect_plan_operators(replace_plan_state()).includes(target)
})

function do_replace() {
  if (!requireEditing()) return
  apply_operator_replace(replace_plan_state(), replace_source.value, replace_target.value)
  message.success(t('plans.replaced'))
  show_replace_dialog.value = false
}

function apply_replace() {
  if (!requireEditing()) return
  if (!replace_source.value || !replace_target.value) {
    message.error(t('plans.chooseReplacement'))
    return
  }
  if (replace_source.value === replace_target.value) {
    message.error(t('plans.sameReplacement'))
    return
  }
  if (target_already_in_plan.value) {
    dialog.warning({
      title: t('plans.targetAlreadyExists'),
      content: t('plans.replaceExistingConfirm'),
      positiveText: t('plans.replaceAnyway'),
      negativeText: t('plans.cancel'),
      onPositiveClick: do_replace
    })
    return
  }
  do_replace()
}

import DocumentExport from '@vicons/carbon/es/DocumentExport'
import DocumentImport from '@vicons/carbon/es/DocumentImport'
import IosArrowBack from '@vicons/ionicons4/es/IosArrowBack'
import IosArrowForward from '@vicons/ionicons4/es/IosArrowForward'
import CodeSlash from '@vicons/ionicons5/es/CodeSlash'
import Help from '@vicons/ionicons5/es/Help'
import TrashOutline from '@vicons/ionicons5/es/TrashOutline'
import AddTaskRound from '@vicons/material/es/AddTaskRound'
import RefreshRound from '@vicons/material/es/RefreshRound'
import PlusRound from '@vicons/material/es/PlusRound'
import Pencil from '@vicons/tabler/es/Pencil'
import UndoRound from '@vicons/material/es/UndoRound'

async function import_plan({ event }) {
  try {
    const msg = event.target.response
    if (msg == '排班已加载') {
      sub_plan.value = 'main'
      if (!rescue) await config_store.load_config()
      await load_plan()
      message.success(t('plans.imported'))
    } else {
      message.error(msg)
    }
  } catch (error) {
    message.error(error.message || t('plans.reloadImportedFailed'))
  } finally {
    import_saves.resume()
  }
}

function import_error() {
  import_saves.resume()
  message.error(t('plans.uploadFailed'))
}

const import_url = `${import.meta.env.VITE_HTTP_URL}/import${rescue ? '?rescue=1' : ''}`

const token = inject('token')

const PlanIncomeDialog = defineAsyncComponent(() => import('@/components/PlanIncomeDialog.vue'))
const income_open = ref(false)
const income_snapshot = shallowRef(null)
const income_error = ref('')
let income_preparation = 0
let income_original_facility = null

function closeIncome() {
  if (income_original_facility !== null) facility.value = income_original_facility
  income_original_facility = null
  income_preparation++
  income_open.value = false
  income_snapshot.value = null
  preparing_income.value = false
}
onUnmounted(closeIncome)

async function prepareIncome() {
  if (!requireEditing() || rescue || income_open.value) return
  const generation = ++income_preparation
  income_open.value = true
  preparing_income.value = true
  income_error.value = ''
  income_snapshot.value = null
  income_original_facility = facility.value
  try {
    const plan = JSON.parse(JSON.stringify(plan_store.build_plan()))
    plan.advanced_settings = JSON.parse(JSON.stringify(config_store.build_advanced_settings()))
    const droneRoom = config_store.drone_room
    const { incomeWorkspace } = await import('@/riic/income')
    incomeWorkspace(plan)
    if (generation !== income_preparation) return
    const imageTheme = theme.value
    const label =
      sub_plan.value === 'main' ? t('plans.mainPlan') : backup_plans.value[sub_plan.value].name
    facility.value = ''
    await nextTick()
    if (Bowser.getParser(window.navigator.userAgent).getEngine().name === 'WebKit') {
      await toBlob(plan_editor.value.outer)
    }
    const root = plan_editor.value.outer
    const rootRect = root.getBoundingClientRect()
    const rootStyle = getComputedStyle(root)
    const roomBounds = Object.fromEntries(
      [...root.querySelectorAll('[data-income-room]')].map((element) => {
        const rect = element.getBoundingClientRect()
        return [
          element.dataset.incomeRoom,
          {
            x: (rect.left - rootRect.left - parseFloat(rootStyle.paddingLeft)) * 3,
            y: (rect.top - rootRect.top - parseFloat(rootStyle.paddingTop) + 8) * 3,
            width: rect.width * 3,
            height: rect.height * 3
          }
        ]
      })
    )
    const capture = await toBlob(plan_editor.value.outer, {
      pixelRatio: 3,
      backgroundColor: imageTheme === 'light' ? '#ffffff' : '#000000',
      style: { margin: 0, padding: '8px 0' }
    })
    if (generation !== income_preparation) return
    if (!capture) throw new Error(t('plans.snapshotImageFailed'))
    const form = new FormData()
    form.append('img', capture)
    form.append('plan', JSON.stringify(plan))
    form.append('theme', imageTheme)
    const { data } = await axios.post(`${import.meta.env.VITE_HTTP_URL}/dialog/save/img`, form, {
      responseType: 'blob',
      timeout: 60000
    })
    if (generation === income_preparation)
      income_snapshot.value = { plan, image: data, theme: imageTheme, label, roomBounds, droneRoom }
  } catch (error) {
    if (generation === income_preparation)
      income_error.value = error.message || t('plans.snapshotFailed')
  } finally {
    if (generation === income_preparation) {
      preparing_income.value = false
      if (income_original_facility !== null) facility.value = income_original_facility
      income_original_facility = null
    }
  }
}

const export_options = computed(() => [
  {
    label: t('plans.exportJson'),
    key: 'json'
  }
])

async function export_json() {
  await drainConfigurationSaves(config_store, plan_store)
  await plan_store.save_plan()
  const { data } = await axios.get(
    `${import.meta.env.VITE_HTTP_URL}/${rescue ? 'rescue-plan' : 'export-json'}`,
    {
      responseType: 'blob'
    }
  )
  const url = window.URL.createObjectURL(data)
  const link = document.createElement('a')
  link.href = url
  link.setAttribute('download', 'plan.json')
  document.body.appendChild(link)
  link.click()
  document.body.removeChild(link)
  window.URL.revokeObjectURL(url)
}

function movePlanBackward() {
  if (!requireEditing()) return
  if (sub_plan.value !== 'main' && sub_plan.value > 0) {
    const currentIndex = sub_plan.value
    swap(currentIndex, currentIndex - 1, backup_plans.value)
    sub_plan.value = currentIndex - 1
  }
}

function movePlanForward() {
  if (!requireEditing()) return
  if (sub_plan.value !== 'main' && sub_plan.value < backup_plans.value.length - 1) {
    const currentIndex = sub_plan.value
    swap(currentIndex, currentIndex + 1, backup_plans.value)
    sub_plan.value = currentIndex + 1
  }
}
</script>

<template>
  <template v-if="rescue_ready">
    <trigger-dialog />
    <task-dialog />
    <rename-dialog />
    <div class="plan-toolbar-viewport mx-auto mt-12" :aria-label="t('plans.toolbar')">
      <div class="plan-bar">
        <n-button-group class="plan-restore-group">
          <n-tooltip trigger="hover" placement="top">
            <template #trigger>
              <n-button
                class="plan-restore-button"
                :aria-label="rescue ? t('plans.backSettings') : t('plans.restoreRunning')"
                :disabled="edit_locked || (!rescue && !running)"
                :loading="restoring_running_plan"
                @click="rescue ? returnToSettings() : restoreRunningPlan()"
              >
                <template #icon>
                  <n-icon><ios-arrow-back v-if="rescue" /><undo-round v-else /></n-icon>
                </template>
              </n-button>
            </template>
            {{
              rescue
                ? t('plans.backSettings')
                : running
                  ? t('plans.restoreRunning')
                  : t('plans.restoreAvailable')
            }}
          </n-tooltip>
        </n-button-group>
        <n-button-group class="mower-sub-plan-controls plan-sort-controls">
          <n-button
            :title="t('plans.backupUp')"
            :aria-label="t('plans.backupUp')"
            :disabled="edit_locked || sub_plan == 'main' || sub_plan == 0"
            @click="movePlanBackward"
          >
            <template #icon>
              <n-icon><ios-arrow-back /></n-icon>
            </template>
          </n-button>
          <n-button
            :title="t('plans.backupDown')"
            :aria-label="t('plans.backupDown')"
            :disabled="edit_locked || sub_plan == 'main' || sub_plan == backup_plans.length - 1"
            @click="movePlanForward"
          >
            <template #icon>
              <n-icon><ios-arrow-forward /></n-icon>
            </template>
          </n-button>
        </n-button-group>
        <n-button-group class="mower-sub-plan-controls">
          <n-select
            v-model:value="sub_plan"
            :show="sub_plan_dropdown_open"
            style="width: 150px"
            :options="sub_plan_options"
            :menu-props="{ class: 'mower-sub-plan-menu' }"
            @update:show="onSubPlanShowUpdate"
            @update:value="onSubPlanSelected"
          />
          <n-button :disabled="edit_locked || sub_plan == 'main'" @click="show_name_editor = true">
            <template #icon>
              <n-icon>
                <Pencil />
              </n-icon>
            </template>
          </n-button>
        </n-button-group>
        <n-button-group>
          <n-button :title="t('plans.newBackup')" :disabled="edit_locked" @click="create_sub_plan">
            <template #icon>
              <n-icon :size="22"><plus-round /></n-icon> </template
            >{{ t('plans.newBackup') }}</n-button
          >
          <n-button
            v-if="sub_plan == 'main'"
            :title="t('plans.validate')"
            :loading="validating_plan"
            :disabled="validating_plan"
            @click="validate_plan"
          >
            <template #icon>
              <n-icon><help /></n-icon> </template
            >{{ t('plans.validate') }}</n-button
          >
          <n-button
            v-else
            :title="t('plans.editConditions')"
            :disabled="edit_locked"
            @click="show_trigger_editor = true"
          >
            <template #icon>
              <n-icon><code-slash /></n-icon> </template
            >{{ t('plans.editConditions') }}</n-button
          >
          <n-button
            v-if="sub_plan == 'main'"
            :title="t('plans.replaceOperators')"
            :disabled="edit_locked"
            @click="show_replace_dialog = true"
          >
            <template #icon>
              <n-icon><refresh-round /></n-icon> </template
            >{{ t('plans.replaceOperators') }}</n-button
          >
          <n-button
            v-else
            :title="t('plans.editTasks')"
            :disabled="edit_locked"
            @click="show_task = true"
          >
            <template #icon>
              <n-icon><add-task-round /></n-icon> </template
            >{{ t('plans.editTasks') }}</n-button
          >
          <n-button
            :title="t('plans.deleteBackup')"
            :disabled="edit_locked || sub_plan == 'main'"
            @click="delete_sub_plan"
          >
            <template #icon>
              <n-icon><trash-outline /></n-icon> </template
            >{{ t('plans.deleteBackup') }}</n-button
          >
        </n-button-group>
        <component
          :is="rescue ? DropDown : 'div'"
          v-bind="
            rescue
              ? {
                  select: importMainPlan,
                  options: [{ label: t('plans.importMain'), key: 'main', disabled: edit_locked }]
                }
              : {}
          "
        >
          <n-upload
            :disabled="edit_locked"
            :on-before-upload="beforeImport"
            style="width: auto"
            :action="import_url"
            :headers="
              () => ({
                token,
                [CONFIG_GENERATION_HEADER]: axios.defaults.headers.common[CONFIG_GENERATION_HEADER]
              })
            "
            :show-file-list="false"
            name="img"
            @finish="import_plan"
            @error="import_error"
          >
            <n-button :title="t('plans.importPlan')" :disabled="edit_locked">
              <template #icon>
                <n-icon><document-import /></n-icon> </template
              >{{ t('plans.importPlan') }}</n-button
            >
          </n-upload>
        </component>
        <drop-down :select="export_json" :options="export_options">
          <n-button
            :title="t('plans.exportImage')"
            @click="save"
            :loading="generating_image"
            :disabled="generating_image"
          >
            <template #icon>
              <n-icon><document-export /></n-icon> </template
            >{{ t('plans.exportImage') }}</n-button
          >
        </drop-down>
      </div>
    </div>
    <PlanIncomeDialog
      v-if="income_open"
      :snapshot="income_snapshot"
      :preparing="preparing_income"
      :prepare-error="income_error"
      @close="closeIncome"
    />
    <plan-editor ref="plan_editor" class="w-980 mx-auto mw-980 px-12" />
    <div v-if="!rescue" class="plan-advanced-actions w-980 mx-auto px-12 mw-980">
      <n-button @click="show_advanced_settings_dialog = true">{{ t('plans.advanced') }}</n-button>
      <n-button @click="show_mood_limits_dialog = true">{{ t('plans.moraleLimits') }}</n-button>
      <n-button
        type="success"
        :disabled="edit_locked"
        :loading="preparing_income"
        @click="prepareIncome"
        >{{ t('plans.calculateIncome') }}</n-button
      >
      <PlanFacilityLevels class="inline-power" />
    </div>
    <PlanFacilityLevels v-if="rescue" class="w-980 mx-auto px-12 mw-980" />
    <n-form
      class="w-980 mx-auto mb-12 px-12 mw-980"
      :label-placement="mobile ? 'top' : 'left'"
      :show-feedback="false"
      :label-width="i18n.global.locale.value === 'en-US' ? 220 : 160"
      label-align="left"
    >
      <n-form-item v-if="!rescue">
        <template #label
          ><span>{{ t('plans.fullRecoveryOperators') }}</span
          ><help-text>{{ t('plans.fullRecoveryHelp') }}</help-text></template
        >
        <PlanOperatorSelect
          :disabled="edit_locked"
          :backup="!rescue && sub_plan !== 'main'"
          v-model="current_conf.rest_in_full"
          v-model:removed="current_removed.rest_in_full"
        ></PlanOperatorSelect>
      </n-form-item>
      <n-form-item v-if="!rescue">
        <template #label>
          <span>{{ t('plans.exhaustOperators') }}</span>
          <help-text>{{ t('plans.exhaustHelp') }}</help-text>
        </template>
        <PlanOperatorSelect
          :disabled="edit_locked"
          :backup="!rescue && sub_plan !== 'main'"
          v-model="current_conf.exhaust_require"
          v-model:removed="current_removed.exhaust_require"
        ></PlanOperatorSelect>
      </n-form-item>
      <n-form-item v-if="!rescue">
        <template #label>
          <span>{{ t('plans.highPriorityOperators') }}</span>
          <help-text>
            <p>{{ t('plans.priorityOrderHelp') }}</p>
            <p>{{ t('plans.bedPriorityHelp') }}</p>
            <p>{{ t('plans.fullPriorityHelp') }}</p>
          </help-text>
        </template>
        <PlanOperatorSelect
          :disabled="edit_locked"
          :backup="!rescue && sub_plan !== 'main'"
          v-model="current_conf.ope_resting_priority"
          v-model:removed="current_removed.ope_resting_priority"
        ></PlanOperatorSelect>
      </n-form-item>
      <n-form-item v-if="!rescue">
        <template #label>
          <span>{{ t('plans.lowPriorityOperators') }}</span>
          <help-text>{{ t('plans.lowPriorityHelp') }}</help-text>
        </template>
        <PlanOperatorSelect
          :disabled="edit_locked"
          :backup="!rescue && sub_plan !== 'main'"
          v-model="current_conf.resting_priority"
          v-model:removed="current_removed.resting_priority"
        ></PlanOperatorSelect>
      </n-form-item>
      <n-form-item v-if="!rescue">
        <template #label>
          <span>{{ t('plans.highPriorityReplacements') }}</span>
          <help-text>{{ t('plans.highReplacementHelp') }}</help-text>
        </template>
        <PlanOperatorSelect
          :disabled="edit_locked"
          :backup="!rescue && sub_plan !== 'main'"
          v-model="current_conf.resting_priority_replacement"
          v-model:removed="current_removed.resting_priority_replacement"
        ></PlanOperatorSelect>
      </n-form-item>
      <n-form-item v-if="!rescue">
        <template #label>
          <span>{{ t('plans.standbyOperators') }}</span>
          <help-text
            >{{ t('plans.standbyPriorityHelp') }}
            <p>{{ t('plans.standbyHelp') }}</p>
          </help-text>
        </template>
        <PlanOperatorSelect
          :disabled="edit_locked"
          :backup="!rescue && sub_plan !== 'main'"
          v-model="current_conf.resting_standby"
          v-model:removed="current_removed.resting_standby"
        ></PlanOperatorSelect>
      </n-form-item>
      <n-form-item>
        <template #label>
          <span>{{ t('plans.zeroMoraleOperators') }}</span
          ><help-text>{{ t('plans.zeroMoraleHelp') }}</help-text>
        </template>
        <PlanOperatorSelect
          :disabled="edit_locked"
          :backup="!rescue && sub_plan !== 'main'"
          v-model="current_conf.workaholic"
          v-model:removed="current_removed.workaholic"
        ></PlanOperatorSelect>
      </n-form-item>
      <n-form-item>
        <template #label>
          <span>{{ t('plans.dormBlacklist') }}</span>
          <help-text>{{ t('plans.dormBlacklistHelp') }}</help-text>
        </template>
        <PlanOperatorSelect
          :disabled="edit_locked"
          :backup="!rescue && sub_plan !== 'main'"
          v-model="current_conf.free_blacklist"
          v-model:removed="current_removed.free_blacklist"
        ></PlanOperatorSelect>
      </n-form-item>
      <n-form-item v-if="!rescue">
        <template #label>
          <span>{{ t('plans.retainedDormOperators') }}</span>
          <help-text>{{ t('plans.retainedDormHelp') }}</help-text>
        </template>
        <PlanOperatorSelect
          :disabled="edit_locked"
          :backup="sub_plan !== 'main'"
          v-model="current_conf.free_room_exclusions"
          v-model:removed="current_removed.free_room_exclusions"
        ></PlanOperatorSelect>
      </n-form-item>
      <n-form-item v-if="!rescue">
        <template #label>
          <span>{{ t('plans.refreshTradingOperators') }}</span>
          <help-text>
            <p>{{ t('plans.refreshTradingHelp') }}</p>
            <p>
              {{ t('plans.refreshTradingDefaultHelp') }}<br />{{
                t('plans.refreshTradingExternalHelp')
              }}
            </p>
          </help-text>
        </template>
        <PlanOperatorSelect
          :disabled="edit_locked"
          :backup="!rescue && sub_plan !== 'main'"
          v-model="current_conf.refresh_trading"
          v-model:removed="current_removed.refresh_trading"
        ></PlanOperatorSelect>
      </n-form-item>
      <n-form-item v-if="!rescue">
        <template #label>
          <span>{{ t('plans.refreshExhaustion') }}</span>
          <help-text>
            <p>{{ t('plans.refreshExhaustionHelp') }}</p>
            <p>{{ t('plans.refreshExhaustionTimingHelp') }}</p>
          </help-text>
        </template>
        <PlanOperatorSelect
          :disabled="edit_locked"
          :backup="!rescue && sub_plan !== 'main'"
          v-model="current_conf.refresh_drained"
          v-model:removed="current_removed.refresh_drained"
        ></PlanOperatorSelect>
      </n-form-item>
      <n-form-item>
        <template #label>
          <span>{{ t('plans.dormPriority') }}</span>
          <help-text>{{ t('plans.dormPriorityHelp') }}</help-text>
        </template>
        <slick-dorm-select
          :disabled="edit_locked"
          v-model="current_conf.dorm_order"
          room-only
          include-low
          @update:model-value="update_dorm_order_override"
        ></slick-dorm-select>
      </n-form-item>
    </n-form>
    <div v-if="rescue" class="w-980 mx-auto mb-12 px-12 mw-980">
      <n-space align="center">
        <n-button :disabled="edit_locked" @click="clearRescueBindings">{{
          t('plans.clearBindings')
        }}</n-button>
        <span>{{ t('plans.clearBindingsHelp') }}</span>
      </n-space>
    </div>
    <div v-if="rescue" class="w-980 mx-auto mt-12 mb-12 px-12 mw-980">
      <n-alert :title="t('plans.rescueHelpTitle')" type="info">
        <n-space vertical :size="6">
          <div>{{ t('plans.rescueIntroHelp') }}</div>
          <div>{{ t('plans.rescueCompatibilityHelp') }}</div>
          <div>{{ t('plans.rescueDeploymentHelp') }}</div>
          <div>{{ t('plans.rescueSpecialHelp') }}</div>
          <div>{{ t('plans.rescueReplacementHelp') }}</div>
          <div>{{ t('plans.rescueImportHelp') }}</div>
          <div>{{ t('plans.rescueExitHelp') }}</div>
        </n-space>
      </n-alert>
    </div>
    <n-modal
      v-model:show="show_advanced_settings_dialog"
      :auto-focus="false"
      preset="card"
      :title="t('plans.advanced')"
      :style="{ width: '800px', maxWidth: 'calc(100vw - 24px)' }"
      :content-style="{ maxHeight: '75vh', overflowY: 'auto' }"
    >
      <PlanAdvancedSettings :disabled="edit_locked" />
      <template #footer>
        <n-space justify="end">
          <n-button @click="show_advanced_settings_dialog = false">{{ t('plans.done') }}</n-button>
        </n-space>
      </template>
    </n-modal>
    <n-modal
      v-model:show="show_mood_limits_dialog"
      :auto-focus="false"
      preset="card"
      :title="t('plans.moraleLimits')"
      :style="{ width: '680px', maxWidth: 'calc(100vw - 24px)' }"
      :content-style="{ maxHeight: '70vh', overflowY: 'auto' }"
    >
      <n-form label-placement="top" :show-feedback="false">
        <n-form-item>
          <template #label>
            <span>{{ t('plans.lingDuskMode') }}</span>
            <help-text>
              <div>{{ t('plans.lingDuskWorkHelp') }}</div>
              <div>{{ t('plans.lingDuskAlignHelp') }}</div>
              <div>{{ t('plans.lingDuskPerceptionHelp') }}</div>
              <div>{{ t('plans.lingDuskWorldHelp') }}</div>
              <div>{{ t('plans.lingDuskBalancedHelp') }}</div>
              <div>{{ t('plans.lingDuskPriorityHelp') }}</div>
            </help-text>
          </template>
          <n-radio-group v-model:value="current_conf.ling_xi" :disabled="edit_locked">
            <n-space>
              <n-radio :value="1">{{ t('plans.lingDuskPerception') }}</n-radio>
              <n-radio :value="2">{{ t('plans.lingDuskWorld') }}</n-radio>
              <n-radio :value="3">{{ t('plans.lingDuskBalanced') }}</n-radio>
            </n-space>
          </n-radio-group>
        </n-form-item>
        <n-form-item :label="t('plans.customLimits')">
          <mood-limits-editor
            v-model:defaults="current_conf.mood_limits"
            v-model:overrides="current_conf.operator_mood_limits"
            :disabled="edit_locked"
            :operators="operators"
            :is-backup="sub_plan !== 'main'"
          />
        </n-form-item>
      </n-form>
      <template #footer>
        <n-space justify="end">
          <n-button @click="show_mood_limits_dialog = false">{{ t('plans.done') }}</n-button>
        </n-space>
      </template>
    </n-modal>
    <n-modal
      v-model:show="show_replace_dialog"
      preset="card"
      :title="t('plans.replaceOperators')"
      :style="{ width: '560px' }"
    >
      <n-alert :title="t('plans.warning')" type="warning">{{ t('plans.replaceWarning') }}</n-alert>
      <div class="replace-flow">
        <div class="replace-side">
          <div class="replace-side-label">{{ t('plans.sourceOperator') }}</div>
          <n-select
            v-model:value="replace_source"
            :disabled="edit_locked"
            :options="replace_source_options"
            :placeholder="t('plans.chooseSource')"
            filterable
            :filter="filterOperatorOption"
            :render-label="render_op_label"
            :render-option="render_op_option"
          />
        </div>
        <svg
          class="replace-arrow"
          width="24"
          height="24"
          viewBox="0 0 24 24"
          fill="none"
          aria-hidden="true"
        >
          <path
            d="M5 12h13m-5-5 5 5-5 5"
            stroke="currentColor"
            stroke-width="2"
            stroke-linecap="round"
            stroke-linejoin="round"
          />
        </svg>
        <div class="replace-side">
          <div class="replace-side-label">{{ t('plans.targetOperator') }}</div>
          <n-select
            v-model:value="replace_target"
            :disabled="edit_locked"
            :options="operators"
            :placeholder="t('plans.chooseTarget')"
            filterable
            :filter="filterOperatorOption"
            :render-label="render_op_label"
            :render-option="render_op_option"
          />
        </div>
      </div>
      <n-alert
        v-if="target_already_in_plan"
        :title="t('plans.targetAlreadyExists')"
        type="warning"
        class="replace-duplicate"
        >{{ t('plans.targetAlreadyExistsHelp') }}</n-alert
      >
      <template #footer>
        <n-space justify="end">
          <n-button @click="show_replace_dialog = false">{{ t('plans.cancel') }}</n-button>
          <n-button type="primary" :disabled="edit_locked" @click="apply_replace">{{
            t('plans.replace')
          }}</n-button>
        </n-space>
      </template>
    </n-modal>
  </template>
</template>

<style scoped lang="scss">
.plan-advanced-actions.mx-auto {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 12px;
  margin-bottom: 12px;
}

.inline-power {
  margin: 0;
}

.w-980 {
  width: 100%;
  max-width: 980px;
}

.mx-auto {
  margin: 0 auto;
}

.mt-12 {
  margin-top: 12px;
}

.mb-12 {
  margin-bottom: 12px;
}

.px-12 {
  padding: 0 12px;
}

.mw-980 {
  min-width: 980px;
}

.plan-restore-button {
  min-width: 34px;
  padding: 0 6px;
}

.plan-restore-group {
  flex-shrink: 0;
}

.plan-toolbar-viewport {
  box-sizing: border-box;
  position: sticky;
  top: 0;
  z-index: 10;
  width: calc(100% - 16px);
  max-width: 1180px;
  min-height: 52px;
  overflow-x: auto;
  overflow-y: hidden;
  padding: 8px 0 12px;
  background-color: var(--n-color, #fff);
  scrollbar-width: thin;
  scrollbar-color: #a0a7a5 transparent;
  overscroll-behavior-x: contain;
}

.plan-bar {
  box-sizing: border-box;
  display: flex;
  flex-direction: row;
  flex-wrap: nowrap;
  width: max-content;
  min-width: 100%;
  min-height: 36px;
  gap: clamp(2px, 0.3vw, 5px);
  padding: 0 8px;
  align-items: center;
  justify-content: center;
  white-space: nowrap;
  overflow: visible;
}

.plan-bar > * {
  flex-shrink: 0;
}

.plan-bar :deep(.n-button) {
  padding-inline: clamp(5px, 0.45vw, 9px);
  min-width: 0;
}

.plan-sort-controls :deep(.n-button) {
  width: 32px;
  min-width: 32px;
  padding-inline: 5px;
}

.plan-bar :deep(.n-button__content) {
  gap: 4px;
}

.replace-flow {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-top: 12px;
}

.replace-side {
  flex: 1;
  min-width: 0;
}

.replace-side-label {
  margin-bottom: 6px;
  font-size: 13px;
  color: rgb(153, 153, 153);
}

.replace-arrow {
  flex-shrink: 0;
  color: rgb(153, 153, 153);
}

.replace-duplicate {
  margin-top: 12px;
}
</style>
