<script setup>
import { formatMoodRate } from '@/utils/mood_rate'
import { moodBadgeBackground } from '@/utils/mood_colors'

defineProps({
  entries: { type: Array, default: () => [] },
  groupName: { type: String, default: '' }
})
const emit = defineEmits(['toggle'])
</script>

<template>
  <div class="mood-rate-legend" :aria-label="groupName + ' 的干员图例与平均速率'">
    <button
      v-for="(entry, index) in entries"
      :key="entry.name + ':' + index"
      class="mood-rate-badge"
      type="button"
      :class="{ 'mood-rate-hidden': !entry.visible }"
      :style="{
        backgroundColor: moodBadgeBackground(entry.color),
        borderColor: entry.color
      }"
      :aria-pressed="entry.visible"
      :aria-label="
        entry.name +
        ' 消耗 ' +
        formatMoodRate(entry.consumption) +
        ' 恢复 ' +
        formatMoodRate(entry.recovery) +
        ' 点每小时，点击切换曲线'
      "
      :title="
        entry.name +
        '｜↓平均消耗 ' +
        formatMoodRate(entry.consumption) +
        '｜↑平均恢复 ' +
        formatMoodRate(entry.recovery) +
        ' 点/小时'
      "
      @click="emit('toggle', index)"
    >
      <span class="mood-badge-stroke" :style="{ backgroundColor: entry.color }"></span>
      <strong class="mood-badge-name">{{ entry.name }}</strong>
      <span class="mood-badge-rate">↓{{ formatMoodRate(entry.consumption) }}</span>
      <span class="mood-badge-rate">↑{{ formatMoodRate(entry.recovery) }}</span>
    </button>
    <span v-if="!entries.length" class="mood-rate-empty">暂无可用心情记录</span>
  </div>
</template>

<style scoped>
.mood-rate-legend {
  display: flex;
  align-content: start;
  align-items: start;
  justify-content: center;
  flex-wrap: wrap;
  gap: 5px;
  max-height: 80px;
  min-height: 27px;
  overflow-y: auto;
  overscroll-behavior: contain;
  padding: 3px 2px 5px;
}
.mood-rate-badge {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  flex-wrap: wrap;
  gap: 3px 5px;
  max-width: 100%;
  min-width: 0;
  color: var(--n-text-color, #202830);
  padding: 4px 7px;
  border: 1px solid;
  border-radius: 7px;
  font-size: 11px;
  line-height: 1.25;
  cursor: pointer;
  transition:
    opacity 0.15s,
    box-shadow 0.15s;
}
.mood-rate-badge:hover {
  box-shadow: inset 0 0 0 1px currentColor;
}
.mood-rate-badge:focus-visible {
  outline: 2px solid currentColor;
  outline-offset: 2px;
}
.mood-rate-hidden {
  opacity: 0.43;
  text-decoration: line-through;
}
.mood-badge-stroke {
  display: block;
  flex: 0 0 13px;
  height: 3px;
  border-radius: 3px;
}
.mood-badge-name {
  font-weight: 650;
  overflow-wrap: anywhere;
}
.mood-badge-rate {
  font-variant-numeric: tabular-nums;
  white-space: nowrap;
}
.mood-rate-empty {
  font-size: 12px;
  opacity: 0.65;
}
</style>
