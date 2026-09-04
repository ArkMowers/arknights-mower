<script setup>
import { storeToRefs } from 'pinia'
import { computed, ref, watch } from 'vue'
import draggable from 'vuedraggable'
import { useConfigStore } from '@/stores/config'
import {
  ANNIHILATION_STAGE,
  WEEKDAYS,
  buildTableStageOptions,
  createStageOption,
  isStageAvailableOnWeekday,
  mergeTableStageOrder,
  reorderWeeklyPlanStages,
  setStageForWeekday,
  splitStageInventoryLabel
} from '@/utils/maa_weekly_plan'

const props = defineProps({
  latestActivityOptions: {
    type: Array,
    default: () => []
  },
  filterStageByAvailability: {
    type: Boolean,
    default: true
  }
})

const store = useConfigStore()
const { maa_weekly_plan } = storeToRefs(store)

const manuallyAddedOptions = ref([])
const stageToAdd = ref(null)
const stageOrderStorageKey = 'maa-weekly-plan-table-stage-order'
const stageOrderVersionStorageKey = 'maa-weekly-plan-table-stage-order-version'
const stageOrderVersion = 'annihilation-first-v1'

function loadSavedStageOrder() {
  try {
    const order = JSON.parse(window.localStorage.getItem(stageOrderStorageKey) || '[]')
    return Array.isArray(order) ? order.filter((value) => typeof value === 'string') : []
  } catch {
    return []
  }
}

const savedStageOrder = loadSavedStageOrder()
const sortableStageOptions = ref([])
let needsDefaultOrderMigration =
  window.localStorage.getItem(stageOrderVersionStorageKey) !== stageOrderVersion

const currentWeekdayIndex = computed(() => {
  const day = new Date().getDay()
  return day === 0 ? 6 : day - 1
})

const availableStageOptions = computed(() =>
  buildTableStageOptions(
    props.latestActivityOptions,
    maa_weekly_plan.value,
    manuallyAddedOptions.value
  ).map((option) => ({
    ...option,
    ...splitStageInventoryLabel(option.label)
  }))
)

watch(
  availableStageOptions,
  (options) => {
    let currentOrder = sortableStageOptions.value.length
      ? sortableStageOptions.value.map((option) => option.value)
      : savedStageOrder
    if (needsDefaultOrderMigration) {
      currentOrder = [
        ANNIHILATION_STAGE,
        ...currentOrder.filter((value) => value !== ANNIHILATION_STAGE)
      ]
      needsDefaultOrderMigration = false
      window.localStorage.setItem(stageOrderVersionStorageKey, stageOrderVersion)
    }
    sortableStageOptions.value = mergeTableStageOrder(
      options,
      currentOrder,
      props.latestActivityOptions.map((option) => option.value)
    )
  },
  { immediate: true }
)

watch(
  sortableStageOptions,
  (options) => {
    window.localStorage.setItem(
      stageOrderStorageKey,
      JSON.stringify(options.map((option) => option.value))
    )
  },
  { deep: true }
)

const priorityOrder = computed(() => sortableStageOptions.value.map((option) => option.value))

function dayPlan(weekday) {
  return maa_weekly_plan.value.find((plan) => plan.weekday === weekday)
}

function isToday(weekday) {
  return WEEKDAYS[currentWeekdayIndex.value] === weekday
}

function isSelected(stage, weekday) {
  const stages = dayPlan(weekday)?.stage
  return Array.isArray(stages) && stages.includes(stage)
}

function canToggle(stage, weekday) {
  return (
    !props.filterStageByAvailability ||
    isStageAvailableOnWeekday(stage, weekday) ||
    isSelected(stage, weekday)
  )
}

function toggleStage(stage, weekday) {
  if (!canToggle(stage, weekday)) {
    return
  }
  setStageForWeekday(
    maa_weekly_plan.value,
    weekday,
    stage,
    !isSelected(stage, weekday),
    priorityOrder.value
  )
}

function selectableDays(stage) {
  return WEEKDAYS.filter(
    (weekday) => !props.filterStageByAvailability || isStageAvailableOnWeekday(stage, weekday)
  )
}

