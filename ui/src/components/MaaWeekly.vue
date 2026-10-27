<script setup>
import { i18n } from '@/i18n'
const { t } = i18n.global

defineProps({ showEnable: { type: Boolean, default: true } })
import { storeToRefs } from 'pinia'
import { NTag, NCheckbox } from 'naive-ui'
import axios from 'axios'
import { computed, h, inject, onMounted, onBeforeUnmount, ref, watch } from 'vue'
import { useConfigStore } from '@/stores/config'
import { useResourceVersionStore } from '@/stores/resourceVersion'
import {
  CHIP_STAGES,
  WEEKDAYS,
  formatWeekday,
  buildStageOptions,
  createStageOption,
  formatStageLabel,
  getGameWeekdayIndex,
  isStageAvailableOnWeekday,
  promoteChipStageOrder,
  reorderWeeklyPlanStages,
  setStageForWeekday
} from '@/utils/maa_weekly_plan'
import MaaWeeklyTable from './MaaWeeklyTable.vue'
import MaaStageInventory from './MaaStageInventory.vue'
import WeeklyPlanSelector from './WeeklyPlanSelector.vue'

const store = useConfigStore()
const {
  maa_weekly_plan,
  stage_plan_enable,
  stage_plan_runner,
  medicine_expire_days,
  maa_report_to_yituliu,
  maa_yituliu_id,
  maa_report_to_penguin,
  maa_penguin_id,
  ap_fallback
} = storeToRefs(store)

const mobile = inject('mobile')

// 最近开启活动（后端当前资源包）：prepend 到关卡下拉最前
const latestActivityOptions = ref([])
const activityLoading = ref(false)
const activityErrorKey = ref('')
const activityError = computed(() => (activityErrorKey.value ? t(activityErrorKey.value) : ''))
const resourceVersion = useResourceVersionStore()
let activityRequest = 0
onBeforeUnmount(() => {
  activityRequest += 1
})

async function loadLatestActivityStages() {
  const request = ++activityRequest
  activityLoading.value = true
  activityErrorKey.value = ''
  try {
    const response = await axios.get(`${import.meta.env.VITE_HTTP_URL}/stage/latest-activity`)
    if (request !== activityRequest) return
    latestActivityOptions.value = Array.isArray(response.data) ? response.data : []
  } catch {
    if (request !== activityRequest) return
    latestActivityOptions.value = []
    activityErrorKey.value = 'tasks.eventStagesFailed'
  } finally {
    if (request === activityRequest) activityLoading.value = false
  }
}

onMounted(loadLatestActivityStages)
watch(() => resourceVersion.info.current_version, loadLatestActivityStages)

const copyDialogVisible = ref(false)
const copyStageValue = ref('')
const copySourceWeekday = ref('')
const copyTargetDays = ref([])
let copyDialogLongPressTimer = null
let copyDialogLongPressTriggered = false

// 关卡过滤开关（活动期间可关闭）
const filterStageByAvailability = ref(true)
const editorModeStorageKey = 'maa-weekly-plan-editor-mode'
const savedEditorMode = window.localStorage.getItem(editorModeStorageKey)
const editorMode = ref(savedEditorMode === 'table' ? 'table' : 'list')
const stageOrderStorageKey = 'maa-weekly-plan-table-stage-order'
const tableStageOrder = ref(loadSavedStageOrder())

function loadSavedStageOrder() {
  try {
    const order = JSON.parse(window.localStorage.getItem(stageOrderStorageKey) || '[]')
    return Array.isArray(order) ? order.filter((stage) => typeof stage === 'string') : []
  } catch {
    return []
  }
}

watch(tableStageOrder, (order) => {
  window.localStorage.setItem(stageOrderStorageKey, JSON.stringify(order))
})

function applyChipStageSelection() {
  tableStageOrder.value = promoteChipStageOrder(tableStageOrder.value)
  for (const plan of maa_weekly_plan.value) {
    for (const stage of CHIP_STAGES) {
      if (!filterStageByAvailability.value || isStageAvailableOnWeekday(stage, plan.weekday)) {
        setStageForWeekday(maa_weekly_plan.value, plan.weekday, stage, true, tableStageOrder.value)
      }
    }
  }
  reorderWeeklyPlanStages(maa_weekly_plan.value, tableStageOrder.value)
}

watch(editorMode, (mode) => {
  if (mode === 'list' || mode === 'table') {
    window.localStorage.setItem(editorModeStorageKey, mode)
  }
})

