<script setup>
import { computed, ref } from 'vue'
import { useConfigStore } from '@/stores/config'

const props = defineProps({ usage: { type: Object, default: null }, busy: Boolean })
const config = useConfigStore()
const open = ref(false)
const pinned = ref(false)
function close() {
  open.value = false
  pinned.value = false
}
function pin() {
  open.value = true
  pinned.value = true
}
const usage = computed(() => {
  const value = props.usage
  return value &&
    Number.isSafeInteger(value.used_tokens) &&
    value.used_tokens >= 0 &&
    Number.isSafeInteger(value.max_tokens) &&
    value.max_tokens > 0
    ? value
    : null
})
const capacity = computed(
  () =>
    usage.value?.max_tokens ??
    (config.ai_type === 'deepseek'
      ? (config.ai_deepseek_context_tokens ?? 1000000)
      : (config.ai_context_tokens ?? 256000))
)
const usedPercent = computed(() =>
  usage.value ? Math.round((usage.value.used_tokens / capacity.value) * 100) : null
)
const remainingPercent = computed(() => Math.max(0, 100 - (usedPercent.value ?? 0)))
const ringOffset = computed(() => 50.265 * (1 - Math.min(100, usedPercent.value ?? 0) / 100))
const compacting = computed(() => props.busy && usage.value?.compacting)
const formatTokens = (value) =>
  value >= 1000000
    ? `${Number((value / 1000000).toFixed(2))}M`
    : value >= 1000
      ? `${Number((value / 1000).toFixed(1))}k`
      : String(value)
const label = computed(() =>
  usage.value
    ? `上下文窗口：${usage.value.estimated ? '估算' : ''}已用 ${usage.value.used_tokens.toLocaleString('zh-CN')} token，共 ${capacity.value.toLocaleString('zh-CN')} token，${usedPercent.value}% 已用，剩余 ${remainingPercent.value}%`
    : `上下文窗口：总容量 ${formatTokens(capacity.value)} token，发送后显示用量`
)
</script>

<template>
  <n-popover
    :show="open"
    trigger="manual"
    placement="top-end"
    :show-arrow="false"
    :style="{ maxWidth: 'min(280px, calc(100vw - 88px))', boxSizing: 'border-box' }"
    @clickoutside="close"
  >
    <template #trigger>
      <button
        type="button"
        class="context-usage-button"
        :class="{ 'context-usage-high': (usedPercent ?? 0) >= 80 }"
        :aria-label="label"
        :aria-expanded="open"
        @mouseenter="open = true"
        @mouseleave="!pinned && (open = false)"
        @focus="open = true"
        @blur="close"
        @click="pin"
        @keydown.esc="close"
      >
        <svg width="20" height="20" viewBox="0 0 24 24" aria-hidden="true">
          <circle cx="12" cy="12" r="8" class="context-ring-track" />
          <circle
            v-if="usage"
            cx="12"
            cy="12"
            r="8"
            class="context-ring-value"
            stroke-dasharray="50.265"
            :stroke-dashoffset="ringOffset"
          />
        </svg>
      </button>
    </template>
    <div class="context-usage-detail">
      <div class="context-usage-title">上下文窗口</div>
      <template v-if="usage">
        <div class="context-usage-percent">
          {{ usedPercent }}% 已用（剩余 {{ remainingPercent }}%）
        </div>
        <div>
          {{ usage.estimated ? '估算已用' : '已用' }}
          {{ formatTokens(usage.used_tokens) }} token，共 {{ formatTokens(capacity) }} token
        </div>
        <div v-if="compacting" class="context-usage-note" role="status">
          正在压缩较早的工具记录…
        </div>
        <div v-else-if="usage.compactions" class="context-usage-note">
          本轮已压缩 {{ usage.compactions }} 次
        </div>
        <div class="context-usage-note">最近一次模型输入；不包含未发送的草稿。</div>
      </template>
      <template v-else>
        <div>总容量 {{ formatTokens(capacity) }} token</div>
        <div class="context-usage-note">发送后显示本轮用量。</div>
      </template>
    </div>
  </n-popover>
</template>

<style scoped>
.context-usage-button {
  display: grid;
  place-items: center;
  flex: 0 0 40px;
  width: 40px;
  height: 40px;
  padding: 0;
  border: 0;
  border-radius: 50%;
  background: transparent;
  color: var(--mower-text-muted);
  cursor: pointer;
}
.context-usage-button:hover {
  background: var(--mower-control-surface);
}
.context-usage-button:focus-visible {
  outline: 2px solid currentColor;
  outline-offset: 1px;
}
.context-usage-high {
  color: var(--mower-warning, #b88724);
}
.context-ring-track,
.context-ring-value {
  fill: none;
  stroke: currentColor;
  stroke-width: 2.5;
}
.context-ring-track {
  opacity: 0.22;
}
.context-ring-value {
  transform: rotate(-90deg);
  transform-origin: 12px 12px;
  stroke-linecap: round;
  transition: stroke-dashoffset 160ms ease;
}
.context-usage-detail {
  max-width: 100%;
  padding: 2px;
  font-size: 12px;
  line-height: 1.75;
  font-variant-numeric: tabular-nums;
  overflow-wrap: anywhere;
}
.context-usage-title,
.context-usage-note {
  color: var(--mower-text-muted);
}
.context-usage-percent {
  font-size: 14px;
  font-weight: 500;
}
@media (prefers-reduced-motion: reduce) {
  .context-ring-value {
    transition: none;
  }
}
</style>
