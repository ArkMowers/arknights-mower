<script setup>
import { nextTick, onBeforeUnmount, onMounted, ref } from 'vue'

const props = defineProps({ selector: String, label: String })
const root = ref(null)
const scrollbar = ref(null)
const contentWidth = ref(0)
const viewportWidth = ref(0)
let target = null
let resizeObserver
let mutationObserver

function syncFromContent() {
  if (target && scrollbar.value) scrollbar.value.scrollLeft = target.scrollLeft
}
function syncFromScrollbar() {
  if (target && scrollbar.value) target.scrollLeft = scrollbar.value.scrollLeft
}
function measure() {
  contentWidth.value = target?.scrollWidth ?? 0
  viewportWidth.value = target?.clientWidth ?? 0
  nextTick(syncFromContent)
}
function bindTarget() {
  const next = root.value.querySelector(props.selector)
  if (next === target) return
  target?.removeEventListener('scroll', syncFromContent)
  resizeObserver.disconnect()
  target = next
  if (target) {
    target.addEventListener('scroll', syncFromContent, { passive: true })
    resizeObserver.observe(target)
    if (target.firstElementChild) resizeObserver.observe(target.firstElementChild)
  }
  measure()
}
onMounted(() => {
  resizeObserver = new ResizeObserver(measure)
  mutationObserver = new MutationObserver(bindTarget)
  mutationObserver.observe(root.value, { childList: true, subtree: true })
  bindTarget()
})
onBeforeUnmount(() => {
  target?.removeEventListener('scroll', syncFromContent)
  resizeObserver?.disconnect()
  mutationObserver?.disconnect()
})
</script>

<template>
  <div ref="root" class="income-horizontal-scroll">
    <slot />
    <div
      v-show="contentWidth > viewportWidth"
      ref="scrollbar"
      class="income-horizontal-scrollbar"
      :style="{ width: `${viewportWidth}px` }"
      role="region"
      :aria-label="label"
      tabindex="0"
      @scroll="syncFromScrollbar"
    >
      <div :style="{ width: `${contentWidth}px`, height: '1px' }" />
    </div>
  </div>
</template>

<style scoped>
.income-horizontal-scroll {
  min-width: 0;
}
.income-horizontal-scrollbar {
  position: sticky;
  bottom: 0;
  z-index: 20;
  max-width: 100%;
  height: 10px;
  overflow-x: scroll;
  overflow-y: hidden;
  background: var(--timeline-surface);
  scrollbar-width: auto;
  scrollbar-color: auto;
}
.income-horizontal-scrollbar::-webkit-scrollbar {
  height: 8px;
}
.income-horizontal-scrollbar::-webkit-scrollbar-track {
  background: var(--timeline-control);
}
.income-horizontal-scrollbar::-webkit-scrollbar-thumb {
  background: var(--timeline-muted);
  border: 1px solid var(--timeline-control);
  border-radius: 4px;
}
.income-horizontal-scrollbar:focus-visible {
  outline: 2px solid var(--timeline-primary);
  outline-offset: -2px;
}
</style>
