<script setup>
defineProps({
  groupOptions: { type: Array, default: () => [] },
  operatorOptions: { type: Array, default: () => [] },
  pinnedGroups: { type: Array, default: () => [] },
  pinnedOperators: { type: Array, default: () => [] }
})
const emit = defineEmits(['update:pinnedGroups', 'update:pinnedOperators'])
</script>

<template>
  <div class="mood-order-controls">
    <label class="mood-priority-field">
      <span>优先编组</span>
      <n-select
        :value="pinnedGroups"
        :options="groupOptions"
        multiple
        filterable
        clearable
        max-tag-count="responsive"
        placeholder="选择需要置顶的编组"
        @update:value="emit('update:pinnedGroups', $event)"
      />
    </label>
    <label class="mood-priority-field">
      <span>优先干员</span>
      <n-select
        :value="pinnedOperators"
        :options="operatorOptions"
        multiple
        filterable
        clearable
        max-tag-count="responsive"
        placeholder="优先展示包含该干员的编组"
        @update:value="emit('update:pinnedOperators', $event)"
      />
    </label>
    <span class="mood-order-hint"
      >按添加顺序优先显示；其余编组保持原顺序。选择保存在本机浏览器。</span
    >
  </div>
</template>

<style scoped>
.mood-order-controls {
  display: flex;
  flex-wrap: wrap;
  justify-content: center;
  align-items: end;
  gap: 10px 16px;
  margin: 0 auto 20px;
  max-width: 1100px;
}
.mood-priority-field {
  display: flex;
  flex: 1 1 245px;
  max-width: 440px;
  flex-direction: column;
  gap: 6px;
  font-size: 13px;
}
.mood-order-hint {
  flex-basis: 100%;
  text-align: center;
  font-size: 12px;
  opacity: 0.65;
}
</style>
