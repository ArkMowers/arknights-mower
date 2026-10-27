<script setup>
import { computed, inject, onMounted, ref } from 'vue'
import { storeToRefs } from 'pinia'
import { useMessage } from 'naive-ui'
import { useConfigStore } from '@/stores/config'
import { parseCopilotCode } from '@/utils/maaCopilotCode'

const store = useConfigStore()
const { copilot } = storeToRefs(store)
const axios = inject('axios')
const mobile = inject('mobile')
const message = useMessage()
const endpoint = `${import.meta.env.VITE_HTTP_URL || ''}/maa-copilot`
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
const formation_options = [0, 1, 2, 3, 4].map((value) => ({
  value,
  label: value ? `第 ${value} 编队` : '不切换编队'
}))
const support_options = [
  { label: '不使用助战', value: 0 },
  { label: '只补一名缺失干员', value: 1 },
  { label: '补缺失干员，否则使用指定助战', value: 2 },
  { label: '补缺失干员，否则使用随机助战', value: 3 }
]
const skill_options = [0, 1, 2, 3].map((value) => ({
  value,
  label: value ? `${value} 技能` : '默认技能'
}))

async function refresh() {
  try {
    library.value = (await axios.get(endpoint)).data.scripts
  } catch (error) {
    message.error(error.response?.data?.message || '读取作业失败')
  }
}
onMounted(refresh)

function add_script(id) {
  if (!id || copilot.value.scripts.length >= 32) return
  copilot.value.scripts.push({ id, nav_name_override: '', is_raid: false })
}
async function upload_blob(blob) {
  const form = new FormData()
  form.append('copilot', blob)
  const { data } = await axios.post(endpoint, form)
  await refresh()
  selected.value = data.id
  add_script(data.id)
  message.success('作业已导入并加入队列')
}
async function upload({ file, onFinish, onError }) {
  loading.value = true
  try {
    await upload_blob(file.file)
    onFinish()
  } catch (error) {
    message.error(error.response?.data?.message || '作业导入失败')
    onError()
  } finally {
    loading.value = false
  }
}
async function download() {
  let number
  try {
    number = parseCopilotCode(code.value)
  } catch (error) {
    message.error(error.message)
    return
  }
  loading.value = true
  try {
    const { data } = await axios.get(
      `${import.meta.env.VITE_HTTP_URL || ''}/network/maa-copilot/${number}`
    )
    await upload_blob(new Blob([data.data.content], { type: 'application/json' }))
    code.value = ''
  } catch (error) {
    message.error(error.response?.data?.message || '作业下载失败，请检查网络代理')
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
    message.error(error.response?.data?.message || '删除作业失败')
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
  return item ? `${item.stage_name} · ${item.title}` : '作业文件缺失，请重新导入'
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
    message.success('已开启新一轮作业，下次大型任务空闲时从首项执行')
  } catch (error) {
    message.error(error.response?.data?.message || '保存重新执行请求失败')
  }
}
</script>

