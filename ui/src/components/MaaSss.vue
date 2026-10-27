<script setup>
import { computed, inject, onMounted, ref } from 'vue'
import { storeToRefs } from 'pinia'
import { useMessage } from 'naive-ui'
import { useConfigStore } from '@/stores/config'
import { copilotMessage, downloadCopilotScripts } from '@/utils/maaCopilotCode'
import { i18n } from '@/i18n'
import { operatorDisplayName } from '@/i18n/gameNames'

const { t } = i18n.global

const store = useConfigStore()
const { sss } = storeToRefs(store)
const axios = inject('axios')
const mobile = inject('mobile')
const message = useMessage()
const endpoint = `${import.meta.env.VITE_HTTP_URL || ''}/sss-copilot`
const library = ref([])
const selected = ref(null)
const code = ref('')
const loading = ref(false)
const options = computed(() =>
  library.value.map((item) => ({ label: `${item.stage_name} · ${item.title}`, value: item.id }))
)
const selected_in_queue = computed(() =>
  sss.value.scripts.some((item) => item.id === selected.value)
)
async function refresh() {
  try {
    library.value = (await axios.get(endpoint)).data.scripts
  } catch (error) {
    message.error(copilotMessage(error.response?.data?.message) || t('maaQueue.readFailed'))
  }
}
onMounted(refresh)

function add_script(id) {
  if (!id || sss.value.scripts.length >= 32) return
  sss.value.scripts.push({ id, type: 1, ec: 1, times: 1 })
}
async function upload_blob(blob) {
  const form = new FormData()
  form.append('copilot', blob)
  const { data } = await axios.post(endpoint, form)
  await refresh()
  selected.value = data.id
  add_script(data.id)
  message.success(t('maaQueue.imported'))
}
async function upload({ file, onFinish, onError }) {
  loading.value = true
  try {
    await upload_blob(file.file)
    onFinish()
  } catch (error) {
    message.error(copilotMessage(error.response?.data?.message) || t('maaQueue.importFailed'))
    onError()
  } finally {
    loading.value = false
  }
}
async function download() {
  if (loading.value) return
  loading.value = true
  try {
    const scripts = await downloadCopilotScripts(
      axios,
      code.value,
      endpoint,
      32 - sss.value.scripts.length
    )
    await refresh()
    if (sss.value.scripts.length + scripts.length > 32) {
      throw new Error('队列已变更且剩余容量不足。队列未改变，已入库作业可从已有作业中选择')
    }
    sss.value.scripts.push(...scripts.map(({ id }) => ({ id, type: 1, ec: 1, times: 1 })))
    selected.value = scripts.at(-1).id
    code.value = ''
    message.success(t('maaQueue.importedCount', { count: scripts.length }))
  } catch (error) {
    if (error.refreshLibrary) await refresh()
    message.error(
      copilotMessage(error.response?.data?.message || error.message) || t('maaQueue.downloadFailed')
    )
  } finally {
    loading.value = false
  }
}
async function delete_script() {
  if (!selected.value || selected_in_queue.value) return
  try {
    await store.flush_config_saves()
    await axios.delete(`${endpoint}/${selected.value}`)
    selected.value = null
    await refresh()
  } catch (error) {
    message.error(copilotMessage(error.response?.data?.message) || t('maaQueue.deleteFailed'))
  }
}
function move(index, offset) {
  const scripts = [...sss.value.scripts]
  const target = index + offset
  if (target < 0 || target >= scripts.length) return
  ;[scripts[index], scripts[target]] = [scripts[target], scripts[index]]
  sss.value.scripts = scripts
}
function info(id) {
  return library.value.find((item) => item.id === id)
}
function title(id) {
  const item = library.value.find((item) => item.id === id)
  return item ? `${item.stage_name} · ${item.title}` : t('maaQueue.fileMissing')
}
async function restart_queue() {
  sss.value.run_id = Array.from(crypto.getRandomValues(new Uint32Array(4)), (value) =>
    value.toString(16).padStart(8, '0')
  ).join('')
  try {
    await store.flush_config_saves()
    message.success(t('maaQueue.restarted'))
  } catch (error) {
    message.error(copilotMessage(error.response?.data?.message) || t('maaQueue.restartSaveFailed'))
  }
}
</script>

