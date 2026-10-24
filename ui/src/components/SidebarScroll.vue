<script setup>
import { NScrollbar } from 'naive-ui'
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'

const scrollbar = ref(null)
const root = ref(null)
const scrollTop = ref(0)
const scrollRange = ref(0)
const canScrollUp = computed(() => scrollTop.value > 1)
const canScrollDown = computed(() => scrollTop.value < scrollRange.value - 1)
let observer

function sync() {
  const container = root.value?.querySelector('.n-scrollbar-container')
  if (!container) return
  scrollRange.value = Math.max(0, container.scrollHeight - container.clientHeight)
  scrollTop.value = Math.max(0, container.scrollTop)
}

function scroll(direction) {
  const container = root.value?.querySelector('.n-scrollbar-container')
  if (!container) return
  const step = Math.max(36, container.clientHeight * 0.7)
  const top = Math.max(0, Math.min(scrollRange.value, container.scrollTop + direction * step))
  const reduced = window.matchMedia?.('(prefers-reduced-motion: reduce)').matches
  scrollbar.value.scrollTo({ top, behavior: reduced ? 'auto' : 'smooth' })
}

onMounted(() => {
  if (!root.value) return
  sync()
  if (typeof ResizeObserver === 'undefined') return
  observer = new ResizeObserver(sync)
  const container = root.value.querySelector('.n-scrollbar-container')
  const content = root.value.querySelector('.n-scrollbar-content')
  if (container) observer.observe(container)
  if (content) observer.observe(content)
})

onBeforeUnmount(() => observer?.disconnect())
</script>

<template>
  <div
    ref="root"
    class="sidebar-scroll"
    :class="{ 'sidebar-scroll--up': canScrollUp, 'sidebar-scroll--down': canScrollDown }"
  >
    <n-scrollbar
      ref="scrollbar"
      class="sidebar-scroll__viewport"
      trigger="none"
      :container-style="{ overflowX: 'hidden' }"
      :content-style="{ minWidth: 0 }"
      :vertical-rail-style="{ top: '13px', bottom: '13px', right: '4px' }"
      :theme-overrides="{ width: '4px' }"
      @scroll="sync"
      @resize="sync"
    >
      <slot />
    </n-scrollbar>
    <template v-if="scrollRange > 1">
      <button
        class="sidebar-scroll__arrow sidebar-scroll__arrow--up"
        type="button"
        aria-label="向上滚动侧边栏"
        :disabled="!canScrollUp"
        @click="scroll(-1)"
      />
      <button
        class="sidebar-scroll__arrow sidebar-scroll__arrow--down"
        type="button"
        aria-label="向下滚动侧边栏"
        :disabled="!canScrollDown"
        @click="scroll(1)"
      />
    </template>
  </div>
</template>

<style scoped>
.sidebar-scroll {
  position: relative;
  min-width: 0;
  min-height: 0;
  height: 100%;
  overflow: hidden;
}

.sidebar-scroll__viewport {
  height: 100%;
}

.sidebar-scroll :deep(.n-scrollbar-rail--vertical) {
  opacity: 0;
  transition: opacity 0.15s;
}

.sidebar-scroll:hover :deep(.n-scrollbar-rail--vertical),
.sidebar-scroll:focus-within :deep(.n-scrollbar-rail--vertical) {
  opacity: 1;
}

.sidebar-scroll__arrow {
  position: absolute;
  z-index: 2;
  right: 1px;
  display: flex;
  align-items: center;
  justify-content: center;
  width: 10px;
  height: 11px;
  padding: 0;
  border: 0;
  border-radius: 2px;
  background: transparent;
  color: var(--sidebar-muted, var(--mower-text));
  opacity: 0;
  cursor: pointer;
  transition: opacity 0.15s;
}

.sidebar-scroll__arrow::before {
  content: '';
  width: 0;
  height: 0;
  border-right: 3px solid transparent;
  border-left: 3px solid transparent;
}

.sidebar-scroll__arrow--up {
  top: 1px;
}

.sidebar-scroll__arrow--up::before {
  border-bottom: 4px solid currentColor;
}

.sidebar-scroll__arrow--down {
  bottom: 1px;
}

.sidebar-scroll__arrow--down::before {
  border-top: 4px solid currentColor;
}

.sidebar-scroll:hover .sidebar-scroll__arrow,
.sidebar-scroll:focus-within .sidebar-scroll__arrow {
  opacity: 0.65;
}

.sidebar-scroll:hover .sidebar-scroll__arrow:disabled,
.sidebar-scroll:focus-within .sidebar-scroll__arrow:disabled {
  opacity: 0.2;
  cursor: default;
}

.sidebar-scroll__arrow:focus-visible {
  outline: 1px solid var(--sidebar-focus, var(--mower-primary));
  outline-offset: 1px;
}

@media (hover: none) {
  .sidebar-scroll :deep(.n-scrollbar-rail--vertical) {
    opacity: 1;
  }

  .sidebar-scroll .sidebar-scroll__arrow {
    opacity: 0.65;
  }

  .sidebar-scroll .sidebar-scroll__arrow:disabled {
    opacity: 0.2;
  }
}

@media (prefers-reduced-motion: reduce) {
  .sidebar-scroll :deep(.n-scrollbar-rail--vertical),
  .sidebar-scroll__arrow {
    transition: none;
  }
}
</style>