function selectedDayCount(stage) {
  return selectableDays(stage).filter((weekday) => isSelected(stage, weekday)).length
}

function toggleStageForAllDays(stage) {
  const days = selectableDays(stage)
  const shouldSelect = selectedDayCount(stage) !== days.length
  for (const weekday of days) {
    setStageForWeekday(maa_weekly_plan.value, weekday, stage, shouldSelect, priorityOrder.value)
  }
}

function addStageRow(value) {
  if (typeof value !== 'string') {
    return
  }
  const option = createStageOption(value)
  if (!availableStageOptions.value.some((item) => item.value === option.value)) {
    manuallyAddedOptions.value = [...manuallyAddedOptions.value, option]
  }
  stageToAdd.value = null
}

function applyStageOrder() {
  reorderWeeklyPlanStages(maa_weekly_plan.value, priorityOrder.value)
}
</script>

<template>
  <div class="table-editor">
    <div class="table-editor-toolbar">
      <n-select
        v-model:value="stageToAdd"
        class="stage-row-input"
        filterable
        tag
        clearable
        placeholder="输入关卡并回车，添加表格行"
        :options="sortableStageOptions"
        :on-create="createStageOption"
        @update:value="addStageRow"
      />
      <span class="table-editor-hint">
        当期剿灭默认置顶，活动关卡紧随其后；可拖动把手调整，表格只选择关卡
      </span>
    </div>

    <div class="task-table-wrap">
      <table class="task-table">
        <thead>
          <tr>
            <th class="select-all-column">全选</th>
            <th class="stage-column">关卡</th>
            <th
              v-for="weekday in WEEKDAYS"
              :key="weekday"
              class="day-column"
              :class="{ 'today-header': isToday(weekday) }"
            >
              {{ weekday.slice(1) }}
              <span v-if="isToday(weekday)" class="today-dot" title="今天"></span>
            </th>
          </tr>
        </thead>
        <draggable
          v-model="sortableStageOptions"
          tag="tbody"
          item-key="value"
          handle=".stage-drag-handle"
          @end="applyStageOrder"
        >
          <template #item="{ element: option }">
            <tr>
              <td class="select-all-column">
                <n-checkbox
                  :checked="selectedDayCount(option.value) === selectableDays(option.value).length"
                  :indeterminate="
                    selectedDayCount(option.value) > 0 &&
                    selectedDayCount(option.value) < selectableDays(option.value).length
                  "
                  :aria-label="`全选 ${option.label}`"
                  @update:checked="toggleStageForAllDays(option.value)"
                />
              </td>
              <td class="stage-column">
                <div class="stage-label" :title="option.label">
                  <button
                    type="button"
                    class="stage-drag-handle"
                    :aria-label="`拖动调整 ${option.label} 的优先级`"
                    title="拖动调整上下顺序"
                  >
                    ⋮⋮
                  </button>
                  <span class="stage-name">
                    <span class="stage-name-main">{{ option.stageLabel }}</span>
                    <span v-if="option.inventoryLabel" class="stage-inventory">
                      {{ option.inventoryLabel }}
                    </span>
                  </span>
                </div>
              </td>
              <td
                v-for="weekday in WEEKDAYS"
                :key="`${option.value}-${weekday}`"
                class="stage-cell"
                :class="{
                  selected: isSelected(option.value, weekday),
                  unavailable: !isStageAvailableOnWeekday(option.value, weekday)
                }"
              >
                <button
                  type="button"
                  class="stage-cell-button"
                  :disabled="!canToggle(option.value, weekday)"
                  :aria-pressed="isSelected(option.value, weekday)"
                  :aria-label="`${weekday}${isSelected(option.value, weekday) ? '取消' : '选择'}${option.label}`"
                  @click="toggleStage(option.value, weekday)"
                >
                  <span v-if="isSelected(option.value, weekday)">打</span>
                  <span v-else-if="!isStageAvailableOnWeekday(option.value, weekday)">—</span>
                </button>
              </td>
            </tr>
          </template>
        </draggable>
      </table>
    </div>
  </div>
