<script setup>
import { computed } from 'vue'
import { useThemeVars } from 'naive-ui'
import ScheduleTimelineGantt from '@/riic/vendor/components/workbench/ScheduleTimelineGantt.vue'

const props = defineProps({ report: Object, timelineData: Object })
const theme = useThemeVars()
const colors = computed(() => ({
  '--timeline-surface': theme.value.cardColor,
  '--timeline-raised': theme.value.modalColor,
  '--timeline-control': theme.value.actionColor,
  '--timeline-hover': theme.value.hoverColor,
  '--timeline-input': theme.value.inputColor,
  '--timeline-text': theme.value.textColor2,
  '--timeline-muted': theme.value.textColor3,
  '--timeline-heading': theme.value.textColor1,
  '--timeline-border': theme.value.borderColor,
  '--timeline-primary': theme.value.primaryColor,
  '--timeline-radius': theme.value.borderRadius,
  '--timeline-shadow': theme.value.boxShadow3
}))
</script>

<template>
  <div class="income-timeline" :style="colors">
    <ScheduleTimelineGantt
      :report="props.report"
      :timeline-data="props.timelineData"
      :initial-window-hours="24"
      initially-collapsed
    />
  </div>
</template>

<style scoped>
.income-timeline {
  font-variant-numeric: tabular-nums;
}
.income-timeline :deep(.schedule-timeline-gantt) {
  margin: 8px 0 0;
  background: var(--timeline-surface);
  border-color: var(--timeline-border);
  border-radius: var(--timeline-radius);
  color: var(--timeline-text);
  font-family: inherit;
}
.income-timeline :deep(.gantt-header) {
  padding: 16px;
  background: var(--timeline-surface);
  border-color: var(--timeline-border);
}
.income-timeline :deep(.gantt-title) {
  color: var(--timeline-heading);
  font-size: 15px;
  letter-spacing: normal;
}
.income-timeline :deep(.gantt-subtitle) {
  margin-top: 6px;
  line-height: 1.6;
}
.income-timeline
  :deep(
    :is(
      .gantt-subtitle,
      .ctrl-label,
      .event-toggle-label,
      .overview-header-row,
      .overview-title,
      .overview-tick-label,
      .time-window-info,
      .axis-title,
      .tick-label,
      .slot-badge,
      .op-duty-badge,
      .tooltip-subtitle,
      .row-label,
      .event-desc,
      .export-modal-subtitle,
      .scale-title,
      .range-sep,
      .banner-legend,
      .export-axis-col,
      .export-canvas-footer
    )
  ) {
  color: var(--timeline-muted);
}
.income-timeline :deep(:is(.gantt-title-actions, .gantt-controls-bar, .nav-btn-group)) {
  gap: 8px;
}
.income-timeline :deep(:is(button, input, select)) {
  font-family: inherit;
  font-size: 12px;
  transition-property: background-color, border-color, color, box-shadow;
  transition-duration: 150ms;
}
.income-timeline
  :deep(
    :is(
      .export-gantt-btn,
      .toggle-btn,
      .chip-btn,
      .zoom-chip,
      .zoom-btn,
      .nav-btn,
      .scale-btn,
      .export-action-btn.secondary
    )
  ) {
  min-height: 32px;
  padding: 4px 10px;
  border: 1px solid var(--timeline-border);
  border-radius: var(--timeline-radius);
  background: var(--timeline-surface);
  color: var(--timeline-text);
  box-shadow: none;
}
.income-timeline :deep(button:hover:not(:disabled)) {
  background: var(--timeline-hover);
  border-color: var(--timeline-primary);
  color: var(--timeline-primary);
  box-shadow: none;
}
.income-timeline :deep(button.active) {
  background: var(--timeline-hover);
  border-color: var(--timeline-primary);
  color: var(--timeline-primary);
}
.income-timeline :deep(:is(button, input, select):focus-visible) {
  outline: 2px solid var(--timeline-primary);
  outline-offset: 2px;
}
.income-timeline
  :deep(
    :is(
      .view-mode-toggle,
      .window-slider-group,
      .gantt-overview-scrubber,
      .scale-mode-selector,
      .volume-picker-wrap,
      .custom-range-wrap
    )
  ) {
  background: var(--timeline-control);
  border-color: var(--timeline-border);
  border-radius: var(--timeline-radius);
}
.income-timeline :deep(.view-mode-toggle) {
  gap: 4px;
}
.income-timeline :deep(.window-slider-group) {
  flex-wrap: wrap;
  padding: 8px;
}
.income-timeline :deep(.window-size-slider) {
  accent-color: var(--timeline-primary);
}
.income-timeline :deep(.event-toggle-label input) {
  accent-color: var(--timeline-primary);
}
.income-timeline
  :deep(:is(.gantt-search-input, .cycle-select, .volume-select, .custom-range-input)) {
  box-sizing: border-box;
  min-height: 32px;
  background: var(--timeline-input);
  border-color: var(--timeline-border);
  border-radius: var(--timeline-radius);
  color: var(--timeline-text);
}
.income-timeline :deep(.gantt-search-input) {
  width: 220px;
}
.income-timeline :deep(.gantt-search-input::placeholder) {
  color: var(--timeline-muted);
}
.income-timeline :deep(:is(.search-clear-btn, .export-close-btn)) {
  color: var(--timeline-muted);
}
.income-timeline
  :deep(
    :is(
      .gantt-window-nav-bar,
      .time-window-info,
      .facility-group,
      .group-title-col,
      .gantt-axis-label-col,
      .gantt-ruler-row,
      .track-label-col,
      .export-ruler-row,
      .export-axis-col,
      .export-banner,
      .export-canvas-footer
    )
  ) {
  border-color: var(--timeline-border);
}
.income-timeline
  :deep(
    :is(
      .slider-val-badge,
      .overview-pct,
      .major-day .tick-label,
      .facility-eff,
      .row-val.eff-val,
      .banner-time-badge,
      .range-unit
    )
  ) {
  color: var(--timeline-primary);
}
.income-timeline
  :deep(
    :is(
      .time-window-info strong,
      .facility-name,
      .op-name,
      .tooltip-title,
      .row-val,
      .export-modal-title,
      .banner-title,
      .empty-title
    )
  ) {
  color: var(--timeline-heading);
}
.income-timeline
  :deep(
    :is(
      .gantt-ruler-row,
      .gantt-axis-label-col,
      .track-label-col,
      .export-ruler-row,
      .export-axis-col,
      .facility-group-header
    )
  ) {
  background: var(--timeline-control);
}
.income-timeline :deep(:is(.overview-track, .overview-day-tick, .tick-line, .grid-line)) {
  background: var(--timeline-border);
  border-color: var(--timeline-border);
}
.income-timeline :deep(:is(.overview-window-viewport, .overview-window-viewport:hover)) {
  background: var(--timeline-hover);
  border-color: var(--timeline-primary);
  box-shadow: none;
}
.income-timeline :deep(.viewport-tag) {
  color: var(--timeline-primary);
  text-shadow: none;
}
.income-timeline :deep(:is(.scrubber-cursor, .major-day .tick-line)) {
  background: var(--timeline-primary);
}
.income-timeline :deep(.gantt-container) {
  scrollbar-width: thin;
}
.income-timeline :deep(.gantt-container::-webkit-scrollbar) {
  display: block;
  height: 8px;
}
.income-timeline :deep(.gantt-container::-webkit-scrollbar-thumb) {
  background: var(--timeline-border);
  border-radius: 4px;
}
.income-timeline :deep(.facility-tag) {
  display: none;
}
.income-timeline :deep(.block-content) {
  color: #fff;
}
.income-timeline :deep(.gantt-block.status-idle) {
  background: var(--timeline-control);
  border-color: var(--timeline-border);
}
.income-timeline :deep(.status-idle :is(.block-content, .block-name)) {
  color: var(--timeline-muted);
}
.income-timeline :deep(.gantt-tooltip) {
  background: var(--timeline-raised);
  border-color: var(--timeline-border);
  color: var(--timeline-text);
  box-shadow: var(--timeline-shadow);
}
.income-timeline :deep(.gantt-export-modal-overlay) {
  background: rgba(0, 0, 0, 0.4);
  backdrop-filter: none;
  padding: 16px;
}
.income-timeline :deep(.gantt-export-modal-card) {
  width: 100%;
  max-height: calc(100dvh - 32px);
  background: var(--timeline-raised);
  border-color: var(--timeline-border);
  border-radius: var(--timeline-radius);
  box-shadow: var(--timeline-shadow);
}
.income-timeline
  :deep(:is(.export-modal-header, .export-modal-body, .export-canvas, .export-tracks-body)) {
  background: var(--timeline-surface);
  color: var(--timeline-text);
  border-color: var(--timeline-border);
}
.income-timeline :deep(.export-modal-header) {
  gap: 16px;
  flex-wrap: wrap;
}
.income-timeline :deep(.export-action-btn.primary) {
  min-height: 32px;
  background: var(--timeline-primary);
  color: var(--timeline-surface);
  border-radius: var(--timeline-radius);
}
.income-timeline :deep(.export-close-btn) {
  width: 40px;
  height: 40px;
}
@media (max-width: 650px) {
  .income-timeline :deep(.gantt-header) {
    padding: 12px;
  }
  .income-timeline :deep(:is(.gantt-title-actions, .window-slider-group, .search-wrap)) {
    width: 100%;
  }
  .income-timeline :deep(:is(.slider-quick-chips, .export-header-actions)) {
    flex-wrap: wrap;
  }
  .income-timeline :deep(.gantt-search-input) {
    width: 100%;
  }
  .income-timeline :deep(:is(button, select, .gantt-search-input)) {
    min-height: 40px;
  }
  .income-timeline :deep(.gantt-export-modal-overlay) {
    padding: 8px;
  }
}
</style>
