<script setup>
import { publicAsset } from '@/utils/publicAsset'
import { computed, inject, onMounted } from 'vue'
import { storeToRefs } from 'pinia'
import { useMessage } from 'naive-ui'
import { useConfigStore } from '@/stores/config'
import { appendCopilotScript, useCopilotLibrary } from '@/utils/maaCopilotCode'
import MaaTaskStatus from '@/components/MaaTaskStatus.vue'

const store = useConfigStore()
const configs = storeToRefs(store)
const { sss } = configs
const axios = inject('axios')
const mobile = inject('mobile')
const message = useMessage()
const kind = 'sss'
const {
  backupWarning,
  code,
  canDelete,
  delete_script,
  download,
  failures,
  rosterReports,
  library,
  loading,
  refresh,
  selected,
  upload
} = useCopilotLibrary({ axios, configs, kind, message, store })
const rosterIssues = computed(
  () => rosterReports.value.filter((script) => script.roster_check.status !== 'ready').length
)
onMounted(refresh)
const options = computed(() =>
  library.value.map((item) => ({ label: `${item.stage_name} · ${item.title}`, value: item.id }))
)
function add_script(id) {
  if (!id) return
  appendCopilotScript(configs, kind, { id })
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
  return item ? `${item.stage_name} · ${item.title}` : '作业文件缺失，请重新导入'
}
async function restart_queue() {
  sss.value.run_id = Array.from(crypto.getRandomValues(new Uint32Array(4)), (value) =>
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
    <n-form-item label="目前状态">
      <MaaTaskStatus kind="sss" :settings="sss" />
    </n-form-item>
    <n-form-item label="导入作业">
      <n-flex vertical style="width: 100%">
        <n-flex :wrap="false">
          <n-input
            v-model:value="code"
            placeholder="prts://作业或作业集代码、prts.plus 作业链接"
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
        <n-text depth="3">
          支持保全派驻作业。导入作业集（如
          s123）时，普通作业和保全作业按顺序加入各自队列。单个文件最多 1
          MB。请提前在游戏中准备编队。
        </n-text>
        <n-alert v-if="backupWarning" type="warning">{{ backupWarning }}</n-alert>
        <n-text v-if="rosterIssues" type="warning">
          本次导入的普通作业中，有 {{ rosterIssues }} 份需要核对练度，可在普通自动战斗队列查看详情。
        </n-text>
        <details v-if="failures.length">
          <summary>导入结果 · {{ failures.length }} 份作业未加入队列</summary>
          <ul>
            <li v-for="failure in failures" :key="failure">{{ failure }}</li>
          </ul>
        </details>
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
          <n-button :disabled="!selected" @click="add_script(selected)">加入队列</n-button>
          <n-button :disabled="!canDelete" @click="delete_script">删除未选作业</n-button>
        </n-flex>
      </n-flex>
    </n-form-item>
    <n-form-item label="执行队列">
      <n-flex vertical style="width: 100%">
        <n-empty v-if="!sss.scripts.length" description="尚未选择作业" />
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
            <n-text v-if="info(item.id)?.operators?.length" depth="3"
              >干员：{{
                info(item.id)
                  .operators.map((operator) => `${operator.name}（${operator.skill} 技能）`)
                  .join('、')
              }}</n-text
            >
            <n-flex align="center">
              <span>关卡</span>
              <help-text><n-image :src="publicAsset('/help/sss-type.png')" /></help-text>
              <n-radio-group v-model:value="item.type">
                <n-space
                  ><n-radio v-for="value in 2" :key="value" :value="value">{{
                    value
                  }}</n-radio></n-space
                >
              </n-radio-group>
            </n-flex>
            <n-flex align="center">
              <span>导能单元</span>
              <n-radio-group v-model:value="item.ec">
                <n-space
                  ><n-radio v-for="value in 3" :key="value" :value="value">{{
                    value
                  }}</n-radio></n-space
                >
              </n-radio-group>
            </n-flex>
            <n-flex align="center">
              <span>刷取次数</span>
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
              <n-button :disabled="index === 0" @click="move(index, -1)">上移</n-button>
              <n-button :disabled="index === sss.scripts.length - 1" @click="move(index, 1)"
                >下移</n-button
              >
              <n-button @click="sss.scripts.splice(index, 1)">移出队列</n-button>
            </n-flex>
          </n-flex>
        </n-card>
        <n-text depth="3"
          >按顺序执行。每次完整通关一轮才计数，可为两处关卡分别添加作业和次数。中断后保留已完成轮数，当前轮交由
          MAA
          从游戏现状接续。全部完成后停止，等待手动重跑；清缓存启动保留进度。修改队列、关卡、导能单元或次数会开启新一轮。未通关时暂停本队列，等待修改队列或手动重跑。</n-text
        >
        <n-button :disabled="!sss.scripts.length" @click="restart_queue">重新执行整份队列</n-button>
      </n-flex>
    </n-form-item>
  </n-form>
</template>
