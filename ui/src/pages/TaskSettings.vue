<script setup>
import TaskConfiguration from '@/task-workflow/TaskConfiguration.vue'

defineOptions({ name: 'TaskSettings' })
</script>

<template>
  <section class="task-settings-page" aria-label="任务配置">
    <h1>任务配置</h1>
    <TaskConfiguration />
  </section>
</template>

<style scoped>
.task-settings-page {
  display: flex;
  flex: 1;
  flex-direction: column;
  min-height: 0;
  box-sizing: border-box;
  width: 100%;
  max-width: 1320px;
  margin: 0 auto;
  padding: 24px;
  container: main-content / inline-size;
}
.task-settings-page:has(.task-workspace--waterfall) {
  flex: none;
  max-width: 1800px;
}
h1 {
  flex: none;
  margin: 0 0 22px;
  color: var(--mower-text);
  font-size: 25px;
  font-weight: 650;
  line-height: 1.3;
}
@container main-content (max-width: 760px) {
  .task-settings-page {
    flex: none;
  }
}
@media (max-width: 760px) {
  .task-settings-page {
    padding: 20px 12px;
  }
}
</style>
