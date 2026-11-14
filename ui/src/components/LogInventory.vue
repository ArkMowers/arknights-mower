<script setup>
import { computed, ref, useId } from 'vue'
import { itemIconUrl } from '@/utils/depot_inventory'

const props = defineProps({
  items: { type: Array, required: true },
  source: { type: String, required: true }
})
const emit = defineEmits(['resize'])
const expanded = ref(false)
const listId = useId()
const failedIcons = ref(new Set())
const shown = computed(() => (expanded.value ? props.items : props.items.slice(0, 3)))
function toggle() {
  expanded.value = !expanded.value
  emit('resize')
}
function hideIcon(name) {
  failedIcons.value = new Set([...failedIcons.value, name])
}
</script>

<template>
  <span class="log-inventory" :data-log-source="source">
    <span class="log-inventory__summary">仓库扫描：已识别{{ items.length }}种物品</span>
    <span :id="listId" class="log-inventory__items">
      <span
        v-for="(item, index) in shown"
        :key="`${index}:${item.name}`"
        class="log-inventory__item"
      >
        <img
          v-if="!failedIcons.has(item.name)"
          :src="itemIconUrl(item.name)"
          width="18"
          height="18"
          alt=""
          aria-hidden="true"
          @error="hideIcon(item.name)"
        />
        <span>{{ item.name }}：{{ item.count }}</span>
      </span>
    </span>
    <button
      v-if="items.length > 3"
      type="button"
      class="log-inventory__toggle"
      :aria-expanded="expanded"
      :aria-controls="listId"
      @click="toggle"
    >
      {{ expanded ? '收起' : `还有${items.length - 3}项，展开` }}
    </button>
  </span>
</template>

<style scoped>
.log-inventory {
  display: inline;
  text-indent: 0;
  vertical-align: top;
  white-space: normal;
}
.log-inventory__summary {
  display: inline;
}
.log-inventory__items {
  display: flex;
  flex-wrap: wrap;
  gap: 3px 14px;
  margin-top: 3px;
}
.log-inventory__item {
  display: inline-flex;
  align-items: center;
  gap: 3px;
  max-width: 100%;
  overflow-wrap: anywhere;
}
.log-inventory__item img {
  flex: none;
  object-fit: contain;
}
.log-inventory__item > span {
  min-width: 0;
  overflow-wrap: anywhere;
}
.log-inventory__toggle {
  padding: 2px 0;
  border: 0;
  background: transparent;
  color: var(--log-room-ink);
  font: inherit;
  cursor: pointer;
  text-decoration: underline;
  text-underline-offset: 3px;
}
.log-inventory__toggle:focus-visible {
  outline: 2px solid currentColor;
  outline-offset: 2px;
}
</style>
