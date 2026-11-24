import { ref } from 'vue'

// 启动画面：页面在 index.html 里先画出与主题一致、与界面布局相同的骨架屏，脚本、配置、
// 运行日志和背景图都准备好以后再整体淡出，避免用户看到界面分几次拼出来。
// 每个仍在准备的部分持有一个占用；占用全部释放后的下一帧淡出。读取配置失败时
// 画面改为显示原因和重新加载按钮，不淡出成一片空白。

export const BOOT_SCREEN_ID = 'mower-boot'
// 页面自己的占用（例如运行日志等背景图）最多等这么久，超时后照常淡出。
export const BOOT_PAGE_LIMIT = 4000
export const BOOT_LEAVE_DURATION = 360
export const BOOT_FRAME_FALLBACK = 200

export function createBootScreen({
  element = null,
  windowObject = globalThis.window,
  documentObject = globalThis.document
} = {}) {
  const active = Boolean(element)
  const revealed = ref(!active)
  const holds = new Set(active ? ['app'] : [])
  let scheduled = false
  let failed = false
  let pageTimer

  function reveal() {
    scheduled = false
    if (revealed.value || failed || holds.size) return
    revealed.value = true
    clearTimeout(pageTimer)
    if (documentObject?.hidden) {
      element.remove()
      return
    }
    element.classList.add('mower-boot--leaving')
    element.setAttribute('aria-busy', 'false')
    setTimeout(() => element.remove(), BOOT_LEAVE_DURATION + 60)
  }

  function schedule() {
    if (scheduled || revealed.value || failed || holds.size) return
    scheduled = true
    // 等界面在启动画面下面画完一帧再淡出；窗口隐藏时浏览器不推进动画帧，直接移除。
    // 窗口被遮挡时动画帧也可能暂停，由计时器兜底，启动画面不会因此一直不淡出。
    const frame = windowObject?.requestAnimationFrame
    if (documentObject?.hidden || typeof frame !== 'function') {
      reveal()
      return
    }
    const fallback = setTimeout(reveal, BOOT_FRAME_FALLBACK)
    frame(() =>
      frame(() => {
        clearTimeout(fallback)
        reveal()
      })
    )
  }

  function hold(key) {
    if (revealed.value || failed) return () => {}
    holds.add(key)
    if (key !== 'app' && pageTimer === undefined) {
      pageTimer = setTimeout(() => {
        for (const name of [...holds]) if (name !== 'app') holds.delete(name)
        schedule()
      }, BOOT_PAGE_LIMIT)
    }
    return () => release(key)
  }

  function release(key) {
    if (!holds.delete(key)) return
    schedule()
  }

  function fail(message) {
    if (revealed.value || failed) return
    failed = true
    clearTimeout(pageTimer)
    const reason = element.querySelector('[data-boot-error]')
    if (reason) reason.textContent = message
    element.classList.add('mower-boot--failed')
    element.setAttribute('aria-busy', 'false')
  }

  return { active, revealed, hold, release, fail }
}

const bootScreen = createBootScreen({
  element: globalThis.document?.getElementById?.(BOOT_SCREEN_ID) ?? null
})

export const bootScreenActive = bootScreen.active
export const bootRevealed = bootScreen.revealed
export const holdBoot = bootScreen.hold
export const releaseBoot = bootScreen.release
export const failBoot = bootScreen.fail
