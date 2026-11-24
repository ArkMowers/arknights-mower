<script setup>
import { publicAsset } from '@/utils/publicAsset'
import { computed, onMounted, onUnmounted, ref, watch } from 'vue'
import {
  resourceVersionBadge,
  resourceVersionHint,
  resourceVersionParts
} from '@/utils/versionBadges'
import SoftwareVersionBadge from '@/components/SoftwareVersionBadge.vue'
import HalloweenDecor from '@/components/HalloweenDecor.vue'
import { useHalloweenSeason } from '@/composables/halloween'

const halloweenActive = useHalloweenSeason()
const props = defineProps({
  collapsed: { type: Boolean, default: false },
  collapsible: { type: Boolean, default: true },
  showLogo: { type: Boolean, default: true },
  version: { type: String, default: '' },
  deployment: { type: String, default: null },
  displayMode: { type: String, default: 'version' },
  updatesEnabled: { type: Boolean, default: false },
  softwareChecking: { type: Boolean, default: false },
  resourceChecking: { type: Boolean, default: false },
  resourceDisabled: { type: Boolean, default: false },
  resourceVersion: { type: String, default: '' },
  resourceMetadata: { type: Object, default: () => ({}) },
  navigationId: { type: String, default: 'sidebar-navigation' }
})
const emit = defineEmits(['toggle', 'check-software', 'check-resource'])

const now = ref(Date.now())
const resourceBadge = computed(() => resourceVersionBadge(props.resourceMetadata, now.value))
const resourceHint = computed(() => resourceVersionHint(props.resourceVersion, resourceBadge.value))
const resourceParts = computed(() => resourceVersionParts(props.resourceVersion))
// 资源进度条与资源徽标同源：取决定颜色的那项活动的剩余比例。
const resourceStyle = computed(() => {
  const badge = resourceBadge.value
  if (badge.state === 'unknown') return {}
  const remaining = Math.max(0, Math.min(1, badge.remaining / (badge.end - badge.start)))
  return {
    '--resource-badge-hue': badge.hue,
    '--resource-remaining': Math.round(remaining * 1000) / 1000
  }
})
const resourceActionHint = computed(() => {
  if (props.resourceChecking) return `${resourceHint.value}\n正在检查资源更新…`
  if (!props.updatesEnabled || props.resourceDisabled) return resourceHint.value
  return `${resourceHint.value}\n点击检查资源更新`
})
const resourceTooltipOpen = ref(false)
const resourceTooltipFocused = ref(false)
let clock = null
let stopClockWatch

function checkResource() {
  if (props.updatesEnabled && !props.resourceChecking && !props.resourceDisabled) {
    emit('check-resource')
  }
}

function stopClock() {
  if (clock !== null) clearInterval(clock)
  clock = null
}

onMounted(() => {
  stopClockWatch = watch(
    () => [props.resourceMetadata, props.resourceVersion, props.collapsed],
    () => {
      stopClock()
      resourceTooltipOpen.value = false
      resourceTooltipFocused.value = false
      now.value = Date.now()
      if (!props.collapsed && props.resourceVersion && resourceBadge.value.refresh) {
        clock = setInterval(() => {
          now.value = Date.now()
          if (!resourceBadge.value.refresh) stopClock()
        }, 60000)
      }
    },
    { immediate: true, deep: true }
  )
})
onUnmounted(() => {
  stopClockWatch?.()
  stopClock()
})
</script>

