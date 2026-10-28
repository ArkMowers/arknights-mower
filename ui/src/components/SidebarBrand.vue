<script setup>
import { computed, onMounted, onUnmounted, ref, watch } from 'vue'
import { i18n } from '@/i18n'
const { t } = i18n.global
import { resourceVersionBadge, resourceVersionHint } from '@/utils/versionBadges'
import SoftwareVersionBadge from '@/components/SoftwareVersionBadge.vue'

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
const resourceActionHint = computed(() => {
  if (props.resourceChecking) return `${resourceHint.value}\n${t('updates.checkingResources')}`
  if (!props.updatesEnabled || props.resourceDisabled) return resourceHint.value
  return `${resourceHint.value}\n${t('updates.checkResources')}`
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
      'sidebar-brand--text-only': !showLogo
    }"
    aria-label="Mower"
  >
    <div class="sidebar-brand-row">
      <div class="sidebar-brand-home">
        <slot name="home">
          <img v-if="showLogo" :src="'/favicon.ico'" alt="" width="28" height="28" />
          <span class="sidebar-brand-name" :aria-hidden="collapsed">Mower</span>
        </slot>
      </div>
      <button
        v-if="collapsible"
        type="button"
        class="sidebar-brand-toggle"
        :aria-label="t(collapsed ? 'runtime.expandSidebar' : 'runtime.collapseSidebar')"
        :title="t(collapsed ? 'runtime.expandSidebar' : 'runtime.collapseSidebar')"
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
                :style="
                  resourceBadge.state === 'unknown'
                    ? {}
                    : { '--resource-badge-hue': resourceBadge.hue }
                "
                :tabindex="collapsed ? -1 : 0"
                :aria-label="resourceActionHint"
                :aria-busy="resourceChecking"
                :disabled="!updatesEnabled || resourceChecking || resourceDisabled"
                @focus="resourceTooltipFocused = true"
                @blur="resourceTooltipFocused = false"
                @keydown.esc="resourceTooltipOpen = resourceTooltipFocused = false"
                @click="checkResource"
              >
                {{ resourceVersion }}
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
  z-index: 2;
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
  border-radius: 4px;
}
.sidebar-brand-home img {
  flex: none;
  object-fit: contain;
  transition: opacity 0.16s;
}
.sidebar-brand:not(.sidebar-brand--collapsed) .sidebar-brand-home {
  overflow: visible;
}
.sidebar-brand-resource-slot {
  display: flex;
  flex: 0 1 auto;
  align-items: center;
  min-width: 0;
  max-width: 100%;
}
.sidebar-brand-name {
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
  border-radius: 6px;
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
.sidebar-brand-versions {
  display: grid;
  grid-template-rows: 1fr;
  overflow: hidden;
  margin: 8px 0 0 38px;
  transition:
    grid-template-rows 0.24s,
    opacity 0.16s;
}
.sidebar-brand-version-lines {
  display: flex;
  flex-wrap: wrap;
  align-content: flex-start;
  align-items: flex-start;
  gap: 6px;
  min-height: 0;
  overflow: hidden;
}
.sidebar-brand-version-item {
  display: flex;
  align-items: center;
  gap: 6px;
  min-width: 0;
  max-width: 100%;
  overflow: hidden;
}
.sidebar-brand-resource {
  display: block;
  max-width: 100%;
  min-width: 0;
  min-height: 24px;
  box-sizing: border-box;
  padding: 2px 8px;
  border: 1px solid var(--mower-border);
  border-radius: 6px;
  background: var(--mower-control-surface);
  color: var(--mower-text-muted);
  font: inherit;
  font-size: 11px;
  font-weight: 500;
  line-height: 18px;
  font-variant-numeric: tabular-nums;
  white-space: normal;
  overflow-wrap: anywhere;
  cursor: pointer;
  transition:
    border-color 0.16s ease,
    opacity 0.16s ease;
}
.sidebar-brand-resource:enabled:hover {
  opacity: 0.94;
}
.sidebar-brand-resource:not(.sidebar-brand-resource--dated):enabled:hover {
  border-color: var(--mower-text-muted);
}
.sidebar-brand-resource--dated:enabled:hover {
  border-color: hsl(var(--resource-badge-hue) 45% 68%);
}
:global(html[data-mower-theme='dark'] .sidebar-brand-resource--dated:enabled:hover) {
  border-color: hsl(var(--resource-badge-hue) 35% 42%);
}
.sidebar-brand-resource:enabled:active {
  opacity: 0.86;
}
.sidebar-brand-resource:disabled {
  cursor: default;
}
.sidebar-brand-resource[aria-busy='true']::before {
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
  animation: resource-badge-spin 0.8s linear infinite;
}
@keyframes resource-badge-spin {
  to {
    transform: rotate(360deg);
  }
}
.sidebar-brand-resource--dated {
  color: hsl(var(--resource-badge-hue) 65% 28%);
  border-color: hsl(var(--resource-badge-hue) 35% 79%);
  background: hsl(var(--resource-badge-hue) 55% 93%);
}
:global(html[data-mower-theme='dark'] .sidebar-brand-resource--dated) {
  color: hsl(var(--resource-badge-hue) 64% 74%);
  border-color: hsl(var(--resource-badge-hue) 28% 31%);
  background: hsl(var(--resource-badge-hue) 35% 19%);
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
  margin: 6px 0 0;
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
  grid-template-rows: 0fr;
  margin-top: 0;
  visibility: hidden;
  opacity: 0;
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
  .sidebar-brand-resource[aria-busy='true']::before {
    animation: none;
  }
  .sidebar-brand-home img,
  .sidebar-brand-name,
  .sidebar-brand-toggle svg,
  .sidebar-brand-versions,
  .sidebar-brand-resource {
    transition: none;
  }
}
</style>
