import { defineStore } from 'pinia'
import { computed, onScopeDispose, ref } from 'vue'
import axios from 'axios'
import { i18n } from '@/i18n'
import {
  DEFAULT_LOCALE,
  isInterfaceLanguagePreference,
  readBrowserLanguages,
  resolveInterfaceLanguage
} from '@/i18n/languagePreference'

const appearanceUrl = `${import.meta.env.VITE_HTTP_URL || ''}/gui/appearance`
const validDisplay = (value) => value === 'version' || value === 'channel'
const validLanguage = (value) => value === 'zh' || value === 'en'
const validLayout = (value) => value === 'checklist' || value === 'waterfall'

export const useGuiStore = defineStore('gui', () => {
  const softwareVersionDisplay = ref('version')
  const softwareVersionLanguage = ref('en')
  const interfaceLanguage = ref(DEFAULT_LOCALE)
  const browserLanguages = ref(readBrowserLanguages())
  const resolvedInterfaceLanguage = computed(() =>
    resolveInterfaceLanguage(interfaceLanguage.value, browserLanguages.value)
  )
  const languageTarget = globalThis.window
  function updateBrowserLanguages() {
    browserLanguages.value = readBrowserLanguages()
  }
  languageTarget?.addEventListener?.('languagechange', updateBrowserLanguages)
  onScopeDispose(() =>
    languageTarget?.removeEventListener?.('languagechange', updateBrowserLanguages)
  )
  const interfaceLanguageSaving = ref(false)
  const interfaceLanguageErrorKey = ref('')
  const interfaceLanguageError = computed(() =>
    interfaceLanguageErrorKey.value ? i18n.global.t(interfaceLanguageErrorKey.value) : ''
  )
  const taskSettingsLayout = ref('checklist')
  const watermarkVisible = ref(true)
  const loaded = ref(false)
  const loading = ref(false)
  const saving = ref(false)
  const layoutSaving = ref(false)
  const watermarkSaving = ref(false)
  const errorKey = ref('')
  const error = computed(() => (errorKey.value ? i18n.global.t(errorKey.value) : ''))
  const layoutErrorKey = ref('')
  const layoutError = computed(() =>
    layoutErrorKey.value ? i18n.global.t(layoutErrorKey.value) : ''
  )
  const watermarkErrorKey = ref('')
  const watermarkError = computed(() =>
    watermarkErrorKey.value ? i18n.global.t(watermarkErrorKey.value) : ''
  )
  const appearanceBusy = computed(
    () =>
      loading.value ||
      saving.value ||
      layoutSaving.value ||
      watermarkSaving.value ||
      interfaceLanguageSaving.value
  )
  const displayDisabled = computed(() => !loaded.value || appearanceBusy.value)
  const layoutDisabled = displayDisabled
  const watermarkDisabled = displayDisabled
  const interfaceLanguageDisabled = displayDisabled
  let loadRequest = null
  let failedDisplay = null
  let failedLanguage = null
  let failedLayout = null
  let failedWatermark = null
  let failedInterfaceLanguage = null

  async function load() {
    if (loadRequest) return loadRequest
    if (loaded.value) return true
    loading.value = true
    errorKey.value = ''
    layoutErrorKey.value = ''
    watermarkErrorKey.value = ''
    interfaceLanguageErrorKey.value = ''
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
        softwareVersionDisplay.value = data.software_version_display
        softwareVersionLanguage.value = data.software_version_language ?? 'en'
        interfaceLanguage.value = isInterfaceLanguagePreference(data.ui_language)
          ? data.ui_language
          : DEFAULT_LOCALE
        taskSettingsLayout.value = data.task_settings_layout ?? 'checklist'
        watermarkVisible.value = data.watermark_visible ?? true
        loaded.value = true
        return true
      } catch {
        errorKey.value = 'settings.gui.versionLoadFailed'
        layoutErrorKey.value = 'settings.gui.layoutLoadFailed'
        watermarkErrorKey.value = 'settings.gui.watermarkLoadFailed'
        interfaceLanguageErrorKey.value = 'appearance.loadFailed'
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
    errorKey.value = ''
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
      errorKey.value = 'settings.gui.versionSaveFailed'
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
    errorKey.value = ''
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
      errorKey.value = 'settings.gui.versionLanguageSaveFailed'
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
    layoutErrorKey.value = ''
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
      layoutErrorKey.value = 'settings.gui.layoutSaveFailed'
      return false
    } finally {
      layoutSaving.value = false
    }
  }

  function retryTaskSettingsLayout() {
    return loaded.value ? setTaskSettingsLayout(failedLayout) : load()
  }

  async function setWatermarkVisible(value, confirmation = '') {
    if (watermarkDisabled.value || typeof value !== 'boolean') return false
    if (value === watermarkVisible.value) return true
    if (!value && confirmation !== '反馈问题时务必说明具体版本') return false
    const previous = watermarkVisible.value
    watermarkVisible.value = value
    watermarkSaving.value = true
    watermarkErrorKey.value = ''
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
      watermarkErrorKey.value = 'settings.gui.watermarkSaveFailed'
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

  async function setInterfaceLanguage(value) {
    if (interfaceLanguageDisabled.value || !isInterfaceLanguagePreference(value)) return false
    if (value === interfaceLanguage.value) return true
    const previous = interfaceLanguage.value
    interfaceLanguage.value = value
    interfaceLanguageSaving.value = true
    interfaceLanguageErrorKey.value = ''
    failedInterfaceLanguage = null
    try {
      const { data } = await axios.put(appearanceUrl, { ui_language: value }, { timeout: 5000 })
      if (data?.ui_language !== value) throw new Error()
      return true
    } catch {
      interfaceLanguage.value = previous
      failedInterfaceLanguage = value
      interfaceLanguageErrorKey.value = 'appearance.saveFailed'
      return false
    } finally {
      interfaceLanguageSaving.value = false
    }
  }

  function retryInterfaceLanguage() {
    if (!loaded.value) return load()
    return failedInterfaceLanguage === null ? false : setInterfaceLanguage(failedInterfaceLanguage)
  }

  return {
    softwareVersionDisplay,
    softwareVersionLanguage,
    interfaceLanguage,
    resolvedInterfaceLanguage,
    interfaceLanguageSaving,
    interfaceLanguageError,
    interfaceLanguageDisabled,
    appearanceBusy,
    taskSettingsLayout,
    watermarkVisible,
    loaded,
    loading,
    saving,
    layoutSaving,
    watermarkSaving,
    error,
    layoutError,
    watermarkError,
    displayDisabled,
    layoutDisabled,
    watermarkDisabled,
    load,
    setSoftwareVersionDisplay,
    setSoftwareVersionLanguage,
    setInterfaceLanguage,
    retryInterfaceLanguage,
    setTaskSettingsLayout,
    setWatermarkVisible,
    retry,
    retryTaskSettingsLayout,
    retryWatermarkVisible
  }
})
