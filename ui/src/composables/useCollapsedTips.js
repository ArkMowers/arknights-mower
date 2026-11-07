import { computed, ref, toValue, watch } from 'vue'

// Label tooltips for a collapsible sidebar. While collapsed, a row shows its tooltip on hover or
// keyboard focus; pointer focus shows nothing. Collapsing by keyboard restores the tooltip of the
// focused row, expanding hides it, and Escape dismisses it from anywhere without moving focus.
export function useCollapsedTips(collapsed) {
  const isCollapsed = computed(() => toValue(collapsed))
  const tipKey = ref(null)
  // Row that holds keyboard focus, remembered so a keyboard collapse can restore its tooltip.
  const focusKey = ref(null)

  function setTip(key, show) {
    if (show) {
      if (isCollapsed.value) tipKey.value = key
    } else if (tipKey.value === key) {
      tipKey.value = null
    }
  }

  function focusTip(key, target) {
    focusKey.value = target.matches(':focus-visible') ? key : null
    if (focusKey.value && isCollapsed.value) tipKey.value = key
  }

  function blurTip(key) {
    if (focusKey.value === key) focusKey.value = null
    if (tipKey.value === key) tipKey.value = null
  }

  watch(isCollapsed, (value) => {
    tipKey.value = value ? focusKey.value : null
  })

  watch(tipKey, (key, _previous, onCleanup) => {
    if (!key) return
    const dismiss = (event) => {
      if (event.key === 'Escape') tipKey.value = null
    }
    document.addEventListener('keydown', dismiss)
    onCleanup(() => document.removeEventListener('keydown', dismiss))
  })

  return { tipKey, setTip, focusTip, blurTip }
}
