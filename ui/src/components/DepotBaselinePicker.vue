<template>
  <div class="depot-baseline-picker">
    <n-popover
      v-model:show="popoverOpen"
      trigger="click"
      placement="bottom-end"
      :flip="false"
      raw
      :show-arrow="false"
      class="baseline-popover-panel"
      @update:show="handlePopoverShowChange"
    >
      <template #trigger>
        <button
          type="button"
          class="baseline-trigger-btn"
          :class="{ active: popoverOpen, 'custom-active': modelValue.preset !== 'previous' }"
          :disabled="history.length < 2"
          :title="
            history.length < 2 ? '历史快照不足 2 次，暂无法对比' : '点击切换对比基准与时间范围'
          "
        >
          <span class="trigger-icon">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8">
              <rect x="3" y="4" width="18" height="18" rx="2" ry="2" />
              <line x1="16" y1="2" x2="16" y2="6" />
              <line x1="8" y1="2" x2="8" y2="6" />
              <line x1="3" y1="10" x2="21" y2="10" />
            </svg>
          </span>
          <span class="trigger-label">{{ activeTriggerLabel }}</span>
          <span class="trigger-arrow">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <path d="m6 9 6 6 6-6" stroke-linecap="round" stroke-linejoin="round" />
            </svg>
          </span>
        </button>
      </template>

      <!-- 弹出卡片主体（单列紧凑，:flip="false" 始终向下弹出，杜绝遮挡） -->
      <div class="baseline-popover-card">
        <!-- 顶部：快捷周期标签 -->
        <div class="popover-presets-grid">
          <button
            v-for="p in BASELINE_PRESETS"
            :key="p.key"
            type="button"
            class="preset-pill-btn"
            :class="{ active: draftPreset === p.key }"
            @click="selectPreset(p.key)"
          >
            <span>{{ p.label }}</span>
          </button>
        </div>

        <div class="popover-divider" />

        <!-- 中部：起止时间微调与选项 -->
        <div class="popover-time-form">
          <div class="pane-section-title">自定义起止时间</div>

          <!-- 开始时间输入卡片 -->
          <div class="time-input-card">
            <span class="time-card-label">开始时间</span>
            <n-date-picker
              v-model:value="draftStartMs"
              type="datetime"
              size="small"
              :clearable="false"
              class="time-card-picker"
              placeholder="选择开始时间"
              @update:value="onManualTimeChange"
            />
          </div>

          <!-- 结束时间输入卡片 -->
          <div class="time-input-card" :class="{ disabled: draftFollowLatest }">
            <span class="time-card-label">结束时间</span>
            <n-date-picker
              v-model:value="draftEndMs"
              type="datetime"
              size="small"
              :clearable="false"
              :disabled="draftFollowLatest"
              class="time-card-picker"
              placeholder="选择结束时间"
              @update:value="onManualTimeChange"
            />
          </div>

          <!-- 结束时间跟随最新记录 -->
          <div class="follow-latest-row">
            <n-checkbox
              v-model:checked="draftFollowLatest"
              size="small"
              @update:checked="onFollowLatestChange"
            >
              结束时间跟随最新扫描
            </n-checkbox>
          </div>

          <!-- 匹配快照反馈与摘要 -->
          <div class="match-summary-card">
            <template v-if="alignmentPreview.matchedCount >= 2">
              <div class="match-count-text">
                已匹配 <b>{{ alignmentPreview.matchedCount }}</b> 次有效快照
              </div>
              <div class="match-range-text">
                {{ formatTimestamp(alignmentPreview.startSnapshot.at).slice(5) }} 至
                {{ formatTimestamp(alignmentPreview.endSnapshot.at).slice(5) }}
              </div>
            </template>
            <template v-else-if="alignmentPreview.matchedCount === 1">
              <div class="match-count-text warning-text">所选区间内仅 1 次快照</div>
              <div class="match-range-text">单次快照无差额对比，请扩大时间范围</div>
            </template>
            <template v-else>
              <div class="match-count-text warning-text">所选时间段内暂无快照</div>
              <div class="match-range-text">未匹配到有效扫描记录，请重新选择</div>
            </template>
          </div>

          <!-- 操作按钮 -->
          <div class="popover-action-row">
            <n-button size="small" quaternary class="action-btn" @click="handleCancel">
              取消
            </n-button>
            <n-button
              size="small"
              type="primary"
              class="action-btn confirm-btn"
              :disabled="alignmentPreview.matchedCount < 2"
              @click="handleApply"
            >
              确定
            </n-button>
          </div>
        </div>
      </div>
    </n-popover>
  </div>
</template>

<script setup>
import { computed, ref } from 'vue'
import {
  alignSnapshotsToRange,
  BASELINE_PRESETS,
  computePresetRange,
  formatTimestamp,
  usableSnapshots
} from '../utils/depot_inventory'

const props = defineProps({
  history: {
    type: Array,
    default: () => []
  },
  modelValue: {
    type: Object,
    default: () => ({
      preset: 'previous',
      range: null,
      followLatest: true
    })
  }
})

