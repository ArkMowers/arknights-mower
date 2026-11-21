import { onScopeDispose, ref, shallowRef } from 'vue'

export function useLazyForm(load) {
  const component = shallowRef(null)
  const show = ref(false)
  const failed = ref(false)
  let loading = false
  let active = true
  onScopeDispose(() => {
    active = false
  })

  async function open() {
    if (!active || loading) return
    if (!component.value) {
      loading = true
      failed.value = false
      try {
        const { default: form } = await load()
        if (!active) return
        component.value = form
      } catch {
        if (active) failed.value = true
        return
      } finally {
        loading = false
      }
    }
    show.value = true
  }

  return { component, show, failed, open }
}
