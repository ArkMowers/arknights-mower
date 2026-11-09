import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { effectScope, nextTick, onMounted, reactive } from 'vue'
import { routeLocationKey } from 'vue-router'
import axios from 'axios'
import {
  BlobReader,
  BlobWriter,
  TextReader,
  TextWriter,
  ZipReader,
  ZipWriter
} from '@zip.js/zip.js'

import LogSchedule from './LogSchedule.vue'

const state = vi.hoisted(() => ({ client: null, route: null }))
vi.mock('vue', async (original) => ({
  ...(await original()),
  useSSRContext: () => ({ modules: new Set() }),
  inject: (key) => (key === routeLocationKey ? state.route : state.client),
  onMounted: vi.fn(),
  onUnmounted: vi.fn()
}))

const row = (summary, level = 'INFO') => ({
  time: '2026-10-10 12:00:00',
  message: `2026-10-10 12:00:00,123 utils/task.py:42 ${level} run: ${summary}`,
  screenshot: null
})
const event = {
  id: '123',
  time_ns: new Date('2026-10-10T12:00:00').getTime() * 1e6,
  message: '失败',
  screenshots: ['errors/123/123.jpg']
}
const deferred = () => {
  let resolve, reject
  const promise = new Promise((yes, no) => {
    resolve = yes
    reject = no
  })
  return { promise, resolve, reject }
}

describe('authenticated diagnostic screenshots', () => {
  let scope, page, requests, fetchImage, createUrl, revokeUrl

  beforeEach(() => {
    requests = []
    fetchImage = vi.fn().mockResolvedValue(new Blob(['synthetic image'], { type: 'image/jpeg' }))
    state.client = axios.create({
      headers: { token: 'image-fixture-token' },
      adapter: async (request) => {
        requests.push(request)
        const data = request.url.startsWith('/screenshots/')
          ? await fetchImage(request)
          : request.url.endsWith('/diagnostics/errors')
            ? { events: [] }
            : { logs: [], screenshots: ['first.jpg', 'second.jpg'] }
        return { data, status: 200, headers: {}, config: request }
      }
    })
    createUrl = vi.spyOn(URL, 'createObjectURL').mockReturnValue('blob:first')
    revokeUrl = vi.spyOn(URL, 'revokeObjectURL').mockImplementation(() => {})
    scope = effectScope()
    page = scope.run(() => LogSchedule.setup({}, { expose: vi.fn() }))
  })

  afterEach(() => {
    scope.stop()
    vi.restoreAllMocks()
  })

  it('loads image blobs with the instance token and releases them after navigation and unmount', async () => {
    scope.run(() => onMounted.mock.calls.at(-1)[0]())
    await vi.waitFor(() => expect(page.imageUrl.value).toBe('blob:first'))
    const first = requests.find((request) => request.url === '/screenshots/first.jpg')
    expect(first.headers.get('token')).toBe('image-fixture-token')
    expect(first.responseType).toBe('blob')
    expect(first.timeout).toBe(10000)
    createUrl.mockReturnValue('blob:second')
    page.moveImage(1)
    await vi.waitFor(() => expect(page.imageUrl.value).toBe('blob:second'))
    expect(first.signal.aborted).toBe(true)
    expect(revokeUrl).toHaveBeenCalledWith('blob:first')
    const second = requests.find((request) => request.url === '/screenshots/second.jpg')
    expect(second.headers.get('token')).toBe('image-fixture-token')
    scope.stop()
    expect(second.signal.aborted).toBe(true)
    expect(revokeUrl).toHaveBeenCalledWith('blob:second')
  })

  it('does not display a response for a screenshot that has already been replaced', async () => {
    const pending = deferred()
    fetchImage.mockReturnValueOnce(pending.promise)
    scope.run(() => onMounted.mock.calls.at(-1)[0]())
    await vi.waitFor(() => expect(fetchImage).toHaveBeenCalledOnce())
    const first = requests.find((request) => request.url === '/screenshots/first.jpg')
    createUrl.mockReturnValue('blob:second')
    page.moveImage(1)
    await vi.waitFor(() => expect(page.imageUrl.value).toBe('blob:second'))
    expect(first.signal.aborted).toBe(true)
    pending.resolve(new Blob(['old image']))
    await nextTick()
    await Promise.resolve()
    expect(page.imageUrl.value).toBe('blob:second')
    expect(createUrl).toHaveBeenCalledOnce()
    expect(page.imageFailed.value).toBe(false)
  })

  it('shows the existing failure state when the authenticated image request fails', async () => {
    fetchImage.mockRejectedValueOnce(new Error('synthetic request failure'))
    scope.run(() => onMounted.mock.calls.at(-1)[0]())
    await vi.waitFor(() => expect(page.imageFailed.value).toBe(true))
    expect(page.imageUrl.value).toBe('')
    expect(createUrl).not.toHaveBeenCalled()
  })

  it('triggers the in-app image preview when opening original image', () => {
    const click = vi.fn()
    page.shotImage.value = { click }
    page.openImagePreview()
    expect(click).toHaveBeenCalledOnce()
  })
})

