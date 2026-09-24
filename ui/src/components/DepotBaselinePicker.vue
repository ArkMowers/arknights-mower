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
          ref="triggerRef"
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
      <div
        class="baseline-popover-card"
        :style="panelMaxHeight ? { maxHeight: panelMaxHeight } : undefined"
      >
        <!-- 顶部：按时间 / 按快照 -->
        <div class="popover-mode-row">
          <n-radio-group v-model:value="draftMode" size="small" @update:value="onModeChange">
            <n-radio-button v-for="m in BASELINE_MODES" :key="m.value" :value="m.value">
              {{ m.label }}
            </n-radio-button>
          </n-radio-group>
          <span class="mode-hint">
            {{ draftMode === 'time' ? '看某段时间内的变化' : '跟具体某两次扫描比' }}
          </span>
        </div>

        <div class="popover-divider" />

        <!-- 按时间：快捷周期 + 起止时间 -->
        <div v-if="draftMode === 'time'" class="popover-time-form">
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
        </div>

        <!-- 按快照：直接挑两次扫描 -->
        <div v-else class="popover-snapshot-form">
          <div class="pane-section-title">选择起止扫描</div>
          <div class="time-input-card">
            <span class="time-card-label">开始</span>
            <n-select
              v-model:value="draftStartKey"
              :options="startOptions"
              size="small"
              filterable
              placeholder="选择起始扫描"
            />
          </div>
          <div class="time-input-card">
            <span class="time-card-label">结束</span>
            <n-select
              v-model:value="draftEndKey"
              :options="endOptions"
              size="small"
              filterable
              placeholder="选择结束扫描"
            />
          </div>
        </div>

        <!-- 匹配快照反馈与摘要（两种模式共用） -->
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
            <div class="match-count-text warning-text">只匹配到 1 次快照</div>
            <div class="match-range-text">
              {{
                draftMode === 'time'
                  ? '单次快照无差额对比，请扩大时间范围'
                  : '起止选了同一次扫描，无差额可比'
              }}
            </div>
          </template>
          <template v-else>
            <div class="match-count-text warning-text">
              {{ draftMode === 'time' ? '所选时间段内暂无快照' : '没有匹配到快照' }}
            </div>
            <div class="match-range-text">
              {{ draftMode === 'time' ? '未匹配到有效扫描记录，请重新选择' : '请重新选择起止扫描' }}
            </div>
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
    </n-popover>
  </div>
</template>

<script setup>
import { computed, nextTick, onMounted, onUnmounted, ref } from 'vue'
import {
  alignSnapshotsToRange,
  BASELINE_MODES,
  BASELINE_PRESETS,
  buildBaselineEndOptions,
  buildBaselineStartOptions,
  computePresetRange,
  DEFAULT_BASELINE_CONFIG,
  formatTimestamp,
  isValidBaselineRange,
  resolveSnapshot,
  usableSnapshots
} from '../utils/depot_inventory'

const props = defineProps({
  history: {
    type: Array,
    default: () => []
  },
  modelValue: {
    type: Object,
    // 默认值直接取数据层的常量：之前这里抄了一份字面量，改一处忘一处就会分叉。
    default: () => ({ ...DEFAULT_BASELINE_CONFIG })
  }
})

const emit = defineEmits(['update:modelValue', 'change'])

const popoverOpen = ref(false)
const triggerRef = ref(null)
const panelMaxHeight = ref('')

// 草稿状态（打开弹窗时克隆，确定时提交，取消时回滚）
const draftMode = ref('time')
const draftPreset = ref('previous')
const draftStartMs = ref(null)
const draftEndMs = ref(null)
const draftFollowLatest = ref(true)
const draftStartKey = ref('previous')
const draftEndKey = ref('latest')

const usable = computed(() => usableSnapshots(props.history))

// 按快照模式的候选：直接复用数据层已经写好并有测试覆盖的选项构造器。
const startOptions = computed(() => buildBaselineStartOptions(props.history))
const endOptions = computed(() => buildBaselineEndOptions(props.history))

function initDraftFromValue() {
  const current = props.modelValue || {}
  draftMode.value = current.mode === 'snapshot' ? 'snapshot' : 'time'
  draftPreset.value = current.preset || 'previous'
  draftFollowLatest.value = current.followLatest !== false
  draftStartKey.value = current.startKey || 'previous'
  draftEndKey.value = current.endKey || 'latest'

  const nowMs = Date.now()

  // 只有自定义范围才照搬存下来的那对时间：相对预设（今天 / 近 N 天）的数字是上次
  // 点选时算出来的，直接恢复会让日期框停在上次的时间点上，和标签写的周期对不上。
  if (draftPreset.value === 'custom' && isValidBaselineRange(current.range)) {
    draftStartMs.value = current.range[0]
    draftEndMs.value = current.range[1]
    return
  }

  // "最早至今"要显示本地第一条快照的时间。computePresetRange('all') 给的是
  // [0, now]，直接塞进日期框就是 1970-01-01，看着像配置坏了（匹配本身没问题，
  // 对齐时 all 走的是快照首尾，不看这个范围）。
  if (draftPreset.value === 'all' && usable.value.length >= 2) {
    const first = resolveSnapshot(usable.value, 'first')
    const latest = resolveSnapshot(usable.value, 'latest')
    draftStartMs.value = first.at * 1000
    draftEndMs.value = latest.at * 1000
    return
  }

  const range = computePresetRange(draftPreset.value, nowMs)
  if (isValidBaselineRange(range)) {
    draftStartMs.value = range[0]
    draftEndMs.value = range[1]
  } else if (usable.value.length >= 2) {
    const previous = resolveSnapshot(usable.value, 'previous')
    const latest = resolveSnapshot(usable.value, 'latest')
    draftStartMs.value = previous.at * 1000
    draftEndMs.value = latest.at * 1000
  }
}

