<script setup>
import { computed } from 'vue'
import { RouterLink, useRoute, useRouter } from 'vue-router'
import { sessionLocation } from '@/utils/sessionNavigation'
import { readWindowShellMetadata } from '@/window-shell/adapter'

defineOptions({ inheritAttrs: false })
const props = defineProps({
  to: { type: [String, Object], required: true },
  replace: Boolean,
  matchHash: Boolean,
  activeClass: { type: String, default: 'router-link-active' },
  exactActiveClass: { type: String, default: 'router-link-exact-active' }
})
const router = useRouter()
const route = useRoute()
const desktopShellRequested = readWindowShellMetadata(globalThis.window?.location).requested
const destination = computed(() => sessionLocation(router.resolve(props.to), route))

const matchesLocation = computed(() => !props.matchHash || route.hash === destination.value.hash)

function follow(event, navigate) {
  if (
    props.matchHash &&
    route.fullPath === router.resolve(destination.value).fullPath &&
    event.button === 0 &&
    !event.defaultPrevented &&
    !event.metaKey &&
    !event.ctrlKey &&
    !event.shiftKey &&
    !event.altKey
  ) {
    event.preventDefault()
    return router.replace({ ...destination.value, force: true })
  }
  if (
    (!desktopShellRequested && !window.pywebview?.api) ||
    event.button > 1 ||
    event.defaultPrevented
  ) {
    return navigate(event)
  }
  event.preventDefault()
  return router[props.replace ? 'replace' : 'push'](destination.value)
}
</script>

<template>
  <RouterLink
    v-slot="{ href, navigate, isActive, isExactActive }"
    :to="destination"
    :replace="replace"
    custom
  >
    <a
      v-bind="$attrs"
      :href="href"
      :aria-current="
        isExactActive && matchesLocation ? (matchHash ? 'location' : 'page') : undefined
      "
      :class="{
        [activeClass]: isActive && matchesLocation,
        [exactActiveClass]: isExactActive && matchesLocation
      }"
      @click="follow($event, navigate)"
      @auxclick="follow($event, navigate)"
      ><slot
    /></a>
  </RouterLink>
</template>
