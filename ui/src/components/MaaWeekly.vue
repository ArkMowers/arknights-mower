<script setup>
import { storeToRefs } from 'pinia'
import { NTag, NCheckbox } from 'naive-ui'
import axios from 'axios'
import { computed, h, inject, onMounted, ref } from 'vue'
import { useConfigStore } from '@/stores/config'
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

const weekdays = ['周一', '周二', '周三', '周四', '周五', '周六', '周日']
const weekdayIndices = { 周一: 0, 周二: 1, 周三: 2, 周四: 3, 周五: 4, 周六: 5, 周日: 6 }

const general_important_stages = ['', 'Annihilation']
const general_unimportant_stages = [
  '1-7',
  'LS-6',
  'CE-6',
  'AP-5',
  'SK-5',
  'CA-5',
  'PR-A-2',
  'PR-A-1',
  'PR-B-2',
  'PR-B-1',
  'PR-C-2',
  'PR-C-1',
  'PR-D-2',
  'PR-D-1'
]
const time_table = {
  CE: [1, 3, 5, 6],
  AP: [0, 3, 5, 6],
  SK: [0, 2, 4, 5],
  CA: [1, 2, 4, 6],
  'PR-A': [0, 3, 4, 6],
  'PR-B': [0, 1, 4, 5],
  'PR-C': [2, 3, 5, 6],
  'PR-D': [1, 2, 5, 6]
}

const stageDisplayNames = {
  '': '上次作战',
  Annihilation: '当期剿灭',
  'LS-6': '经验书',
  'CE-6': '龙门币',
  'AP-5': '红票',
  'SK-5': '碳本',
  'CA-5': '技能书',
  'PR-A-1': '医疗重装1',
  'PR-A-2': '医疗重装2',
  'PR-B-1': '狙击术师1',
  'PR-B-2': '狙击术师2',
  'PR-C-1': '先锋辅助1',
  'PR-C-2': '先锋辅助2',
  'PR-D-1': '近卫特种1',
  'PR-D-2': '近卫特种2',
  '1-7': '1-7'
}
const stageValueMap = Object.fromEntries(Object.entries(stageDisplayNames).map(([k, v]) => [v, k]))

const presetStages = Object.keys(stageDisplayNames)

const copyDialogVisible = ref(false)
const copyStageValue = ref('')
const copySourceWeekday = ref('')
const copyTargetDays = ref([])
let copyDialogLongPressTimer = null
let copyDialogLongPressTriggered = false

// 关卡过滤开关（活动期间可关闭）
const filterStageByAvailability = ref(true)

const currentWeekdayIndex = computed(() => {
  const day = new Date().getDay()
  return day === 0 ? 6 : day - 1
})

const stageOptions = computed(() => [
  ...latestActivityOptions.value,
  ...presetStages.map((value) => ({
    label: value ? `${stageDisplayNames[value]} (${value})` : stageDisplayNames[value],
    value
  }))
])

// 根据开关过滤关卡选项
function filteredStageOptions(weekday) {
  if (!filterStageByAvailability.value) {
    return stageOptions.value
  }
  return stageOptions.value.filter((opt) => isStageAvailableOnWeekday(opt.value, weekday))
}

// --- 关卡可用性预计算 ---
const stageAvailability = computed(() => {
  const availabilityMap = new Map()
  const allDaysAvailable = Array(7).fill(true)
  general_important_stages.forEach((stage) => availabilityMap.set(stage, allDaysAvailable))
  general_unimportant_stages.forEach((stage) => {
    let availableDays = allDaysAvailable
    for (const [prefix, days] of Object.entries(time_table)) {
      if (stage.startsWith(prefix)) {
        const weekAvailability = Array(7).fill(false)
        days.forEach((dayIndex) => {
          weekAvailability[dayIndex] = true
        })
        availableDays = weekAvailability
        break
      }
    }
    availabilityMap.set(stage, availableDays)
  })
  return availabilityMap
})

function isStageAvailableOnWeekday(stage, weekdayName) {
  const dayIndex = weekdayIndices[weekdayName]
  if (dayIndex === undefined) return true
  const available = stageAvailability.value.get(stage)
  if (!available) return true
  return available[dayIndex]
}

function formatStageLabel(value) {
  if (value in stageDisplayNames) {
    return stageDisplayNames[value]
  }
  if (typeof value === 'string' && value.endsWith('-HARD')) {
    return `${value.slice(0, -5)} 困难`
  }
  if (typeof value === 'string' && value.endsWith('-NORMAL')) {
    return `${value.slice(0, -7)} 标准`
  }
  return value
}

function normalizeCreatedStage(label) {
  if (label in stageValueMap) {
    return stageValueMap[label]
  }
  if (label.endsWith('困难')) {
    return `${label.slice(0, -2)}-HARD`
  }
  if (label.endsWith('标准')) {
    return `${label.slice(0, -2)}-NORMAL`
  }
  return label
}

function createTag(label) {
  const value = normalizeCreatedStage(label.trim())
  return {
    label: formatStageLabel(value),
    value
  }
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
  return weekdays[currentWeekdayIndex.value] === weekday
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
  copyTargetDays.value = checked ? [...weekdays] : []
}

function applyStageToSelectedDays() {
  for (const weekday of weekdays) {
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
        <div>2. 在每天的关卡栏里可直接下拉选择，也可以手动输入后回车生成关卡标签。</div>
        <div>3. 右键(或者长按)关卡标签，可快速追加或移除到其他日期。</div>
        <div>4. 每天可分别设置体力阈值</div>
        <div>5. 每天可分别设置吃药次数（敬请期待）。</div>
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
            <n-input-number v-model:value="plan.medicine" :min="0" :max="999" :show-button="false">
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
          :checked="copyTargetDays.length === weekdays.length"
          :indeterminate="copyTargetDays.length > 0 && copyTargetDays.length < weekdays.length"
          @update:checked="toggleSelectAllCopyDays"
        >
          全选
        </n-checkbox>
        <n-checkbox-group v-model:value="copyTargetDays">
          <n-space vertical>
            <n-checkbox v-for="weekday in weekdays" :key="weekday" :value="weekday">
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