<template>
  <n-form :label-placement="mobile ? 'top' : 'left'" :show-feedback="false">
    <n-form-item :label="t('tasks.importCopilot')">
      <n-flex vertical style="width: 100%">
        <n-flex :wrap="mobile">
          <n-input
            v-model:value="code"
            :style="{ flex: mobile ? '1 1 100%' : '1 1 0', minWidth: '0' }"
            :placeholder="t('maaQueue.codePlaceholder')"
            :disabled="loading"
            @keydown.enter="download"
          />
          <n-button :loading="loading" @click="download">{{ t('tasks.download') }}</n-button>
          <n-upload
            accept=".json,application/json"
            :custom-request="upload"
            :show-file-list="false"
            :disabled="loading"
            style="width: auto"
          >
            <n-button :disabled="loading">{{ t('tasks.chooseCopilotFile') }}</n-button>
          </n-upload>
        </n-flex>
        <n-text depth="3">{{ t('maaQueue.sssImportHelp') }}</n-text>
      </n-flex>
    </n-form-item>
    <n-form-item :label="t('maaQueue.existingScripts')">
      <n-flex vertical style="width: 100%">
        <n-select
          v-model:value="selected"
          :options="options"
          filterable
          clearable
          :placeholder="t('maaQueue.selectScript')"
        />
        <n-flex>
          <n-button
            :disabled="!selected || sss.scripts.length >= 32"
            @click="add_script(selected)"
            >{{ t('maaQueue.addToQueue') }}</n-button
          >
          <n-button :disabled="!selected || selected_in_queue" @click="delete_script">{{
            t('maaQueue.deleteUnused')
          }}</n-button>
        </n-flex>
      </n-flex>
    </n-form-item>
    <n-form-item :label="t('maaQueue.executionQueue')">
      <n-flex vertical style="width: 100%">
        <n-empty v-if="!sss.scripts.length" :description="t('tasks.noOperationSelected')" />
        <n-card
          v-for="(item, index) in sss.scripts"
          :key="index"
          size="small"
          :title="`${index + 1}. ${title(item.id)}`"
        >
          <n-flex vertical>
            <n-text v-if="info(item.id)?.details" style="white-space: pre-wrap">{{
              info(item.id).details
            }}</n-text>
            <n-text v-if="info(item.id)?.operators?.length" depth="3">{{
              t('maaQueue.operators', {
                names: info(item.id)
                  .operators.map((operator) =>
                    t('maaQueue.operatorSkill', {
                      name: operatorDisplayName(operator.name),
                      skill: operator.skill
                    })
                  )
                  .join(', ')
              })
            }}</n-text>
            <n-flex align="center">
              <span>{{ t('tasks.stage') }}</span>
              <help-text><n-image src="/help/sss-type.png" /></help-text>
              <n-radio-group v-model:value="item.type">
                <n-space
                  ><n-radio v-for="value in 2" :key="value" :value="value">{{
                    value
                  }}</n-radio></n-space
                >
              </n-radio-group>
            </n-flex>
            <n-flex align="center">
              <span>{{ t('tasks.sssEquipment') }}</span>
              <n-radio-group v-model:value="item.ec">
                <n-space
                  ><n-radio v-for="value in 3" :key="value" :value="value">{{
                    value
                  }}</n-radio></n-space
                >
              </n-radio-group>
            </n-flex>
            <n-flex align="center">
              <span>{{ t('maaQueue.rounds') }}</span>
              <n-input-number
                :value="item.times"
                :min="1"
                :max="9999"
                :precision="0"
                :update-value-on-input="false"
                :show-feedback="false"
                :on-update:value="(value) => (item.times = value ?? 1)"
              />
            </n-flex>
            <n-flex>
              <n-button :disabled="index === 0" @click="move(index, -1)">{{
                t('maaQueue.moveUp')
              }}</n-button>
              <n-button :disabled="index === sss.scripts.length - 1" @click="move(index, 1)">{{
                t('maaQueue.moveDown')
              }}</n-button>
              <n-button @click="sss.scripts.splice(index, 1)">{{
                t('maaQueue.removeFromQueue')
              }}</n-button>
            </n-flex>
          </n-flex>
        </n-card>
        <n-text depth="3">{{ t('maaQueue.sssQueueHelp') }}</n-text>
        <n-button :disabled="!sss.scripts.length" @click="restart_queue">{{
          t('maaQueue.restart')
        }}</n-button>
      </n-flex>
    </n-form-item>
  </n-form>
</template>
