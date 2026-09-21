<script setup>
import { inject, watch } from 'vue'
const show = inject('show_trigger_editor')

import { storeToRefs } from 'pinia'
import { usePlanStore } from '@/stores/plan'
import { usedepotStore } from '@/stores/depot'
import { useFacilityStore } from '@/stores/facility'
import { useMasteryStore } from '@/stores/mastery'

const plan_store = usePlanStore()
const { sub_plan, backup_plans } = storeToRefs(plan_store)
const depot_store = usedepotStore()
const facility_store = useFacilityStore()
const mastery_store = useMasteryStore()

watch(show, (visible) => {
  if (visible) {
    depot_store.loadInventory(true).catch(() => {})
    facility_store.load(true).catch(() => {})
    mastery_store.loadPlanSummary(true).catch(() => {})
  }
})

const triggerTimingOptions = [
  { label: '任务开始', value: 'BEGINNING' },
  { label: '进入工作站前', value: 'BEFORE_WORK' },
  { label: '入住宿舍前', value: 'BEFORE_DORM' },
  { label: '下班结束', value: 'BEFORE_PLANNING' },
  { label: '上班结束', value: 'AFTER_PLANNING' },
  { label: '任务结束', value: 'END' }
]

const exitTriggerTimingOptions = [
  { label: '与切入阶段一致（默认）', value: null },
  ...triggerTimingOptions
]

function update_trigger(data) {
  backup_plans.value[sub_plan.value].trigger = data
}
</script>

<template>
  <n-modal
    v-model:show="show"
    preset="card"
    title="触发条件"
    :auto-focus="false"
    transform-origin="center"
    style="width: auto; max-width: 90vw"
  >
    <div class="dropdown-container">
      <label class="dropdown-label"
        >最早切入阶段
        <help-text :max-width="560" nowrap>
          <div>该选项表示最早允许切表的阶段。</div>
          <div>任务开始：调度器选中一个待执行任务后，在处理前允许切表。</div>
          <div>进入工作站前：进入本轮第一间非宿舍设施前。</div>
          <div>入住宿舍前：工作站换班完成、进入第一间宿舍前；副表任务会先于原宿舍安排执行。</div>
          <div>下班结束：适合需要在上班前切换产物或订单的副表。</div>
          <div>上班结束：等本轮换班完成后再允许切表。</div>
          <div>任务结束：仅在当前任务收尾或完整状态刷新后允许切表。</div>
          <div>后续检查点仍会复查，条件未变化时不会重复切换。</div>
        </help-text>
      </label>
      <n-select
        v-model:value="backup_plans[sub_plan].trigger_timing"
        :options="triggerTimingOptions"
        placeholder="Select Trigger Timing"
        class="dropdown-select"
      >
      </n-select>
    </div>
    <div class="dropdown-container">
      <label class="dropdown-label"
        >最早切出阶段
        <help-text :max-width="560" nowrap>
          <div>副表条件失效后，最早允许退出副表的阶段。</div>
          <div>默认跟随切入阶段；也可单独设置，例如切入选“入住宿舍前”、切出选“进入工作站前”。</div>
        </help-text>
      </label>
      <n-select
        v-model:value="backup_plans[sub_plan].exit_trigger_timing"
        :options="exitTriggerTimingOptions"
        placeholder="与切入阶段一致"
        class="dropdown-select"
      >
      </n-select>
    </div>

    <n-scrollbar style="max-height: 80vh; margin-top: 5px">
      <n-scrollbar x-scrollable>
        <trigger-editor :data="backup_plans[sub_plan].trigger" @update="update_trigger" />
      </n-scrollbar>
      <n-card style="margin-top: 8px" content-style="padding: 8px" embedded>
        <n-code
          :code="JSON.stringify(backup_plans[sub_plan].trigger, null, 2)"
          language="json"
          word-wrap
        />
      </n-card>
    </n-scrollbar>
  </n-modal>
</template>

<style>
.dropdown-container {
  display: flex;
  align-items: center;
  margin-top: 5px;
}

.dropdown-label {
  flex: 0 0 40%;
  max-width: 125px;
}

.dropdown-select {
  flex: 1;
}
</style>
