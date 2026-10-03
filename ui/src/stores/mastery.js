import axios from 'axios'
import { computed, ref } from 'vue'
import { defineStore } from 'pinia'

export const useMasteryStore = defineStore('mastery', () => {
  const loading = ref(false)
  const recommendations = ref([])
  const hasData = ref(false)
  const error = ref('')
  const filterAchievable = ref(false)
  const cultivateOk = ref(false)
  const cultivateMsg = ref('')
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
        planSummaryError.value = e?.message || '读取专精计划失败'
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
      const response = await axios.get(`${import.meta.env.VITE_HTTP_URL}/mastery-recommendation`)
      const data = response.data
      if (data.error) {
        error.value = data.error
        return
      }
      recommendations.value = data.operators || []
      hasData.value = data.has_data || false
    } catch (e) {
      error.value = `请求失败: ${e.message || e}`
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
    try {
      const response = await axios.get(`${import.meta.env.VITE_HTTP_URL}/cultivate-fetch`)
      const data = response.data
      if (data.success) {
        cultivateOk.value = true
        cultivateMsg.value = data.message || '拉取成功'
        await fetchRecommendations()
      } else {
        cultivateOk.value = false
        cultivateMsg.value = data.message || '拉取失败'
        error.value = `数据拉取失败: ${data.message}`
        loading.value = false
      }
    } catch (e) {
      cultivateOk.value = false
      cultivateMsg.value = e.message || '请求失败'
      error.value = `请求失败: ${e.message || e}`
      loading.value = false
    }
  }

  return {
    loading,
    recommendations,
    hasData,
    error,
    filterAchievable,
    filteredRecommendations,
    fetchRecommendations,
    fetchCultivate,
    cultivateOk,
    cultivateMsg,
    planCount,
    isTraining,
    planSummaryLoaded,
    planSummaryError,
    loadPlanSummary
  }
})
