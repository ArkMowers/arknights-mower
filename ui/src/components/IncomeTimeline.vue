<script setup>
import { computed, ref, watch } from 'vue'
import { useThemeVars } from 'naive-ui'
import ScheduleTimelineGantt from '@/riic/vendor/components/workbench/ScheduleTimelineGantt.vue'

const props = defineProps({ report: Object, timelineData: Object })
const overviewPage = ref(1)
const operators = computed(() => props.report?.operators ?? [])
const overviewRows = computed(() =>
  operators.value.slice((overviewPage.value - 1) * 20, overviewPage.value * 20)
)
watch(
  () => props.report,
  () => (overviewPage.value = 1)
)
const hours = (value) => Number(value).toLocaleString('zh-CN', { maximumFractionDigits: 2 })
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
    <n-collapse class="time-overview" :default-expanded-names="['operator-time']">
      <n-collapse-item title="干员时间总览" name="operator-time">
        <p>
          仅统计采样期
          {{ hours(props.report?.observedHours ?? 0) }}
          小时，不含预热。工作、休息、空闲和心情涣散驻岗分别统计，主班和替班工时不含心情涣散驻岗。
        </p>
        <p>工作占比 = 工作时长 / 采样时长；工休比 = 工作时长 / 休息时长，无休息时显示 —。</p>
        <div class="time-overview-table">
          <n-table size="small">
            <thead>
              <tr>
                <th>干员</th>
                <th>工作占比</th>
                <th>工休比</th>
                <th>工作（小时）</th>
                <th>主班（小时）</th>
                <th>替班（小时）</th>
                <th>休息（小时）</th>
                <th>空闲（小时）</th>
                <th>心情涣散（小时）</th>
                <th>期末心情</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="operator in overviewRows" :key="operator.operatorId">
                <td>{{ operator.operatorName }}</td>
                <td>{{ hours(operator.workFraction * 100) }}%</td>
                <td>
                  {{
                    operator.workRestRatio == null ? '—' : `${hours(operator.workRestRatio)} : 1`
                  }}
                </td>
                <td>{{ hours(operator.workHours) }}</td>
                <td>{{ hours(operator.mainWorkHours) }}</td>
                <td>{{ hours(operator.substituteWorkHours) }}</td>
                <td>{{ hours(operator.restHours) }}</td>
                <td>{{ hours(operator.idleHours) }}</td>
                <td>{{ hours(operator.exhaustedHours) }}</td>
                <td>{{ hours(operator.finalMorale) }} / 24</td>
              </tr>
            </tbody>
          </n-table>
        </div>
        <n-pagination
          v-if="operators.length > 20"
          v-model:page="overviewPage"
          :item-count="operators.length"
          :page-size="20"
          simple
        />
      </n-collapse-item>
    </n-collapse>
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
.time-overview {
  margin: 12px 0 20px;
}
.time-overview :deep(.n-pagination) {
  margin-top: 12px;
}
.time-overview-table {
  overflow-x: auto;
}
.time-overview-table :deep(table) {
  min-width: 1040px;
  white-space: nowrap;
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