const currentWeekdayIndex = computed(() => getGameWeekdayIndex())

const stageOptions = computed(() => buildStageOptions(latestActivityOptions.value))

// 根据开关过滤关卡选项
function filteredStageOptions(weekday) {
  if (!filterStageByAvailability.value) {
    return stageOptions.value
  }
  return stageOptions.value.filter((opt) => isStageAvailableOnWeekday(opt.value, weekday))
}

function createTag(label) {
  return createStageOption(label)
}

function renderStageTag(plan) {
  return ({ option, handleClose }) =>
    h(
      NTag,
      {
        type: isToday(plan.weekday) ? 'error' : 'default',
        closable: true,
        bordered: false,
        onMousedown: (event) => {
          event.preventDefault()
          event.stopPropagation()
        },
        onContextmenu: (event) => {
          event.stopPropagation()
          openCopyDialog(plan, option.value, event)
        },
        onPointerdown: (event) => {
          if (event.pointerType === 'touch') {
            event.preventDefault()
            event.stopPropagation()
            startCopyDialogLongPress(plan, option.value)
          }
        },
        onPointerup: (event) => {
          event.stopPropagation()
          endCopyDialogLongPress(event)
        },
        onPointercancel: (event) => {
          event.stopPropagation()
          cancelCopyDialogLongPress()
        },
        onPointerleave: (event) => {
          event.stopPropagation()
          cancelCopyDialogLongPress()
        },
        onTouchstart: (event) => {
          event.preventDefault()
          event.stopPropagation()
          startCopyDialogLongPress(plan, option.value)
        },
        onTouchend: (event) => {
          event.stopPropagation()
          endCopyDialogLongPress(event)
        },
        onTouchmove: (event) => {
          event.stopPropagation()
          cancelCopyDialogLongPress()
        },
        onTouchcancel: (event) => {
          event.stopPropagation()
          cancelCopyDialogLongPress()
        },
        onClick: (event) => {
          event.preventDefault()
          event.stopPropagation()
        },
        onClose: (event) => {
          cancelCopyDialogLongPress()
          event.stopPropagation()
          handleClose()
        }
      },
      {
        default: () => formatStageLabel(option.value)
      }
    )
}

function isToday(weekday) {
  return WEEKDAYS[currentWeekdayIndex.value] === weekday
}

function openCopyDialog(plan, stage, event = null) {
  event?.preventDefault?.()
  cancelCopyDialogLongPress()
  copySourceWeekday.value = plan.weekday
  copyStageValue.value = stage
  copyTargetDays.value = maa_weekly_plan.value
    .filter((item) => Array.isArray(item.stage))
    .filter((item) => item.stage.includes(stage))
    .map((item) => item.weekday)
  copyDialogVisible.value = true
}

function toggleSelectAllCopyDays(checked) {
  copyTargetDays.value = checked ? [...WEEKDAYS] : []
}

function applyStageToSelectedDays() {
  for (const weekday of WEEKDAYS) {
    const plan = maa_weekly_plan.value.find((item) => item.weekday === weekday)
    if (!plan) {
      continue
    }
    if (!Array.isArray(plan.stage)) {
      plan.stage = []
    }
    const shouldInclude = copyTargetDays.value.includes(weekday)
    const alreadyIncluded = plan.stage.includes(copyStageValue.value)
    if (shouldInclude && !alreadyIncluded) {
      plan.stage = [...plan.stage, copyStageValue.value]
    } else if (!shouldInclude && alreadyIncluded) {
      plan.stage = plan.stage.filter((stage) => stage !== copyStageValue.value)
    }
  }
  closeCopyDialog()
}

function closeCopyDialog() {
  cancelCopyDialogLongPress()
  copyDialogVisible.value = false
  copyTargetDays.value = []
  copySourceWeekday.value = ''
  copyStageValue.value = ''
}

function startCopyDialogLongPress(plan, stage) {
  cancelCopyDialogLongPress()
  copyDialogLongPressTriggered = false
  copyDialogLongPressTimer = window.setTimeout(() => {
    copyDialogLongPressTriggered = true
    openCopyDialog(plan, stage)
  }, 600)
}

function endCopyDialogLongPress(event) {
  if (copyDialogLongPressTriggered) {
    event?.preventDefault?.()
    event?.stopPropagation?.()
  }
  cancelCopyDialogLongPress()
}

