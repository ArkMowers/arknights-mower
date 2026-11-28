import { onActivated, onDeactivated, onMounted, onScopeDispose, ref, watch } from 'vue'

export function onFirstPanelVisit(host, visit, eager = () => false) {
  const active = ref(false)
  const visited = ref(false)
  let observer

  function disconnect() {
    observer?.disconnect()
    observer = undefined
  }

  function start() {
    if (!active.value || visited.value) return
    visited.value = true
    disconnect()
    return visit()
  }

  function observe() {
    if (!active.value || visited.value) return
    const element = host.value?.$el ?? host.value
    const Observer = element?.ownerDocument?.defaultView?.IntersectionObserver
    if (eager() || !Observer) return start()
    if (observer) return
    observer = new Observer(
      (entries, current) => {
        if (observer === current && entries.some((entry) => entry.isIntersecting)) start()
      },
      { rootMargin: '240px 0px' }
    )
    observer.observe(element)
  }

  function activate() {
    active.value = true
    return observe()
  }

  function deactivate() {
    active.value = false
    disconnect()
  }

  watch(eager, observe)
  onMounted(activate)
  onActivated(activate)
  onDeactivated(deactivate)
  onScopeDispose(deactivate)
  return { active, visited }
}
