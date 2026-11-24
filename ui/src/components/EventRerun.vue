<script setup>
import { computed, inject, onMounted, onUnmounted, ref, watch } from 'vue'
import { storeToRefs } from 'pinia'
import { useMessage } from 'naive-ui'
import { downloadCopilotFile, parseCopilotCode } from '@/utils/maaCopilotCode'
import { useConfigStore } from '@/stores/config'
import { useResourceVersionStore } from '@/stores/resourceVersion'

const { event_rerun } = storeToRefs(useConfigStore())
const resourceVersion = useResourceVersionStore()
const axios = inject('axios')
const mobile = inject('mobile')
const message = useMessage()
const base = import.meta.env.VITE_HTTP_URL || ''
const event = ref(null)
const progress = ref({})
const stageSeconds = ref(240)
const loaded = ref(false)
const loadError = ref('')
const scripts = ref([])
const importing = ref(false)
const code = ref('')
let statusRequest
let timer
let disposed = false

const selected = computed(() =>
  event_rerun.value.event_key === event.value?.key
    ? event_rerun.value
    : {
        stages: [],
        use_sanity_potion: event_rerun.value.use_sanity_potion ?? true,
        raid_enabled: false,
        script_id: ''
      }
)
const scriptStageNames = computed(
  () => new Set((event.value?.raid?.script_stage_names ?? []).map((name) => name.toLowerCase()))
)
function matchesRaid(script) {
  return scriptStageNames.value.has(script.stage_name?.trim().toLowerCase())
}
const options = computed(() =>
  scripts.value.filter(matchesRaid).map((script) => ({
    label: `${script.stage_name} · ${script.title}`,
    value: script.id
  }))
)
const expectedMinutes = computed(
  () =>
    ((selected.value.stages.length + Number(selected.value.raid_enabled)) * stageSeconds.value) / 60
)

function updateSettings(changes) {
  if (!event.value) return
  event_rerun.value = { ...selected.value, ...changes, event_key: event.value.key }
}

function statusLabel(code) {
  if (progress.value[code] === 'completed') return '已完成'
  if (progress.value[code] === 'attempted') return '已启动，结算待确认'
  return ''
}

async function refreshStatus() {
  if (statusRequest) return statusRequest
  statusRequest = (async () => {
    try {
      const { data } = await axios.get(`${base}/maa-long-task-status?kind=event_rerun`)
      event.value = data.event
      progress.value = data.progress
      stageSeconds.value = data.stage_seconds
      loadError.value = ''
    } catch (error) {
      loadError.value = error.response?.data?.message || '读取复刻SS活动失败'
    } finally {
      loaded.value = true
    }
  })()
  try {
    await statusRequest
  } finally {
    statusRequest = null
  }
}

async function refreshScripts() {
  const { data } = await axios.get(`${base}/maa-copilot`)
  scripts.value = data.scripts
}

async function importScript(file) {
  if (importing.value) return false
  const eventKey = event.value?.key
  importing.value = true
  try {
    const body = new FormData()
    if (!file) {
      const target = parseCopilotCode(code.value)
      if (target.set) throw new Error('突袭只使用一份作业，请粘贴单份作业码或详情页链接')
      file = await downloadCopilotFile(axios, target.id)
    }
    body.append('copilot', file)
    const { data } = await axios.post(`${base}/maa-copilot`, body)
    await refreshScripts()
    if (!disposed && event.value?.key === eventKey && selected.value.raid_enabled) {
      if (matchesRaid(data)) updateSettings({ script_id: data.id })
      else message.error('作业已导入，关卡与本期 EX-8 不符')
    }
    return true
  } catch (error) {
    message.error(error.response?.data?.message || error.message || '作业导入失败')
    return false
  } finally {
    importing.value = false
  }
}

async function upload({ file, onFinish, onError }) {
  if (await importScript(file.file)) onFinish()
  else onError()
}

async function download() {
  if (await importScript()) code.value = ''
}

