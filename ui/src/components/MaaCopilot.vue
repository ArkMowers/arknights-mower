<script setup>
import { computed, inject, onMounted, ref } from 'vue'
import { storeToRefs } from 'pinia'
import { useMessage } from 'naive-ui'
import { useConfigStore } from '@/stores/config'
import { copilotMessage, downloadCopilotScripts } from '@/utils/maaCopilotCode'
import { i18n } from '@/i18n'

const { t } = i18n.global

const props = defineProps({ paradox: { type: Boolean, default: false } })
const store = useConfigStore()
const configs = storeToRefs(store)
const copilot = computed(() => (props.paradox ? configs.paradox.value : configs.copilot.value))
const axios = inject('axios')
const mobile = inject('mobile')
const message = useMessage()
const endpoint = `${import.meta.env.VITE_HTTP_URL || ''}/${props.paradox ? 'maa-paradox' : 'maa-copilot'}`
const library = ref([])
const selected = ref(null)
const code = ref('')
const loading = ref(false)
const options = computed(() =>
  library.value.map((item) => ({ label: `${item.stage_name} · ${item.title}`, value: item.id }))
)
const selected_in_queue = computed(() =>
  copilot.value.scripts.some((item) => item.id === selected.value)
)
const formation_options = computed(() =>
  [0, 1, 2, 3, 4].map((value) => ({
    value,
    label: value
      ? t('maaQueue.formationNumber', { number: value })
      : t('maaQueue.noFormationSwitch')
  }))
)
const support_options = computed(() =>
  ['supportNone', 'supportOneMissing', 'supportSpecifiedFallback', 'supportRandomFallback'].map(
    (key, value) => ({ value, label: t(`maaQueue.${key}`) })
  )
)
const skill_options = computed(() =>
  [0, 1, 2, 3].map((value) => ({
    value,
    label: value ? t('maaQueue.skillNumber', { number: value }) : t('maaQueue.defaultSkill')
  }))
)

async function refresh() {
  try {
    library.value = (await axios.get(endpoint)).data.scripts
  } catch (error) {
    message.error(copilotMessage(error.response?.data?.message) || t('maaQueue.readFailed'))
  }
}
onMounted(refresh)

function queue_item(id) {
  return props.paradox ? { id } : { id, nav_name_override: '', is_raid: false }
}
function add_script(id) {
  if (!id || copilot.value.scripts.length >= 32) return
  copilot.value.scripts.push(queue_item(id))
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
      32 - copilot.value.scripts.length
    )
    await refresh()
    if (copilot.value.scripts.length + scripts.length > 32) {
      throw new Error('队列已变更且剩余容量不足。队列未改变，已入库作业可从已有作业中选择')
    }
    copilot.value.scripts.push(...scripts.map(({ id }) => queue_item(id)))
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
  const scripts = [...copilot.value.scripts]
  const target = index + offset
  if (target < 0 || target >= scripts.length) return
  ;[scripts[index], scripts[target]] = [scripts[target], scripts[index]]
  copilot.value.scripts = scripts
}
function title(id) {
  const item = library.value.find((item) => item.id === id)
  return item ? `${item.stage_name} · ${item.title}` : t('maaQueue.fileMissing')
}
function add_operator() {
  copilot.value.user_additional.push({ name: '', skill: 0 })
}
async function restart_queue() {
  copilot.value.run_id = Array.from(crypto.getRandomValues(new Uint32Array(4)), (value) =>
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
        <n-text depth="3">{{ t('maaQueue.ordinaryImportHelp') }}</n-text>
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
            :disabled="!selected || copilot.scripts.length >= 32"
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
        <n-empty v-if="!copilot.scripts.length" :description="t('tasks.noOperationSelected')" />
        <n-card
          v-for="(item, index) in copilot.scripts"
          :key="index"
          size="small"
          :title="`${index + 1}. ${title(item.id)}`"
        >
          <n-flex vertical>
            <n-input
              v-if="!paradox"
              v-model:value="item.nav_name_override"
              :placeholder="t('maaQueue.navStagePlaceholder')"
            />
            <n-checkbox v-if="!paradox" v-model:checked="item.is_raid">{{
              t('maaQueue.raidMode')
            }}</n-checkbox>
            <n-flex>
              <n-button :disabled="index === 0" @click="move(index, -1)">{{
                t('maaQueue.moveUp')
              }}</n-button>
              <n-button :disabled="index === copilot.scripts.length - 1" @click="move(index, 1)">{{
                t('maaQueue.moveDown')
              }}</n-button>
              <n-button @click="copilot.scripts.splice(index, 1)">{{
                t('maaQueue.removeFromQueue')
              }}</n-button>
            </n-flex>
          </n-flex>
        </n-card>
        <n-text v-if="!paradox" depth="3">{{ t('maaQueue.ordinaryQueueHelp') }}</n-text>
        <n-text v-else depth="3">{{ t('maaQueue.paradoxQueueHelp') }}</n-text>
        <n-button :disabled="!copilot.scripts.length" @click="restart_queue">{{
          t('maaQueue.restart')
        }}</n-button>
      </n-flex>
    </n-form-item>
    <n-form-item v-if="!paradox" :show-label="false"
      ><n-checkbox v-model:checked="copilot.use_sanity_potion">{{
        t('maaQueue.allowPotion')
      }}</n-checkbox></n-form-item
    >
    <n-form-item v-if="!paradox" :show-label="false"
      ><n-checkbox v-model:checked="copilot.formation">{{
        t('maaQueue.autoFormation')
      }}</n-checkbox></n-form-item
    >
    <template v-if="!paradox && copilot.formation">
      <n-form-item :label="t('maaQueue.formationLabel')"
        ><n-select v-model:value="copilot.formation_index" :options="formation_options"
      /></n-form-item>
      <n-form-item :show-label="false"
        ><n-checkbox v-model:checked="copilot.add_trust">{{
          t('maaQueue.fillTrust')
        }}</n-checkbox></n-form-item
      >
      <n-form-item :show-label="false"
        ><n-checkbox v-model:checked="copilot.ignore_requirements">{{
          t('maaQueue.ignoreRequirements')
        }}</n-checkbox></n-form-item
      >
      <n-form-item :label="t('maaQueue.specifiedSupport')"
        ><n-input
          v-model:value="copilot.support_unit_name"
          :placeholder="t('maaQueue.supportNamePlaceholder')"
      /></n-form-item>
      <n-form-item :label="t('maaQueue.supportMode')"
        ><n-select v-model:value="copilot.support_unit_usage" :options="support_options"
      /></n-form-item>
      <n-form-item :label="t('maaQueue.additionalOperators')">
        <n-flex vertical style="width: 100%">
          <n-flex v-for="(item, index) in copilot.user_additional" :key="index" :wrap="false">
            <n-input
              v-model:value="item.name"
              :placeholder="t('maaQueue.operatorNamePlaceholder')"
            />
            <n-select
              v-model:value="item.skill"
              :options="skill_options"
              style="min-width: 110px"
            />
            <n-button @click="copilot.user_additional.splice(index, 1)">{{
              t('maaQueue.remove')
            }}</n-button>
          </n-flex>
          <n-button v-if="copilot.user_additional.length < 12" @click="add_operator">{{
            t('maaQueue.addOperator')
          }}</n-button>
        </n-flex>
      </n-form-item>
    </template>
  </n-form>
</template>
