<script setup>
import { i18n } from '@/i18n'
const { t } = i18n.global

import { inject, onMounted, onUnmounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { useMessage } from 'naive-ui'
import { resourceUpdateMessage } from '@/utils/resourceUpdatePresentation'
import { useConfigStore } from '@/stores/config'
import { usePlanStore } from '@/stores/plan'
import { useResourceVersionStore } from '@/stores/resourceVersion'
import { pendingSoftwarePackage } from '@/stores/updateUpload'
import {
  droppedUpdateFile,
  isUpdateFileDrag,
  postManualUpdate,
  updatePackageKind
} from '@/utils/manualUpdate'

const axios = inject('axios')
const router = useRouter()
const messages = useMessage()
const resources = useResourceVersionStore()
const config = useConfigStore()
const plan = usePlanStore()
const dragging = ref(false)
const show = ref(false)
const selected = ref(null)
const busy = ref(false)
const result = ref(null)
const progress = ref(0)
const reading = ref(false)
let disposed = false
let depth = 0

function resetDrag() {
  dragging.value = false
  depth = 0
}

function localDropzone(event) {
  return (
    event.target instanceof Element &&
    event.target.closest(
      '.n-upload, input, textarea, [contenteditable="true"], [draggable="true"], [data-update-dropzone], [data-no-update-drop]'
    )
  )
}

function enter(event) {
  if (localDropzone(event)) {
    resetDrag()
    return
  }
  if (event.defaultPrevented || !isUpdateFileDrag(event)) return
  depth += 1
  dragging.value = true
}

function over(event) {
  if (localDropzone(event)) {
    resetDrag()
    return
  }
  if (event.defaultPrevented || !isUpdateFileDrag(event)) return
  event.preventDefault()
  event.dataTransfer.dropEffect = busy.value || reading.value ? 'none' : 'copy'
  dragging.value = !busy.value && !reading.value
}

function leave() {
  depth = Math.max(0, depth - 1)
  if (!depth) dragging.value = false
}

async function drop(event) {
  resetDrag()
  if (event.defaultPrevented || !isUpdateFileDrag(event) || localDropzone(event)) return
  event.preventDefault()
  event.stopPropagation()
  if (busy.value || reading.value || resources.installing) {
    messages.warning(t('runtime.updateBusy'))
    return
  }
  reading.value = true
  try {
    const file = droppedUpdateFile(event)
    const kind = await updatePackageKind(file)
    if (disposed) return
    if (!kind) throw new Error(t('runtime.unrecognizedUpdate'))
    if (kind === 'software') {
      pendingSoftwarePackage.value = file
      show.value = false
      await router.push('/mowersettings#software-update-manual')
    } else {
      selected.value = file
      result.value = null
      progress.value = 0
      show.value = true
    }
  } catch (error) {
    if (!disposed) messages.error(error.message)
  } finally {
    reading.value = false
  }
}

async function installResource() {
  if (busy.value || reading.value || !selected.value) return
  busy.value = true
  result.value = null
  try {
    result.value = await postManualUpdate(
      axios,
      `${import.meta.env.VITE_HTTP_URL || ''}/resource-update/manual`,
      selected.value,
      ({ percent }) => {
        progress.value = percent
      }
    )
    if (result.value.ok && result.value.kind === 'resource') {
      await resources.loadResourceVersionLocal()
      const refreshed = await Promise.allSettled([
        config.load_item(),
        config.load_shop(),
        plan.load_operators()
      ])
      if (refreshed.some((item) => item.status === 'rejected')) {
        messages.warning(t('runtime.resourceRefreshFailed'))
      }
    }
  } catch (error) {
    result.value = {
      ok: false,
      message: error.response?.data?.message || error.message || t('runtime.installationFailed')
    }
  } finally {
    busy.value = false
  }
}

onMounted(() => {
  // Bubble after existing upload/sort handlers; never take over a consumed event.
  window.addEventListener('dragenter', enter)
  window.addEventListener('dragover', over)
  window.addEventListener('dragleave', leave)
  window.addEventListener('drop', drop)
  window.addEventListener('drop', resetDrag, true)
  window.addEventListener('dragend', resetDrag)
  window.addEventListener('blur', resetDrag)
  document.addEventListener('visibilitychange', resetDrag)
})
onUnmounted(() => {
  disposed = true
  window.removeEventListener('dragenter', enter)
  window.removeEventListener('dragover', over)
  window.removeEventListener('dragleave', leave)
  window.removeEventListener('drop', drop)
  window.removeEventListener('drop', resetDrag, true)
  window.removeEventListener('dragend', resetDrag)
  window.removeEventListener('blur', resetDrag)
  document.removeEventListener('visibilitychange', resetDrag)
})
</script>

<template>
  <Teleport to="body">
    <div v-if="dragging || reading" class="global-update-drop" aria-live="polite">
      <div class="global-update-drop__content">
        <strong>{{ reading ? t('runtime.readingUpdate') : t('runtime.releaseForUpdate') }}</strong>
        <span>{{ t('runtime.updateFormats') }}</span>
        <span>{{ t('runtime.oneUpdateFile') }}</span>
      </div>
    </div>
  </Teleport>
  <n-modal
    v-model:show="show"
    preset="card"
    :title="t('runtime.installResource')"
    style="width: min(560px, calc(100vw - 32px))"
    :closable="!busy"
    :mask-closable="!busy"
    :close-on-esc="!busy"
  >
    <n-space vertical :size="16">
      <n-text style="overflow-wrap: anywhere">{{ selected?.name }}</n-text>
      <n-text depth="3">{{ t('runtime.resourceImmediate') }}</n-text>
      <n-progress v-if="busy" type="line" :percentage="progress" />
      <n-alert v-if="result" :type="result.ok ? 'success' : 'error'" aria-live="polite">{{
        resourceUpdateMessage(result.message)
      }}</n-alert>
      <n-space justify="end">
        <n-button :disabled="busy" @click="show = false">{{
          result?.ok ? t('runtime.done') : t('runtime.cancel')
        }}</n-button>
        <n-button
          v-if="!result?.ok"
          type="primary"
          :disabled="reading"
          :loading="busy"
          @click="installResource"
          >{{ t('runtime.confirmInstall') }}</n-button
        >
      </n-space>
    </n-space>
  </n-modal>
</template>

<style scoped>
.global-update-drop {
  position: fixed;
  inset: 12px;
  z-index: 10000;
  display: grid;
  place-items: center;
  padding: 24px;
  border: 2px dashed #36ad6a;
  border-radius: 16px;
  background: rgba(24, 80, 49, 0.94);
  color: white;
  pointer-events: none;
}
.global-update-drop__content {
  display: grid;
  gap: 16px;
  text-align: center;
  text-wrap: pretty;
}
.global-update-drop strong {
  font-size: 24px;
}
</style>
