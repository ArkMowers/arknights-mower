<template>
  <n-tooltip
    trigger="manual"
    :show="hovered || focused"
    to="body"
    style="max-width: min(360px, calc(100vw - 32px))"
  >
    <template #trigger>
      <span
        class="help"
        @pointerenter="showHelp"
        @pointerleave="hideHelp"
        @mouseenter="showHelp"
        @mouseleave="hideHelp"
        @focusin="focused = true"
        @focusout="focused = false"
      >
        <n-button tertiary circle size="tiny" :disabled="false" :aria-label="label" @click.stop>
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
import { onBeforeUnmount, ref } from 'vue'
import { NButton, NIcon, NTooltip } from 'naive-ui'

defineProps({ label: { type: String, default: '查看说明' } })
const hovered = ref(false)
const focused = ref(false)
let hideTimer

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

onBeforeUnmount(() => clearTimeout(hideTimer))
</script>

<style scoped>
.help {
  display: inline-flex;
  vertical-align: middle;
  flex-shrink: 0;
}
</style>
