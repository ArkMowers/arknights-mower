import { i18n } from '@/i18n'
import { operatorSyncMessage } from '@/i18n/operatorSync'
import axios from 'axios'
import { computed, ref, shallowRef } from 'vue'
import { defineStore } from 'pinia'

function displayMessage(value) {
  return value?.key
    ? i18n.global.t(
        value.key,
        Object.fromEntries(
          Object.entries(value.params || {}).map(([key, message]) => [
            key,
            operatorSyncMessage(message)
          ])
        )
      )
    : operatorSyncMessage(value)
}

export const useMasteryStore = defineStore('mastery', () => {
  const loading = ref(false)
  const recommendations = shallowRef([])
  const statistics = ref(null)
  const personalStatistics = ref(null)
  const history = ref([])
  const goals = ref([])
  const hasData = ref(false)
  const rawError = ref('')
  const error = computed({
    get: () => displayMessage(rawError.value),
    set: (message) => {
      rawError.value = message
    }
  })
  const filterAchievable = ref(false)
  const cultivateOk = ref(false)
  const rawCultivateMsg = ref('')
  const cultivateMsg = computed({
    get: () => displayMessage(rawCultivateMsg.value),
    set: (message) => {
      rawCultivateMsg.value = message
    }
  })
  const yituliuSyncResult = ref(null)
  const planCount = ref(0)
  const isTraining = ref(false)
  const planSummaryLoaded = ref(false)
  const planSummaryError = ref('')
  let planSummaryLoadedAt = 0
  let planSummaryRequest = null

  async function loadPlanSummary(force = false) {
    if (!force && planSummaryLoaded.value && Date.now() - planSummaryLoadedAt < 30_000) {
      return { planCount: planCount.value, isTraining: isTraining.value }
    }
    if (planSummaryRequest) return planSummaryRequest
    planSummaryError.value = ''
    planSummaryRequest = axios
      .get(`${import.meta.env.VITE_HTTP_URL}/mastery-plan`)
      .then((response) => {
        const plans = Array.isArray(response.data?.plans) ? response.data.plans : []
        planCount.value = plans.length
        isTraining.value = plans.some(({ status }) => status === 'training')
        planSummaryLoaded.value = true
        planSummaryLoadedAt = Date.now()
        return { planCount: planCount.value, isTraining: isTraining.value }
      })
      .catch((e) => {
        planSummaryError.value =
          e?.message || i18n.global.t('growth.store.failedToReadMasteryPlans')
        throw e
      })
      .finally(() => {
        planSummaryRequest = null
      })
    return planSummaryRequest
  }

  async function fetchRecommendations() {
    loading.value = true
    error.value = ''
    try {
      const response = await axios.get(`${import.meta.env.VITE_HTTP_URL}/mastery-recommendation`, {
        params: { materials: 0 },
        timeout: 30000
      })
      const data = response.data
      if (data.error) {
        error.value = data.error
        return
      }
      recommendations.value = data.operators || []
      statistics.value = data.statistics || null
      personalStatistics.value = data.personal_statistics || null
      history.value = data.history || []
      goals.value = data.goals || []
      hasData.value = data.has_data || false
    } catch (e) {
      error.value = { key: 'growth.store.requestFailed', params: { value0: e.message || e } }
    } finally {
      loading.value = false
    }
  }

  const filteredRecommendations = computed(() => {
    if (!filterAchievable.value) return recommendations.value
    return recommendations.value
      .map((op) => ({
        ...op,
        recommendations: op.recommendations.filter((r) => r.full_chain_achievable)
      }))
      .filter((op) => op.recommendations.length > 0)
  })

  async function fetchCultivate() {
    loading.value = true
    error.value = ''
    cultivateOk.value = false
    cultivateMsg.value = ''
    yituliuSyncResult.value = null
    try {
      const response = await axios.get(`${import.meta.env.VITE_HTTP_URL}/cultivate-fetch`)
      const data = response.data
      yituliuSyncResult.value = data.yituliu_sync || null
      if (data.success) {
        cultivateOk.value = true
        cultivateMsg.value = data.message || { key: 'growth.store.fetchedSuccessfully' }
        await fetchRecommendations()
      } else {
        cultivateOk.value = false
        cultivateMsg.value = data.message || { key: 'growth.store.fetchFailed' }
        error.value = { key: 'growth.store.dataFetchFailed', params: { value0: data.message } }
        loading.value = false
      }
    } catch (e) {
      cultivateOk.value = false
      cultivateMsg.value = e.message || { key: 'growth.store.requestFailed2' }
      error.value = { key: 'growth.store.requestFailed', params: { value0: e.message || e } }
      loading.value = false
    }
  }

  return {
    loading,
    recommendations,
    statistics,
    personalStatistics,
    history,
    goals,
    hasData,
    error,
    filterAchievable,
    filteredRecommendations,
    fetchRecommendations,
    fetchCultivate,
    cultivateOk,
    cultivateMsg,
    yituliuSyncResult,
    planCount,
    isTraining,
    planSummaryLoaded,
    planSummaryError,
    loadPlanSummary
  }
})
