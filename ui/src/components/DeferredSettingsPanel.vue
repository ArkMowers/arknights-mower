<script setup>
import { onServerPrefetch, ref, shallowRef, watch } from 'vue'
import { useLazyForm } from '@/composables/lazyForm'
import { onFirstPanelVisit } from '@/composables/firstPanelVisit'

const props = defineProps({
  load: { type: Function, required: true },
  title: { type: String, required: true },
  eager: Boolean
})
const host = ref(null)
const { component, failed, open } = useLazyForm(() => props.load())
const visibleComponent = shallowRef(null)
const { active } = onFirstPanelVisit(host, open, () => props.eager)
watch([component, active, () => props.eager], ([form, current, eager]) => {
  if ((current || eager) && form) visibleComponent.value = form
})
onServerPrefetch(async () => {
  await open()
  visibleComponent.value = component.value
})

function reload() {
  window.location.reload()
}
</script>

<template>
  <div
    ref="host"
    class="settings-card-wide"
    :class="{ 'deferred-settings-panel--pending': !visibleComponent }"
  >
    <component :is="visibleComponent" v-if="visibleComponent" />
    <n-alert v-else-if="failed" type="error" :title="`${title}加载失败`">
      <n-space>
        <n-button size="small" @click="open">重试</n-button>
        <n-button size="small" @click="reload">刷新页面</n-button>
      </n-space>
    </n-alert>
  </div>
</template>

<style scoped>
.deferred-settings-panel--pending {
  min-block-size: 8rem;
}
</style>
