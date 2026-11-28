<script setup>
import { computed, inject } from 'vue'
import { usePlanStore } from '@/stores/plan'
import { importMowerJson } from '@/riic/vendor/workbench/compat/mowerJson'
import { validateRosterWorkspace } from '@/riic/vendor/workbench/validate'

const props = defineProps({
  facility: String,
  locked: Boolean,
  mode: { type: String, default: 'summary' }
})
const store = inject('planStore', null) || usePlanStore()
const state = computed(() => {
  try {
    const workspace = importMowerJson(JSON.stringify(store.build_plan()))
    const validation = validateRosterWorkspace(workspace)
    return {
      facilities: workspace.mainPlan.facilities,
      power: validation.power,
      issues: validation.criticalErrors.filter(
        (issue) =>
          ['POWER_DEFICIT', 'SLOT_OVERFLOW'].includes(issue.code) ||
          (issue.code === 'INVALID_CONFIG' && Object.hasOwn(store.facility_levels, issue.roomId))
      )
    }
  } catch (error) {
    return { error: error.message }
  }
})
const selected = computed(
  () =>
    state.value.facilities?.[props.facility] ??
    (Object.hasOwn(store.facility_levels, props.facility)
      ? { level: store.facility_levels[props.facility], type: '' }
      : null)
)
const editable = computed(() => selected.value && !props.facility.startsWith('gaming_'))
const options = computed(() => {
  if (!editable.value) return []
  const maximum = props.facility === 'central' || props.facility.startsWith('dormitory_') ? 5 : 3
  return Array.from({ length: maximum + 1 }, (_, level) => ({
    label:
      (level ? `${level} 级` : '未建造') +
      (level === selected.value.level && !Object.hasOwn(store.facility_levels, props.facility)
        ? '（默认）'
        : ''),
    value: level
  }))
})
function setLevel(level) {
  if (props.locked || level === null) return
  store.facility_levels[props.facility] = level
}
function resetLevel() {
  if (props.locked) return
  delete store.facility_levels[props.facility]
}
</script>

<template>
  <div class="facility-levels" :class="mode" data-no-update-drop>
    <div class="power-summary" v-if="mode === 'summary' && state.power" role="status">
      <span
        >发电 <b>{{ state.power.generation }}</b></span
      >
      <span
        >耗电 <b>{{ state.power.consumption }}</b></span
      >
      <n-tag :type="state.power.sufficient ? 'success' : 'error'" size="small">
        {{ state.power.sufficient ? '剩余' : '缺电' }} {{ Math.abs(state.power.margin) }}
      </n-tag>
    </div>
    <div v-if="mode === 'level' && editable" class="level-control">
      <span>等级：</span>
      <n-select
        aria-label="设施等级"
        :value="selected.level"
        :options="options"
        :disabled="locked || (facility.startsWith('room_') && !store.plan[facility]?.name)"
        @update:value="setLevel"
      />
      <n-button
        v-if="Object.hasOwn(store.facility_levels, facility)"
        text
        size="small"
        :disabled="locked"
        @click="resetLevel"
        >恢复默认</n-button
      >
    </div>
    <n-alert v-if="mode === 'summary' && state.error" type="warning">{{ state.error }}</n-alert>
    <n-alert v-else-if="mode === 'summary' && state.issues.length" type="warning">
      <div v-for="(issue, i) in state.issues" :key="i">{{ issue.message }}</div>
    </n-alert>
  </div>
</template>

<style scoped>
.facility-levels {
  margin: 8px 0 16px;
}
.power-summary,
.level-control {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 12px;
}
.facility-levels.level {
  margin: 0;
}
.level-control {
  flex-wrap: nowrap;
  gap: 8px;
  white-space: nowrap;
}
.level-control .n-select {
  width: 120px;
}
.n-alert {
  margin-top: 12px;
}
</style>
