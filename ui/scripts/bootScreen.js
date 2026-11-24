import { readFile } from 'node:fs/promises'

// 启动画面写在 src/boot/boot-screen.html，构建和开发服务器把它填进页面里的占位注释，
// 使界面页和离线预览页共用同一份，并在脚本载入前就画出来。
export const BOOT_SCREEN_PLACEHOLDER = '<!-- mower-boot-screen -->'

export function injectBootScreen(html, screen) {
  return html.includes(BOOT_SCREEN_PLACEHOLDER)
    ? html.replace(BOOT_SCREEN_PLACEHOLDER, () => screen.trim())
    : html
}

export function bootScreen(screenPath) {
  return {
    name: 'mower-boot-screen',
    transformIndexHtml: {
      // 在 Vite 处理页面里的资源地址之前填入，标志图片的地址照常按 base 改写。
      order: 'pre',
      async handler(html) {
        if (!html.includes(BOOT_SCREEN_PLACEHOLDER)) return html
        return injectBootScreen(html, await readFile(screenPath, 'utf8'))
      }
    }
  }
}
