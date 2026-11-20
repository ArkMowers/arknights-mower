<script setup>
defineProps({
  selected: Boolean,
  unavailable: Boolean,
  disabled: Boolean,
  label: { type: String, required: true }
})
defineEmits(['toggle'])
</script>

<template>
  <td class="weekly-plan-day-cell" :class="{ selected, unavailable }">
    <button
      type="button"
      :disabled="disabled"
      :aria-pressed="selected"
      :aria-label="label"
      @click="$emit('toggle')"
    >
      <span v-if="selected"><slot /></span>
      <span v-else-if="unavailable">—</span>
    </button>
  </td>
</template>

<style scoped lang="scss">
.weekly-plan-day-cell {
  height: 44px;
  background: rgba(240, 160, 32, 0.08);
}

.weekly-plan-day-cell.selected {
  background: rgba(32, 128, 240, 0.22);
  color: #096dd9;
  font-weight: 600;
}

.weekly-plan-day-cell.unavailable:not(.selected) {
  background: rgba(128, 128, 128, 0.06);
  color: rgba(128, 128, 128, 0.45);
}

.weekly-plan-day-cell button {
  display: block;
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
</style>