</template>

<style scoped lang="scss">
.table-editor {
  min-width: 0;
}

.table-editor-toolbar {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-bottom: 10px;
}

.stage-row-input {
  width: min(300px, 100%);
}

.table-editor-hint {
  color: var(--n-text-color-3);
  font-size: 12px;
  text-wrap: pretty;
}

.task-table-wrap {
  max-height: 520px;
  overflow-x: hidden;
  overflow-y: auto;
  border-radius: 10px;
  box-shadow:
    0 0 0 1px rgba(0, 0, 0, 0.06),
    0 4px 12px rgba(0, 0, 0, 0.04);
}

.task-table {
  width: 100%;
  min-width: 0;
  border-collapse: separate;
  border-spacing: 0;
  table-layout: fixed;

  th,
  td {
    padding: 0;
    text-align: center;
    box-shadow: inset -1px -1px 0 rgba(0, 0, 0, 0.06);
  }

  thead {
    position: sticky;
    top: 0;
    z-index: 2;
    background: var(--n-color, #fff);
  }

  thead > tr:first-child th {
    height: 40px;
    font-weight: 600;
  }

  tbody tr:last-child td {
    box-shadow: inset -1px 0 0 rgba(0, 0, 0, 0.06);
  }
}

.select-all-column {
  width: 44px;
}

.stage-column {
  width: 34%;
  text-align: left !important;
}

th.stage-column {
  padding-left: 10px;
}

.today-header {
  color: #d03050;
}

.today-dot {
  display: inline-block;
  width: 5px;
  height: 5px;
  margin-left: 2px;
  border-radius: 50%;
  background: #d03050;
  vertical-align: 2px;
}

.stage-label {
  display: flex;
  align-items: center;
  gap: 4px;
  min-height: 44px;
  padding: 2px 8px 2px 2px;
  line-height: 1.35;
  text-align: left;
  word-break: break-word;
}

.stage-name {
  min-width: 0;
  flex: 1;
  white-space: normal;
  overflow-wrap: anywhere;
}

.stage-name-main,
.stage-inventory {
  display: block;
}

.stage-inventory {
  white-space: nowrap;
  font-variant-numeric: tabular-nums;
}

.stage-drag-handle {
  width: 40px;
  min-width: 40px;
  height: 40px;
  padding: 0;
  border: 0;
  color: rgba(128, 128, 128, 0.7);
  background: transparent;
  cursor: grab;
  touch-action: none;
  transition-property: color, background-color, transform;
  transition-duration: 120ms;
  transition-timing-function: cubic-bezier(0.2, 0, 0, 1);

  &:hover {
    color: inherit;
    background: rgba(128, 128, 128, 0.08);
  }

  &:active {
    transform: scale(0.96);
    cursor: grabbing;
  }
}

.stage-cell {
  height: 44px;
  background: rgba(240, 160, 32, 0.08);
}

.stage-cell.selected {
  background: rgba(32, 128, 240, 0.22);
  color: #096dd9;
  font-weight: 600;
}

.stage-cell.unavailable:not(.selected) {
  background: rgba(128, 128, 128, 0.06);
  color: rgba(128, 128, 128, 0.45);
}

.stage-cell-button {
  width: 100%;
  min-height: 44px;
  padding: 0;
  border: 0;
  color: inherit;
  background: transparent;
  cursor: pointer;
  transition-property: transform, background-color;
  transition-duration: 120ms;
  transition-timing-function: cubic-bezier(0.2, 0, 0, 1);

  &:active:not(:disabled) {
    transform: scale(0.96);
  }

  &:hover:not(:disabled) {
    background: rgba(32, 128, 240, 0.08);
  }

  &:disabled {
    cursor: not-allowed;
  }
}

@media (max-width: 600px) {
  .table-editor-toolbar {
    align-items: stretch;
    flex-direction: column;
  }

  .stage-row-input {
    width: 100%;
  }

  .task-table-wrap {
    max-height: 420px;
  }

  .select-all-column {
    width: 40px;
  }

  .stage-column {
    width: 36%;
  }
}
</style>
