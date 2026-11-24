<script setup>
defineProps({ showEnable: { type: Boolean, default: true } })
import { computed, inject, ref, watch } from 'vue'
import { storeToRefs } from 'pinia'
import { useConfigStore } from '@/stores/config'
import { WEEKDAYS } from '@/utils/maa_weekly_plan'
import { longTaskConflictTime, longTaskWindowConflicts } from '@/utils/longTaskWindows'
import LongTaskParameters from './LongTaskParameters.vue'
import WeeklyPlanDayCell from './WeeklyPlanDayCell.vue'
const config_store = useConfigStore()
const {
  maa_rg_enable,
  maa_long_task_type,
  maa_long_task_extra_windows,
  maa_long_task_weekly_windows,
  maa_rg_sleep_min,
  maa_rg_sleep_max
} = storeToRefs(config_store)
const longTaskEnabled = computed({
  get: () => maa_rg_enable.value === true || maa_rg_enable.value === 1,
  set: (value) => (maa_rg_enable.value = value)
})

const everyDay = WEEKDAYS.map((_, day) => day)
const validTime = (value) => /^(?:[01]?[0-9]|2[0-3]):[0-5][0-9]$/.test(value)
const savedTimeWindows = computed(() => {
  if (maa_long_task_weekly_windows.value !== null) return maa_long_task_weekly_windows.value
  const daily = [
    { start: maa_rg_sleep_max.value, end: maa_rg_sleep_min.value },
    ...maa_long_task_extra_windows.value
  ].filter(({ start, end }) => validTime(start) && validTime(end))
  if (!daily.length) daily.push({ start: '0:00', end: '0:00' })
  return daily.map((window) => ({ ...window, weekdays: everyDay.slice() }))
})
const draft = ref(null)
const timeWindows = computed(() => draft.value?.windows ?? savedTimeWindows.value)
const defaultTaskType = computed(() => draft.value?.defaultType ?? maa_long_task_type.value)
const conflicts = computed(() => longTaskWindowConflicts(timeWindows.value, defaultTaskType.value))
const conflictCells = computed(() => {
  return new Set(
    conflicts.value.flatMap(({ left, right }) =>
      [left, right].map(({ row, day }) => `${row}:${day}`)
    )
  )
})

watch([maa_long_task_weekly_windows, maa_long_task_type], () => (draft.value = null), {
  flush: 'sync'
})

function updatePlan(windows, defaultType, changedWindows) {
  if (longTaskWindowConflicts(windows, defaultType).length) {
    draft.value = { windows, defaultType, changedWindows }
    return
  }
  draft.value = null
  if (changedWindows) maa_long_task_weekly_windows.value = windows
  maa_long_task_type.value = defaultType
}

function updateDefaultType(value) {
  updatePlan(timeWindows.value, value, draft.value?.changedWindows ?? false)
}

function addTimeWindow() {
  updatePlan(
    [...timeWindows.value, { start: '8:00', end: '12:00', weekdays: [] }],
    defaultTaskType.value,
    true
  )
}

function removeTimeWindow(index) {
  updatePlan(
    timeWindows.value.filter((_, i) => i !== index),
    defaultTaskType.value,
    true
  )
}

function updateWindow(index, update) {
  updatePlan(
    timeWindows.value.map((window, i) => (i === index ? { ...window, ...update } : window)),
    defaultTaskType.value,
    true
  )
}

function updateTimeWindow(index, field, value) {
  if (validTime(value)) updateWindow(index, { [field]: value })
}

function toggleWeekday(index, day) {
  const days = timeWindows.value[index].weekdays
  const checked = !days.includes(day)
  updateWindow(index, {
    weekdays: everyDay.filter((weekday) => (weekday === day ? checked : days.includes(weekday)))
  })
}

function allDaysSelected(window) {
  return everyDay.every((day) => window.weekdays.includes(day))
}

function clockMinute(time) {
  const [hour, minute] = time.split(':').map(Number)
  return hour * 60 + minute
}

const mobile = inject('mobile')

const taskOptions = [
  { label: '集成战略 (MAA)', value: 'rogue' },
  { label: '自动战斗／作业 (MAA)', value: 'copilot' },
  { label: '悖论模拟 (MAA)', value: 'paradox' },
  { label: '保全派驻 (MAA)', value: 'sss' },
  { label: '生息演算 (MAA)', value: 'rcl' },
  { label: '生息演算', value: 'ra' },
  { label: '隐秘战线', value: 'sf' },
  { label: '卫戍协议 · 个人极速模拟', value: 'garrison' }
]
const windowTaskOptions = [{ label: '跟随默认', value: 'default' }, ...taskOptions]
const editingType = ref(null)
const parameterType = computed({
  get: () => editingType.value ?? maa_long_task_type.value,
  set: (value) => (editingType.value = value)
})