<template>
  <header
    class="sidebar-brand"
    :class="{
      'sidebar-brand--collapsed': collapsed,
      'sidebar-brand--collapsible': collapsible,
      'sidebar-brand--text-only': !showLogo,
      'sidebar-brand--versioned': version || resourceVersion,
      'sidebar-brand--seasonal': halloweenActive
    }"
    aria-label="Mower"
  >
    <div class="sidebar-brand-row">
      <div class="sidebar-brand-home">
        <slot name="home">
          <img v-if="showLogo" :src="publicAsset('/favicon.ico')" alt="" width="28" height="28" />
          <span class="sidebar-brand-name" :aria-hidden="collapsed">
            Mower
            <HalloweenDecor v-if="halloweenActive && !collapsed" kind="wordmark" />
          </span>
        </slot>
        <HalloweenDecor
          v-if="halloweenActive && !collapsed"
          kind="lantern"
          class="sidebar-brand-lantern"
        />
      </div>
      <button
        v-if="collapsible"
        type="button"
        class="sidebar-brand-toggle"
        :aria-label="collapsed ? '展开侧边栏' : '收起侧边栏'"
        :title="collapsed ? '展开侧边栏' : '收起侧边栏'"
        :aria-expanded="!collapsed"
        :aria-controls="navigationId"
        @click="$emit('toggle')"
      >
        <svg viewBox="0 0 24 24" aria-hidden="true">
          <rect x="3" y="4" width="18" height="16" rx="3.5" />
          <path :d="collapsed ? 'M7.5 8v8' : 'M9 4v16'" />
        </svg>
      </button>
    </div>
    <div v-if="version || resourceVersion" class="sidebar-brand-versions" :aria-hidden="collapsed">
      <div class="sidebar-brand-version-lines">
        <div v-if="version" class="sidebar-brand-version-item">
          <SoftwareVersionBadge
            :version="version"
            :deployment="deployment"
            :display-mode="displayMode"
            :disabled="!updatesEnabled"
            :checking="softwareChecking"
            :collapsed="collapsed"
            @check="$emit('check-software')"
          />
        </div>
        <div v-if="resourceVersion" class="sidebar-brand-resource-slot">
          <n-tooltip
            placement="right"
            :show="!collapsed && (resourceTooltipOpen || resourceTooltipFocused)"
            @update:show="resourceTooltipOpen = $event"
          >
            <template #trigger>
              <button
                type="button"
                class="sidebar-brand-resource"
                :class="{ 'sidebar-brand-resource--dated': resourceBadge.state !== 'unknown' }"
                :style="resourceStyle"
                :tabindex="collapsed ? -1 : 0"
                :aria-label="resourceActionHint"
                :aria-busy="resourceChecking"
                :disabled="!updatesEnabled || resourceChecking || resourceDisabled"
                @focus="resourceTooltipFocused = true"
                @blur="resourceTooltipFocused = false"
                @keydown.esc="resourceTooltipOpen = resourceTooltipFocused = false"
                @click="checkResource"
              >
                {{ resourceParts[0]
                }}<span v-if="resourceParts[1]" class="sidebar-brand-resource-date"
                  ><span class="sidebar-brand-resource-date-mark">#</span
                  >{{ resourceParts[1].slice(1) }}</span
                ><span
                  v-if="resourceBadge.state !== 'unknown'"
                  class="sidebar-brand-resource-meter"
                  aria-hidden="true"
                />
              </button>
            </template>
            <span class="sidebar-brand-resource-hint">{{ resourceActionHint }}</span>
          </n-tooltip>
        </div>
      </div>
    </div>
  </header>
</template>

