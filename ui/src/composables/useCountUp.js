import { onScopeDispose, ref, watch } from 'vue'

function prefersReducedMotion() {
  return Boolean(globalThis.matchMedia?.('(prefers-reduced-motion: reduce)').matches)
}

/**
 * 数值变化时从旧值（首次为 0）平滑过渡到新值；非数值直接透传。
 * 不支持动画（SSR、无 requestAnimationFrame 或用户偏好减少动态效果）时立即显示终值。
 */
export function useCountUp(source, duration = 700) {
  const display = ref(source.value)
  let frame = 0

  function stop() {
    if (frame) globalThis.cancelAnimationFrame?.(frame)
    frame = 0
  }

  watch(
    source,
    (target) => {
      stop()
      // 首次得到数值时从 0 开始过渡。
      const from = Number.isFinite(display.value) ? display.value : 0
      const animate =
        Number.isFinite(target) &&
        typeof globalThis.requestAnimationFrame === 'function' &&
        !prefersReducedMotion()
      if (!animate) {
        display.value = target
        return
      }
      const start = globalThis.performance?.now?.() ?? Date.now()
      const step = (now) => {
        const progress = Math.min(1, (now - start) / duration)
        const eased = 1 - Math.pow(1 - progress, 3)
        display.value = progress >= 1 ? target : from + (target - from) * eased
        frame = progress >= 1 ? 0 : globalThis.requestAnimationFrame(step)
      }
      frame = globalThis.requestAnimationFrame(step)
    },
    { flush: 'sync' }
  )

  onScopeDispose(stop)
  return display
}
