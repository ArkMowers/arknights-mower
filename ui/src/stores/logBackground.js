import { computed, onScopeDispose, ref } from 'vue'
import { defineStore } from 'pinia'
import axios from 'axios'

const endpoint = `${import.meta.env.VITE_HTTP_URL || ''}/gui/log-background`
export const MAX_BACKGROUND_BYTES = 8 * 1024 * 1024

export const useLogBackgroundStore = defineStore('log-background', () => {
  const customUrl = ref('')
  const loaded = ref(false)
  const busy = ref(false)
  const error = ref('')
  const url = computed(() => customUrl.value || '/bg.webp')
  let loading = null
  let disposed = false

  function replace(blob) {
    if (disposed) return
    const previous = customUrl.value
    customUrl.value = blob ? URL.createObjectURL(blob) : ''
    if (previous) URL.revokeObjectURL(previous)
  }

  function accept(response) {
    if (response.status === 204) replace(null)
    else if (response.data instanceof Blob && response.data.type === 'image/webp')
      replace(response.data)
    else throw new Error('背景图响应无效')
  }

  async function load() {
    if (loading) return loading
    if (loaded.value) return true
    busy.value = true
    error.value = ''
    loading = (async () => {
      try {
        accept(await axios.get(endpoint, { responseType: 'blob', timeout: 10000 }))
        loaded.value = true
        return true
      } catch {
        error.value = '运行日志背景图读取失败，请重试。'
        return false
      } finally {
        busy.value = false
        loading = null
      }
    })()
    return loading
  }

  async function upload(file) {
    if (busy.value || !loaded.value) return false
    if (!file || !['image/png', 'image/jpeg', 'image/webp'].includes(file.type)) {
      error.value = '请选择 PNG、JPEG 或 WebP 图片。'
      return false
    }
    if (file.size > MAX_BACKGROUND_BYTES) {
      error.value = '图片不能超过 8 MiB。'
      return false
    }
    busy.value = true
    error.value = ''
    try {
      accept(
        await axios.put(endpoint, file, {
          headers: { 'Content-Type': file.type },
          responseType: 'blob',
          timeout: 30000
        })
      )
      return true
    } catch (failure) {
      const blob = failure?.response?.data
      let message = ''
      if (blob instanceof Blob) {
        try {
          message = JSON.parse(await blob.text()).message || ''
        } catch {
          // 错误响应可能不是 JSON。
        }
      }
      error.value = message || '运行日志背景图保存失败，请重试。'
      return false
    } finally {
      busy.value = false
    }
  }

  async function reset() {
    if (busy.value || !loaded.value || !customUrl.value) return false
    busy.value = true
    error.value = ''
    try {
      const response = await axios.delete(endpoint, { timeout: 10000 })
      if (response.status !== 204) throw new Error()
      replace(null)
      return true
    } catch {
      error.value = '运行日志背景图恢复默认失败，请重试。'
      return false
    } finally {
      busy.value = false
    }
  }

  onScopeDispose(() => {
    disposed = true
    if (customUrl.value) URL.revokeObjectURL(customUrl.value)
  })

  return { customUrl, url, loaded, busy, error, load, upload, reset }
})