<style scoped>
.sidebar-brand {
  position: relative;
  flex: none;
  min-height: 48px;
  padding: 10px 10px 4px;
  box-sizing: border-box;
  color: var(--mower-text);
}
.sidebar-brand-row {
  position: relative;
  display: flex;
  align-items: center;
  gap: 4px;
  min-height: 32px;
}
.sidebar-brand-home {
  display: inline-flex;
  flex: 1;
  min-width: 0;
  align-items: center;
  gap: 10px;
  min-height: 32px;
  overflow: hidden;
  color: inherit;
  text-decoration: none;
  border-radius: calc(4px * var(--mower-corner-scale));
  corner-shape: var(--mower-corner-shape);
}
.sidebar-brand-home img {
  flex: none;
  object-fit: contain;
  transition: opacity 0.16s;
}
.sidebar-brand-lantern {
  margin-left: auto;
  flex: none;
  width: 26px;
  height: 26px;
}
.sidebar-brand:not(.sidebar-brand--collapsed) .sidebar-brand-home {
  overflow: visible;
}
.sidebar-brand-resource-slot {
  display: flex;
  min-width: 0;
}
.sidebar-brand-name {
  position: relative;
  flex: none;
  font-size: 18px;
  font-weight: 600;
  line-height: 1.3;
  white-space: nowrap;
  transition:
    opacity 0.16s,
    transform 0.24s;
}
.sidebar-brand-toggle {
  display: inline-grid;
  place-items: center;
  flex: none;
  width: 36px;
  height: 36px;
  padding: 0;
  border: 0;
  border-radius: calc(6px * var(--mower-corner-scale));
  corner-shape: var(--mower-corner-shape);
  background: transparent;
  color: var(--mower-text-muted);
  cursor: pointer;
}
.sidebar-brand-toggle:hover {
  background: var(--mower-control-hover);
  color: var(--mower-text);
}
.sidebar-brand-toggle svg {
  width: 18px;
  height: 18px;
  fill: none;
  stroke: currentColor;
  stroke-width: 1.5;
  stroke-linecap: round;
  stroke-linejoin: round;
  transition: opacity 0.16s;
}
.sidebar-brand-toggle:focus-visible {
  outline: 2px solid var(--mower-primary);
  outline-offset: -2px;
}
/* 有版本信息时 Mower 与版本号组成刊头：Mower 用粗体墨色字，与发光的细体版本号一实一虚；
   万圣节期间的字标装饰按原字号排布，不改变名称样式。 */
.sidebar-brand--versioned:not(.sidebar-brand--collapsed, .sidebar-brand--seasonal)
  .sidebar-brand-name,
.sidebar-brand--versioned:not(.sidebar-brand--collapsed, .sidebar-brand--seasonal)
  :deep(.app-menu-bar__brand-trigger) {
  font-family: Bahnschrift, 'Segoe UI Variable Display', 'Segoe UI', system-ui, sans-serif;
  font-size: 22px;
  font-weight: 700;
  letter-spacing: -0.01em;
  line-height: 26px;
}
.sidebar-brand--versioned.sidebar-brand--text-only:not(.sidebar-brand--collapsed)
  .sidebar-brand-row,
.sidebar-brand--versioned.sidebar-brand--text-only:not(.sidebar-brand--collapsed)
  .sidebar-brand-home {
  min-height: 26px;
}
.sidebar-brand-versions {
  /* WKWebView can retain narrow-width grid row heights after the sider expands.
     Let this block follow the version lines' intrinsic height. */
  margin: 4px -2px 0;
}
.sidebar-brand-version-lines {
  display: flex;
  flex-direction: column;
  align-items: stretch;
  gap: 2px;
  min-height: 0;
}
.sidebar-brand-version-item {
  position: relative;
  display: flex;
  width: fit-content;
  max-width: 100%;
  min-width: 0;
}
/* 悬停底色只包住版本号的实际内容，左右留白相同。支持裁去行高余量的内核把发布号的行框裁到
   大写字母高度与基线之间，上下留白相同，数字在底色里上下居中；其他内核用不对称的留白补偿
   数字下方的行高余量。 */