/**
 * 弹窗一律向下展开（:flip="false" 修的是被吸顶工具栏遮住的老问题），代价是触发
 * 按钮越靠屏幕下方，卡片越容易伸出视口底部，"确定"就点不到了。这里按触发按钮到
 * 视口底部的实际距离给卡片一个即时高度上限，让它自己内部滚动，而不是整块飘出去。
 */
function updatePanelSpace() {
  const trigger = triggerRef.value
  if (!trigger || typeof window === 'undefined') return
  const rect = trigger.getBoundingClientRect()
  const available = window.innerHeight - rect.bottom - 16
  panelMaxHeight.value = `${Math.max(180, Math.min(available, window.innerHeight - 120))}px`
}

function handlePopoverShowChange(show) {
  if (show) {
    initDraftFromValue()
    // 等吸顶栏/展开的筛选区排完版再量，否则量到的还是展开前的位置。
    nextTick(updatePanelSpace)
  } else {
    panelMaxHeight.value = ''
  }
}

function onWindowResize() {
  if (popoverOpen.value) updatePanelSpace()
}

onMounted(() => window.addEventListener('resize', onWindowResize))

onUnmounted(() => window.removeEventListener('resize', onWindowResize))

// 实时预览当前草稿配置对齐到的快照
const alignmentPreview = computed(() => {
  return alignSnapshotsToRange(
    props.history,
    {
      mode: draftMode.value,
      preset: draftPreset.value,
      range: [draftStartMs.value, draftEndMs.value],
      followLatest: draftFollowLatest.value,
      startKey: draftStartKey.value,
      endKey: draftEndKey.value
    },
    Date.now()
  )
})

function selectPreset(presetKey) {
  draftPreset.value = presetKey
  const nowMs = Date.now()

  // 自定义不动起止时间：点它就是想接着在下面两个日期框里调。
  if (presetKey === 'custom') return

  // "最早至今"按本地第一条快照算，而不是 computePresetRange 给的 0（1970）。
  if (presetKey === 'all' && usable.value.length >= 2) {
    const first = resolveSnapshot(usable.value, 'first')
    const latest = resolveSnapshot(usable.value, 'latest')
    draftStartMs.value = first.at * 1000
    draftEndMs.value = latest.at * 1000
    draftFollowLatest.value = true
    return
  }

  const range = computePresetRange(presetKey, nowMs)
  if (isValidBaselineRange(range)) {
    draftStartMs.value = range[0]
    draftEndMs.value = range[1]
    draftFollowLatest.value = true
    return
  }

  // previous 没有绝对窗口，按快照序列取上次与最新。
  if (usable.value.length >= 2) {
    const start = resolveSnapshot(usable.value, 'previous')
    const latest = resolveSnapshot(usable.value, 'latest')
    draftStartMs.value = start.at * 1000
    draftEndMs.value = latest.at * 1000
    draftFollowLatest.value = true
  }
}

/** 切到"按快照"时给一对像样的默认值：上一次 → 最新，和"较上次"看到的一致。 */
function onModeChange(mode) {
  if (mode !== 'snapshot') return
  const start = resolveSnapshot(usable.value, 'previous')
  const latest = resolveSnapshot(usable.value, 'latest')
  if (start && latest) {
    draftStartKey.value = String(start.at)
    draftEndKey.value = String(latest.at)
  }
}

function onManualTimeChange() {
  if (draftStartMs.value && draftEndMs.value) {
    draftPreset.value = 'custom'
  }
}

function onFollowLatestChange(checked) {
  const latest = resolveSnapshot(usable.value, 'latest')
  if (checked && latest) {
    draftEndMs.value = latest.at * 1000
  }
}

function handleCancel() {
  popoverOpen.value = false
}

function handleApply() {
  const byTime = draftMode.value === 'time'
  const result = {
    mode: draftMode.value,
    preset: draftPreset.value,
    // 只有"按时间 + 自定义"需要带着那对时间走：相对预设下次打开会按当时的时间重算，
    // previous/all 直接按快照序列取点，存下来的窗口只会让人误会。
    range: byTime && draftPreset.value === 'custom' ? [draftStartMs.value, draftEndMs.value] : null,
    followLatest: draftFollowLatest.value,
    startKey: draftStartKey.value,
    endKey: draftEndKey.value
  }
  emit('update:modelValue', result)
  emit('change', result)
  popoverOpen.value = false
}

// 触发按钮上的紧凑文本
const activeTriggerLabel = computed(() => {
  const current = props.modelValue || {}

  if (current.mode === 'snapshot') {
    const preview = alignSnapshotsToRange(props.history, current)
    if (preview.startSnapshot && preview.endSnapshot) {
      const startStr = formatTimestamp(preview.startSnapshot.at).slice(5, 10)
      const endStr = formatTimestamp(preview.endSnapshot.at).slice(5, 10)
      return `对比：${startStr} ~ ${endStr}`
    }
    return '对比：按快照'
  }

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

/* 顶部模式切换：按时间 / 按快照 */
.popover-mode-row {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.mode-hint {
  font-size: 11px;
  color: var(--mower-text-muted, rgba(0, 0, 0, 0.5));
}

/* 中部表单 */
.popover-time-form {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.popover-snapshot-form {
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
