import { onActivated, onDeactivated, onMounted, onScopeDispose, ref } from 'vue'
import { getGameWeekdayIndex, getNextGameDayStart } from '@/utils/maa_weekly_plan'

export function useGameWeekdayIndex() {
  const weekday = ref(getGameWeekdayIndex())
  let timer
  const pageWindow = globalThis.window
  const pageDocument = globalThis.document

  function refresh() {
    clearTimeout(timer)
    const now = new Date()
    weekday.value = getGameWeekdayIndex(now)
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
  return weekday
}
