<script setup>
import { storeToRefs } from 'pinia'
import { NTag, NCheckbox } from 'naive-ui'
import axios from 'axios'
import { computed, h, inject, onMounted, ref, watch } from 'vue'
import { useConfigStore } from '@/stores/config'
import {
  WEEKDAYS,
  buildStageOptions,
  createStageOption,
  formatStageLabel,
  isStageAvailableOnWeekday
} from '@/utils/maa_weekly_plan'
import MaaWeeklyTable from './MaaWeeklyTable.vue'
import MaaStageInventory from './MaaStageInventory.vue'
import WeeklyPlanSelector from './WeeklyPlanSelector.vue'

const store = useConfigStore()
const {
  maa_weekly_plan,
  maa_enable,
  maa_expiring_medicine,
  exipring_medicine_on_weekend,
  ap_fallback
} = storeToRefs(store)

const mobile = inject('mobile')

// 最近开启活动（后端供给，热更后最新）：prepend 到关卡下拉最前
const latestActivityOptions = ref([])

async function loadLatestActivityStages() {
  try {
    const response = await axios.get(`${import.meta.env.VITE_HTTP_URL}/stage/latest-activity`)
    latestActivityOptions.value = Array.isArray(response.data) ? response.data : []
  } catch (error) {
    // 接口不可用时静默忽略，保住基础常驻关下拉
    latestActivityOptions.value = []
  }
}

onMounted(loadLatestActivityStages)

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

watch(editorMode, (mode) => {
  if (mode === 'list' || mode === 'table') {
    window.localStorage.setItem(editorModeStorageKey, mode)
  }
})

