<script setup>
import { computed } from 'vue'
import { RouterLink, useRoute, useRouter } from 'vue-router'
import { sessionLocation } from '@/utils/sessionNavigation'
import { readWindowShellMetadata } from '@/window-shell/adapter'

defineOptions({ inheritAttrs: false })
const props = defineProps({
  to: { type: [String, Object], required: true },
  replace: Boolean,
  activeClass: { type: String, default: 'router-link-active' },
  exactActiveClass: { type: String, default: 'router-link-exact-active' }
})
const router = useRouter()
const route = useRoute()
const desktopShellRequested = readWindowShellMetadata(globalThis.window?.location).requested
const destination = computed(() => sessionLocation(router.resolve(props.to), route))

function follow(event, navigate) {
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
      :aria-current="isExactActive ? 'page' : undefined"
      :class="{ [activeClass]: isActive, [exactActiveClass]: isExactActive }"
      @click="follow($event, navigate)"
      @auxclick="follow($event, navigate)"
      ><slot
    /></a>
  </RouterLink>
</template>
