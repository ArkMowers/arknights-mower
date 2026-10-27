import axios from 'axios'
import { defineStore } from 'pinia'
import { computed, ref } from 'vue'
import { useResourceVersionStore } from '@/stores/resourceVersion'
import { requestSoftwareUpdateCheck } from '@/utils/softwareUpdate'
import { i18n } from '@/i18n'

export const useVersionChecksStore = defineStore('versionChecks', () => {
  const resources = useResourceVersionStore()
  const softwareChecking = ref(false)
  const softwareInfo = ref(null)
  const resourceChecking = computed(() => resources.loading)
  const resourceDisabled = computed(() => resources.installing)
  let softwareRequest = null
  let resourceRequest = null

  function checkSoftware() {
    if (softwareRequest) return softwareRequest
    softwareChecking.value = true
    softwareRequest = (async () => {
      const base = `${import.meta.env.VITE_HTTP_URL || ''}/software-update`
      const { data } = await axios.get(`${base}/info`)
      if (!data.ok) throw new Error(data.message || i18n.global.t('updates.softwareInfoFailed'))
      softwareInfo.value = data
      return requestSoftwareUpdateCheck(axios, data.settings.channel)
    })().finally(() => {
      softwareChecking.value = false
      softwareRequest = null
    })
    return softwareRequest
  }

  function checkResource() {
    if (resourceRequest) return resourceRequest
    if (resources.loading || resources.installing) return Promise.resolve(null)
    resourceRequest = resources
      .loadResourceVersion(true)
      .then((result) => {
        if (result.error) throw new Error(result.error)
        return result
      })
      .finally(() => {
        resourceRequest = null
      })
    return resourceRequest
  }

  return {
    softwareInfo,
    softwareChecking,
    resourceChecking,
    resourceDisabled,
    checkSoftware,
    checkResource
  }
})
