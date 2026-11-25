<script setup>
import { computed, inject, onMounted } from 'vue'
import { storeToRefs } from 'pinia'
import { useMessage } from 'naive-ui'
import { useConfigStore } from '@/stores/config'
import { appendCopilotScript, useCopilotLibrary } from '@/utils/maaCopilotCode'
import MaaTaskStatus from '@/components/MaaTaskStatus.vue'

const props = defineProps({ paradox: { type: Boolean, default: false } })
const store = useConfigStore()
const configs = storeToRefs(store)
const copilot = computed(() => (props.paradox ? configs.paradox.value : configs.copilot.value))
const axios = inject('axios')
const mobile = inject('mobile')
const message = useMessage()
const kind = props.paradox ? 'paradox' : 'copilot'
const {
  backupWarning,
  code,
  canDelete,
  delete_script,
  download,
  failures,
  library,
  loading,
  refresh,
  selected,
  upload
} = useCopilotLibrary({ axios, configs, kind, message, store })
onMounted(refresh)
const options = computed(() =>
  library.value.map((item) => ({ label: `${item.stage_name} · ${item.title}`, value: item.id }))
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

function add_script(id) {
  const script = library.value.find((item) => item.id === id)
  if (!script) return
  appendCopilotScript(configs, kind, script)
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
    <n-form-item v-if="!paradox" :show-label="false">
      <n-alert type="warning" :show-icon="false">
        请先在“AI 助手与模型服务”中配置 Mower AI 使用的模型服务，再使用普通作业的自动地图导航。Mower
        会先进入目标关卡地图，导航失败时不启动 MAA。
      </n-alert>
    </n-form-item>
    <n-form-item label="目前状态">
      <MaaTaskStatus :kind="paradox ? 'paradox' : 'copilot'" :settings="copilot" />
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
        <n-text v-if="paradox" depth="3">
          支持悖论模拟作业和作业集（如 s123）。单个文件最多 1 MB。
        </n-text>
        <n-text v-else depth="3">
          支持普通自动战斗作业。导入作业集（如
          s123）时，普通作业和保全作业按顺序加入各自队列。单个文件最多 1 MB。
        </n-text>
        <n-alert v-if="backupWarning" type="warning">{{ backupWarning }}</n-alert>
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
        <n-empty v-if="!copilot.scripts.length" description="尚未选择作业" />
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
              placeholder="导航关卡名，例如 1-7（留空由作业确定）"
            />
            <n-checkbox v-if="!paradox" v-model:checked="item.is_raid">突袭模式</n-checkbox>
            <n-flex>
              <n-button :disabled="index === 0" @click="move(index, -1)">上移</n-button>
              <n-button :disabled="index === copilot.scripts.length - 1" @click="move(index, 1)"
                >下移</n-button
              >
              <n-button @click="copilot.scripts.splice(index, 1)">移出队列</n-button>
            </n-flex>
          </n-flex>
        </n-card>
        <n-text v-if="!paradox" depth="3"
          >按队列顺序执行。作业同时支持普通和突袭时，依次加入普通、突袭两项。Mower
          先进入每份作业对应的关卡地图，MAA
          再定位关卡并执行作业；无法识别作业内部关卡标识时，请填写导航关卡名。请确认作业与关卡、难度及干员练度相符。中断后从未完成项重新执行，已完成项会保存并跳过；整轮完成后停止。清缓存启动保留进度。修改执行队列会开启新一轮，调整编队或理智药设置保留已完成项。</n-text
        >
        <n-text v-else depth="3">
          导入 mem_ 开头关卡的悖论模拟作业。MAA 自动寻找对应干员并选择作业技能；Mower
          会先通过导航栏进入干员列表，无需手动打开页面，请确认已解锁悖论模拟。中断后重新执行未完成项，已完成项会保存并跳过；清缓存启动保留进度。队列全部完成后等待手动重跑，修改队列开启新一轮。
        </n-text>
        <n-button :disabled="!copilot.scripts.length" @click="restart_queue"
          >重新执行整份队列</n-button
        >
      </n-flex>
    </n-form-item>
    <n-form-item v-if="!paradox" :show-label="false"
      ><n-checkbox v-model:checked="copilot.use_sanity_potion"
        >允许使用理智药</n-checkbox
      ></n-form-item
    >
    <n-form-item v-if="!paradox" :show-label="false"
      ><n-checkbox v-model:checked="copilot.formation">自动编队</n-checkbox></n-form-item
    >
    <template v-if="!paradox && copilot.formation">
      <n-form-item :show-label="false">
        <n-flex vertical>
          <n-checkbox v-model:checked="copilot.operbox_assist">使用干员练度辅助编队</n-checkbox>
          <n-text depth="3">
            需要 MAA v6.19.0 或更新版本。请先在「养成规划」中刷新当前账号的森空岛干员练度。MAA
            会按作业要求选择干员，无法配齐时停止执行。
          </n-text>
        </n-flex>
      </n-form-item>
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
