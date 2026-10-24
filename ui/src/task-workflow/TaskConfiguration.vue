<script setup>
import { computed, inject, nextTick, ref, watch } from 'vue'
import { routeLocationKey } from 'vue-router'
import { useConfigStore } from '@/stores/config'
import { deviceConnectionNavigationKey } from '@/composables/deviceConnectionNavigation'
import TaskSettingsPanels from '@/components/TaskSettingsPanels.vue'
import TaskWorkflow from './TaskWorkflow.vue'
import { createTaskWorkflow, setTaskEnabled } from './model'

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
const requestedTarget = ref('')
const panels = ref(null)
const editorRequest = ref(0)
const workflow = computed(() => createTaskWorkflow(config))
watch(activeEditor, (id) => emit('editing', Boolean(id)), { flush: 'sync' })
watch(
  [workflow, activeEditor],
  () => {
    if (activeEditor.value && !workflow.value.editors.some(({ id }) => id === activeEditor.value))
      activeEditor.value = 'base'
  },
  { flush: 'sync' }
)
watch(editorRequest, () => {
  nextTick(() => panels.value?.revealActive?.(requestedTarget.value))
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

function openEditor(id, target = '') {
  if (!workflow.value.editors.some((editor) => editor.id === id)) return
  emit('reveal')
  requestedTarget.value = target
  selectEditor(id)
  editorRequest.value += 1
}

defineExpose({ openEditor })

async function revealHash(hash) {
  const target = hash?.replace(/^#/, '')
  if (!target) return
  if (legacyEditors[target]) {
    openEditor(legacyEditors[target], target)
    return
  }
  const request = editorRequest.value
  await nextTick()
  if (request !== editorRequest.value) return
  const editor = panels.value?.resolveTarget?.(target) || legacyEditors[target]
  if (editor) openEditor(editor, target)
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
  const anchor = event.target.closest?.('a[href^="#"]')
  const target = anchor?.getAttribute('href').slice(1)
  const editor = panels.value?.resolveTarget?.(target) || legacyEditors[target]
  if (!editor) return
  event.preventDefault()
  openEditor(editor, target)
}
</script>

<template>
  <TaskWorkflow
    v-model="activeEditor"
    :workflow="workflow"
    :embedded="embedded"
    :tabbed="tabbed"
    :queue="queue"
    :editor-request="editorRequest"
    @select="openEditor"
    @toggle="(id, value) => setTaskEnabled(config, id, value)"
  >
    <div @click="followLegacyLink">
      <TaskSettingsPanels
        ref="panels"
        :active="activeEditor"
        @select="openEditor"
        @visible-editor="selectEditor"
      />
    </div>
  </TaskWorkflow>
</template>
