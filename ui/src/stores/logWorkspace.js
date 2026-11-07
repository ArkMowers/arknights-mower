import { defineStore, storeToRefs } from 'pinia'
import { ref, shallowRef, watch } from 'vue'

import { useMowerStore } from './mower'

// 只保留当前实例的上一帧和显示状态；离页后不继续请求。
export const useLogWorkspaceStore = defineStore('log-workspace', () => {
  const visited = ref(false)
  const screenshot = shallowRef(null)
  const dailyStatus = shallowRef(null)
  const dailyView = ref(false)
  const wideLayout = ref(false)
  const layout = ref({ screenshot_height: null, task_height: null, rail_width: null })
  const mobileScreenshotHeight = ref(null)
  const { running } = storeToRefs(useMowerStore())

  watch(
    running,
    (active) => {
      if (!active) {
        dailyStatus.value = null
        dailyView.value = false
      }
    },
    { flush: 'sync' }
  )

  function restoreDailyStatus() {
    // 北京时间 04:00 换日，相当于 UTC 时刻加 4 小时后取日期。
    const gameDay = new Date(Date.now() + 4 * 60 * 60 * 1000).toISOString().slice(0, 10)
    if (!running.value || dailyStatus.value?.game_day !== gameDay) dailyStatus.value = null
    return dailyStatus.value
  }

  return {
    visited,
    screenshot,
    dailyStatus,
    dailyView,
    wideLayout,
    layout,
    mobileScreenshotHeight,
    restoreDailyStatus
  }
})
