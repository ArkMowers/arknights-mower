import { defineStore } from 'pinia'
import { computed, ref } from 'vue'
import axios from 'axios'

const appearanceUrl = `${import.meta.env.VITE_HTTP_URL || ''}/gui/appearance`
const validDisplay = (value) => value === 'version' || value === 'channel'
const validLanguage = (value) => value === 'zh' || value === 'en'
const validLayout = (value) => value === 'checklist' || value === 'waterfall'
const validReportMode = (value) => value === 'standard' || value === 'stock'

export const useGuiStore = defineStore('gui', () => {
  const softwareVersionDisplay = ref('version')
  const softwareVersionLanguage = ref('en')
  const taskSettingsLayout = ref('checklist')
  const watermarkVisible = ref(true)
  const baseReportMode = ref('standard')
  const loaded = ref(false)
  const loading = ref(false)
  const saving = ref(false)
  const layoutSaving = ref(false)
  const watermarkSaving = ref(false)
  const reportModeSaving = ref(false)
  const error = ref('')
  const layoutError = ref('')
  const watermarkError = ref('')
  const reportModeError = ref('')
  const displayDisabled = computed(
    () =>
      !loaded.value ||
      loading.value ||
      saving.value ||
      layoutSaving.value ||
      watermarkSaving.value ||
      reportModeSaving.value
  )
  const layoutDisabled = displayDisabled
  const watermarkDisabled = displayDisabled
  const reportModeDisabled = displayDisabled
  let loadRequest = null
  let failedDisplay = null
  let failedLanguage = null
  let failedLayout = null
  let failedWatermark = null
  let failedReportMode = null

  async function load() {
    if (loadRequest) return loadRequest
    if (loaded.value) return true
    loading.value = true
    error.value = ''
    layoutError.value = ''
    watermarkError.value = ''
    reportModeError.value = ''
    loadRequest = (async () => {
      try {
        const { data } = await axios.get(appearanceUrl, { timeout: 5000 })
        if (!validDisplay(data?.software_version_display)) throw new Error()
        if (
          data.software_version_language !== undefined &&
          !validLanguage(data.software_version_language)
        )
          throw new Error()
        if (data.task_settings_layout !== undefined && !validLayout(data.task_settings_layout))
          throw new Error()
        if (data.watermark_visible !== undefined && typeof data.watermark_visible !== 'boolean')
          throw new Error()
        if (data.base_report_mode !== undefined && !validReportMode(data.base_report_mode))
          throw new Error()
        softwareVersionDisplay.value = data.software_version_display
        softwareVersionLanguage.value = data.software_version_language ?? 'en'
        taskSettingsLayout.value = data.task_settings_layout ?? 'checklist'
        watermarkVisible.value = data.watermark_visible ?? true
        baseReportMode.value = data.base_report_mode ?? 'standard'
        loaded.value = true
        return true
      } catch {
        error.value = '软件版本显示偏好读取失败，请重试。'
        layoutError.value = '全部设置显示偏好读取失败，请重试。'
        watermarkError.value = '版本水印设置读取失败，请重试。'
        reportModeError.value = '基建报表显示偏好读取失败，请重试。'
        return false
      } finally {
        loading.value = false
      }
    })().finally(() => {
      loadRequest = null
    })
    return loadRequest
  }

  async function setSoftwareVersionDisplay(value) {
    if (displayDisabled.value || !validDisplay(value)) return false
    if (value === softwareVersionDisplay.value) return true
    const previous = softwareVersionDisplay.value
    softwareVersionDisplay.value = value
    saving.value = true
    error.value = ''
    failedDisplay = null
    failedLanguage = null
    try {
      const { data } = await axios.put(
        appearanceUrl,
        { software_version_display: value },
        { timeout: 5000 }
      )
      if (data?.software_version_display !== value) throw new Error()
      return true
    } catch {
      softwareVersionDisplay.value = previous
      failedDisplay = value
      error.value = '软件版本显示偏好保存失败，已恢复原来的显示。请重试。'
      return false
    } finally {
      saving.value = false
    }
  }

  function retry() {
    if (!loaded.value) return load()
    return failedLanguage === null
      ? setSoftwareVersionDisplay(failedDisplay)
      : setSoftwareVersionLanguage(failedLanguage)
  }

  async function setSoftwareVersionLanguage(value) {
    if (displayDisabled.value || !validLanguage(value)) return false
    if (value === softwareVersionLanguage.value) return true
    const previous = softwareVersionLanguage.value
    softwareVersionLanguage.value = value
    saving.value = true
    error.value = ''
    failedDisplay = null
    failedLanguage = null
    try {
      const { data } = await axios.put(
        appearanceUrl,
        { software_version_language: value },
        { timeout: 5000 }
      )
      if (data?.software_version_language !== value) throw new Error()
      return true
    } catch {
      softwareVersionLanguage.value = previous
      failedLanguage = value
      error.value = '软件版本类型语言保存失败，已恢复原来的显示。请重试。'
      return false
    } finally {
      saving.value = false
    }
  }

  async function setTaskSettingsLayout(value) {
    if (layoutDisabled.value || !validLayout(value)) return false
    if (value === taskSettingsLayout.value) return true
    const previous = taskSettingsLayout.value
    taskSettingsLayout.value = value
    layoutSaving.value = true
    layoutError.value = ''
    failedLayout = null
    try {
      const { data } = await axios.put(
        appearanceUrl,
        { task_settings_layout: value },
        { timeout: 5000 }
      )
      if (data?.task_settings_layout !== value) throw new Error()
      return true
    } catch {
      taskSettingsLayout.value = previous
      failedLayout = value
      layoutError.value = '全部设置显示偏好保存失败，已恢复原来的显示。请重试。'
      return false
    } finally {
      layoutSaving.value = false
    }
  }

  function retryTaskSettingsLayout() {
    return loaded.value ? setTaskSettingsLayout(failedLayout) : load()
  }

  async function setBaseReportMode(value) {
    if (reportModeDisabled.value || !validReportMode(value)) return false
    if (value === baseReportMode.value) return true
    const previous = baseReportMode.value
    baseReportMode.value = value
    reportModeSaving.value = true
    reportModeError.value = ''
    failedReportMode = null
    try {
      const { data } = await axios.put(
        appearanceUrl,
        { base_report_mode: value },
        { timeout: 5000 }
      )
      if (data?.base_report_mode !== value) throw new Error()
      return true
    } catch {
      baseReportMode.value = previous
      failedReportMode = value
      reportModeError.value = '基建报表显示偏好保存失败，已恢复原来的显示。请重试。'
      return false
    } finally {
      reportModeSaving.value = false
    }
  }

  function retryReportMode() {
    return loaded.value ? setBaseReportMode(failedReportMode) : load()
  }

  async function setWatermarkVisible(value, confirmation = '') {
    if (watermarkDisabled.value || typeof value !== 'boolean') return false
    if (value === watermarkVisible.value) return true
    if (!value && confirmation !== '反馈问题时务必说明具体版本') return false
    const previous = watermarkVisible.value
    watermarkVisible.value = value
    watermarkSaving.value = true
    watermarkError.value = ''
    failedWatermark = null
    const payload = { watermark_visible: value }
    if (!value) payload.watermark_confirmation = confirmation
    try {
      const { data } = await axios.put(appearanceUrl, payload, { timeout: 5000 })
      if (data?.watermark_visible !== value) throw new Error()
      return true
    } catch {
      watermarkVisible.value = previous
      failedWatermark = { value, confirmation }
      watermarkError.value = '版本水印设置保存失败，已恢复原来的显示。请重试。'
      return false
    } finally {
      watermarkSaving.value = false
    }
  }

  function retryWatermarkVisible() {
    if (!loaded.value) return load()
    return failedWatermark
      ? setWatermarkVisible(failedWatermark.value, failedWatermark.confirmation)
      : false
  }

  return {
    softwareVersionDisplay,
    softwareVersionLanguage,
    taskSettingsLayout,
    watermarkVisible,
    baseReportMode,
    loaded,
    loading,
    saving,
    layoutSaving,
    watermarkSaving,
    reportModeSaving,
    error,
    layoutError,
    watermarkError,
    reportModeError,
    displayDisabled,
    layoutDisabled,
    watermarkDisabled,
    reportModeDisabled,
    load,
    setSoftwareVersionDisplay,
    setSoftwareVersionLanguage,
    setTaskSettingsLayout,
    setBaseReportMode,
    setWatermarkVisible,
    retry,
    retryTaskSettingsLayout,
    retryReportMode,
    retryWatermarkVisible
  }
})
