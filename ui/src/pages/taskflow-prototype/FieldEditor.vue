<script setup>
// PROTOTYPE：三个变体共用的字段编辑器，只改内存里的假数据。
defineProps({
  fields: { type: Array, required: true },
  dense: { type: Boolean, default: false }
})
</script>

<template>
  <div class="proto-fields" :class="{ 'proto-fields--dense': dense }">
    <label v-for="field in fields" :key="field.key" class="proto-field">
      <span class="proto-field-label">{{ field.label }}</span>
      <n-switch v-if="field.type === 'switch'" v-model:value="field.value" size="small" />
      <n-input-number
        v-else-if="field.type === 'number'"
        v-model:value="field.value"
        size="small"
        :min="field.min"
        :max="field.max"
        :step="field.step"
        style="width: 148px"
      >
        <template #suffix>{{ field.unit }}</template>
      </n-input-number>
      <n-select
        v-else-if="field.type === 'select'"
        v-model:value="field.value"
        size="small"
        :options="field.options.map((o) => ({ label: o, value: o }))"
        style="width: 148px"
      />
      <n-slider
        v-else-if="field.type === 'slider'"
        v-model:value="field.value"
        :min="field.min"
        :max="field.max"
        style="width: 148px"
      />
      <n-input v-else v-model:value="field.value" size="small" style="width: 148px" />
    </label>
    <p v-if="!fields.length" class="proto-field-empty">这一站没有可调整的参数，启用即可。</p>
  </div>
</template>

<style scoped>
.proto-fields {
  display: flex;
  flex-direction: column;
  gap: 12px;
}
.proto-fields--dense {
  gap: 8px;
}
.proto-field {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  font-size: 13px;
}
.proto-field-label {
  color: var(--mower-text);
}
.proto-field-empty {
  margin: 0;
  font-size: 13px;
  color: var(--mower-text-muted);
}
</style>