const currentWeekdayIndex = computed(() => {
  const day = new Date().getDay()
  return day === 0 ? 6 : day - 1
})

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
  <n-card>
    <template #header>
      <n-checkbox v-model:checked="maa_enable">
        <div class="card-title">刷理智周计划</div>
      </n-checkbox>
      <help-text>
        <div>支持 MAA 支持的所有关卡。</div>
        <div>操作流程：</div>
        <div>1. 先在"方案"里选择已有方案，或输入新方案名后按回车创建。</div>
        <div>2. 列表计划与表格计划编辑同一份配置，切换视图后会立即同步。</div>
        <div>3. 列表中可手动输入关卡；右键（或长按）标签可批量追加到其他日期。</div>
        <div>4. 表格中点击格子切换“打”，活动关卡会跟随资源包动态加入表格。</div>
        <div>5. 吃药次数和体力阈值在列表计划中设置。</div>
        <div>6. 库存选关只作用于周计划已选择的关卡，不会自动加入关卡。</div>
        <div>
          7.
          可为当前活动方案设置“结束后”目标；资源包检测到其中活动关卡全部结束后，刷理智前自动切换方案。
        </div>
      </help-text>
      <n-button
        text
        tag="a"
        href="https://m.prts.wiki/w/%E5%85%B3%E5%8D%A1%E4%B8%80%E8%A7%88/%E8%B5%84%E6%BA%90%E6%94%B6%E9%9B%86"
        target="_blank"
        type="primary"
        class="prts-wiki-link"
      >
        <div class="prts-wiki-link-text">PRTS.wiki：关卡一览 / 资源收集</div>
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
          <n-flex class="weekly-plan-toolbar" align="center">
            <n-checkbox v-model:checked="maa_expiring_medicine">使用将要过期的理智药</n-checkbox>
            <n-checkbox
              v-model:checked="exipring_medicine_on_weekend"
              :disabled="!maa_expiring_medicine"
            >
              周末使用
            </n-checkbox>
            <div class="weekly-plan-selector-wrap">
              <WeeklyPlanSelector compact />
            </div>
          </n-flex>
          <n-flex>
            <n-checkbox v-model:checked="filterStageByAvailability">只显示当日开放关卡</n-checkbox>
            <n-input-number
              v-model:value="ap_fallback"
              :min="0"
              :max="999"
              :show-button="false"
              placeholder="体力"
              style="width: 90px"
            >
              <template #suffix>体力</template>
            </n-input-number>
          </n-flex>
        </n-flex>
      </n-form-item>
    </n-form>

    <n-tabs v-model:value="editorMode" type="segment" animated class="weekly-plan-editors">
      <n-tab-pane name="list" tab="列表计划">
        <table class="weekly-plan-table">
          <thead>
            <tr>
              <th class="weekday-column">日期</th>
              <th>关卡</th>
              <th class="number-column">每次吃药</th>
              <th class="number-column">体力阈值</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="plan in maa_weekly_plan" :key="plan.weekday">
              <td class="weekday-column">
                <span class="weekday-pill" :class="{ 'today-pill': isToday(plan.weekday) }">
                  {{ plan.weekday }}
                </span>
              </td>
              <td>
                <n-select
                  v-model:value="plan.stage"
                  multiple
                  filterable
                  tag
                  :options="filteredStageOptions(plan.weekday)"
                  :render-tag="renderStageTag(plan)"
                  :on-create="createTag"
                />
              </td>
              <td class="number-column">
                <n-input-number
                  v-model:value="plan.medicine"
                  :min="0"
                  :max="999"
                  :show-button="false"
                >
                  <template #suffix>药</template>
                </n-input-number>
              </td>
              <td class="number-column">
                <n-input-number
                  v-model:value="plan.sanity_threshold"
                  :min="0"
                  :max="210"
                  :show-button="false"
                >
                  <template #suffix>理智</template>
                </n-input-number>
              </td>
            </tr>
          </tbody>
        </table>
      </n-tab-pane>
      <n-tab-pane name="table" tab="表格计划">
        <MaaWeeklyTable
          :latest-activity-options="latestActivityOptions"
          :filter-stage-by-availability="filterStageByAvailability"
        />
      </n-tab-pane>
      <n-tab-pane name="inventory" tab="库存选关">
        <MaaStageInventory />
      </n-tab-pane>
    </n-tabs>

    <n-modal
      v-model:show="copyDialogVisible"
      preset="card"
      title="追加到其他日期"
      :style="{ width: '320px', maxWidth: 'calc(100vw - 32px)' }"
      :mask-closable="false"
    >
      <n-space vertical :size="12">
        <div>
          关卡：<b>{{ formatStageLabel(copyStageValue) }}</b>
        </div>
        <div>
          来源日期：<b>{{ copySourceWeekday }}</b>
        </div>
        <n-checkbox
          :checked="copyTargetDays.length === WEEKDAYS.length"
          :indeterminate="copyTargetDays.length > 0 && copyTargetDays.length < WEEKDAYS.length"
          @update:checked="toggleSelectAllCopyDays"
        >
          全选
        </n-checkbox>
        <n-checkbox-group v-model:value="copyTargetDays">
          <n-space vertical>
            <n-checkbox v-for="weekday in WEEKDAYS" :key="weekday" :value="weekday">
              <span
                :class="{
                  'stage-unavailable': !isStageAvailableOnWeekday(copyStageValue, weekday)
                }"
              >
                {{ weekday }}
              </span>
              <span v-if="!isStageAvailableOnWeekday(copyStageValue, weekday)" class="stage-hint">
                (本日不开)</span
              >
            </n-checkbox>
          </n-space>
        </n-checkbox-group>
        <n-flex justify="end">
          <n-button @click="closeCopyDialog">取消</n-button>
          <n-button type="primary" @click="applyStageToSelectedDays">确认追加</n-button>
        </n-flex>
      </n-space>
    </n-modal>
  </n-card>
</template>

<style scoped lang="scss">
.weekly-plan-table {
  width: 100%;
  border-collapse: collapse;

  th,
  td {
    padding: 8px 6px;
    vertical-align: middle;
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
  flex-wrap: nowrap;
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