.sidebar-brand-version-item > :deep(.sidebar-brand-channel) {
  flex: 0 1 auto;
  justify-content: center;
  padding: 3px 8px 4px;
  border-radius: calc(6px * var(--mower-corner-scale));
  corner-shape: var(--mower-corner-shape);
}
@supports (text-box: trim-both cap alphabetic) {
  .sidebar-brand-version-item > :deep(.sidebar-brand-channel:not(.sidebar-brand-channel--plain)) {
    padding: 8px;
  }
  .sidebar-brand-version-item :deep(.version-badge-release) {
    text-box: trim-both cap alphabetic;
  }
}
/* 版本号自身发出类型色的光：浅色主题下是一层带色的柔影，深色主题下是贴字的辉光。 */
.sidebar-brand-version-item :deep(.version-badge-release) {
  filter: drop-shadow(0 2px 8px color-mix(in srgb, var(--badge-tone) 30%, transparent));
}
:global(html[data-mower-theme='dark'] .sidebar-brand-version-item .version-badge-release) {
  filter: drop-shadow(0 0 3px color-mix(in srgb, var(--badge-tone) 50%, transparent))
    drop-shadow(0 0 14px color-mix(in srgb, var(--badge-tone) 40%, transparent));
}
/* 资源版本是刊头的说明行，下方一道细线表示剩余时间：整条淡轨是活动的全程，亮线从文字起点
   铺到剩余比例处，越近末端越亮，末端一点亮芯带着淡淡的辉光，颜色随剩余时间由绿经黄到红。
   亮线出现时从文字起点生长到当前位置一次，之后保持静止。进度条不占文字的位置，名称再长也
   照常换行；无进行中的限时活动时为中性色且没有进度条。 */
