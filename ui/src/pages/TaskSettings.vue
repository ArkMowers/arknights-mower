<script setup>
import { onMounted, onUnmounted, ref } from 'vue'
import { i18n } from '@/i18n'
const { t } = i18n.global

import TaskConfiguration from '@/task-workflow/TaskConfiguration.vue'

defineOptions({ name: 'TaskSettings' })
const page = ref(null)
let viewportObserver
onMounted(() => {
  const viewport = page.value?.closest('.layout-content-container')
  if (!viewport || typeof ResizeObserver === 'undefined') return
  const resize = () => {
    page.value?.style.setProperty('--settings-viewport-height', `${viewport.clientHeight}px`)
  }
  viewportObserver = new ResizeObserver(resize)
  viewportObserver.observe(viewport)
  resize()
})
onUnmounted(() => viewportObserver?.disconnect())
</script>

<template>
  <section ref="page" class="task-settings-page" :aria-label="t('tasks.allSettings')">
    <TaskConfiguration />
  </section>
</template>

<style scoped>
.task-settings-page {
  display: flex;
  flex: none;
  flex-direction: column;
  min-height: 0;
  box-sizing: border-box;
  width: 100%;
  max-width: 1720px;
  margin: 0 auto;
  padding: 20px 24px;
  container: main-content / inline-size;
}
@media (max-width: 760px) {
  .task-settings-page {
    padding: 20px 12px;
  }
}
</style>
