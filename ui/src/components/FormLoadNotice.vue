<script setup>
import StatusNotification from './StatusNotification.vue'

defineProps({ title: String, show: Boolean })
const emit = defineEmits(['retry'])

function reload() {
  window.location.reload()
}
</script>

<template>
  <StatusNotification
    :show="show"
    :title="title"
    type="error"
    role="alert"
    content="请重新加载表单。若仍无法打开，请刷新页面。"
  >
    <template #action>
      <n-space>
        <n-button size="small" @click="emit('retry')">重新加载表单</n-button>
        <n-button size="small" @click="reload">刷新页面</n-button>
      </n-space>
    </template>
  </StatusNotification>
</template>