<template>
  <n-form :label-placement="mobile ? 'top' : 'left'" :show-feedback="false">
    <n-form-item label="导入作业">
      <n-flex vertical style="width: 100%">
        <n-flex :wrap="false">
          <n-input
            v-model:value="code"
            placeholder="prts://作业编号或 prts.plus 作业链接"
            :disabled="loading"
            @keydown.enter="download"
          />
          <n-button :loading="loading" @click="download">下载</n-button>
          <n-upload
            accept=".json,application/json"
            :custom-request="upload"
            :show-file-list="false"
            :disabled="loading"
            style="width: auto"
          >
            <n-button :disabled="loading">选择文件</n-button>
          </n-upload>
        </n-flex>
        <n-text depth="3"
          >支持普通自动战斗作业；保全作业请在保全派驻中导入。单个文件最多 1 MB。</n-text
        >
      </n-flex>
    </n-form-item>
    <n-form-item label="已有作业">
      <n-flex vertical style="width: 100%">
        <n-select
          v-model:value="selected"
          :options="options"
          filterable
          clearable
          placeholder="选择已导入的作业"
        />
        <n-flex>
          <n-button
            :disabled="!selected || copilot.scripts.length >= 32"
            @click="add_script(selected)"
            >加入队列</n-button
          >
          <n-button :disabled="!selected || selected_in_queue" @click="delete_script"
            >删除未选作业</n-button
          >
        </n-flex>
      </n-flex>
    </n-form-item>
    <n-form-item label="执行队列">
      <n-flex vertical style="width: 100%">
        <n-empty v-if="!copilot.scripts.length" description="尚未选择作业" />
        <n-card
          v-for="(item, index) in copilot.scripts"
          :key="index"
          size="small"
          :title="`${index + 1}. ${title(item.id)}`"
        >
          <n-flex vertical>
            <n-input
              v-model:value="item.nav_name_override"
              placeholder="导航关卡名（留空由作业确定）"
            />
            <n-checkbox v-model:checked="item.is_raid">突袭模式</n-checkbox>
            <n-flex>
              <n-button :disabled="index === 0" @click="move(index, -1)">上移</n-button>
              <n-button :disabled="index === copilot.scripts.length - 1" @click="move(index, 1)"
                >下移</n-button
              >
              <n-button @click="copilot.scripts.splice(index, 1)">移出队列</n-button>
            </n-flex>
          </n-flex>
        </n-card>
        <n-text depth="3"
          >按队列顺序执行，最多 32 项。关卡导航由 MAA
          完成；请确认作业与关卡、难度及干员练度相符。中断后从未完成项重新执行，已完成项会保存并跳过；整轮完成后停止。清缓存启动保留进度。修改执行队列会开启新一轮，调整编队或理智药设置保留已完成项。</n-text
        >
        <n-button :disabled="!copilot.scripts.length" @click="restart_queue"
          >重新执行整份队列</n-button
        >
      </n-flex>
    </n-form-item>
    <n-form-item :show-label="false"
      ><n-checkbox v-model:checked="copilot.use_sanity_potion"
        >允许使用理智药</n-checkbox
      ></n-form-item
    >
    <n-form-item :show-label="false"
      ><n-checkbox v-model:checked="copilot.formation">自动编队</n-checkbox></n-form-item
    >
    <template v-if="copilot.formation">
      <n-form-item label="使用编队"
        ><n-select v-model:value="copilot.formation_index" :options="formation_options"
      /></n-form-item>
      <n-form-item :show-label="false"
        ><n-checkbox v-model:checked="copilot.add_trust"
          >空位补充低信赖干员</n-checkbox
        ></n-form-item
      >
      <n-form-item :show-label="false"
        ><n-checkbox v-model:checked="copilot.ignore_requirements"
          >忽略可跳过的干员练度要求</n-checkbox
        ></n-form-item
      >
      <n-form-item label="指定助战"
        ><n-input
          v-model:value="copilot.support_unit_name"
          placeholder="干员中文名（指定助战模式使用）"
      /></n-form-item>
      <n-form-item label="助战方式"
        ><n-select v-model:value="copilot.support_unit_usage" :options="support_options"
      /></n-form-item>
      <n-form-item label="补充干员">
        <n-flex vertical style="width: 100%">
          <n-flex v-for="(item, index) in copilot.user_additional" :key="index" :wrap="false">
            <n-input v-model:value="item.name" placeholder="干员中文名" />
            <n-select
              v-model:value="item.skill"
              :options="skill_options"
              style="min-width: 110px"
            />
            <n-button @click="copilot.user_additional.splice(index, 1)">移除</n-button>
          </n-flex>
          <n-button v-if="copilot.user_additional.length < 12" @click="add_operator"
            >添加干员</n-button
          >
        </n-flex>
      </n-form-item>
    </template>
  </n-form>
</template>
