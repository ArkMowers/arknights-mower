export const WAIT_DISPLAY_DELAY = 1200

// 只有这些场景代表“还在切换/加载”，此时的日志沉默才值得显示等待指示。
// 9 CONNECTING（正在提交反馈至神经）、9998 LOADING（场景跳转时的等待界面）、
// -1 UNKNOWN（识别不到画面，通常也在黑屏或转场）。
export const WAIT_SCENES = new Set([9, 9998, -1])

const SCENE = /Scene:?\s+(-?\d+):\s*(.*)$/u

export function matchScene(text) {
  const match = SCENE.exec(String(text ?? ''))
  if (!match) return null
  return { scene: Number(match[1]), comment: (match[2] ?? '').trim() }
}

// 一条等待场景行开启一次等待，直到出现场景号不同的下一条场景行。
// 等待中的“使用联网等待补偿”“场景图导航”等非场景行不结束等待。
export function scanSceneWaits(lines) {
  const durations = new Map()
  let active = null
  for (let index = 0; index < lines.length; index += 1) {
    const scene = matchScene(lines[index].text)
    if (!scene) continue
    const at = Number.isFinite(lines[index].at) ? lines[index].at : null
    if (active && scene.scene !== active.scene) {
      if (active.at !== null && at !== null && at - active.at >= WAIT_DISPLAY_DELAY) {
        durations.set(active.index, at - active.at)
      }
      active = null
    }
    if (!active && WAIT_SCENES.has(scene.scene)) {
      active = { index, scene: scene.scene, comment: scene.comment, at }
    }
  }
  return { durations, active }
}

// 等待时长用一条固定小数位、等宽数字的短格式，避免宽度跳动。
export function formatWaitDuration(ms) {
  const elapsed = Math.max(0, ms) / 1000
  const tenths = Math.round(elapsed * 10)
  if (tenths < 600) return `${(tenths / 10).toFixed(1)}s`
  const seconds = Math.round(elapsed)
  return `${Math.floor(seconds / 60)}分${seconds % 60}秒`
}
