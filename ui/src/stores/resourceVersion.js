import { defineStore } from 'pinia'
import { computed, ref } from 'vue'

import axios from 'axios'

export const useResourceVersionStore = defineStore('resourceVersion', () => {
  const info = ref({
    current_version: '',
    current_display: '',
    remote_version: '',
    remote_display: '',
    update_available: null,
    error: null
  })
  const loading = ref(false)
  const loaded = ref(false)
  const job = ref({ status: 'idle' })
  const starting = ref(false)
  const installing = computed(() => starting.value || job.value.status === 'running')
  const progress_error = ref('')
  let tracking = null
  let versionRequest = null
  let revision = 0
  const install_message = ref('')
  const canInstall = computed(
    () =>
      loaded.value && !loading.value && !installing.value && info.value.update_available === true
  )

  async function loadResourceVersion(force = false) {
    if (versionRequest) {
      if (!force) return versionRequest
      await versionRequest
      return loadResourceVersion(true)
    }
    if (loaded.value && !force) return info.value
    loading.value = true
    loaded.value = false
    info.value = {
      ...info.value,
      remote_version: '',
      remote_display: '',
      update_available: null,
      error: null
    }
    versionRequest = (async () => {
      try {
        const response = await axios.get(`${import.meta.env.VITE_HTTP_URL}/resource-version`)
        info.value = {
          current_version: response.data.current_version || '',
          current_display: response.data.current_display || '',
          remote_version: response.data.remote_version || '',
          remote_display: response.data.remote_display || '',
          update_available: response.data.update_available ?? null,
          error: response.data.error || null
        }
        loaded.value = true
      } catch (error) {
        info.value = {
          ...info.value,
          remote_version: '',
          remote_display: '',
          update_available: null,
          error: '网络错误：无法获取资源版本'
        }
      } finally {
        loading.value = false
      }
      return info.value
    })().finally(() => {
      versionRequest = null
    })
    return versionRequest
  }

  async function loadResourceVersionLocal() {
    // 只读本地已装版本，常驻显示「当前版本」，不触碰网络。
    loaded.value = false
    info.value = {
      ...info.value,
      remote_version: '',
      remote_display: '',
      update_available: null,
      error: null
    }
    try {
      const response = await axios.get(`${import.meta.env.VITE_HTTP_URL}/resource-version?local=1`)
      info.value = {
        ...info.value,
        current_version: response.data.current_version || '',
        current_display: response.data.current_display || '',
        remote_version: '',
        remote_display: '',
        update_available: null,
        error: null
      }
    } catch (error) {
      // 本地读取失败保持「未安装」，不打扰用户
    }
  }

  async function trackJob(initial) {
    if (tracking) return tracking
    job.value = initial
    const id = initial.id
    tracking = (async () => {
      while (job.value.status === 'running') {
        await new Promise((resolve) => setTimeout(resolve, 800))
        try {
          const { data } = await axios.get(`${import.meta.env.VITE_HTTP_URL}/resource/status`, {
            timeout: 5000
          })
          if (!data.ok) throw new Error(data.message)
          if (data.job.id !== id) {
            job.value = {
              id,
              status: 'error',
              message: '资源更新任务已改变，请重新查看当前资源版本'
            }
            break
          }
          job.value = data.job
          progress_error.value = ''
        } catch {
          progress_error.value = '资源进度连接暂时断开，正在重试'
        }
      }
      progress_error.value = ''
      install_message.value = job.value.message || ''
      if (job.value.status === 'success') {
        loaded.value = false
        await loadResourceVersion(true)
      }
      return job.value.status === 'success'
    })().finally(() => {
      tracking = null
    })
    return tracking
  }

  async function loadResourceJob() {
    if (tracking) return tracking
    if (starting.value) return
    const requestedRevision = revision
    try {
      const { data } = await axios.get(`${import.meta.env.VITE_HTTP_URL}/resource/status`, {
        timeout: 5000
      })
      if (requestedRevision !== revision || !data.ok) return
      if (tracking) return tracking
      job.value = data.job
      if (data.job.status === 'running') return trackJob(data.job)
    } catch {
      // Local version information remains usable when progress is unavailable.
    }
  }

  async function installResource() {
    if (installing.value) return false
    if (!canInstall.value) {
      if (!loading.value) {
        install_message.value = '请先检查更新，发现新版本后再安装'
      }
      return false
    }
    revision += 1
    starting.value = true
    job.value = {
      id: '',
      status: 'running',
      phase: 'preparing',
      message: '正在启动资源更新',
      progress: null
    }
    install_message.value = ''
    progress_error.value = ''
    try {
      const { data } = await axios.post(`${import.meta.env.VITE_HTTP_URL}/resource/install`, {
        background: true
      })
      if (!data.ok) {
        install_message.value = data.message || '资源更新启动失败'
        throw new Error(install_message.value)
      }
      starting.value = false
      return await trackJob(data.job)
    } catch (error) {
      install_message.value =
        error.response?.data?.message || install_message.value || '安装失败：网络错误'
      job.value = { status: 'error', message: install_message.value, progress: null }
      return false
    } finally {
      starting.value = false
    }
  }

  return {
    info,
    loading,
    loaded,
    installing,
    job,
    progress_error,
    loadResourceJob,
    install_message,
    canInstall,
    loadResourceVersion,
    loadResourceVersionLocal,
    installResource
  }
})
