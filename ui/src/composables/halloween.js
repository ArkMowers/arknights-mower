import { inject, onBeforeUnmount, onMounted, provide, readonly, ref } from 'vue'
import { isHalloweenSeason } from '@/utils/halloween'

const halloweenSeasonKey = Symbol('halloween-season')

export function provideHalloweenSeason() {
  const active = ref(isHalloweenSeason())
  let midnightTimer = null

  function refresh() {
    active.value = isHalloweenSeason()
    const nextMidnight = new Date()
    nextMidnight.setHours(24, 0, 0, 0)
    clearTimeout(midnightTimer)
    midnightTimer = setTimeout(refresh, Math.max(1, nextMidnight.getTime() - Date.now()))
  }

  function onVisibilityChange() {
    if (globalThis.document?.visibilityState === 'visible') refresh()
  }

  onMounted(() => {
    refresh()
    globalThis.document?.addEventListener?.('visibilitychange', onVisibilityChange)
  })
  onBeforeUnmount(() => {
    clearTimeout(midnightTimer)
    globalThis.document?.removeEventListener?.('visibilitychange', onVisibilityChange)
  })
  provide(halloweenSeasonKey, readonly(active))
  return readonly(active)
}

export function useHalloweenSeason() {
  return inject(halloweenSeasonKey, () => readonly(ref(isHalloweenSeason())), true)
}
