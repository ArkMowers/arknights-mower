<script setup>
import { computed } from 'vue'
import SlickOperatorSelect from './SlickOperatorSelect.vue'

const props = defineProps({
  backup: Boolean,
  disabled: Boolean
})
const added = defineModel({ type: Array, default: () => [] })
const removed = defineModel('removed', { type: Array, default: () => [] })
const additions = computed({
  get: () => added.value,
  set: (value) => {
    if (props.disabled) return
    if (props.backup) removed.value = removed.value.filter((name) => !value.includes(name))
    added.value = value
  }
})
const removals = computed({
  get: () => removed.value,
  set: (value) => {
    if (props.disabled) return
    added.value = added.value.filter((name) => !value.includes(name))
    removed.value = value
  }
})
</script>

<template>
  <div class="operator-lists" :class="{ 'operator-lists--backup': backup }">
    <div class="operator-list">
      <span v-if="backup" class="operation-label">增</span>
      <SlickOperatorSelect v-model="additions" :disabled="disabled" />
    </div>
    <div v-if="backup" class="operator-list">
      <span class="operation-label">减</span>
      <SlickOperatorSelect v-model="removals" :disabled="disabled" />
    </div>
  </div>
</template>

<style scoped>
.operator-lists {
  width: 100%;
  min-width: 0;
}
.operator-lists--backup {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 12px;
}
.operator-list {
  display: flex;
  align-items: center;
  gap: 8px;
  min-width: 0;
}
.operation-label {
  flex-shrink: 0;
  font-size: 13px;
  opacity: 0.7;
}
</style>
