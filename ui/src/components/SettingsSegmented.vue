<script setup>
defineProps({
  value: { type: String, default: '' },
  options: { type: Array, default: () => [] },
  disabled: { type: Boolean, default: false },
  busy: { type: Boolean, default: false },
  label: { type: String, default: '' }
})
defineEmits(['update:value'])
</script>

<template>
  <n-tabs
    class="settings-segmented"
    type="segment"
    size="small"
    animated
    :value="value"
    role="group"
    :aria-label="label"
    :aria-busy="busy"
    @update:value="$emit('update:value', $event)"
  >
    <n-tab
      v-for="option in options"
      :key="option.value"
      :name="option.value"
      :disabled="disabled || option.disabled"
    >
      <button
        type="button"
        class="settings-segmented-choice"
        :disabled="disabled || option.disabled"
        :aria-pressed="value === option.value"
      >
        <n-icon v-if="option.icon" :component="option.icon" size="16" aria-hidden="true" />
        <span>{{ option.label }}</span>
      </button>
    </n-tab>
  </n-tabs>
</template>

<style scoped>
.settings-segmented {
  container: settings-segmented / inline-size;
  width: 100%;
}
.settings-segmented :deep(.n-tabs-tab) {
  padding: 0;
}
.settings-segmented :deep(.n-tabs-tab__label) {
  width: 100%;
  min-width: 0;
}
.settings-segmented-choice {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 6px;
  width: 100%;
  min-width: 0;
  padding: 7px 8px;
  border: 0;
  border-radius: 4px;
  background: transparent;
  color: inherit;
  font: inherit;
  white-space: nowrap;
  cursor: pointer;
}
.settings-segmented-choice:disabled {
  cursor: default;
}
.settings-segmented-choice:focus-visible {
  outline: 2px solid var(--mower-primary);
  outline-offset: -2px;
}
@container settings-segmented (max-width: 280px) {
  .settings-segmented-choice :deep(.n-icon) {
    display: none;
  }
}
@media (prefers-reduced-motion: reduce) {
  .settings-segmented :deep(.n-tabs-capsule) {
    transition: none;
  }
}
</style>
