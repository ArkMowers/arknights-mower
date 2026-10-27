<script setup>
import { computed, ref } from 'vue'
import { i18n } from '@/i18n'

const { t } = i18n.global

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
        :aria-label="t('groupResting.thresholdLabel', { group })"
        @update:value="update(group, $event)"
      >
        <template #suffix>%</template>
      </mower-input-number>
      <n-button :disabled="disabled" quaternary @click="remove(group)">{{
        t('plans.remove')
      }}</n-button>
    </div>
    <div class="threshold-row">
      <n-select
        v-model:value="selected"
        class="group-select"
        :options="choices"
        :disabled="disabled"
        filterable
        clearable
        :placeholder="t('groupResting.chooseGroup')"
        :aria-label="t('groupResting.groupSelectionLabel')"
      />
      <n-button :disabled="disabled || !selected" @click="add">{{ t('plans.add') }}</n-button>
    </div>
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
