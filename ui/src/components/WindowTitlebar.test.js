import { createSSRApp, h } from 'vue'
import { renderToString } from '@vue/server-renderer'
import { describe, expect, it, vi } from 'vitest'
import WindowTitlebar from './WindowTitlebar.vue'

async function renderTitlebar(nativeControls) {
  return renderToString(
    createSSRApp({
      render: () =>
        h(WindowTitlebar, {
          active: true,
          title: 'Mower',
          version: 'alpha',
          instanceName: '默认实例',
          theme: 'light',
          controlSide: nativeControls ? 'start' : 'end',
          maximized: false,
          controls: ['minimize', 'maximize', 'close'].map((id) => ({ id, icon: id, label: id })),
          busy: {},
          resizable: false,
          nativeControls,
          onControl: vi.fn(),
          onToggleMaximize: vi.fn(),
          onResize: vi.fn(),
          onMove: vi.fn()
        })
    })
  )
}

describe('desktop title bar controls', () => {
  it('leaves the Cocoa traffic lights outside draggable HTML and omits duplicate buttons', async () => {
    const html = await renderTitlebar(true)
    expect(html).toContain('window-titlebar__native-controls')
    expect(html.indexOf('window-titlebar__native-controls')).toBeLessThan(
      html.indexOf('data-window-drag-region')
    )
    expect(html).not.toContain('<button')
  })

  it('keeps the three HTML window controls for GTK, Qt and WinForms', async () => {
    const html = await renderTitlebar(false)
    expect(html).not.toContain('window-titlebar__native-controls')
    expect(html.match(/<button/g)).toHaveLength(3)
    expect(html).toContain('data-window-control="close"')
  })
})
