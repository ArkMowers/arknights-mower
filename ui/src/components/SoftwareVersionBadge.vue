<script setup>
import { computed } from 'vue'
import { getActivePinia } from 'pinia'
import { useGuiStore } from '@/stores/gui'
import { softwareVersionBadge } from '@/utils/versionBadges'

const props = defineProps({
  version: { type: String, default: '' },
  deployment: { type: String, default: null },
  displayMode: { type: String, default: 'version' },
  disabled: { type: Boolean, default: false },
  checking: { type: Boolean, default: false },
  readOnly: { type: Boolean, default: false },
  collapsed: { type: Boolean, default: false }
})
const emit = defineEmits(['check'])

const pinia = getActivePinia()
const gui = pinia ? useGuiStore(pinia) : null
const chineseNames = { source: '源码部署', alpha: '公测版', nightly: '开发版', stable: '正式版' }
const badge = computed(() => softwareVersionBadge(props.version, props.deployment))
const kindLabel = computed(() =>
  gui?.softwareVersionLanguage === 'zh' ? chineseNames[badge.value] : badge.value
)
const label = computed(() =>
  props.displayMode === 'channel' && badge.value ? kindLabel.value : props.version
)
const hint = computed(() => {
  const kind = badge.value === 'source' ? '源码启动' : kindLabel.value
  const detail = `软件版本 ${props.version}${kind ? ` · ${kind}` : ''}`
  if (props.checking) return `${detail}\n正在检查软件更新…`
  if (props.readOnly || props.disabled) return detail
  return `${detail}\n点击检查软件更新`
})

function check() {
  if (!props.disabled && !props.checking && !props.readOnly) emit('check')
}
</script>

<template>
  <button
    v-if="version"
    type="button"
    class="sidebar-brand-channel"
    :class="badge ? `sidebar-brand-channel--${badge}` : ''"
    :title="hint"
    :aria-label="hint"
    :aria-busy="checking"
    :disabled="disabled || checking || readOnly"
    :tabindex="collapsed ? -1 : 0"
    @click="check"
  >
    {{ label }}
  </button>
</template>

<style scoped>
.sidebar-brand-channel {
  display: inline-block;
  max-width: 100%;
  min-width: 0;
  min-height: 24px;
  box-sizing: border-box;
  padding: 2px 8px;
  border: 1px solid rgb(0 0 0 / 8%);
  border-radius: 6px;
  background: var(--mower-control-surface);
  font: inherit;
  font-size: 11px;
  font-weight: 500;
  line-height: 18px;
  font-variant-numeric: tabular-nums;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  color: var(--mower-text-muted);
  cursor: pointer;
  transition:
    border-color 0.16s ease,
    opacity 0.16s ease;
}
.sidebar-brand-channel:enabled:hover {
  border-color: rgb(0 0 0 / 16%);
  opacity: 0.94;
}
.sidebar-brand-channel:enabled:active {
  opacity: 0.86;
}
.sidebar-brand-channel:focus-visible {
  outline: 2px solid var(--mower-primary);
  outline-offset: -2px;
}
.sidebar-brand-channel:disabled {
  cursor: default;
}
.sidebar-brand-channel[aria-busy='true']::before {
  content: '';
  display: inline-block;
  width: 10px;
  height: 10px;
  margin-right: 4px;
  box-sizing: border-box;
  border: 1.5px solid currentColor;
  border-right-color: transparent;
  border-radius: 50%;
  vertical-align: -1px;
  animation: version-badge-spin 0.8s linear infinite;
}
@keyframes version-badge-spin {
  to {
    transform: rotate(360deg);
  }
}
@media (prefers-reduced-motion: reduce) {
  .sidebar-brand-channel[aria-busy='true']::before {
    animation: none;
  }
  .sidebar-brand-channel {
    transition: none;
  }
}
.sidebar-brand-channel--alpha,
.sidebar-brand-channel--nightly,
.sidebar-brand-channel--stable {
  color: #fff;
}
.sidebar-brand-channel--alpha {
  background: #c52a3d;
}
.sidebar-brand-channel--nightly {
  background: #173c79;
}
.sidebar-brand-channel--source {
  background: #f2c14b;
  color: #593b08;
}
.sidebar-brand-channel--stable {
  background: #15834a;
}
</style>
