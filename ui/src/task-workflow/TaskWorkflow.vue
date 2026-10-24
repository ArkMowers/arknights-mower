<script setup>
import { computed, ref } from 'vue'
import TaskChecklistNavigation from './TaskChecklistNavigation.vue'

const props = defineProps({
  workflow: { type: Object, required: true },
  modelValue: { type: String, default: '' },
  embedded: { type: Boolean, default: false },
  tabbed: { type: Boolean, default: false },
  editorRequest: { type: Number, default: 0 },
  queue: { type: Array, default: () => [] }
})
const emit = defineEmits(['update:modelValue', 'select', 'toggle', 'set-all'])
const navigationCollapsed = ref(false)
const editor = computed(() => props.workflow.editors.find((item) => item.id === props.modelValue))
</script>

<template>
  <div
    class="task-workspace task-workspace--continuous"
    :class="{
      'task-workspace--embedded': embedded,
      'task-workspace--navigation-collapsed': navigationCollapsed
    }"
  >
    <div class="task-workspace-body">
      <TaskChecklistNavigation
        v-model:collapsed="navigationCollapsed"
        :tasks="workflow.tasks"
        :groups="workflow.groups"
        :selected-id="modelValue === 'idle' ? 'device' : modelValue"
        :selected-title="editor?.title"
        :statuses="workflow.statuses"
        :connection-enabled="workflow.editors.some(({ id }) => id === 'device')"
        :connection-keywords="workflow.editors.find(({ id }) => id === 'device')?.searchKeywords"
        :selection-request="editorRequest"
        @select="emit('select', $event)"
        @toggle="(id, value) => emit('toggle', id, value)"
        @set-all="emit('set-all', $event)"
      />
      <section class="task-inspector" aria-label="全部设置">
        <div class="inspector-content"><slot /></div>
      </section>
    </div>
  </div>
</template>

<style scoped>
.task-workspace {
  flex: none;
  min-width: 0;
  container: task-configuration / inline-size;
  color: var(--mower-text);
}
.task-workspace-body {
  display: grid;
  grid-template-columns: 216px minmax(0, 1fr);
  align-items: start;
  gap: 24px;
  min-width: 0;
}
.task-inspector {
  min-width: 0;
}
.inspector-content {
  container: task-settings-content / inline-size;
}
.task-workspace--navigation-collapsed .task-workspace-body {
  grid-template-columns: 52px minmax(0, 1fr);
}
@container main-content (max-width: 760px) {
  .task-workspace {
    --task-target-scroll-margin: 64px;
  }
  .task-workspace-body,
  .task-workspace--navigation-collapsed .task-workspace-body {
    grid-template-columns: minmax(0, 1fr);
    gap: 16px;
  }
}
</style>
