import { defineStore, storeToRefs } from 'pinia'
import { ref, shallowRef, watch } from 'vue'

import { useMowerStore } from './mower'

const DAY_MS = 24 * 60 * 60 * 1000
const GAME_DAY_OFFSET_MS = 4 * 60 * 60 * 1000

export function dailyStatusExpiry(status, now = Date.now()) {
  if (status?.source !== 'live') return null
  // 北京时间 04:00 换日，相当于 UTC 时刻加 4 小时后取日期。
  const gameDayStart = Math.floor((now + GAME_DAY_OFFSET_MS) / DAY_MS) * DAY_MS
  if (status.game_day !== new Date(gameDayStart).toISOString().slice(0, 10)) return null
  return gameDayStart + DAY_MS - GAME_DAY_OFFSET_MS
}

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
    if (!running.value || dailyStatusExpiry(dailyStatus.value) === null) dailyStatus.value = null
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
