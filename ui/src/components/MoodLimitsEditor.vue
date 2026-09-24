<script setup>
import { computed, ref } from 'vue'
import { pinyin_match } from '@/utils/common'
import { render_op_label } from '@/utils/op_select'

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
    <n-checkbox :checked="defaults !== null" :disabled="disabled" @update:checked="enableDefaults">
      自定义排班内全体干员
    </n-checkbox>
    <div v-if="defaults" class="mood-range">
      <span>下限</span>
      <mower-input-number
        :value="defaults.lower"
        :disabled="disabled"
        :min="0"
        :max="defaults.upper - 0.1"
        :precision="1"
        aria-label="全体心情下限"
        @update:value="updateRange(null, 'lower', $event)"
      />
      <span>上限</span>
      <mower-input-number
        :value="defaults.upper"
        :disabled="disabled"
        :min="defaults.lower + 0.1"
        :max="24"
        :precision="1"
        aria-label="全体心情上限"
        @update:value="updateRange(null, 'upper', $event)"
      />
    </div>
    <div v-for="[name, limits] in rows" :key="name" class="mood-range">
      <span class="operator-name">{{ name }}</span>
      <span>下限</span>
      <mower-input-number
        :value="limits.lower"
        :disabled="disabled"
        :min="0"
        :max="limits.upper - 0.1"
        :precision="1"
        :aria-label="`${name}心情下限`"
        @update:value="updateRange(name, 'lower', $event)"
      />
      <span>上限</span>
      <mower-input-number
        :value="limits.upper"
        :disabled="disabled"
        :min="limits.lower + 0.1"
        :max="24"
        :precision="1"
        :aria-label="`${name}心情上限`"
        @update:value="updateRange(name, 'upper', $event)"
      />
      <n-button :disabled="disabled" quaternary @click="removeOperator(name)">移除</n-button>
    </div>
    <div class="mood-range">
      <n-select
        v-model:value="selected"
        class="operator-select"
        :disabled="disabled"
        :options="choices"
        :render-label="render_op_label"
        :filter="(input, option) => pinyin_match(option.label, input)"
        filterable
        clearable
        placeholder="选择单独设置的干员"
        aria-label="单独设置心情的干员"
      />
      <n-button :disabled="disabled || !selected" @click="addOperator">添加</n-button>
    </div>
    <n-text depth="3">
      令夕模式优先，其次单独设置、全体设置；未设置沿用{{
        isBackup ? '主表或此前副表' : '令夕等自动规则'
      }}。 仅对当前排班内主班、替班生效。阈值按上下限换算，到上限离宿、不再入宿，固定宿管保留。
    </n-text>
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
