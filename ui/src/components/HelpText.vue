<template>
  <n-tooltip
    :trigger="clickable ? 'click' : 'manual'"
    :show="clickable ? opened : hovered || focused"
    @update:show="updateOpened"
    :placement="centeredTooltip ? 'top' : undefined"
    :width="centeredTooltip ? 'trigger' : undefined"
    :flip="centeredTooltip ? false : undefined"
    :show-arrow="centeredTooltip ? false : undefined"
    :animated="centeredTooltip ? false : undefined"
    to="body"
    :style="tooltipStyle"
  >
    <template #trigger>
      <span
        ref="trigger"
        class="help"
        @pointerenter="showHelp"
        @pointerleave="hideHelp"
        @mouseenter="showHelp"
        @mouseleave="hideHelp"
        @focusin="focused = true"
        @focusout="focused = false"
        @click.stop
      >
        <n-button
          tertiary
          circle
          size="tiny"
          :disabled="false"
          :aria-label="label"
          :aria-expanded="clickable ? opened : undefined"
        >
          <template #icon>
            <n-icon>
              <svg
                xmlns="http://www.w3.org/2000/svg"
                xmlns:xlink="http://www.w3.org/1999/xlink"
                viewBox="0 0 512 512"
              >
                <path
                  d="M160 164s1.44-33 33.54-59.46C212.6 88.83 235.49 84.28 256 84c18.73-.23 35.47 2.94 45.48 7.82C318.59 100.2 352 120.6 352 164c0 45.67-29.18 66.37-62.35 89.18S248 298.36 248 324"
                  fill="none"
                  stroke="currentColor"
                  stroke-linecap="round"
                  stroke-miterlimit="10"
                  stroke-width="40"
                ></path>
                <circle cx="248" cy="399.99" r="32" fill="currentColor"></circle>
              </svg>
            </n-icon>
          </template>
        </n-button>
      </span>
    </template>
    <div
      @pointerenter="showHelp"
      @pointerleave="hideHelp"
      @mouseenter="showHelp"
      @mouseleave="hideHelp"
      @focusin="focused = true"
      @focusout="focused = false"
    >
      <slot />
    </div>
  </n-tooltip>
</template>

<script setup>
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import { NButton, NIcon, NTooltip } from 'naive-ui'

const props = defineProps({
  label: { type: String, default: '查看说明' },
  maxWidth: { type: Number, default: 360 },
  nowrap: { type: Boolean, default: false },
  clickable: { type: Boolean, default: false },
  centered: { type: Boolean, default: false }
})
const trigger = ref(null)
const centeredTooltip = computed(() => props.clickable && props.centered)
const centeredStyle = ref({})
const tooltipStyle = computed(() => ({
  maxWidth: `min(${props.maxWidth}px, calc(100vw - 32px))`,
  whiteSpace: props.nowrap ? 'nowrap' : 'normal',
  ...(centeredTooltip.value ? centeredStyle.value : {})
}))
const hovered = ref(false)
const focused = ref(false)
const opened = ref(false)
let hideTimer

function positionCenteredTooltip() {
  if (!centeredTooltip.value || !trigger.value) return
  const bounds = trigger.value.getBoundingClientRect()
  const viewport = globalThis.visualViewport
  const width = viewport?.width ?? globalThis.innerWidth
  const left = viewport?.offsetLeft ?? 0
  const top = viewport?.offsetTop ?? 0
  const zoom = Number.parseFloat(getComputedStyle(document.documentElement).zoom) || 1
  const availableWidth = Math.max(0, (width - 32) / zoom)
  const tooltipWidth = Math.min(props.maxWidth, availableWidth)
  centeredStyle.value = {
    width: `${tooltipWidth}px`,
    maxWidth: `${availableWidth}px`,
    maxHeight: `${Math.max(0, (bounds.top - top - 26) / zoom)}px`,
    boxSizing: 'border-box',
    overflow: 'auto',
    left: `${(left + width / 2 - bounds.left) / zoom - tooltipWidth / 2}px`
  }
}

function updateOpened(value) {
  if (value) positionCenteredTooltip()
  opened.value = value
}

function removeViewportListeners() {
  globalThis.removeEventListener?.('resize', positionCenteredTooltip)
  globalThis.visualViewport?.removeEventListener('resize', positionCenteredTooltip)
  globalThis.visualViewport?.removeEventListener('scroll', positionCenteredTooltip)
}

watch(
  () => centeredTooltip.value && opened.value,
  (active) => {
    removeViewportListeners()
    if (!active) return
    positionCenteredTooltip()
    globalThis.addEventListener?.('resize', positionCenteredTooltip)
    globalThis.visualViewport?.addEventListener('resize', positionCenteredTooltip)
    globalThis.visualViewport?.addEventListener('scroll', positionCenteredTooltip)
  }
)

// Listen on a native element: hover must not depend on NButton forwarding events
// or on the button gaining focus after a click in a desktop webview.
function showHelp() {
  clearTimeout(hideTimer)
  hovered.value = true
}

function hideHelp() {
  clearTimeout(hideTimer)
  // Keep links in the help content reachable while the pointer crosses the gap.
  hideTimer = setTimeout(() => {
    hovered.value = false
  }, 100)
}

onBeforeUnmount(() => {
  clearTimeout(hideTimer)
  removeViewportListeners()
})
</script>

<style scoped>
.help {
  display: inline-flex;
  vertical-align: middle;
  flex-shrink: 0;
}
</style>