function cancelCopyDialogLongPress() {
  if (copyDialogLongPressTimer !== null) {
    window.clearTimeout(copyDialogLongPressTimer)
    copyDialogLongPressTimer = null
  }
  copyDialogLongPressTriggered = false
}
</script>

<template>
  <n-card class="maa-weekly">
    <template #header>
      <n-checkbox
        v-if="showEnable"
        v-model:checked="stage_plan_enable"
        :aria-label="t('tasks.enableWeeklyPlan')"
      >
        <div class="card-title">{{ t('tasks.weeklySanityPlan') }}</div>
      </n-checkbox>
      <span v-else class="weekly-plan-heading">{{ t('tasks.weeklyPlan') }}</span>
      <help-text :label="t('tasks.weeklyPlanHelp')">
        <div>{{ t('tasks.maaStageSupport') }}</div>
        <div>{{ t('tasks.workflowSteps') }}</div>
        <div>{{ t('tasks.weeklyStep1') }}</div>
        <div>{{ t('tasks.weeklyStep2') }}</div>
        <div>{{ t('tasks.weeklyStep3') }}</div>
        <div>{{ t('tasks.weeklyStep4') }}</div>
        <div>{{ t('tasks.weeklyStep5') }}</div>
        <div>{{ t('tasks.weeklyStep6') }}</div>
        <div>{{ t('tasks.weeklyStep7') }}</div>
      </help-text>
      <n-button
        text
        tag="a"
        href="https://m.prts.wiki/w/%E5%85%B3%E5%8D%A1%E4%B8%80%E8%A7%88/%E8%B5%84%E6%BA%90%E6%94%B6%E9%9B%86"
        target="_blank"
        type="primary"
        class="prts-wiki-link"
      >
        <div class="prts-wiki-link-text">{{ t('tasks.prtsStageReference') }}</div>
      </n-button>
    </template>
    <n-form
      :label-placement="mobile ? 'top' : 'left'"
      :show-feedback="false"
      label-width="72"
      label-align="left"
    >
      <n-form-item :show-label="false">
        <n-flex vertical :size="8">
          <n-flex align="center">
            <span>{{ t('tasks.runner') }}</span>
            <n-radio-group v-model:value="stage_plan_runner" :disabled="!stage_plan_enable">
              <n-space>
                <n-radio value="maa">MAA</n-radio>
                <n-radio value="mower">Mower</n-radio>
              </n-space>
            </n-radio-group>
            <help-text>
              <div>{{ t('tasks.maaCombatHelp') }}</div>
              <div>{{ t('tasks.mowerCombatHelp') }}</div>
            </help-text>
          </n-flex>
          <n-flex class="weekly-plan-toolbar" align="center">
            <span>{{ t('tasks.usePotionsBefore') }}</span>
            <mower-input-number
              v-model:value="medicine_expire_days"
              :min="0"
              :max="999"
              :show-button="false"
              placeholder="0"
              style="width: 90px"
            >
              <template #suffix>{{ t('tasks.days') }}</template>
            </mower-input-number>
            <span>{{ t('tasks.expiringPotionsAfter') }}</span>
            <help-text>
              <div>{{ t('tasks.potionExpiryHelp') }}</div>
              <div>{{ t('tasks.potionZeroHelp') }}</div>
            </help-text>
          </n-flex>
          <n-flex align="center" v-if="stage_plan_runner === 'maa'">
            <n-checkbox v-model:checked="maa_report_to_penguin">{{
              t('tasks.reportPenguin')
            }}</n-checkbox>
            <n-input
              v-model:value="maa_penguin_id"
              :disabled="!maa_report_to_penguin"
              :placeholder="t('tasks.penguinId')"
              style="width: 200px"
            />
          </n-flex>
          <n-flex align="center" v-if="stage_plan_runner === 'maa'">
            <n-checkbox v-model:checked="maa_report_to_yituliu">{{
              t('tasks.reportYituliu')
            }}</n-checkbox>
            <n-input
              v-model:value="maa_yituliu_id"
              :disabled="!maa_report_to_yituliu"
              :placeholder="t('tasks.yituliuId')"
              style="width: 200px"
            />
            <help-text>
              <div>
                {{ t('tasks.reportDropHelpBefore')
                }}<n-a href="https://penguin-stats.io/" target="_blank" rel="noopener noreferrer">{{
                  t('tasks.penguinStatistics')
                }}</n-a
                >{{ t('tasks.or')
                }}<n-a href="https://ark.yituliu.cn/" target="_blank" rel="noopener noreferrer">{{
                  t('tasks.yituliu')
                }}</n-a>
                。
              </div>
              <div>{{ t('tasks.reportDropHelpAfter') }}</div>
            </help-text>
          </n-flex>
          <n-flex align="center">
            <n-checkbox v-model:checked="filterStageByAvailability">{{
              t('tasks.openStagesOnly')
            }}</n-checkbox>
            <n-flex align="center" v-if="stage_plan_runner === 'mower'">
              <span>{{ t('tasks.defaultStageSanity') }}</span>
              <mower-input-number
                v-model:value="ap_fallback"
                :min="0"
                :max="999"
                :show-button="false"
                :placeholder="t('tasks.stamina')"
                style="width: 90px"
              >
                <template #suffix>{{ t('tasks.stamina') }}</template>
              </mower-input-number>
              <help-text>
                <div>{{ t('tasks.defaultStageSanityHelp') }}</div>
              </help-text>
            </n-flex>
          </n-flex>
        </n-flex>
      </n-form-item>
    </n-form>

    <n-flex align="center" :size="8" class="activity-resource-status">
      <span v-if="activityLoading">{{ t('tasks.loadingEventStages') }}</span>
      <span v-else-if="activityError" role="alert">{{ activityError }}</span>
      <span v-else-if="!latestActivityOptions.length">{{ t('tasks.noEventStages') }}</span>
      <span v-else>{{ t('tasks.eventStagesLoaded') }}</span>
      <n-button size="small" :loading="activityLoading" @click="loadLatestActivityStages">{{
        t('tasks.reloadEvents')
      }}</n-button>
    </n-flex>

    <div class="weekly-plan-selector-wrap">
      <WeeklyPlanSelector compact />
    </div>

    <n-tabs v-model:value="editorMode" type="segment" class="weekly-plan-editors">
      <n-tab-pane name="list" :tab="t('tasks.listPlan')">
        <table class="weekly-plan-table">
          <thead>
            <tr>
              <th class="weekday-column">{{ t('tasks.date') }}</th>
              <th>{{ t('tasks.stage') }}</th>
              <th v-if="stage_plan_runner === 'maa'" class="number-column">
                {{ t('tasks.potionsPerRun') }}
              </th>
              <th v-if="stage_plan_runner === 'mower'" class="number-column">
                {{ t('tasks.sanityThreshold') }}
              </th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="plan in maa_weekly_plan" :key="plan.weekday">
              <td class="weekday-column">
                <span class="weekday-pill" :class="{ 'today-pill': isToday(plan.weekday) }">
                  {{ formatWeekday(plan.weekday) }}
                </span>
              </td>
              <td class="stage-column">
                <n-select
                  v-model:value="plan.stage"
                  multiple
                  filterable
                  tag
                  :options="filteredStageOptions(plan.weekday)"
                  :render-tag="renderStageTag(plan)"
                  :on-create="createTag"
                  :consistent-menu-width="false"
                />
              </td>
              <td v-if="stage_plan_runner === 'maa'" class="number-column">
                <span class="weekly-mobile-label">{{ t('tasks.potionsPerRun') }}</span>
                <mower-input-number
                  v-model:value="plan.medicine"
                  :min="0"
                  :max="999"
                  :show-button="false"
                  :input-props="{
                    'aria-label': t('tasks.weekdayPotions', {
                      weekday: formatWeekday(plan.weekday)
                    })
                  }"
                >
                  <template #suffix>{{ t('tasks.potions') }}</template>
                </mower-input-number>
              </td>
              <td v-if="stage_plan_runner === 'mower'" class="number-column">
                <span class="weekly-mobile-label">{{ t('tasks.sanityThreshold') }}</span>
                <mower-input-number
                  v-model:value="plan.sanity_threshold"
                  :min="0"
                  :max="210"
                  :show-button="false"
                  :input-props="{
                    'aria-label': t('tasks.weekdaySanityThreshold', {
                      weekday: formatWeekday(plan.weekday)
                    })
                  }"
                >
                  <template #suffix>{{ t('tasks.sanity') }}</template>
                </mower-input-number>
              </td>
            </tr>
          </tbody>
        </table>
      </n-tab-pane>
      <n-tab-pane name="table" :tab="t('tasks.tablePlan')">
        <MaaWeeklyTable
          v-model:stage-order="tableStageOrder"
          :latest-activity-options="latestActivityOptions"
          :filter-stage-by-availability="filterStageByAvailability"
        />
      </n-tab-pane>
      <n-tab-pane name="inventory" :tab="t('tasks.inventoryStageSelection')">
        <MaaStageInventory @chip-limits-applied="applyChipStageSelection" />
      </n-tab-pane>
    </n-tabs>

    <n-modal
      v-model:show="copyDialogVisible"
      preset="card"
      :title="t('tasks.appendOtherDays')"
      :style="{ width: '320px', maxWidth: 'calc(100vw - 32px)' }"
      :mask-closable="false"
    >
      <n-space vertical :size="12">
        <div>
          {{ t('tasks.stagePrefix') }}<b>{{ formatStageLabel(copyStageValue) }}</b>
        </div>
        <div>
          {{ t('tasks.sourceDay') }}<b>{{ formatWeekday(copySourceWeekday) }}</b>
        </div>
        <n-checkbox
          :checked="copyTargetDays.length === WEEKDAYS.length"
          :indeterminate="copyTargetDays.length > 0 && copyTargetDays.length < WEEKDAYS.length"
          @update:checked="toggleSelectAllCopyDays"
          >{{ t('tasks.selectAll') }}</n-checkbox
        >
        <n-checkbox-group v-model:value="copyTargetDays">
          <n-space vertical>
            <n-checkbox v-for="weekday in WEEKDAYS" :key="weekday" :value="weekday">
              <span
                :class="{
                  'stage-unavailable': !isStageAvailableOnWeekday(copyStageValue, weekday)
                }"
              >
                {{ formatWeekday(weekday) }}
              </span>
              <span v-if="!isStageAvailableOnWeekday(copyStageValue, weekday)" class="stage-hint">{{
                t('tasks.closedToday')
              }}</span>
            </n-checkbox>
          </n-space>
        </n-checkbox-group>
        <n-flex justify="end">
          <n-button @click="closeCopyDialog">{{ t('tasks.cancel') }}</n-button>
          <n-button type="primary" @click="applyStageToSelectedDays">{{
            t('tasks.confirmAppend')
          }}</n-button>
        </n-flex>
      </n-space>
    </n-modal>
  </n-card>