const emit = defineEmits(['update:modelValue', 'change'])

const popoverOpen = ref(false)

// 草稿状态（打开弹窗时克隆，确定时提交，取消时回滚）
const draftPreset = ref('previous')
const draftStartMs = ref(null)
const draftEndMs = ref(null)
const draftFollowLatest = ref(true)

const usable = computed(() => usableSnapshots(props.history))

function initDraftFromValue() {
  const current = props.modelValue || {}
  draftPreset.value = current.preset || 'previous'
  draftFollowLatest.value = current.followLatest !== false

  const nowMs = Date.now()
  let range = current.range

  if (!range || !Array.isArray(range) || range.length < 2) {
    range = computePresetRange(draftPreset.value, nowMs)
  }

  if (range && range[0] && range[1]) {
    draftStartMs.value = range[0]
    draftEndMs.value = range[1]
  } else if (usable.value.length >= 2) {
    const prev = usable.value[usable.value.length - 2]
    const latest = usable.value[usable.value.length - 1]
    draftStartMs.value = prev.at * 1000
    draftEndMs.value = latest.at * 1000
  }
}

function handlePopoverShowChange(show) {
  if (show) {
    initDraftFromValue()
  }
}

// 实时预览当前草稿配置对齐到的快照
const alignmentPreview = computed(() => {
  return alignSnapshotsToRange(
    props.history,
    {
      preset: draftPreset.value,
      range: [draftStartMs.value, draftEndMs.value],
      followLatest: draftFollowLatest.value
    },
    Date.now()
  )
})

function selectPreset(presetKey) {
  draftPreset.value = presetKey
  const nowMs = Date.now()

  if (presetKey === 'previous' && usable.value.length >= 2) {
    const prev = usable.value[usable.value.length - 2]
    const latest = usable.value[usable.value.length - 1]
    draftStartMs.value = prev.at * 1000
    draftEndMs.value = latest.at * 1000
    draftFollowLatest.value = true
    return
  }

  if (presetKey === 'all' && usable.value.length >= 2) {
    const first = usable.value[0]
    const latest = usable.value[usable.value.length - 1]
    draftStartMs.value = first.at * 1000
    draftEndMs.value = latest.at * 1000
    draftFollowLatest.value = true
    return
  }

  const range = computePresetRange(presetKey, nowMs)
  if (range && range[0] && range[1]) {
    draftStartMs.value = range[0]
    draftEndMs.value = range[1]
    draftFollowLatest.value = true
  }
}

function onManualTimeChange() {
  if (draftStartMs.value && draftEndMs.value) {
    draftPreset.value = 'custom'
  }
}

function onFollowLatestChange(checked) {
  if (checked && usable.value.length) {
    draftEndMs.value = usable.value[usable.value.length - 1].at * 1000
  }
}

function handleCancel() {
  popoverOpen.value = false
}

function handleApply() {
  const result = {
    preset: draftPreset.value,
    range: [draftStartMs.value, draftEndMs.value],
    followLatest: draftFollowLatest.value
  }
  emit('update:modelValue', result)
  emit('change', result)
  popoverOpen.value = false
}

// 触发按钮上的紧凑文本
const activeTriggerLabel = computed(() => {
  const current = props.modelValue || {}
  const preset = current.preset || 'previous'

  const foundPreset = BASELINE_PRESETS.find((p) => p.key === preset)
  if (foundPreset && preset !== 'custom') {
    return `对比：${foundPreset.label}`
  }

  if (current.range && current.range[0] && current.range[1]) {
    const startStr = formatTimestamp(Math.floor(current.range[0] / 1000)).slice(5, 10)
    const endStr = formatTimestamp(Math.floor(current.range[1] / 1000)).slice(5, 10)
    return `对比：${startStr} ~ ${endStr}`
  }

  return '对比：较上次'
})
</script>

<style scoped>
.depot-baseline-picker {
  display: inline-flex;
  align-items: center;
}

