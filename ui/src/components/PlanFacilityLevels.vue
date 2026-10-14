<script setup>
import { computed, inject, ref } from 'vue'
import { usePlanStore } from '@/stores/plan'
import { importMowerJson } from '@/riic/vendor/workbench/compat/mowerJson'
import { validateRosterWorkspace } from '@/riic/vendor/workbench/validate'
import { getRoomDisplayName } from '@/riic/vendor/workbench/operatorHelpers'

const props = defineProps({ facility: String, locked: Boolean })
const store = inject('planStore', null) || usePlanStore()
const expanded = ref(false)
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
    label: level ? `${level} 级` : '未建造',
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
  <div class="facility-levels" data-no-update-drop>
    <div class="power-summary" v-if="state.power" role="status">
      <span
        >发电 <b>{{ state.power.generation }}</b></span
      >
      <span
        >耗电 <b>{{ state.power.consumption }}</b></span
      >
      <n-tag :type="state.power.sufficient ? 'success' : 'error'" size="small">
        {{ state.power.sufficient ? '剩余' : '缺电' }} {{ Math.abs(state.power.margin) }}
      </n-tag>
      <n-button text size="small" @click="expanded = !expanded">设施等级说明</n-button>
    </div>
    <p v-if="expanded" class="level-help">
      点击下方设施设置等级，随排班自动保存，主副表共用，导入导出保留。未设置的设施沿用推断等级；未排班但已建造的右侧设施也需填写等级，才能计入电量。
      宿舍按当前等级满氛围计算恢复速度；工作心情消耗按实际进驻人数、中枢和技能计算。电量不足或人数超过等级容量时不能演算，可继续编辑排班。
    </p>
    <div v-if="editable" class="level-control">
      <span>{{ getRoomDisplayName(facility, selected.type) }}等级</span>
      <n-select
        aria-label="设施等级"
        :value="selected.level"
        :options="options"
        :disabled="locked || (facility.startsWith('room_') && !store.plan[facility]?.name)"
        @update:value="setLevel"
      />
      <span class="level-source">{{
        Object.hasOwn(store.facility_levels, facility) ? '已设置' : '推断值'
      }}</span>
      <n-button
        v-if="Object.hasOwn(store.facility_levels, facility)"
        text
        size="small"
        :disabled="locked"
        @click="resetLevel"
        >恢复推断</n-button
      >
      <span v-if="selected.type === 'dormitory' && selected.level > 0">
        氛围 {{ selected.level * 1000 }} · 基础恢复 {{ 1.5 + selected.level * 0.5 }} 点/小时
      </span>
    </div>
    <n-alert v-if="state.error" type="warning">{{ state.error }}</n-alert>
    <n-alert v-else-if="state.issues.length" type="warning">
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
.level-control {
  margin-top: 12px;
}
.level-control .n-select {
  width: 130px;
}
.level-source {
  opacity: 0.65;
}
.level-help {
  line-height: 1.7;
}
.n-alert {
  margin-top: 12px;
}
</style>