async function archiveBundle(message, withScreenshots = true) {
  const writer = new ZipWriter(new BlobWriter('application/zip'), { useWebWorkers: false })
  await writer.add('runtime.log', new TextReader(message))
  if (withScreenshots) await writer.add('screenshots/frame.jpg', new TextReader('frame'))
  await writer.add('readme.txt', new TextReader('Diagnostic logs and current saved plan'))
  await writer.add('plan.json', new TextReader('{"plan1":{}}'))
  return writer.close()
}

describe('log schedule browsing', () => {
  let scope, page
  beforeEach(() => {
    vi.spyOn(Date, 'now').mockReturnValue(new Date('2026-10-11T00:00:00Z').getTime())
    state.client = { get: vi.fn(), post: vi.fn(), delete: vi.fn() }
    scope = effectScope()
    page = scope.run(() => LogSchedule.setup({}, { expose: vi.fn() }))
  })
  afterEach(() => {
    scope.stop()
    state.route = null
    vi.restoreAllMocks()
    vi.unstubAllGlobals()
  })

  it('loads a linked timestamp and the nearest retained screenshot without using the server display time', async () => {
    const firstAt = new Date('2026-10-10T13:00:00Z').getTime()
    const nextAt = firstAt + 2000
    const firstImage = `${BigInt(firstAt - 500) * 1000000n}.jpg`
    const nextImage = `${BigInt(nextAt + 200) * 1000000n}.jpg`
    state.route = reactive({ name: 'log_schedule', query: { at: String(firstAt) } })
    state.client.get.mockImplementation(async (url) => {
      if (url.endsWith('/diagnostics/errors')) return { data: { events: [] } }
      if (url.includes('/screenshots/')) return { data: new Blob(['frame']) }
      return {
        data: { logs: [row('日志时间使用服务端时区')], screenshots: [firstImage, nextImage] }
      }
    })
    scope.stop()
    scope = effectScope()
    page = scope.run(() => LogSchedule.setup({}, { expose: vi.fn() }))
    scope.run(() => onMounted.mock.calls.at(-1)[0]())

    await vi.waitFor(() => expect(page.imagePath.value).toBe(firstImage))
    expect(page.queryAt.value).toBe(firstAt)
    expect(page.imageCaption.value).toContain('所选时间附近的截图')
    expect(state.client.get).toHaveBeenCalledWith('/diagnostics/timeline', {
      params: { at: firstAt }
    })

    state.route.query.at = String(nextAt)
    await vi.waitFor(() => expect(page.imagePath.value).toBe(nextImage))
    expect(page.loadedAt.value).toBe(nextAt)

    state.route.query.at = [String(firstAt), String(nextAt)]
    await vi.waitFor(() => expect(page.loadedAt.value).toBe(Date.now()))
  })

  it('parses the file formatter and filters CRITICAL without losing traceback details', () => {
    page.logs.value = [
      row('正常'),
      {
        ...row('失败', 'CRITICAL'),
        message: row('失败', 'CRITICAL').message + '\nTraceback\n  ValueError: bad'
      }
    ]
    expect(page.visibleLogs.value.map((item) => item.summary)).toEqual(['正常', '失败'])
    page.levelFilter.value = 'CRITICAL'
    expect(page.visibleLogs.value).toHaveLength(1)
    expect(page.visibleLogs.value[0].detail).toBe('Traceback\n  ValueError: bad')
  })

  it.each(['jpg', 'png'])(
    'browses %s screenshots even when no log row links to a frame',
    async (suffix) => {
      const center = new Date('2026-10-10T12:00:00').getTime()
      const shots = [-90, 2, 60].map(
        (seconds) => `20261010-12/${(center + seconds * 1000) * 1e6}.${suffix}`
      )
      state.client.get.mockResolvedValue({
        data: { logs: [row('运行')], screenshots: shots, truncated: true }
      })
      await page.loadWindow(center)
      expect(page.screenshots.value).toEqual(shots)
      expect(page.imageIndex.value).toBe(1)
      expect(page.imagePath.value).toBe(shots[1])
      expect(page.imageTime(shots[1])).toBe(page.formatTime((center + 2000) * 1e6))
      expect(page.truncated.value).toBe(true)
      page.moveImage(1)
      expect(page.imagePath.value).toBe(shots[2])
      page.showScreenshot(shots[0])
      expect(page.imageIndex.value).toBe(0)
      expect(page.imageFailed.value).toBe(false)
    }
  )

  it('moves contiguous windows from the loaded center and restores time browsing after an archive', async () => {
    const center = new Date('2026-10-10T12:00:00').getTime()
    state.client.get.mockResolvedValue({ data: { logs: [], screenshots: [] } })
    await page.loadWindow(center)
    page.queryAt.value = center - 3600000
    await page.moveWindow(-1)
    expect(page.loadedAt.value).toBe(center - 600000)
    expect(state.client.get.mock.calls.at(-1)[1].params.at).toBe(center - 600000)
    page.events.value = [event]
    await page.setBrowseMode('archives')
    expect(page.activeEventId.value).toBe(event.id)
    expect(page.screenshots.value).toEqual(event.screenshots)
    await page.setBrowseMode('time')
    expect(page.activeEventId.value).toBe('')
    expect(page.loadedAt.value).toBe(center - 600000)
    expect(page.screenshots.value).toEqual([])
  })

  it('uses the loaded center for export while the date picker has an unsubmitted edit', async () => {
    const center = 1791604800000
    state.client.get.mockResolvedValue({ data: { logs: [], screenshots: [] } })
    await page.loadWindow(center)
    page.queryAt.value = center - 86400000
    page.beginExport()
    expect(page.showExportDialog.value).toBe(true)
    expect(page.exportRange.value).toEqual([center - 3600000, center + 300000])
    const link = { click: vi.fn(), remove: vi.fn() }
    vi.stubGlobal('document', { createElement: () => link, body: { appendChild: vi.fn() } })
    vi.stubGlobal('URL', { createObjectURL: () => 'blob:test', revokeObjectURL: vi.fn() })
    await page.exportWindow()
    expect(state.client.get.mock.calls.at(-1)).toEqual([
      '/diagnostics/export',
      {
        params: { at: center, start: center - 3600000, end: center + 300000, screenshots: '1' },
        responseType: 'blob'
      }
    ])
    expect(link.click).toHaveBeenCalledOnce()
    expect(link.download).toMatch(/^logs-\d{8}-\d{6}\.zip$/)
    expect(page.showExportDialog.value).toBe(false)
  })

  it('exports a custom interval without screenshots after choosing a longer preset', async () => {
    const center = 1791604800000
    state.client.get.mockResolvedValue({ data: { logs: [] } })
    await page.loadWindow(center)
    page.beginExport()
    page.queryAt.value = center - 86400000
    page.setExportHours(24)
    expect(page.exportRange.value).toEqual([center - 86400000, center + 300000])
    page.exportRange.value = [center - 7200000, center - 600000]
    page.includeScreenshots.value = false
    const link = { click: vi.fn(), remove: vi.fn() }
    vi.stubGlobal('document', { createElement: () => link, body: { appendChild: vi.fn() } })
    vi.stubGlobal('URL', { createObjectURL: () => 'blob:test', revokeObjectURL: vi.fn() })
    await page.exportWindow()
    expect(state.client.get.mock.calls.at(-1)).toEqual([
      '/diagnostics/export',
      {
        params: { at: center, start: center - 7200000, end: center - 600000, screenshots: '0' },
        responseType: 'blob'
      }
    ])
  })

  it('blocks invalid or oversized ranges and closes a draft when changing source', async () => {
    const center = 1791604800000
    state.client.get.mockResolvedValue({ data: { logs: [] } })
    await page.loadWindow(center)
    page.beginExport()
    for (const range of [
      null,
      [center, center],
      [center, center - 1],
      [center - 8 * 86400000, center]
    ]) {
      page.exportRange.value = range
      expect(page.exportRangeError.value).toBeTruthy()
      const count = state.client.get.mock.calls.length
      await page.exportWindow()
      expect(state.client.get).toHaveBeenCalledTimes(count)
    }
    await page.loadWindow(center - 600000)
    expect(page.showExportDialog.value).toBe(false)
  })

  it('keeps archive export on its saved bounds without ordinary range parameters', async () => {
    page.events.value = [event]
    state.client.get.mockResolvedValue({ data: { logs: [] } })
    await page.selectEvent(event)
    const link = { click: vi.fn(), remove: vi.fn() }
    vi.stubGlobal('document', { createElement: () => link, body: { appendChild: vi.fn() } })
    vi.stubGlobal('URL', { createObjectURL: () => 'blob:test', revokeObjectURL: vi.fn() })
    await page.beginExport()
    expect(state.client.get.mock.calls.at(-1)).toEqual([
      '/diagnostics/errors/123/export',
      { params: { screenshots: '1' }, responseType: 'blob' }
    ])
    expect(page.showExportDialog.value).toBe(false)
    expect(link.click).toHaveBeenCalledOnce()
    expect(link.download).toBe('error-archive-123.zip')
  })

  it('opens the text export with screenshots off and resets the choice for a full export', async () => {
    const center = 1791604800000
    state.client.get.mockResolvedValue({ data: { logs: [] } })
    await page.loadWindow(center)
    page.beginExport(false)
    expect(page.showExportDialog.value).toBe(true)
    expect(page.includeScreenshots.value).toBe(false)
    const link = { click: vi.fn(), remove: vi.fn() }
    vi.stubGlobal('document', { createElement: () => link, body: { appendChild: vi.fn() } })
    vi.stubGlobal('URL', { createObjectURL: () => 'blob:test', revokeObjectURL: vi.fn() })
    await page.exportWindow()
    expect(state.client.get.mock.calls.at(-1)).toEqual([
      '/diagnostics/export',
      {
        params: { at: center, start: center - 3600000, end: center + 300000, screenshots: '0' },
        responseType: 'blob'
      }
    ])
    expect(link.click).toHaveBeenCalledOnce()
    page.beginExport(true)
    expect(page.includeScreenshots.value).toBe(true)
  })

  it.each([true, false])(
    'downloads one checked archive directly with screenshots=%s',
    async (withScreenshots) => {
      page.events.value = [event, { ...event, id: '456' }]
      page.toggleEvent('123', true)
      const bundle = await archiveBundle('archive 123', withScreenshots)
      const pending = deferred()
      state.client.get.mockReturnValueOnce(pending.promise)
      const link = { click: vi.fn(), remove: vi.fn() }
      const createUrl = vi.fn(() => 'blob:test')
      vi.stubGlobal('document', { createElement: () => link, body: { appendChild: vi.fn() } })
      vi.stubGlobal('URL', { createObjectURL: createUrl, revokeObjectURL: vi.fn() })
      const exporting = page.exportSelected(withScreenshots)
      await page.exportSelected(withScreenshots)
      page.toggleEvent('456', true)
      page.confirmDeleteSelected()
      expect(page.pendingDeleteEvents.value).toBe(null)
      expect(page.selectedEventIds.value).toEqual(['123'])
      pending.resolve({ data: bundle })
      await exporting
      expect(state.client.get.mock.calls).toEqual([
        [
          '/diagnostics/errors/123/export',
          { params: { screenshots: withScreenshots ? '1' : '0' }, responseType: 'blob' }
        ]
      ])
      expect(link.click).toHaveBeenCalledOnce()
      expect(createUrl.mock.calls[0][0]).toBe(bundle)
      expect(link.download).toBe('error-archive-123.zip')
      const reader = new ZipReader(new BlobReader(createUrl.mock.calls[0][0]), {
        useWebWorkers: false
      })
      try {
        const entries = await reader.getEntries()
        expect(entries.map((entry) => entry.filename)).toEqual([
          'runtime.log',
          ...(withScreenshots ? ['screenshots/frame.jpg'] : []),
          'readme.txt',
          'plan.json'
        ])
        expect(await entries[0].getData(new TextWriter())).toBe('archive 123')
        expect(await entries.at(-1).getData(new TextWriter())).toBe('{"plan1":{}}')
      } finally {
        await reader.close()
      }
      expect(page.exporting.value).toBe(false)
    }
  )

  it('ignores a superseded archive response and its loading state', async () => {
    const archiveRequest = deferred(),
      windowRequest = deferred()
    state.client.get
      .mockReturnValueOnce(archiveRequest.promise)
      .mockReturnValueOnce(windowRequest.promise)
    page.events.value = [event]
    const older = page.selectEvent(event)
    const newer = page.loadWindow(1791604800000)
    archiveRequest.resolve({ data: { logs: [row('旧归档')] } })
    await older
    expect(page.logs.value).toEqual([])
    expect(page.logLoading.value).toBe(true)
    windowRequest.resolve({ data: { logs: [row('新窗口')], screenshots: ['new.jpg'] } })
    await newer
    expect(page.logs.value[0].message).toContain('新窗口')
    expect(page.imagePath.value).toBe('new.jpg')
    expect(page.activeEventId.value).toBe('')
  })

  it('clears old evidence on a failed source change and blocks export until a successful retry', async () => {
    state.client.get.mockResolvedValueOnce({
      data: { logs: [row('旧窗口')], screenshots: ['old.jpg'] }
    })
    await page.loadWindow(1791604800000)
    state.client.get.mockRejectedValueOnce(new Error('unavailable'))
    await page.selectEvent(event)
    expect(page.logs.value).toEqual([])
    expect(page.imagePath.value).toBe('')
    expect(page.logError.value).toBeTruthy()
    expect(page.canExport.value).toBe(false)
    state.client.get.mockResolvedValueOnce({ data: { logs: [row('恢复')] } })
    page.events.value = [event]
    await page.refreshLogs()
    expect(page.canExport.value).toBe(true)
    expect(page.logs.value[0].message).toContain('恢复')
  })

  it('invalidates pending time requests when opening an empty archive tab', async () => {
    const request = deferred()
    state.client.get.mockReturnValueOnce(request.promise)
    const pending = page.loadWindow(1791604800000)
    await page.setBrowseMode('archives')
    request.resolve({ data: { logs: [row('过期')], screenshots: ['old.jpg'] } })
    await pending
    expect(page.logs.value).toEqual([])
    expect(page.imagePath.value).toBe('')
    expect(page.logLoading.value).toBe(false)
    expect(page.canExport.value).toBe(false)
  })

  it('selects an archive when its list arrives after opening the archive tab', async () => {
    const request = deferred()
    state.client.get.mockReturnValueOnce(request.promise)
    const pending = page.loadEvents()
    await page.setBrowseMode('archives')
    state.client.get.mockResolvedValueOnce({ data: { logs: [row('归档日志')] } })
    request.resolve({ data: { events: [event] } })
    await pending
    await vi.waitFor(() => expect(page.logs.value).toHaveLength(1))
    expect(page.activeEventId.value).toBe(event.id)
    expect(page.screenshots.value).toEqual(event.screenshots)
  })

  it('clears evidence when refreshing a list whose selected archive has expired', async () => {
    page.events.value = [event]
    state.client.get.mockResolvedValueOnce({ data: { logs: [row('旧归档')] } })
    await page.selectEvent(event)
    state.client.get.mockResolvedValueOnce({ data: { events: [] } })
    await page.loadEvents()
    expect(page.logs.value).toEqual([])
    expect(page.imagePath.value).toBe('')
    expect(page.canExport.value).toBe(false)
  })

  it('deletes the final archive without exposing another source or late data', async () => {
    page.events.value = [event]
    state.client.get.mockResolvedValueOnce({ data: { logs: [row('已删除')] } })
    await page.selectEvent(event)
    page.toggleEvent(event.id, true)
    page.confirmDeleteSelected()
    state.client.delete.mockResolvedValueOnce({})
    await page.deleteEvent()
    expect(page.events.value).toEqual([])
    expect(page.logs.value).toEqual([])
    expect(page.imagePath.value).toBe('')
    expect(page.browseMode.value).toBe('archives')
    expect(page.canExport.value).toBe(false)
  })

  it('requires confirmation and keeps empty or cancelled batches unchanged', async () => {
    page.confirmDeleteSelected()
    await page.deleteEvent()
    expect(state.client.delete).not.toHaveBeenCalled()
    page.events.value = [event]
    page.toggleAllEvents(true)
    page.confirmDeleteSelected()
    expect(page.pendingDeleteEvents.value).toEqual([event])
    expect(state.client.delete).not.toHaveBeenCalled()
    page.handleDeleteModal(false)
    await page.deleteEvent()
    expect(page.events.value).toEqual([event])
    expect(state.client.delete).not.toHaveBeenCalled()
  })

  it('deletes the confirmed snapshot and clears late evidence while retaining new archives', async () => {
    const second = { ...event, id: '456' }
    const fresh = { ...event, id: '789', screenshots: [] }
    const oldLogs = deferred()
    page.events.value = [event, second]
    page.toggleAllEvents(true)
    state.client.get.mockReturnValueOnce(oldLogs.promise)
    const old = page.selectEvent(event)
    page.confirmDeleteSelected()
    page.events.value.push(fresh)
    state.client.get.mockResolvedValueOnce({ data: { logs: [row('新归档')] } })
    state.client.delete.mockResolvedValue({})
    await page.deleteEvent()
    oldLogs.resolve({ data: { logs: [row('已删除的归档')] } })
    await old
    expect(state.client.delete.mock.calls).toEqual([
      ['/diagnostics/errors/123', { headers: { 'X-Mower-Diagnostics': '1' } }],
      ['/diagnostics/errors/456', { headers: { 'X-Mower-Diagnostics': '1' } }]
    ])
    expect(page.events.value).toEqual([fresh])
    expect(page.activeEventId.value).toBe(fresh.id)
    expect(page.logs.value[0].message).toContain('新归档')
    expect(page.pendingDeleteEvents.value).toBe(null)
  })

  it('retains failed archives and retries only the failed confirmation targets', async () => {
    const failed = { ...event, id: '456' }
    const fresh = { ...event, id: '789' }
    page.events.value = [event, failed]
    page.toggleAllEvents(true)
    page.confirmDeleteSelected()
    state.client.delete
      .mockResolvedValueOnce({})
      .mockRejectedValueOnce({ response: { status: 403 } })
      .mockResolvedValueOnce({})
    await page.deleteEvent()
    expect(page.events.value).toEqual([failed])
    expect(page.pendingDeleteEvents.value).toEqual([failed])
    expect(page.deleteError.value).toContain('已删除 1 条归档，1 条删除失败')
    page.events.value.push(fresh)
    await page.deleteEvent()
    expect(state.client.delete.mock.calls.map(([url]) => url)).toEqual([
      '/diagnostics/errors/123',
      '/diagnostics/errors/456',
      '/diagnostics/errors/456'
    ])
    expect(page.events.value).toEqual([fresh])
    expect(page.deleteError.value).toBe('')
    expect(page.pendingDeleteEvents.value).toBe(null)
  })

  it('selects all, clears all, and deletes only checked archives', async () => {
    const second = { ...event, id: '456' }
    page.events.value = [event, second]
    page.toggleAllEvents(true)
    expect(page.allEventsSelected.value).toBe(true)
    page.toggleAllEvents(false)
    expect(page.selectedEvents.value).toEqual([])
    page.toggleEvent(second.id, true)
    expect(page.allEventsSelected.value).toBe(false)
    expect(page.selectedEvents.value).toEqual([second])
    page.confirmDeleteSelected()
    state.client.delete.mockResolvedValue({})
    await page.deleteEvent()
    expect(state.client.delete.mock.calls.map(([url]) => url)).toEqual(['/diagnostics/errors/456'])
    expect(page.events.value).toEqual([event])
    expect(page.selectedEventIds.value).toEqual([])
  })

  it('drops expired selections on refresh without selecting newly arrived archives', async () => {
    page.events.value = [event, { ...event, id: '456' }]
    page.toggleAllEvents(true)
    state.client.get.mockResolvedValue({ data: { events: [event, { ...event, id: '789' }] } })
    await page.loadEvents()
    expect(page.selectedEventIds.value).toEqual(['123'])
    expect(page.allEventsSelected.value).toBe(false)
  })

  it('exports only the checked snapshot in one ZIP with original archive contents', async () => {
    page.events.value = [event, { ...event, id: '456' }, { ...event, id: '789' }]
    page.toggleEvent('123', true)
    page.toggleEvent('789', true)
    const firstBundle = await archiveBundle('archive 123')
    const lastBundle = await archiveBundle('archive 789')
    const pending = deferred()
    state.client.get
      .mockReturnValueOnce(pending.promise)
      .mockResolvedValueOnce({ data: lastBundle })
    const link = { click: vi.fn(), remove: vi.fn() }
    let downloaded
    vi.stubGlobal('document', { createElement: () => link, body: { appendChild: vi.fn() } })
    vi.stubGlobal('URL', {
      createObjectURL: (blob) => {
        downloaded = blob
        return 'blob:test'
      },
      revokeObjectURL: vi.fn()
    })
    const exporting = page.exportSelected()
    await page.exportSelected()
    page.toggleAllEvents(false)
    page.confirmDeleteSelected()
    expect(page.pendingDeleteEvents.value).toBe(null)
    pending.resolve({ data: firstBundle })
    await exporting
    expect(state.client.get.mock.calls).toEqual([
      ['/diagnostics/errors/123/export', { params: { screenshots: '1' }, responseType: 'blob' }],
      ['/diagnostics/errors/789/export', { params: { screenshots: '1' }, responseType: 'blob' }]
    ])
    expect(link.click).toHaveBeenCalledOnce()
    expect(link.download).toBe('error-archives-2.zip')
    const reader = new ZipReader(new BlobReader(downloaded), { useWebWorkers: false })
    try {
      const entries = await reader.getEntries()
      expect(entries.map((entry) => entry.filename)).toEqual([
        'error-archive-123.zip',
        'error-archive-789.zip'
      ])
      for (const [index, original] of [firstBundle, lastBundle].entries()) {
        const bundle = await entries[index].getData(new BlobWriter('application/zip'))
        expect(await bundle.arrayBuffer()).toEqual(await original.arrayBuffer())
        const archive = new ZipReader(new BlobReader(bundle), { useWebWorkers: false })
        try {
          const files = await archive.getEntries()
          expect(files.map((entry) => entry.filename)).toEqual([
            'runtime.log',
            'screenshots/frame.jpg',
            'readme.txt',
            'plan.json'
          ])
          expect(await files[0].getData(new TextWriter())).toBe(`archive ${index ? '789' : '123'}`)
          expect(await files.at(-1).getData(new TextWriter())).toBe('{"plan1":{}}')
        } finally {
          await archive.close()
        }
      }
    } finally {
      await reader.close()
    }
    expect(page.exporting.value).toBe(false)
  })

  it('does not download a partial export and retains selection for retry', async () => {
    await page.exportSelected()
    expect(state.client.get).not.toHaveBeenCalled()
    page.events.value = [event, { ...event, id: '456' }]
    page.toggleAllEvents(true)
    const createUrl = vi.fn()
    vi.stubGlobal('URL', { createObjectURL: createUrl, revokeObjectURL: vi.fn() })
    state.client.get
      .mockResolvedValueOnce({ data: new Blob(['archive 123']) })
      .mockRejectedValueOnce(new Error('expired'))
    await page.exportSelected()
    expect(createUrl).not.toHaveBeenCalled()
    expect(page.exportError.value).toContain('未下载文件')
    expect(page.selectedEventIds.value).toEqual(['123', '456'])
    expect(page.exporting.value).toBe(false)
  })

  it('avoids duplicate submissions and treats already expired archives as removed', async () => {
    const pending = deferred()
    page.events.value = [event, { ...event, id: '456' }]
    page.toggleAllEvents(true)
    page.confirmDeleteSelected()
    state.client.delete
      .mockReturnValueOnce(pending.promise)
      .mockRejectedValueOnce({ response: { status: 404 } })
    const deleting = page.deleteEvent()
    await page.deleteEvent()
    page.handleDeleteModal(false)
    expect(page.deleting.value).toBe(true)
    expect(page.pendingDeleteEvents.value).toHaveLength(2)
    expect(state.client.delete).toHaveBeenCalledOnce()
    pending.resolve({})
    await deleting
    expect(state.client.delete).toHaveBeenCalledTimes(2)
    expect(page.events.value).toEqual([])
    expect(page.deleting.value).toBe(false)
    expect(page.deleteError.value).toBe('')
  })
})