function taskLabel(type) {
  return taskOptions.find((option) => option.value === type)?.label ?? type
}

function describeConflict(conflict) {
  const { left, right } = conflict
  return (
    `${longTaskConflictTime(conflict, WEEKDAYS)}，` +
    `第${left.row + 1}段「${taskLabel(left.kind)}」与第${right.row + 1}段「${taskLabel(right.kind)}」重叠。`
  )
}

function configureWindow(window) {
  editingType.value = window.task_type ?? defaultTaskType.value
}
</script>

<template>
  <n-card>
    <template v-if="showEnable" #header>大型任务</template>
    <n-form
      class="long-task-setup"
      :label-placement="mobile ? 'top' : 'left'"
      :show-feedback="false"
    >
      <n-form-item v-if="showEnable" label="启用大型任务">
        <n-switch v-model:value="longTaskEnabled" aria-label="启用大型任务" />
      </n-form-item>
      <n-form-item label="默认任务类型">
        <n-select
          :value="defaultTaskType"
          :options="taskOptions"
          :consistent-menu-width="false"
          aria-label="默认任务类型"
          @update:value="updateDefaultType"
        />
      </n-form-item>
      <div class="long-task-weekly">
        <div class="long-task-weekly-toolbar">
          <span>
            执行时段
            <help-text label="大型任务时段说明">
              按 Mower
              运行机器的时间。相同任务的时段重叠或相接时合并，不同任务的时段不能重叠。起止时间相同表示当天全天，停止时间早于开始时间表示此任务运行到次日。
            </help-text>
          </span>
          <n-button size="small" aria-label="添加执行时段" @click="addTimeWindow">
            添加执行时段
          </n-button>
        </div>
        <div class="long-task-table-wrap">
          <table class="long-task-table" aria-label="大型任务周计划">
            <thead>
              <tr>
                <th scope="col" class="select-all-column">全选</th>
                <th scope="col" class="time-column">
                  <div class="window-fields"><span>时间段</span><span>任务类型</span></div>
                </th>
                <th v-for="weekday in WEEKDAYS" :key="weekday" scope="col" class="weekday-column">
                  {{ weekday.slice(1) }}
                </th>
                <th scope="col" class="window-action">操作</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="(window, index) in timeWindows" :key="index">
                <td class="select-all-column">
                  <n-checkbox
                    :checked="allDaysSelected(window)"
                    :indeterminate="window.weekdays.length > 0 && !allDaysSelected(window)"
                    :aria-label="`第${index + 1}段全选`"
                    @update:checked="
                      updateWindow(index, { weekdays: $event ? everyDay.slice() : [] })
                    "
                  />
                </td>
                <td class="time-column">
                  <div class="window-fields">
                    <div class="time-inputs">
                      <n-time-picker
                        size="small"
                        format="H:mm"
                        :formatted-value="window.start"
                        :aria-label="`第${index + 1}段开始时间`"
                        @update:formatted-value="updateTimeWindow(index, 'start', $event)"
                      />
                      <span>至</span>
                      <n-time-picker
                        size="small"
                        format="H:mm"
                        :formatted-value="window.end"
                        :aria-label="`第${index + 1}段停止时间`"
                        @update:formatted-value="updateTimeWindow(index, 'end', $event)"
                      />
                      <small v-if="clockMinute(window.end) === clockMinute(window.start)"
                        >全天</small
                      >
                      <small v-else-if="clockMinute(window.end) < clockMinute(window.start)"
                        >次日</small
                      >
                    </div>
                    <n-select
                      size="small"
                      :value="window.task_type ?? 'default'"
                      :options="windowTaskOptions"
                      :consistent-menu-width="false"
                      :aria-label="`第${index + 1}段任务类型`"
                      @update:value="
                        updateWindow(index, { task_type: $event === 'default' ? null : $event })
                      "
                    />
                  </div>
                </td>
                <WeeklyPlanDayCell
                  v-for="day in everyDay"
                  :key="day"
                  :selected="window.weekdays.includes(day)"
                  :class="{ 'window-conflict': conflictCells.has(`${index}:${day}`) }"
                  :label="`第${index + 1}段${WEEKDAYS[day]}`"
                  @toggle="toggleWeekday(index, day)"
                >
                  ✓
                </WeeklyPlanDayCell>
                <td class="window-action">
                  <div class="window-buttons">
                    <n-button
                      type="primary"
                      size="small"
                      :aria-label="`配置第${index + 1}段任务`"
                      @click="configureWindow(window)"
                    >
                      配置
                    </n-button>
                    <n-button
                      type="error"
                      size="small"
                      :aria-label="`删除第${index + 1}段`"
                      @click="removeTimeWindow(index)"
                    >
                      删除
                    </n-button>
                  </div>
                </td>
              </tr>
            </tbody>
          </table>
        </div>
        <n-alert v-if="conflicts.length" type="error" role="alert" class="window-conflict-alert">
          <template v-if="conflicts.length === 1">{{ describeConflict(conflicts[0]) }}</template>
          <template v-else>有 {{ conflicts.length }} 处时段冲突。</template>
          修正冲突前继续使用上次保存的计划。
          <details v-if="conflicts.length > 1" class="window-conflict-details">
            <summary>查看冲突时段</summary>
            <ul>
              <li v-for="(conflict, index) in conflicts" :key="index">
                {{ describeConflict(conflict) }}
              </li>
            </ul>
          </details>
        </n-alert>
        <n-text v-if="!timeWindows.some((window) => window.weekdays.length)" depth="3">
          未选执行时段，大型任务暂停自动执行。
        </n-text>
      </div>
    </n-form>
    <section class="task-parameters" aria-label="任务参数">
      <h3>任务参数</h3>
      <n-form :label-placement="mobile ? 'top' : 'left'">
        <n-form-item label="配置类型">
          <n-select
            v-model:value="parameterType"
            :options="taskOptions"
            :consistent-menu-width="false"
            aria-label="配置类型"
          />
        </n-form-item>
      </n-form>
      <LongTaskParameters :task-type="parameterType" />
    </section>
  </n-card>
