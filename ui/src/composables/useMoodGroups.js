import { computed, onScopeDispose, ref, watch } from 'vue'
import { buildObservationGroups } from '@/utils/mood_observation'

export function useMoodGroups(board, reportData, getMoodSeries) {
  const fetchedSeries = ref([])
  const historyLimited = ref(false)
  let requestNumber = 0

  async function refreshSeries() {
    const id = ++requestNumber
    const names = [...new Set(board.views.flatMap((view) => view.operators))].slice(0, 192)
    if (!names.length) {
      fetchedSeries.value = []
      return
    }
    const combined = []
    try {
      for (let index = 0; index < names.length; index += 16) {
        const batch = await getMoodSeries(names.slice(index, index + 16))
        if (id !== requestNumber) return
        combined.push(...batch)
      }
      fetchedSeries.value = combined
      historyLimited.value = false
    } catch {
      if (id === requestNumber) {
        historyLimited.value = true
        fetchedSeries.value = []
      }
    }
  }

  watch(() => JSON.stringify(board.views.map((view) => view.operators)), refreshSeries, {
    immediate: true
  })
  onScopeDispose(() => requestNumber++)

  const groups = computed(() => {
    const custom = buildObservationGroups(board.views, reportData.value, fetchedSeries.value)
    const original = reportData.value.map((group) => ({ ...group, boardKey: group.groupName }))
    const manual = board.groupOrder
    const preferred = [
      ...custom.map((group) => group.boardKey).filter((key) => !manual.includes(key)),
      ...manual
    ]
    const rank = new Map(preferred.map((key, index) => [key, index]))
    return [...custom, ...original]
      .filter((group) => !board.hiddenGroups.includes(group.boardKey))
      .sort((a, b) => (rank.get(a.boardKey) ?? Infinity) - (rank.get(b.boardKey) ?? Infinity))
  })

  return { groups, fetchedSeries, historyLimited, refreshSeries }
}
