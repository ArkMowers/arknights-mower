import { nextTick } from 'vue'

// 完成一次请求后才安排下一次；关闭或卸载时取消请求并释放 Blob URL。
export function createScreenshotPreview({
  fetchSnapshot,
  onChange,
  getCachedSnapshot = () => null,
  cacheSnapshot = () => {},
  interval = 1000
}) {
  let active = false
  let generation = 0
  let timer = null
  let controller = null
  let etag = ''
  let imageUrl = ''
  let previousUrl = ''

  function releasePrevious() {
    if (previousUrl) URL.revokeObjectURL(previousUrl)
    previousUrl = ''
  }

  function restoreImage() {
    const cached = getCachedSnapshot()
    if (imageUrl || !cached?.blob) return
    imageUrl = URL.createObjectURL(cached.blob)
    etag = cached.etag || ''
    onChange(imageUrl, cached.aspect)
  }

  restoreImage()

  function clearImage() {
    releasePrevious()
    if (imageUrl) URL.revokeObjectURL(imageUrl)
    imageUrl = ''
    onChange('')
  }

  async function poll(currentGeneration) {
    const requestController = new AbortController()
    controller = requestController
    let pendingUrl = ''
    let replacedUrl = ''
    const releasePending = () => {
      if (pendingUrl) URL.revokeObjectURL(pendingUrl)
      pendingUrl = ''
    }
    try {
      const response = await fetchSnapshot({
        signal: requestController.signal,
        headers: etag ? { 'If-None-Match': etag } : {},
        responseType: 'blob',
        timeout: 10000,
        validateStatus: (status) => [200, 204, 304].includes(status)
      })
      if (!active || generation !== currentGeneration) return
      if (response.status === 200) {
        if (!response.data || response.data.size === 0) return
        pendingUrl = URL.createObjectURL(response.data)
        requestController.signal.addEventListener('abort', releasePending, { once: true })
        const image = new Image()
        image.src = pendingUrl
        await image.decode()
        if (!active || generation !== currentGeneration) return
        const aspect = image.naturalWidth / image.naturalHeight
        replacedUrl = imageUrl
        previousUrl = replacedUrl
        imageUrl = pendingUrl
        pendingUrl = ''
        etag = response.headers.etag || ''
        cacheSnapshot({ blob: response.data, etag, aspect })
        onChange(imageUrl, aspect)
        await nextTick()
      } else if (response.status === 204) {
        etag = ''
        cacheSnapshot(null)
        clearImage()
      }
    } catch (error) {
      // 网络瞬断时保留上一帧，下次请求恢复；取消请求后也不再回写组件。
      if (!requestController.signal.aborted) console.debug('获取最新截图失败:', error)
    } finally {
      releasePending()
      requestController.signal.removeEventListener('abort', releasePending)
      if (previousUrl === replacedUrl) releasePrevious()
      if (active && generation === currentGeneration) {
        controller = null
        timer = setTimeout(() => poll(currentGeneration), interval)
      }
    }
  }

  function pause() {
    active = false
    generation += 1
    clearTimeout(timer)
    timer = null
    controller?.abort()
    controller = null
  }

  return {
    start() {
      if (active) return
      active = true
      restoreImage()
      poll(++generation)
    },
    pause,
    stop() {
      pause()
      etag = ''
      clearImage()
    }
  }
}