</template>

<style scoped lang="scss">
.maa-weekly {
  container: weekly-plan / inline-size;
}

.weekly-mobile-label {
  display: none;
}

.weekly-plan-heading {
  font-size: 14px;
  font-weight: 500;
}

.weekly-plan-table {
  width: 100%;
  border-collapse: collapse;

  th,
  td {
    padding: 8px 6px;
    vertical-align: middle;
  }
}

@container weekly-plan (max-width: 520px) {
  .weekly-plan-table {
    display: block;

    thead {
      display: none;
    }

    tbody {
      display: grid;
      gap: 16px;
    }

    tr {
      display: grid;
      grid-template-columns: repeat(2, minmax(0, 1fr));
      gap: 10px 12px;
      padding-bottom: 16px;
      border-bottom: 1px solid var(--mower-border);
    }

    td {
      width: auto;
      min-width: 0;
      padding: 0;
    }

    .weekday-column,
    .stage-column {
      grid-column: 1 / -1;
    }

    .number-column {
      display: grid;
      gap: 6px;
    }

    .weekly-mobile-label {
      display: block;
      font-size: 12px;
      color: var(--mower-text-muted);
    }
  }
}

.weekly-plan-editors {
  margin-top: 2px;
}

.weekday-column {
  width: 88px;
  white-space: nowrap;
}

.number-column {
  width: 92px;
}

.weekday-pill {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-width: 48px;
  padding: 4px 10px;
  border-radius: 8px;
}

.today-pill {
  border-radius: 8px;
  border: 1px solid #d03050;
  color: #d03050;
  background: rgba(208, 48, 80, 0.05);
  font-weight: 600;
}

.weekly-plan-toolbar {
  width: 100%;
  flex-wrap: wrap;

  :deep(.n-input-number) {
    flex-shrink: 0;
  }
}

.weekly-plan-selector-wrap {
  flex: 1;
  min-width: 0;
}

.prts-wiki-link {
  margin: 8px 0;
  flex-shrink: 1;
  min-width: 0;
}

.prts-wiki-link-text {
  overflow: hidden;
  text-overflow: ellipsis;
}

.stage-unavailable {
  opacity: 0.45;
}
.stage-hint {
  font-size: 0.8em;
  opacity: 0.6;
  margin-left: 2px;
}
</style>
