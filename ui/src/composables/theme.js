import { computed, onScopeDispose, ref, unref } from 'vue'

export function useResolvedTheme(preference) {
  const media = globalThis.window?.matchMedia?.('(prefers-color-scheme: dark)')
  const systemDark = ref(media?.matches ?? false)
  const update = (event) => {
    systemDark.value = event.matches
  }

  if (media?.addEventListener) {
    media.addEventListener('change', update)
    onScopeDispose(() => media.removeEventListener('change', update))
  } else if (media?.addListener) {
    media.addListener(update)
    onScopeDispose(() => media.removeListener(update))
  }

  return computed(() => {
    const selected = unref(preference)
    return selected === 'dark' || (selected === 'system' && systemDark.value) ? 'dark' : 'light'
  })
}
