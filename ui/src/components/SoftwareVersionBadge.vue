<script setup>
import { computed } from 'vue'
import { getActivePinia } from 'pinia'
import { useGuiStore } from '@/stores/gui'
import { softwareVersionBadge, softwareVersionParts } from '@/utils/versionBadges'

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
// 版本号拆成发布号、预发布后缀与构建后缀；类型名称整段作发布号显示。
const parts = computed(() =>
  label.value === props.version ? softwareVersionParts(label.value) : [label.value, '', '']
)
// 发布号后的两段后缀叠成两行，行位已表明分隔，开头的 `-` 或 `.` 只留在文字中而不显示；
// 没有数字发布号时整段按普通文字排，分隔符照常显示。
const tags = computed(() =>
  parts.value.slice(1).map((text) => {
    const joint = parts.value[0] && /^[-.]/.test(text) ? text[0] : ''
    return { joint, text: text.slice(joint.length) }
  })
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
    :class="[
      badge && `sidebar-brand-channel--${badge}`,
      !parts[0] && 'sidebar-brand-channel--plain'
    ]"
    :title="hint"
    :aria-label="hint"
    :aria-busy="checking"
    :disabled="disabled || checking || readOnly"
    :tabindex="collapsed ? -1 : 0"
    @click="check"
  >
    <span v-if="parts[0]" class="version-badge-release">{{ parts[0] }}</span>
    <span v-if="parts[1] || parts[2]" class="version-badge-tags">
      <span v-if="parts[1]" class="version-badge-tag"
        ><span v-if="tags[0].joint" class="version-badge-joint">{{ tags[0].joint }}</span
        >{{ tags[0].text }}</span
      >
      <span v-if="parts[2]" class="version-badge-build"
        ><span v-if="tags[1].joint" class="version-badge-joint">{{ tags[1].joint }}</span
        >{{ tags[1].text }}</span
      >
    </span>
  </button>
</template>

<style scoped>
/* 数字发布号用大号细体展示字，取类型色；预发布与构建后缀以小字叠在右侧，构建后缀用等宽字。
   类型名称显示时整段占发布号的位置；没有数字发布号的版本按普通文字排。设置页预览经由
   --badge-release-size 等变量缩小同一排法。 */
.sidebar-brand-channel {
  --badge-tone: var(--mower-text-muted);
  --badge-release-size: 30px;
  --badge-tag-size: 11px;
  --badge-plain-size: 15px;
  display: inline-flex;
  align-items: center;
  gap: 2px 8px;
  max-width: 100%;
  min-width: 0;
  box-sizing: border-box;
  padding: 0;
  border: 0;
  border-radius: calc(8px * var(--mower-corner-scale));
  corner-shape: var(--mower-corner-shape);
  background: transparent;
  color: var(--mower-text);
  font: inherit;
  font-family: Bahnschrift, 'Segoe UI Variable Display', 'Segoe UI', system-ui, sans-serif;
  font-variant-numeric: lining-nums tabular-nums;
  text-align: left;
  cursor: pointer;
  transition:
    background-color 0.16s ease,
    opacity 0.16s ease;
}
.version-badge-release {
  flex: none;
  max-width: 100%;
  color: color-mix(in srgb, var(--badge-tone) 72%, var(--mower-text));
  font-size: var(--badge-release-size);
  font-weight: 250;
  line-height: 1;
  letter-spacing: -0.03em;
  overflow-wrap: anywhere;
}
.version-badge-tags {
  display: flex;
  flex-direction: column;
  justify-content: center;
  gap: 2px;
  min-width: 0;
  font-size: var(--badge-tag-size);
  line-height: 1.15;
  overflow-wrap: anywhere;
}
.version-badge-tag {
  color: color-mix(in srgb, var(--badge-tone) 82%, var(--mower-text));
  font-weight: 600;
  letter-spacing: 0.04em;
}
.version-badge-build {
  color: var(--mower-text-muted);
  font-family: 'Cascadia Mono', 'JetBrains Mono', Consolas, 'SF Mono', Menlo, monospace;
  font-size: 0.92em;
  letter-spacing: 0;
}
.version-badge-joint {
  position: absolute;
  width: 1px;
  height: 1px;
  overflow: hidden;
  clip-path: inset(50%);
  white-space: nowrap;
}
.sidebar-brand-channel--plain {
  display: inline;
  font-size: var(--badge-plain-size);
  font-weight: 500;
  line-height: 1.35;
  overflow-wrap: anywhere;
}
.sidebar-brand-channel--plain .version-badge-tags {
  display: inline;
  font-size: inherit;
}
.sidebar-brand-channel--plain .version-badge-tag {
  color: inherit;
  font-weight: inherit;
  letter-spacing: inherit;
}
.sidebar-brand-channel--plain .version-badge-build {
  font-size: 0.8em;
}
.sidebar-brand-channel:enabled:hover {
  background: color-mix(in srgb, var(--mower-text) 6%, transparent);
}
.sidebar-brand-channel:enabled:active {
  background: color-mix(in srgb, var(--mower-text) 10%, transparent);
}
.sidebar-brand-channel:focus-visible {
  outline: 2px solid var(--mower-primary);
  outline-offset: -2px;
}
.sidebar-brand-channel:disabled {
  cursor: default;
}
/* 检查更新时徽标亮度缓慢变化，全局消息提示检查进度和结果。 */
.sidebar-brand-channel[aria-busy='true'] {
  cursor: progress;
  animation: version-badge-busy 1.4s ease-in-out infinite alternate;
}
@keyframes version-badge-busy {
  from {
    opacity: 1;
  }
  to {
    opacity: 0.4;
  }
}
@media (prefers-reduced-motion: reduce) {
  .sidebar-brand-channel {
    transition: none;
  }
  .sidebar-brand-channel[aria-busy='true'] {
    animation: none;
    opacity: 0.6;
  }
}
.sidebar-brand-channel--source {
  --badge-tone: var(--mower-version-source);
}
.sidebar-brand-channel--alpha {
  --badge-tone: var(--mower-version-alpha);
}
.sidebar-brand-channel--nightly {
  --badge-tone: var(--mower-version-nightly);
}
.sidebar-brand-channel--stable {
  --badge-tone: var(--mower-version-stable);
}
</style>