</template>

<style scoped>
.long-task-setup {
  margin-bottom: 16px;
}

.long-task-weekly {
  width: 100%;
  min-width: 0;
  container-type: inline-size;
}

.long-task-weekly-toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  margin-bottom: 10px;
}

.long-task-table-wrap {
  overflow-x: auto;
  border-radius: calc(10px * var(--mower-corner-scale));
  corner-shape: var(--mower-corner-shape);
  box-shadow:
    0 0 0 1px rgba(0, 0, 0, 0.06),
    0 4px 12px rgba(0, 0, 0, 0.04);
}

.long-task-table {
  width: 100%;
  min-width: 872px;
  table-layout: fixed;
  border-collapse: separate;
  border-spacing: 0;
  text-align: center;
}

.long-task-table :is(th, td) {
  padding: 0;
  box-shadow: inset -1px -1px 0 rgba(0, 0, 0, 0.06);
}

.long-task-table th {
  height: 40px;
  font-weight: 600;
}

.select-all-column {
  width: 40px;
}

.time-column {
  text-align: left;
}

.window-fields {
  display: grid;
  grid-template-columns: 230px minmax(208px, 1fr);
  align-items: center;
  gap: 8px;
}

@container (min-width: 872px) {
  .weekday-column {
    width: clamp(36px, calc(36px + (100cqw - 872px) / 12), 62px);
  }
}

.long-task-table .weekly-plan-day-cell.window-conflict {
  background: var(--mower-error-block, rgba(208, 48, 80, 0.1));
  color: var(--mower-error-text, #d03050);
}

.window-conflict-alert {
  margin-top: 8px;
}

.window-conflict-details {
  margin-top: 4px;
}

.window-conflict-details summary {
  cursor: pointer;
}

.window-conflict-details ul {
  margin: 4px 0 0;
  padding-inline-start: 20px;
}

@container (max-width: 871px) {
  .long-task-table {
    min-width: 648px;
  }

  .time-column {
    width: 224px;
  }

  .time-column .time-inputs {
    column-gap: 4px;
  }

  td.time-column .window-fields {
    grid-template-columns: minmax(0, 1fr);
    gap: 4px;
    padding: 5px 0;
  }

  th.time-column .window-fields {
    grid-template-columns: auto auto;
    justify-content: start;
    gap: 0;
  }

  th.time-column .window-fields span + span::before {
    content: '/';
    margin-inline: 8px;
  }
}

.long-task-table .time-column {
  padding: 0 8px;
}

.window-action {
  width: 112px;
}

.window-buttons {
  display: flex;
  justify-content: center;
  gap: 6px;
}

@container (max-width: 700px) {
  .long-task-table {
    min-width: 616px;
  }

  .select-all-column {
    width: 36px;
  }

  .window-action {
    width: 92px;
  }

  .window-buttons {
    gap: 4px;
  }

  .window-buttons :deep(.n-button) {
    padding-inline: 6px;
  }
}

.task-parameters h3 {
  margin: 0 0 12px;
}

.time-inputs {
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto minmax(0, 1fr) 28px;
  align-items: center;
  gap: 6px;
}

.time-inputs small {
  white-space: nowrap;
}
</style>
