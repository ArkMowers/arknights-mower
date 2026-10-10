// 完成一次请求后才安排下一次；关闭或卸载时取消请求并释放 Blob URL。
export function createScreenshotPreview({ fetchSnapshot, onChange, interval = 1000 }) {
  let active = false
  let generation = 0
  let timer = null
  let controller = null
  let etag = ''
  let imageUrl = ''

  function clearImage() {
    if (imageUrl) URL.revokeObjectURL(imageUrl)
    imageUrl = ''
    onChange('')
  }

  async function poll(currentGeneration) {
    const requestController = new AbortController()
    controller = requestController
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
        const nextUrl = URL.createObjectURL(response.data)
        if (imageUrl) URL.revokeObjectURL(imageUrl)
        imageUrl = nextUrl
        etag = response.headers.etag || ''
        onChange(imageUrl)
      } else if (response.status === 204) {
        etag = ''
        clearImage()
      }
    } catch (error) {
      // 网络瞬断时保留上一帧，下次请求恢复；取消请求后也不再回写组件。
      if (!requestController.signal.aborted) console.debug('获取最新截图失败:', error)
    } finally {
      if (active && generation === currentGeneration) {
        controller = null
        timer = setTimeout(() => poll(currentGeneration), interval)
      }
    }
  }

  return {
    start() {
      if (active) return
      active = true
      poll(++generation)
    },
    stop() {
      active = false
      generation += 1
      clearTimeout(timer)
      timer = null
      controller?.abort()
      controller = null
      etag = ''
      clearImage()
    }
  }
}
