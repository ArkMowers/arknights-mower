<script setup>
import { computed, inject, nextTick, ref, watch } from 'vue'
import { routeLocationKey } from 'vue-router'
import { useConfigStore } from '@/stores/config'
import { useGuiStore } from '@/stores/gui'
import { deviceConnectionNavigationKey } from '@/composables/deviceConnectionNavigation'
import TaskSettingsPanels from '@/components/TaskSettingsPanels.vue'
import TaskWorkflow from './TaskWorkflow.vue'
import { createTaskWorkflow, setAllTasksEnabled, setTaskEnabled } from './model'

defineProps({
  embedded: { type: Boolean, default: false },
  tabbed: { type: Boolean, default: false },
  queue: { type: Array, default: () => [] }
})
const emit = defineEmits(['reveal', 'editing'])

const config = useConfigStore()
const route = inject(routeLocationKey, null)
const deviceConnectionNavigation = inject(deviceConnectionNavigationKey, null)
const activeEditor = ref('base')
const gui = useGuiStore()
const layout = computed(() => (gui.taskSettingsLayout === 'waterfall' ? 'waterfall' : 'checklist'))
const panels = ref(null)
const editorRequest = ref(0)
const workflow = computed(() => createTaskWorkflow(config))
watch(activeEditor, (id) => emit('editing', Boolean(id)), { flush: 'sync' })
watch([activeEditor, editorRequest], () => {
  if (layout.value === 'waterfall') nextTick(() => panels.value?.revealActive?.())
})
const legacyEditors = {
  'task-devices': 'device',
  'task-runtime': 'runtime',
  'task-base': 'base',
  'task-daily': 'skland',
  'task-long': 'long',
  'task-accounts': 'accounts',
  'task-maa': 'maa'
}

function selectEditor(id) {
  if (workflow.value.editors.some((editor) => editor.id === id)) activeEditor.value = id
}

function openEditor(id) {
  if (!workflow.value.editors.some((editor) => editor.id === id)) return
  emit('reveal')
  selectEditor(id)
  editorRequest.value += 1
}

defineExpose({ openEditor })

function revealHash(hash) {
  const target = hash?.replace(/^#/, '')
  if (legacyEditors[target]) {
    openEditor(legacyEditors[target])
  }
}

watch(() => route?.hash, revealHash, { immediate: true })

watch(
  () => deviceConnectionNavigation?.request.value,
  (request) => {
    if (!request) return
    openEditor('device')
  },
  { flush: 'sync', immediate: true }
)

function followLegacyLink(event) {
  const anchor = event.target.closest?.('a[href^="#task-"]')
  const editor = legacyEditors[anchor?.getAttribute('href').slice(1)]
  if (!editor) return
  event.preventDefault()
  openEditor(editor)
}
</script>

<template>
  <TaskWorkflow
    v-model="activeEditor"
    :layout="layout"
    :workflow="workflow"
    :embedded="embedded"
    :tabbed="tabbed"
    :queue="queue"
    :editor-request="editorRequest"
    @select="openEditor"
    @toggle="(id, value) => setTaskEnabled(config, id, value)"
    @set-all="setAllTasksEnabled(config, $event)"
  >
    <div @click="followLegacyLink">
      <TaskSettingsPanels
        ref="panels"
        :active="activeEditor"
        :checklist="layout === 'checklist'"
        :layout="layout"
        @select="openEditor"
      />
    </div>
  </TaskWorkflow>
</template>
