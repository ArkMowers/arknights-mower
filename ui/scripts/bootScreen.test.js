import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { runInNewContext } from 'node:vm'
import { describe, expect, it, vi } from 'vitest'
import { BOOT_SCREEN_PLACEHOLDER, bootScreen, injectBootScreen } from './bootScreen.js'

const root = resolve(import.meta.dirname, '..')

describe('startup screen injection', () => {
  it('fills the placeholder in the interface and offline preview pages', async () => {
    const plugin = bootScreen(resolve(root, 'src/boot/boot-screen.html'))
    for (const page of ['index.html', 'preview/index.html']) {
      const html = readFileSync(resolve(root, page), 'utf8')
      expect(html).toContain(BOOT_SCREEN_PLACEHOLDER)
      const output = await plugin.transformIndexHtml.handler(html)
      expect(output).not.toContain(BOOT_SCREEN_PLACEHOLDER)
      expect(output).toContain('id="mower-boot"')
      // 启动画面在界面脚本之前，脚本载入前就能画出来。
      expect(output.indexOf('id="mower-boot"')).toBeLessThan(output.indexOf('type="module"'))
    }
  })

  it('draws an interface skeleton with a hidden loading label and the failure controls', () => {
    const screen = readFileSync(resolve(root, 'src/boot/boot-screen.html'), 'utf8')
    const markup = screen.slice(screen.indexOf('<div id="mower-boot"'))
    const skeletonStart = markup.indexOf('<div class="mower-boot__skeleton" aria-hidden="true">')
    const statusStart = markup.indexOf('<div class="mower-boot__below"')
    // 骨架只是占位，读屏软件只读到它后面的说明和失败提示。
    expect(skeletonStart).toBeGreaterThan(0)
    expect(statusStart).toBeGreaterThan(skeletonStart)
    const skeleton = markup.slice(skeletonStart, statusStart)
    for (const part of ['sider', 'tabs']) {
      expect(skeleton).toContain(`class="mower-boot__${part}"`)
    }
    // 内容区只留底色，不画日志行、按钮或卡片，页面自己的内容在启动画面淡出后出现。
    expect(skeleton).toContain('<div class="mower-boot__content"></div>')
    for (const part of ['log', 'line', 'actions', 'options', 'page', 'card']) {
      expect(skeleton).not.toContain(`mower-boot__${part}`)
    }
    // 载入过程中没有看得见的进度说明，失败时才显示原因和重新加载按钮。
    const status = markup.slice(statusStart)
    expect(status).toContain('<span class="mower-boot__label">正在载入界面</span>')
    expect(status).not.toContain('data-boot-text')
    expect(status).toContain('<p class="mower-boot__message" data-boot-error></p>')
    expect(status).toMatch(/<button type="button" class="mower-boot__retry" data-boot-retry>/)
  })

  it('offers a working reload when the entry module cannot load', () => {
    const markup = readFileSync(resolve(root, 'src/boot/boot-screen.html'), 'utf8')
    const { Event, EventTarget, URLSearchParams } = globalThis
    const retry = new EventTarget()
    const reason = { textContent: '' }
    const screen = {
      querySelector: (selector) => (selector === '[data-boot-retry]' ? retry : reason),
      classList: { add: vi.fn() },
      setAttribute: vi.fn()
    }
    const window = { addEventListener: vi.fn(), removeEventListener: vi.fn() }
    const location = { search: '', reload: vi.fn() }
    const document = { documentElement: { dataset: {} }, getElementById: () => screen }
    for (const [, script] of markup.matchAll(/<script>([\s\S]*?)<\/script>/g)) {
      runInNewContext(script, { document, window, location, URLSearchParams })
    }
    const onError = window.addEventListener.mock.calls.find(([name]) => name === 'error')[1]
    onError({ target: { matches: () => false } })
    expect(reason.textContent).toBe('')
    onError({ target: { matches: (selector) => selector === 'script[type="module"][src]' } })
    expect(reason.textContent).toContain('界面脚本加载失败')
    expect(screen.classList.add).toHaveBeenCalledWith('mower-boot--failed')
    expect(screen.setAttribute).toHaveBeenCalledWith('aria-busy', 'false')
    retry.dispatchEvent(new Event('click'))
    expect(location.reload).toHaveBeenCalledOnce()
  })

  it('leaves pages without the placeholder unchanged', async () => {
    const plugin = bootScreen(resolve(root, 'src/boot/boot-screen.html'))
    const html = '<body><div id="app"></div></body>'
    expect(await plugin.transformIndexHtml.handler(html)).toBe(html)
    expect(injectBootScreen(html, '<div></div>')).toBe(html)
  })

  it('inserts the screen literally', () => {
    expect(injectBootScreen(`a${BOOT_SCREEN_PLACEHOLDER}b`, ' $& ')).toBe('a$&b')
  })
})
