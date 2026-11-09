import { nextTick, onBeforeUnmount, onMounted, onUpdated, ref, watch } from 'vue'
import { groupMeta } from '@/utils/logGroups'
import {
  captureLogScroll,
  isLogAtBottom,
  logScrollEnd,
  restoreLogScroll,
  scrollLogToBottom
} from '@/utils/logScrolling'

const SCROLL_INPUT_GRACE_MS = 150
const scrollKeys = new Set(['ArrowUp', 'ArrowDown', 'PageUp', 'PageDown', 'Home', 'End', ' '])

export function useLogViewport(root, { autoScroll, renderInputs }) {
  const stickyGroup = ref(null)
  const showJumpToLatest = ref(false)
  let container = null
  let observer = null
  let stickyFrame = null
  let beforeUpdate = null
  let readingPosition = null
  let detailResize = null
  let scrollInputUntil = -Infinity
  let stopScrollbarDrag = null
  let disposed = false

  function updateStickyGroup() {
    const top = container?.getBoundingClientRect?.().top ?? 0
    const dividers = container?.querySelectorAll?.('.log-group[data-group]') ?? []
    let current = null
    for (const divider of dividers) {
      const bounds = divider.getBoundingClientRect()
      if (bounds.bottom > top + 1) {
        // 分隔线贴近正文顶部时由它交代分组，避免吸顶提示还在显示上一组。
        if (bounds.top <= top + bounds.height / 2) current = null
        break
      }
      current = divider.getAttribute('data-group')
    }
    stickyGroup.value = current ? (groupMeta(current)?.label ?? null) : null
  }

  function capturePosition() {
    return captureLogScroll(container)
  }

  function updateJumpVisibility() {
    showJumpToLatest.value = container !== null && !isLogAtBottom(container)
  }

  function noteScrollInput(event) {
    if (event?.type === 'wheel' && (!event.deltaY || event.ctrlKey || event.shiftKey)) return
    if (event?.type === 'keydown' && (event.defaultPrevented || !scrollKeys.has(event.key))) return
    scrollInputUntil = performance.now() + SCROLL_INPUT_GRACE_MS
  }

  function startScrollbarDrag(event) {
    if (event.button !== 0 || !event.target?.closest?.('.n-scrollbar-rail--vertical')) return
    const view = container?.ownerDocument?.defaultView
    if (!view) return
    stopScrollbarDrag?.()
    const finish = () => {
      noteScrollInput()
      stopScrollbarDrag()
    }
    view.addEventListener('mouseup', finish, true)
    view.addEventListener('blur', finish)
    stopScrollbarDrag = () => {
      view.removeEventListener('mouseup', finish, true)
      view.removeEventListener('blur', finish)
      stopScrollbarDrag = null
    }
  }

  function shouldHoldTail() {
    return (
      autoScroll() &&
      (detailResize?.snapshot ?? readingPosition)?.atBottom &&
      !stopScrollbarDrag &&
      performance.now() > scrollInputUntil
    )
  }

  function captureBeforeLayout() {
    const snapshot = capturePosition()
    if (snapshot && shouldHoldTail()) snapshot.atBottom = true
    return snapshot
  }

  function restorePosition(snapshot = readingPosition) {
    restoreLogScroll(container, detailResize?.snapshot ?? snapshot, autoScroll())
    if (detailResize) detailResize.scrollTop = container?.scrollTop ?? 0
    else readingPosition = capturePosition()
    updateJumpVisibility()
  }

  function handleScroll() {
    const position = container.scrollTop
    const atBottom = isLogAtBottom(container)
    if (atBottom && (detailResize?.snapshot ?? readingPosition)?.atBottom === false) {
      scrollInputUntil = -Infinity
    }
    if (shouldHoldTail() && !atBottom) {
      restorePosition()
    } else if (detailResize) {
      const max = logScrollEnd(container)
      if (Math.abs(position - Math.min(detailResize.scrollTop, max)) > 0.5) {
        readingPosition = detailResize.snapshot = capturePosition()
        detailResize.scrollTop = position
      }
    } else if (readingPosition?.scrollTop !== position) {
      readingPosition = capturePosition()
    }
    updateJumpVisibility()
    if (stickyFrame !== null) return
    const schedule = globalThis.requestAnimationFrame ?? ((callback) => setTimeout(callback, 16))
    stickyFrame = schedule(() => {
      stickyFrame = null
      updateStickyGroup()
    })
  }

  function detachContainer() {
    stopScrollbarDrag?.()
    scrollInputUntil = -Infinity
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
    updateJumpVisibility()
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

  function jumpToLatest() {
    beforeUpdate = null
    scrollInputUntil = -Infinity
    scrollLogToBottom(container)
    readingPosition = capturePosition()
    if (detailResize) {
      detailResize.snapshot = readingPosition
      detailResize.scrollTop = readingPosition?.scrollTop ?? 0
    }
    updateJumpVisibility()
    updateStickyGroup()
  }

  function preserveInventoryPosition() {
    const snapshot = captureBeforeLayout()
    nextTick(() => {
      if (disposed) return
      restoreLogScroll(container, snapshot, autoScroll())
      readingPosition = capturePosition()
      updateJumpVisibility()
      updateStickyGroup()
    })
  }

  function startDetailResize() {
    if (detailResize) return
    const snapshot = captureBeforeLayout()
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
      if (autoScroll()) jumpToLatest()
      else updateStickyGroup()
    })
  })
  watch(
    renderInputs,
    () => {
      if (!detailResize) beforeUpdate = captureBeforeLayout()
    },
    { deep: true, flush: 'pre' }
  )
  watch(autoScroll, (enabled, previous) => {
    if (!enabled || previous) return
    nextTick(() => {
      if (disposed) return
      bindContainer()
      jumpToLatest()
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
    showJumpToLatest,
    jumpToLatest,
    noteScrollInput,
    startScrollbarDrag,
    preserveInventoryPosition,
    startDetailResize,
    updateDetailResize,
    finishDetailResize,
    interruptDetailResize
  }
}
