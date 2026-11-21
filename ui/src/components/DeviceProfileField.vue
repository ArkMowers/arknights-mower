<script setup>
import HelpText from './HelpText.vue'

defineProps({ field: { type: Object, required: true } })
const emit = defineEmits(['edit', 'browse'])
const pathFields = ['installation_path', 'manager_path', 'config_path', 'adb_path']
</script>

<template>
  <n-form-item :label-width="158">
    <template #label>
      <span>{{ field.label }}</span>
      <help-text v-if="field.help">{{ field.help }}</help-text>
    </template>
    <div class="profile-field">
      <n-text v-if="field.source" depth="3" class="field-source">{{ field.source }}</n-text>
      <n-select
        v-if="field.kind === 'select'"
        :value="field.value || null"
        :options="field.options"
        :disabled="field.disabled"
        :tag="field.tag"
        :filterable="field.tag"
        :consistent-menu-width="false"
        :placeholder="field.placeholder || '请选择明确目标'"
        :aria-label="field.label"
        @update:value="(value) => emit('edit', field.key, value)"
      />
      <n-input-group v-else-if="pathFields.includes(field.key)">
        <n-input
          :value="field.value"
          :disabled="field.disabled"
          :placeholder="field.placeholder"
          :aria-label="field.label"
          @update:value="(value) => emit('edit', field.key, value)"
        />
        <n-button
          :disabled="field.disabled"
          :aria-label="`选择${field.label}`"
          @click="emit('browse', field.key)"
          >选择</n-button
        >
      </n-input-group>
      <n-input
        v-else
        :value="field.value"
        :disabled="field.disabled"
        :placeholder="field.placeholder"
        :aria-label="field.label"
        @update:value="(value) => emit('edit', field.key, value)"
      />
    </div>
  </n-form-item>
</template>

<style scoped>
.profile-field {
  display: grid;
  gap: 4px;
  width: 100%;
  min-width: 0;
}
.field-source {
  font-size: 12px;
}
.profile-field :deep(.n-input-group > .n-input) {
  flex: 1;
  min-width: 0;
}
</style>
