<script setup>
import { computed, ref } from 'vue'

const thresholds = defineModel({ default: () => ({}) })
const props = defineProps({
  groups: { type: Array, default: () => [] },
  defaultThreshold: { type: Number, default: 65 },
  disabled: Boolean
})
const selected = ref(null)
const choices = computed(() =>
  props.groups
    .filter((group) => !Object.hasOwn(thresholds.value, group))
    .map((group) => ({ label: group, value: group }))
)

function update(group, value) {
  if (props.disabled || value == null || !Number.isFinite(value) || value < 35 || value > 100)
    return
  thresholds.value = { ...thresholds.value, [group]: value / 100 }
}
function add() {
  if (!selected.value || !choices.value.some((option) => option.value === selected.value)) return
  update(selected.value, props.defaultThreshold)
  selected.value = null
}
function remove(group) {
  if (props.disabled) return
  const next = { ...thresholds.value }
  delete next[group]
  thresholds.value = next
}
</script>

<template>
  <div class="group-thresholds">
    <div v-for="(threshold, group) in thresholds" :key="group" class="threshold-row">
      <span class="group-name">{{ group }}</span>
      <mower-input-number
        :value="Math.round(threshold * 10000) / 100"
        :min="35"
        :max="100"
        :step="5"
        :disabled="disabled"
        :aria-label="`${group}心情阈值`"
        @update:value="update(group, $event)"
      >
        <template #suffix>%</template>
      </mower-input-number>
      <n-button :disabled="disabled" quaternary @click="remove(group)">移除</n-button>
    </div>
    <div class="threshold-row">
      <n-select
        v-model:value="selected"
        class="group-select"
        :options="choices"
        :disabled="disabled"
        filterable
        clearable
        placeholder="选择单独设置的绑组"
        aria-label="单独设置心情阈值的绑组"
      />
      <n-button :disabled="disabled || !selected" @click="add">添加</n-button>
    </div>
    <n-text depth="3">
      未设置的组和未绑组干员沿用上方心情阈值。主表、副表按相同组名应用，移除后恢复全局值。
      普通下班线和急救线均按组阈值换算，多绑组干员独立休息时沿用全局值。
      大版本维护前的准备时段，所有组统一使用维护阈值。
    </n-text>
  </div>
</template>

<style scoped>
.group-thresholds {
  display: flex;
  flex-direction: column;
  gap: 10px;
  width: 100%;
}
.threshold-row {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 8px;
}
.group-name {
  min-width: 5em;
  overflow-wrap: anywhere;
}
.threshold-row :deep(.n-input-number) {
  width: 110px;
}
.group-select {
  width: 220px;
  max-width: 100%;
}
</style>