onMounted(() => {
  refreshStatus()
  refreshScripts().catch((error) => message.error(error.response?.data?.message || '读取作业失败'))
  timer = setInterval(refreshStatus, 5000)
})
onUnmounted(() => {
  disposed = true
  clearInterval(timer)
})
watch(() => resourceVersion.info.current_version, refreshStatus)
</script>

<template>
  <n-alert v-if="loadError" type="error">{{ loadError }}</n-alert>
  <n-text v-else-if="!loaded" depth="3">正在读取复刻SS活动</n-text>
  <n-empty v-else-if="!event" description="当前资源包没有开放的复刻SS活动" />
  <n-form v-else :label-placement="mobile ? 'top' : 'left'" :show-feedback="false">
    <n-form-item label="本期活动">{{ event.name }}</n-form-item>
    <n-form-item label="理智恢复">
      <n-checkbox
        :checked="selected.use_sanity_potion"
        @update:checked="updateSettings({ use_sanity_potion: $event })"
      >
        允许使用理智药
      </n-checkbox>
    </n-form-item>
    <n-form-item label="普通关">
      <n-checkbox-group :value="selected.stages" @update:value="updateSettings({ stages: $event })">
        <n-space :size="[12, 4]">
          <n-checkbox v-for="stage in event.stages" :key="stage.code" :value="stage.code">
            {{ stage.code }} {{ stage.name }}
            <n-tag v-if="statusLabel(stage.code)" size="small" :bordered="false">
              {{ statusLabel(stage.code) }}
            </n-tag>
          </n-checkbox>
        </n-space>
      </n-checkbox-group>
    </n-form-item>
    <template v-if="event.raid">
      <n-form-item label="EX-8 突袭">
        <n-space align="center">
          <n-checkbox
            :checked="selected.raid_enabled"
            @update:checked="updateSettings({ raid_enabled: $event })"
          >
            启用 {{ event.raid.code }} · 自动编队
          </n-checkbox>
          <n-tag v-if="statusLabel(event.raid.code)" size="small" :bordered="false">
            {{ statusLabel(event.raid.code) }}
          </n-tag>
        </n-space>
      </n-form-item>
      <n-form-item v-if="selected.raid_enabled" label="突袭作业">
        <n-flex style="width: 100%">
          <n-input
            v-model:value="code"
            placeholder="prts:// 作业码、编号或作业详情页链接"
            aria-label="突袭作业码"
            :disabled="importing"
            style="flex: 1; min-width: 180px"
            @keyup.enter="download"
          />
          <n-button :disabled="importing || !code.trim()" @click="download">导入作业码</n-button>
          <n-a href="https://prts.plus/" target="_blank" rel="noopener noreferrer"
            >PRTS Plus 作业站</n-a
          >
        </n-flex>
      </n-form-item>
      <n-form-item v-if="selected.raid_enabled" label="已导入作业">
        <n-flex style="width: 100%">
          <n-select
            :value="selected.script_id || null"
            :options="options"
            :disabled="importing"
            filterable
            clearable
            placeholder="选择对应 EX-8 的作业"
            style="flex: 1; min-width: 180px"
            @update:value="updateSettings({ script_id: $event || '' })"
          />
          <n-upload
            accept=".json,application/json"
            :custom-request="upload"
            :show-file-list="false"
            :disabled="importing"
            style="width: auto"
          >
            <n-button :loading="importing">导入 JSON</n-button>
          </n-upload>
        </n-flex>
      </n-form-item>
    </template>
    <n-text depth="3" class="event-rerun-estimate">
      每关预留 {{ stageSeconds / 60 }} 分钟，已选关卡预计共 {{ expectedMinutes }} 分钟。
      已开始的关卡结算后再交回调度。
    </n-text>
  </n-form>
</template>

<style scoped>
.event-rerun-estimate {
  font-variant-numeric: tabular-nums;
  text-wrap: pretty;
}
</style>