.sidebar-brand-resource {
  --badge-tone: var(--mower-text-muted);
  position: relative;
  display: block;
  width: 100%;
  min-width: 0;
  box-sizing: border-box;
  padding: 4px 8px 6px;
  border: 0;
  border-radius: calc(6px * var(--mower-corner-scale));
  corner-shape: var(--mower-corner-shape);
  background: transparent;
  color: var(--mower-text-muted);
  font: inherit;
  font-size: 12px;
  line-height: 18px;
  text-align: left;
  overflow-wrap: anywhere;
  cursor: pointer;
  transition:
    background-color 0.16s ease,
    color 0.16s ease;
}
.sidebar-brand-resource--dated {
  --badge-tone: hsl(var(--resource-badge-hue) 62% 42%);
  --meter-core: color-mix(in oklab, var(--badge-tone), #000 12%);
  --meter-glow: drop-shadow(0 0 1.5px color-mix(in srgb, var(--badge-tone) 25%, transparent));
  /* 进度条画在按钮自己的层里：悬停底色之上、文字之下。 */
  isolation: isolate;
  padding-bottom: 10px;
  color: color-mix(in srgb, var(--badge-tone) 45%, var(--mower-text-muted));
}
:global(html[data-mower-theme='dark'] .sidebar-brand-resource--dated) {
  --badge-tone: hsl(var(--resource-badge-hue) 58% 62%);
  --meter-core: color-mix(in oklab, var(--badge-tone), #fff 40%);
  --meter-glow: drop-shadow(0 0 2px color-mix(in srgb, var(--badge-tone) 40%, transparent));
}
/* 资源版本名末尾的 #MMDD 是资源构建日期：用软件版本号的数字字形，字号略小、颜色更淡，
   与名称隔开一点；日期整体换行，不从中间断开。 */
.sidebar-brand-resource-date {
  display: inline-block;
  margin-left: 3px;
  font-family: Bahnschrift, 'Segoe UI Variable Display', 'Segoe UI', system-ui, sans-serif;
  font-size: 11.5px;
  font-variant-numeric: lining-nums tabular-nums;
  letter-spacing: 0.03em;
  white-space: nowrap;
  opacity: 0.72;
}
/* # 单独成段再调淡：::first-letter 会把开头的标点和其后的第一个数字算作同一个首字母，
   日期的第一位数字会跟着变淡。 */
.sidebar-brand-resource-date-mark {
  color: color-mix(in srgb, currentColor 60%, transparent);
}
.sidebar-brand-resource-meter {
  --meter-end: calc(var(--resource-remaining, 0) * 100%);
  position: absolute;
  z-index: -1;
  right: 8px;
  bottom: 4px;
  left: 8px;
  height: 1.5px;
  border-radius: 1px;
  background: color-mix(in srgb, var(--mower-text) 7%, transparent);
  pointer-events: none;
}
.sidebar-brand-resource-meter::before {
  position: absolute;
  top: 0;
  bottom: 0;
  left: 0;
  width: var(--meter-end);
  border-radius: inherit;
  background:
    linear-gradient(90deg, transparent calc(100% - 3px), var(--meter-core)),
    linear-gradient(
      90deg,
      color-mix(in oklab, var(--badge-tone) 22%, transparent),
      color-mix(in oklab, var(--badge-tone) 70%, transparent) 62%,
      var(--badge-tone)
    );
  filter: var(--meter-glow);
  animation: sidebar-brand-meter-fill 1.1s cubic-bezier(0.22, 0.8, 0.24, 1) 0.15s both;
  content: '';
}
@keyframes sidebar-brand-meter-fill {
  from {
    width: 0;
  }
}
.sidebar-brand-resource:enabled:hover {
  background: color-mix(in srgb, var(--mower-text) 6%, transparent);
  color: color-mix(in srgb, var(--badge-tone) 45%, var(--mower-text));
}
.sidebar-brand-resource:enabled:active {
  background: color-mix(in srgb, var(--mower-text) 10%, transparent);
}
.sidebar-brand-resource:disabled {
  cursor: default;
}
/* 检查更新期间资源名称与进度条缓慢明暗往复；进度与结果仍由全局消息提示。 */
.sidebar-brand-resource[aria-busy='true'] {
  cursor: progress;
  animation: sidebar-brand-version-busy 0.9s ease-in-out infinite alternate;
}
@keyframes sidebar-brand-version-busy {
  from {
    opacity: 1;
  }
  to {
    opacity: 0.4;
  }
}
.sidebar-brand-resource:focus-visible {
  outline: 2px solid var(--mower-primary);
  outline-offset: -2px;
}
.sidebar-brand-resource-hint {
  white-space: pre-line;
}
.sidebar-brand--text-only {
  padding-left: 16px;
}
.sidebar-brand--text-only .sidebar-brand-row,
.sidebar-brand--text-only .sidebar-brand-home {
  min-height: 28px;
}
.sidebar-brand--text-only .sidebar-brand-versions {
  margin: 4px -2px 0 -8px;
}
.sidebar-brand--collapsed {
  padding-left: calc((var(--shell-rail-size, 64px) - 28px) / 2);
}
.sidebar-brand--collapsed .sidebar-brand-name {
  visibility: hidden;
  opacity: 0;
  transform: translateX(-4px);
}
.sidebar-brand--collapsed .sidebar-brand-versions {
  display: none;
}
.sidebar-brand--collapsed .sidebar-brand-toggle {
  position: absolute;
  top: -6px;
  left: -8px;
  width: 44px;
  height: 44px;
}
.sidebar-brand--collapsed .sidebar-brand-toggle svg {
  opacity: 0;
}
.sidebar-brand--collapsed.sidebar-brand--collapsible
  .sidebar-brand-row:hover
  .sidebar-brand-home
  img,
.sidebar-brand--collapsed .sidebar-brand-row:focus-within .sidebar-brand-home img {
  opacity: 0;
}
.sidebar-brand--collapsed .sidebar-brand-row:hover .sidebar-brand-toggle svg,
.sidebar-brand--collapsed .sidebar-brand-row:focus-within .sidebar-brand-toggle svg {
  opacity: 1;
}
@media (prefers-reduced-motion: reduce) {
  .sidebar-brand-resource[aria-busy='true'] {
    animation: none;
    opacity: 0.6;
  }
  .sidebar-brand-resource-meter::before {
    animation: none;
  }
  .sidebar-brand-home img,
  .sidebar-brand-name,
  .sidebar-brand-toggle svg,
  .sidebar-brand-resource {
    transition: none;
  }
}
</style>
