<script setup>
import { inject, onMounted, onUnmounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { useMessage } from 'naive-ui'
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
  if (event.defaultPrevented || !isUpdateFileDrag(event) || localDropzone(event)) return
  depth += 1
  dragging.value = true
}

function over(event) {
  if (event.defaultPrevented || !isUpdateFileDrag(event)) return
  if (localDropzone(event)) {
    resetDrag()
    return
  }
  event.preventDefault()
  event.dataTransfer.dropEffect = busy.value ? 'none' : 'copy'
  dragging.value = !busy.value
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
  if (busy.value || resources.installing) {
    messages.warning('正在安装更新包，请等待完成')
    return
  }
  try {
    const file = droppedUpdateFile(event)
    if (updatePackageKind(file) === 'software') {
      pendingSoftwarePackage.value = file
      show.value = false
      await router.push('/mowersettings')
    } else {
      selected.value = file
      result.value = null
      progress.value = 0
      show.value = true
    }
  } catch (error) {
    pendingSoftwarePackage.value = null
    messages.error(error.message)
  }
}

async function installResource() {
  if (busy.value || !selected.value) return
  busy.value = true
  result.value = null
  try {
    result.value = await postManualUpdate(
      axios,
      `${import.meta.env.VITE_HTTP_URL || ''}/hot-update/manual`,
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
        messages.warning('资源包已安装，部分页面数据刷新失败，请刷新页面')
      }
    }
  } catch (error) {
    result.value = {
      ok: false,
      message: error.response?.data?.message || error.message || '安装失败，请重试'
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
    <div v-if="dragging" class="global-update-drop" aria-live="polite">
      <div class="global-update-drop__content">
        <strong>松开文件，准备更新</strong>
        <span>资源包 / 热更包 ZIP · Mower 软件安装包 ZIP、tar.gz、DMG</span>
        <span>一次一个文件，确认后安装</span>
      </div>
    </div>
  </Teleport>
  <n-modal
    v-model:show="show"
    preset="card"
    title="安装资源或热更包"
    style="width: min(560px, calc(100vw - 32px))"
    :closable="!busy"
    :mask-closable="!busy"
    :close-on-esc="!busy"
  >
    <n-space vertical :size="16">
      <n-text style="overflow-wrap: anywhere">{{ selected?.name }}</n-text>
      <n-text depth="3">将按包内容识别资源包或热更包。资源包安装后直接生效，无需重启。</n-text>
      <n-progress v-if="busy" type="line" :percentage="progress" />
      <n-alert v-if="result" :type="result.ok ? 'success' : 'error'" aria-live="polite">{{
        result.message
      }}</n-alert>
      <n-space justify="end">
        <n-button :disabled="busy" @click="show = false">{{
          result?.ok ? '完成' : '取消'
        }}</n-button>
        <n-button v-if="!result?.ok" type="primary" :loading="busy" @click="installResource"
          >确认安装</n-button
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
