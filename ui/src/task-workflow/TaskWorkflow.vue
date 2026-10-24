<script setup>
import { computed, nextTick, ref, watch } from 'vue'
import InfoIcon from '@vicons/fluent/es/Info20Regular'
import TaskChecklistNavigation from './TaskChecklistNavigation.vue'

const props = defineProps({
  workflow: { type: Object, required: true },
  modelValue: { type: String, default: '' },
  layout: { type: String, default: 'checklist' },
  embedded: { type: Boolean, default: false },
  tabbed: { type: Boolean, default: false },
  editorRequest: { type: Number, default: 0 },
  queue: { type: Array, default: () => [] }
})
const emit = defineEmits(['update:modelValue', 'select', 'toggle', 'set-all'])
const heading = ref(null)
const inspectorHeading = ref(null)
const content = ref(null)
const navigation = ref(null)
const navigationCollapsed = ref(false)
const editor = computed(() => props.workflow.editors.find((item) => item.id === props.modelValue))

watch(
  () => [props.modelValue, props.editorRequest],
  () => {
    if (props.layout === 'checklist')
      nextTick(() => {
        if (content.value) content.value.scrollTop = 0
        heading.value?.focus?.({ preventScroll: true })
        const menuBounds = navigation.value?.$el?.getBoundingClientRect?.()
        const titleBounds = inspectorHeading.value?.getBoundingClientRect?.()
        if (
          menuBounds &&
          titleBounds &&
          titleBounds.left < menuBounds.right &&
          titleBounds.right > menuBounds.left
        )
          inspectorHeading.value?.scrollIntoView?.({ block: 'start', behavior: 'instant' })
      })
  }
)
</script>

<template>
  <div
    class="task-workspace"
    :class="{
      'task-workspace--embedded': embedded,
      'task-workspace--waterfall': layout === 'waterfall',
      'task-workspace--navigation-collapsed': layout === 'waterfall' && navigationCollapsed
    }"
  >
    <div class="task-workspace-body">
      <TaskChecklistNavigation
        ref="navigation"
        v-model:collapsed="navigationCollapsed"
        :waterfall="layout === 'waterfall'"
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

      <section
        class="task-inspector"
        :aria-label="layout === 'waterfall' ? '全部设置' : `${editor?.title || '全部设置'}设置`"
      >
        <header ref="inspectorHeading" v-show="layout === 'checklist'" class="inspector-heading">
          <div class="inspector-title">
            <h2 ref="heading" tabindex="-1">{{ editor?.title || '全部设置' }}</h2>
            <n-popover v-if="editor?.description" trigger="click" style="max-width: 320px">
              <template #trigger>
                <button class="inspector-help" type="button" :aria-label="`${editor.title}说明`">
                  <n-icon :component="InfoIcon" :size="18" />
                </button>
              </template>
              {{ editor.description }}
            </n-popover>
          </div>
        </header>
        <div ref="content" class="inspector-content"><slot /></div>
      </section>
    </div>
  </div>
</template>

<style scoped>
.task-workspace {
  display: flex;
  flex: 1;
  flex-direction: column;
  min-width: 0;
  min-height: 0;
  container: task-configuration / inline-size;
  color: var(--mower-text);
}
.task-workspace-body {
  display: grid;
  flex: 1;
  grid-template-columns: 236px minmax(0, 1fr);
  min-height: 360px;
  min-width: 0;
  overflow: hidden;
  border: 1px solid var(--mower-border);
  border-radius: 18px;
  background: var(--mower-surface);
}
.task-inspector {
  display: flex;
  flex-direction: column;
  min-width: 0;
  min-height: 0;
}
.task-workspace--waterfall {
  flex: none;
}
.task-workspace--waterfall .task-workspace-body {
  grid-template-columns: 216px minmax(0, 1fr);
  align-items: start;
  gap: 24px;
  flex: none;
  height: auto;
  min-height: 0;
  overflow: visible;
  border: 0;
  border-radius: 0;
  background: transparent;
}
.task-workspace--waterfall .task-inspector {
  display: block;
  border: 0;
  border-radius: 0;
  background: transparent;
}
.task-workspace--waterfall .inspector-content {
  overflow: visible;
  container: task-waterfall / inline-size;
  padding: 0;
}
.inspector-heading {
  flex: none;
  scroll-margin-top: var(--task-target-scroll-margin, 12px);
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding: 22px 28px;
  border-bottom: 1px solid var(--mower-border);
}
.inspector-title {
  display: flex;
  align-items: center;
  gap: 8px;
  min-width: 0;
}
.inspector-heading h2 {
  margin: 0;
  font-size: 20px;
  line-height: 1.5;
  font-weight: 600;
}
.inspector-heading h2:focus {
  outline: none;
}
.inspector-help {
  border: 0;
  background: transparent;
  font: inherit;
  cursor: pointer;
}
.inspector-help {
  display: inline-flex;
  padding: 3px;
  color: var(--mower-text-muted);
}
.inspector-content {
  min-height: 0;
  overflow-y: auto;
  overscroll-behavior: contain;
  scrollbar-width: thin;
  padding: 24px 28px 32px;
  container: task-inspector / inline-size;
}
button:focus-visible {
  outline: 2px solid var(--mower-primary);
  outline-offset: 3px;
}
@container main-content (max-width: 900px) {
  .task-workspace-body {
    grid-template-columns: 216px minmax(0, 1fr);
  }
  .inspector-heading,
  .inspector-content {
    padding: 18px;
  }
}
@container main-content (max-width: 760px) {
  .task-workspace {
    --task-target-scroll-margin: 64px;
    flex: none;
  }
  .task-workspace-body {
    flex: none;
    grid-template-columns: minmax(0, 1fr);
    height: auto;
    min-height: 0;
    overflow: visible;
  }
  .inspector-heading {
    flex-wrap: wrap;
  }
  .task-workspace--waterfall .task-workspace-body {
    grid-template-columns: minmax(0, 1fr);
    gap: 16px;
  }
}
@container task-configuration (min-width: 1500px) {
  .task-workspace--waterfall .task-workspace-body {
    grid-template-columns: 384px minmax(0, 1fr);
  }
}
.task-workspace--navigation-collapsed .task-workspace-body {
  grid-template-columns: 52px minmax(0, 1fr);
}
@container task-waterfall (min-width: 1080px) {
  .task-workspace--navigation-collapsed
    :deep(.task-settings-panels--waterfall[data-masonry-ready]) {
    max-width: 1210px;
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}
@container main-content (max-width: 760px) {
  .task-workspace--navigation-collapsed .task-workspace-body {
    grid-template-columns: minmax(0, 1fr);
  }
}
</style>
