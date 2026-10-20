<script setup>
import { computed } from 'vue'
import { RouterLink, useRoute, useRouter } from 'vue-router'
import { sessionLocation } from '@/utils/sessionNavigation'

defineOptions({ inheritAttrs: false })
const props = defineProps({
  to: { type: [String, Object], required: true },
  replace: Boolean
})
const router = useRouter()
const route = useRoute()
const destination = computed(() => sessionLocation(router.resolve(props.to), route))

function follow(event, navigate) {
  if (!window.pywebview?.api || event.button > 1 || event.defaultPrevented) {
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
      :class="{ 'router-link-active': isActive, 'router-link-exact-active': isExactActive }"
      @click="follow($event, navigate)"
      @auxclick="follow($event, navigate)"
      ><slot
    /></a>
  </RouterLink>
</template>