.baseline-trigger-btn {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  height: 32px;
  padding: 0 10px;
  border-radius: 8px;
  border: 1px solid var(--mower-border, rgba(0, 0, 0, 0.12));
  background: var(--mower-control-surface, #ffffff);
  color: var(--mower-text, #1f1e1c);
  font-size: 13px;
  font-weight: 500;
  cursor: pointer;
  transition:
    border-color 0.16s ease,
    background-color 0.16s ease,
    box-shadow 0.16s ease;
  white-space: nowrap;
}

.baseline-trigger-btn:hover:not(:disabled) {
  border-color: var(--mower-primary, #18a058);
  background: var(--mower-surface-hover, rgba(0, 0, 0, 0.02));
}

.baseline-trigger-btn.active,
.baseline-trigger-btn.custom-active {
  border-color: var(--mower-primary, #18a058);
  color: var(--mower-primary, #18a058);
}

.baseline-trigger-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.trigger-icon {
  display: flex;
  align-items: center;
  width: 15px;
  height: 15px;
  color: currentColor;
  opacity: 0.85;
}

.trigger-icon svg,
.trigger-arrow svg {
  width: 100%;
  height: 100%;
}

.trigger-label {
  line-height: 1;
}

.trigger-arrow {
  display: flex;
  align-items: center;
  width: 13px;
  height: 13px;
  opacity: 0.6;
  transition: transform 0.2s ease;
}

.baseline-trigger-btn.active .trigger-arrow {
  transform: rotate(180deg);
}

/* 浮层卡片主体（紧凑单列设计，340px，防止右侧溢出） */
.baseline-popover-card {
  width: 340px;
  max-width: calc(100vw - 32px);
  max-height: calc(100vh - 120px);
  overflow-y: auto;
  padding: 14px;
  border-radius: 12px;
  background: var(--mower-surface, #ffffff);
  border: 1px solid var(--mower-border, rgba(0, 0, 0, 0.12));
  box-shadow:
    0 6px 20px -3px rgba(0, 0, 0, 0.15),
    0 2px 6px rgba(0, 0, 0, 0.08);
  display: flex;
  flex-direction: column;
  gap: 12px;
  box-sizing: border-box;
}

/* 快捷 Pills 栅格：2 行 3 列平分 */
.popover-presets-grid {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 6px;
}

.preset-pill-btn {
  height: 30px;
  padding: 0 4px;
  border-radius: 6px;
  border: 1px solid var(--mower-border, rgba(0, 0, 0, 0.1));
  background: var(--mower-control-surface, #f7f7f5);
  color: var(--mower-text, #333333);
  font-size: 12px;
  font-weight: 500;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  transition: all 0.15s ease;
  white-space: nowrap;
}

.preset-pill-btn:hover {
  background: var(--mower-surface-hover, rgba(0, 0, 0, 0.05));
  border-color: var(--mower-primary, #18a058);
}

.preset-pill-btn.active {
  background: var(--mower-primary, #18a058);
  border-color: var(--mower-primary, #18a058);
  color: #ffffff;
}

.popover-divider {
  height: 1px;
  background: var(--mower-border, rgba(0, 0, 0, 0.08));
}

/* 中部表单 */
.popover-time-form {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.pane-section-title {
  font-size: 12px;
  color: var(--mower-text-muted, rgba(0, 0, 0, 0.5));
  font-weight: 500;
}

.time-input-card {
  padding: 6px 10px 8px;
  border-radius: 8px;
  border: 1px solid var(--mower-border, rgba(0, 0, 0, 0.12));
  background: var(--mower-control-surface, #fafaf9);
  display: flex;
  flex-direction: column;
  gap: 4px;
  transition: border-color 0.16s ease;
}

.time-input-card.disabled {
  opacity: 0.6;
  pointer-events: none;
}

.time-card-label {
  font-size: 11px;
  color: var(--mower-text-muted, rgba(0, 0, 0, 0.55));
}

.time-card-picker {
  width: 100%;
}

.follow-latest-row {
  display: flex;
  align-items: center;
  padding: 2px 0;
}

/* 匹配摘要卡片 */
.match-summary-card {
  padding: 8px 10px;
  border-radius: 8px;
  background: var(--mower-segment-rail, #f2f2f0);
  font-size: 12px;
  line-height: 1.4;
}

.match-count-text {
  font-weight: 500;
  color: var(--mower-text, #1f1e1c);
}

.match-count-text.warning-text {
  color: #e6a23c;
}

.match-range-text {
  font-size: 11px;
  color: var(--mower-text-muted, rgba(0, 0, 0, 0.5));
  margin-top: 2px;
}

.popover-action-row {
  display: flex;
  align-items: center;
  justify-content: flex-end;
  gap: 8px;
  margin-top: 4px;
}

.action-btn {
  min-width: 64px;
}

/* 暗色主题适配 */
html[data-mower-theme='dark'] .baseline-trigger-btn {
  background: var(--mower-control-surface, rgb(36, 36, 42));
  border-color: var(--mower-border, rgba(255, 255, 255, 0.12));
  color: var(--mower-text, #ffffff);
}

html[data-mower-theme='dark'] .baseline-popover-card {
  background: var(--mower-surface, rgb(28, 28, 33));
  border-color: var(--mower-border, rgba(255, 255, 255, 0.12));
}

html[data-mower-theme='dark'] .preset-pill-btn {
  background: var(--mower-control-surface, rgb(36, 36, 42));
  border-color: var(--mower-border, rgba(255, 255, 255, 0.1));
  color: #eeeeee;
}

html[data-mower-theme='dark'] .popover-divider {
  background: var(--mower-border, rgba(255, 255, 255, 0.08));
}

html[data-mower-theme='dark'] .time-input-card {
  background: var(--mower-control-surface, rgb(36, 36, 42));
  border-color: var(--mower-border, rgba(255, 255, 255, 0.12));
}

html[data-mower-theme='dark'] .match-summary-card {
  background: var(--mower-segment-rail, rgb(36, 36, 42));
}
</style>
