import { nextTick, onBeforeUnmount, onMounted, onUpdated, ref, watch } from 'vue'
import { groupMeta } from '@/utils/logGroups'
import { captureLogScroll, restoreLogScroll, scrollLogToBottom } from '@/utils/logScrolling'

export function useLogViewport(root, { autoScroll, renderInputs }) {
  const stickyGroup = ref(null)
  let container = null
  let observer = null
  let stickyFrame = null
  let beforeUpdate = null
  let readingPosition = null
  let detailResize = null
  let disposed = false

  function updateStickyGroup() {
    const top = container?.getBoundingClientRect?.().top ?? 0
    const dividers = container?.querySelectorAll?.('.log-group[data-group]') ?? []
    let current = null
    for (const divider of dividers) {
      if ((divider.getBoundingClientRect?.().bottom ?? Infinity) > top + 1) break
      current = divider.getAttribute('data-group')
    }
    stickyGroup.value = current ? (groupMeta(current)?.label ?? null) : null
  }

  function capturePosition() {
    return captureLogScroll(container)
  }

  function restorePosition(snapshot = readingPosition) {
    restoreLogScroll(container, detailResize?.snapshot ?? snapshot, autoScroll())
    if (detailResize) detailResize.scrollTop = container?.scrollTop ?? 0
    else readingPosition = capturePosition()
  }

  function handleScroll() {
    const position = container.scrollTop
    if (detailResize) {
      const max = Math.max(0, container.scrollHeight - container.clientHeight)
      if (Math.abs(position - Math.min(detailResize.scrollTop, max)) <= 0.5) return
      readingPosition = detailResize.snapshot = capturePosition()
      detailResize.scrollTop = position
    } else if (readingPosition?.scrollTop !== position) {
      // A resize may deliver the previous restoration's scroll event after geometry changes.
      readingPosition = capturePosition()
    }
    if (stickyFrame !== null) return
    const schedule = globalThis.requestAnimationFrame ?? ((callback) => setTimeout(callback, 16))
    stickyFrame = schedule(() => {
      stickyFrame = null
      updateStickyGroup()
    })
  }

  function detachContainer() {
    container?.removeEventListener?.('scroll', handleScroll)
    observer?.disconnect()
    observer = null
    container = null
  }

  function bindContainer() {
    const next = root.value?.querySelector?.('.n-scrollbar-container') ?? null
    if (next === container) return
    detachContainer()
    container = next
    container?.addEventListener?.('scroll', handleScroll, { passive: true })
    readingPosition = capturePosition()
    if (container && globalThis.ResizeObserver) {
      observer = new ResizeObserver(() => {
        restorePosition()
        updateStickyGroup()
      })
      observer.observe(container)
      const lines = root.value?.querySelector?.('.log-output__lines')
      if (lines) observer.observe(lines)
    }
  }

  function followLatest() {
    scrollLogToBottom(container)
    readingPosition = capturePosition()
    if (detailResize) {
      detailResize.snapshot = readingPosition
      detailResize.scrollTop = readingPosition?.scrollTop ?? 0
    }
  }

  function preserveInventoryPosition() {
    const snapshot = capturePosition()
    nextTick(() => {
      if (disposed) return
      restoreLogScroll(container, snapshot, autoScroll())
      readingPosition = capturePosition()
      updateStickyGroup()
    })
  }

  function startDetailResize() {
    if (detailResize) return
    const snapshot = capturePosition()
    if (snapshot) detailResize = { snapshot, scrollTop: snapshot.scrollTop }
  }

  function updateDetailResize() {
    if (!observer) restorePosition()
  }

  function takeDetailPosition() {
    const snapshot = detailResize?.snapshot
    detailResize = null
    return snapshot
  }

  function finishDetailResize() {
    const snapshot = takeDetailPosition()
    if (snapshot) restorePosition(snapshot)
  }

  function interruptDetailResize() {
    const snapshot = takeDetailPosition()
    if (snapshot) beforeUpdate = snapshot
  }

  onMounted(() => {
    nextTick(() => {
      if (disposed) return
      bindContainer()
      if (autoScroll()) followLatest()
      else readingPosition = capturePosition()
      updateStickyGroup()
    })
  })
  watch(
    renderInputs,
    () => {
      if (!detailResize) beforeUpdate = capturePosition()
    },
    { deep: true, flush: 'pre' }
  )
  watch(autoScroll, (enabled, previous) => {
    if (!enabled || previous) return
    nextTick(() => {
      if (disposed) return
      bindContainer()
      beforeUpdate = null
      followLatest()
      updateStickyGroup()
    })
  })
  onUpdated(() => {
    bindContainer()
    if (beforeUpdate) {
      restorePosition(beforeUpdate)
      beforeUpdate = null
    }
    updateStickyGroup()
  })
  onBeforeUnmount(() => {
    disposed = true
    detachContainer()
    if (stickyFrame !== null) {
      const cancel = globalThis.cancelAnimationFrame ?? clearTimeout
      cancel(stickyFrame)
    }
  })

  return {
    stickyGroup,
    preserveInventoryPosition,
    startDetailResize,
    updateDetailResize,
    finishDetailResize,
    interruptDetailResize
  }
}
