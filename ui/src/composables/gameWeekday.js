import { computed, onActivated, onDeactivated, onMounted, onScopeDispose, ref } from 'vue'
import { getGameDate, getGameWeekdayIndex, getNextGameDayStart } from '@/utils/maa_weekly_plan'

export function useGameDay() {
  const time = ref(new Date())
  let timer
  const pageWindow = globalThis.window
  const pageDocument = globalThis.document

  function refresh() {
    clearTimeout(timer)
    const now = new Date()
    time.value = now
    timer = setTimeout(refresh, getNextGameDayStart(now).getTime() - now.getTime())
  }

  function resumeWhenVisible() {
    if (pageDocument?.visibilityState !== 'hidden') refresh()
  }

  function stop() {
    clearTimeout(timer)
    pageWindow?.removeEventListener?.('focus', refresh)
    pageDocument?.removeEventListener?.('visibilitychange', resumeWhenVisible)
  }

  function start() {
    stop()
    refresh()
    pageWindow?.addEventListener?.('focus', refresh)
    pageDocument?.addEventListener?.('visibilitychange', resumeWhenVisible)
  }

  onMounted(start)
  onActivated(start)
  onDeactivated(stop)
  onScopeDispose(stop)
  return {
    date: computed(() => getGameDate(time.value)),
    weekdayIndex: computed(() => getGameWeekdayIndex(time.value))
  }
}

export function useGameWeekdayIndex() {
  return useGameDay().weekdayIndex
}
