import axios from 'axios'
import { computed, ref } from 'vue'
import { defineStore } from 'pinia'

export const useMasteryStore = defineStore('mastery', () => {
  const loading = ref(false)
  const recommendations = ref([])
  const hasData = ref(false)
  const error = ref('')
  const filterAchievable = ref(false)

  async function fetchRecommendations() {
    loading.value = true
    error.value = ''
    try {
      const response = await axios.get(
        `${import.meta.env.VITE_HTTP_URL}/mastery-recommendation`
      )
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
    try {
      const response = await axios.get(
        `${import.meta.env.VITE_HTTP_URL}/cultivate-fetch`
      )
      const data = response.data
      if (data.success) {
        await fetchRecommendations()
      } else {
        error.value = `数据拉取失败: ${data.message}`
        loading.value = false
      }
    } catch (e) {
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
    fetchCultivate
  }
})
