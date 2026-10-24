<script setup>
import TaskConfiguration from '@/task-workflow/TaskConfiguration.vue'

defineOptions({ name: 'TaskSettings' })
</script>

<template>
  <section class="task-settings-page" aria-label="全部设置">
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
