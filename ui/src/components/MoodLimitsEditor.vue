<script setup>
import { i18n } from '@/i18n'
import { operatorDisplayName } from '@/i18n/gameNames'
const { t } = i18n.global
import { computed, ref } from 'vue'
import { pinyin_match } from '@/utils/common'
import { render_op_option, render_op_label } from '@/utils/op_select'

const defaults = defineModel('defaults', { default: null })
const overrides = defineModel('overrides', { default: () => ({}) })
const props = defineProps({
  disabled: Boolean,
  operators: { type: Array, default: () => [] },
  isBackup: Boolean
})
const selected = ref(null)
const choices = computed(() =>
  props.operators.filter((option) => !Object.hasOwn(overrides.value, option.value))
)
const rows = computed(() => Object.entries(overrides.value))

function enableDefaults(enabled) {
  if (!props.disabled) defaults.value = enabled ? { lower: 0, upper: 24 } : null
}
function updateRange(name, field, value) {
  if (props.disabled || value == null || !Number.isFinite(value)) return
  const current = name == null ? defaults.value : overrides.value[name]
  if (!current) return
  const next = { ...current, [field]: value }
  if (next.lower < 0 || next.lower >= next.upper || next.upper > 24) return
  if (name == null) defaults.value = next
  else overrides.value = { ...overrides.value, [name]: next }
}
function addOperator() {
  if (props.disabled || !selected.value || Object.hasOwn(overrides.value, selected.value)) return
  overrides.value = {
    ...overrides.value,
    [selected.value]: { ...(defaults.value ?? { lower: 0, upper: 24 }) }
  }
  selected.value = null
}
function removeOperator(name) {
  if (props.disabled) return
  const next = { ...overrides.value }
  delete next[name]
  overrides.value = next
}
</script>

<template>
  <div class="mood-limits-editor">
    <n-checkbox
      :checked="defaults !== null"
      :disabled="disabled"
      @update:checked="enableDefaults"
      >{{ t('plans.globalMoraleLimits') }}</n-checkbox
    >
    <div v-if="defaults" class="mood-range">
      <span>{{ t('plans.lowerLimit') }}</span>
      <mower-input-number
        :value="defaults.lower"
        :disabled="disabled"
        :min="0"
        :max="defaults.upper - 0.1"
        :precision="1"
        :aria-label="t('plans.globalLowerLimit')"
        @update:value="updateRange(null, 'lower', $event)"
      />
      <span>{{ t('plans.upperLimit') }}</span>
      <mower-input-number
        :value="defaults.upper"
        :disabled="disabled"
        :min="defaults.lower + 0.1"
        :max="24"
        :precision="1"
        :aria-label="t('plans.globalUpperLimit')"
        @update:value="updateRange(null, 'upper', $event)"
      />
    </div>
    <div v-for="[name, limits] in rows" :key="name" class="mood-range">
      <span class="operator-name">{{ operatorDisplayName(name) }}</span>
      <span>{{ t('plans.lowerLimit') }}</span>
      <mower-input-number
        :value="limits.lower"
        :disabled="disabled"
        :min="0"
        :max="limits.upper - 0.1"
        :precision="1"
        :aria-label="t('plans.personalLowerLimit', { name: operatorDisplayName(name) })"
        @update:value="updateRange(name, 'lower', $event)"
      />
      <span>{{ t('plans.upperLimit') }}</span>
      <mower-input-number
        :value="limits.upper"
        :disabled="disabled"
        :min="limits.lower + 0.1"
        :max="24"
        :precision="1"
        :aria-label="t('plans.personalUpperLimit', { name: operatorDisplayName(name) })"
        @update:value="updateRange(name, 'upper', $event)"
      />
      <n-button :disabled="disabled" quaternary @click="removeOperator(name)">{{
        t('plans.remove')
      }}</n-button>
    </div>
    <div class="mood-range">
      <n-select
        v-model:value="selected"
        class="operator-select"
        :disabled="disabled"
        :options="choices"
        :render-label="render_op_label"
        :render-option="render_op_option"
        :filter="(input, option) => pinyin_match(option.label, input)"
        filterable
        clearable
        :placeholder="t('plans.choosePersonalMorale')"
        :aria-label="t('plans.personalMoraleOperator')"
      />
      <n-button :disabled="disabled || !selected" @click="addOperator">{{
        t('plans.add')
      }}</n-button>
    </div>
    <n-text depth="3">{{
      t('plans.moraleLimitsDescription', {
        rules: isBackup ? t('plans.previousPlanRules') : t('plans.automaticRules')
      })
    }}</n-text>
  </div>
</template>

<style scoped>
.mood-limits-editor {
  display: flex;
  flex-direction: column;
  gap: 10px;
  width: 100%;
}
.mood-range {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 8px;
}
.mood-range :deep(.n-input-number) {
  width: 100px;
}
.operator-name {
  min-width: 5em;
}
.operator-select {
  width: 220px;
  max-width: 100%;
}
</style>