describe('diagnostic log timeline', () => {
  let scope, component

  beforeEach(() => {
    state.client = { get: vi.fn() }
    scope = effectScope()
    component = scope.run(() => LogSchedule.setup({}, { expose: vi.fn() }))
  })

  afterEach(() => scope.stop())

  it.each([
    [
      '2026-10-09 14:15:43,152',
      String.raw`_internal\arknights_mower\utils\device\device.py:661`,
      'DEBUG',
      'tap',
      'tap: (1589, 221)'
    ],
    [
      '2026-10-09 14:15:43',
      'arknights_mower/utils/device/device.py:661',
      'INFO',
      'tap',
      'tap: (1589, 221)'
    ],
    [
      '2026-10-09 14:15:43,483',
      String.raw`C:\Program Files\Mower\arknights_mower\solvers\base_schedule.py:1916`,
      'ERROR',
      'read_agent_mood',
      'MaaTouch 输入发送结果不明确，已停止本次动作'
    ]
  ])('parses %s %s %s log headers', async (timestamp, path, level, action, summary) => {
    const message = `${timestamp} ${path} ${level} ${action}: ${summary}`
    const row = { time: '2026-10-09 14:15:43', message, screenshot: 'errors/test/frame.jpg' }
    state.client.get.mockResolvedValueOnce({ data: { logs: [row] } })

    await component.loadWindow()

    expect(state.client.get).toHaveBeenCalledWith(
      expect.stringContaining('/diagnostics/timeline'),
      { params: { at: component.queryAt.value } }
    )
    expect(component.visibleLogs.value).toEqual([{ ...row, index: 0, level, summary, detail: '' }])
  })

  it('filters archived ERROR and DEBUG logs without losing traceback details', async () => {
    const detail =
      'Traceback (most recent call last):\n  File "session.py", line 166, in close\nValueError: 连接已关闭\n\nThe above exception was the direct cause of the following exception:\n\nTraceback (most recent call last):\n  File "session.py", line 168, in close\nRuntimeError: MaaTouch 进程异常退出：137'
    const logs = [
      {
        time: '2026-10-09 14:15:43',
        message: `2026-10-09 14:15:43,483 _internal/arknights_mower/solvers/base_schedule.py:1916 ERROR read_agent_mood: MaaTouch 输入发送结果不明确\n${detail}`
      },
      {
        time: '2026-10-09 14:15:43',
        message:
          '2026-10-09 14:15:43,406 _internal/arknights_mower/utils/device/maatouch/command.py:41 DEBUG publish: send operation: d 0 1589 221 100'
      }
    ]
    state.client.get.mockResolvedValueOnce({ data: { logs } })

    await component.selectEvent({ id: 'test', time_ns: 1791526543000000000, screenshots: [] })
    component.levelFilter.value = 'ERROR'
    component.searchText.value = 'runtimeerror'

    expect(state.client.get).toHaveBeenCalledWith(
      expect.stringContaining('/diagnostics/errors/test/logs'),
      { params: undefined }
    )
    expect(component.visibleLogs.value).toEqual([
      { ...logs[0], index: 0, level: 'ERROR', summary: 'MaaTouch 输入发送结果不明确', detail }
    ])

    component.levelFilter.value = 'DEBUG'
    component.searchText.value = ''
    expect(component.visibleLogs.value.map((row) => row.summary)).toEqual([
      'send operation: d 0 1589 221 100'
    ])
    expect(component.visibleLogs.value[0].level).toBe('DEBUG')
  })

  it('retains unformatted messages and their multiline details', async () => {
    state.client.get.mockResolvedValueOnce({
      data: { logs: [{ time: '2026-10-09 14:15:43', message: 'message\n  extra detail\n' }] }
    })

    await component.loadWindow()

    expect(component.visibleLogs.value[0]).toMatchObject({
      level: 'INFO',
      summary: 'message',
      detail: 'extra detail'
    })
  })
})
