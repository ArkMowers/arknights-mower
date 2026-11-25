<script setup>
import { computed, inject, onMounted, ref } from 'vue'
import { storeToRefs } from 'pinia'
import ChevronDown from '@vicons/ionicons5/es/ChevronDown'
import { useMessage, useThemeVars } from 'naive-ui'
import { useConfigStore } from '@/stores/config'
import { appendCopilotScript, useCopilotLibrary } from '@/utils/maaCopilotCode'
import StageProgressButton from './StageProgressButton.vue'
import CopilotRosterReport from './CopilotRosterReport.vue'
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
  rosterReports,
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

const taskStatus = ref(null)
const savingProgress = ref(false)
const expandedItem = ref(null)
const theme = useThemeVars()
const scriptsById = computed(() => new Map(library.value.map((script) => [script.id, script])))
const queueProgress = computed(() => {
  const detail = taskStatus.value?.detail
  const { scripts, run_id } = copilot.value
  if (
    !detail?.queue_key ||
    detail.run_id !== (run_id || '') ||
    detail.items?.length !== scripts.length ||
    detail.scripts?.length !== scripts.length
  )
    return null
  const matches = scripts.every((item, index) => {
    const saved = detail.scripts[index]
    return (
      saved.id === item.id &&
      (props.paradox ||
        (saved.is_raid === (item.is_raid ?? false) &&
          saved.nav_name_override === (item.nav_name_override ?? '')))
    )
  })
  return matches ? detail : null
})

async function setCompleted(index, completed) {
  const detail = queueProgress.value
  const expected = detail?.items[index]
  if (savingProgress.value || !expected || expected === 'running') return
  savingProgress.value = true
  try {
    await axios.patch(`${import.meta.env.VITE_HTTP_URL || ''}/maa-long-task-status?kind=${kind}`, {
      queue_key: detail.queue_key,
      index,
      expected,
      completed
    })
  } catch (error) {
    message.error(error.response?.data?.message || '保存作业状态失败')
  } finally {
    await taskStatus.value?.refresh()
    savingProgress.value = false
  }
}

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
function remove(index) {
  copilot.value.scripts.splice(index, 1)
  expandedItem.value = null
}
function add_operator() {
  copilot.value.user_additional.push({ name: '', skill: 0 })
}
</script>

<template>
  <n-form :label-placement="mobile ? 'top' : 'left'" :show-feedback="false">
    <n-form-item label="目前状态">
      <MaaTaskStatus ref="taskStatus" :kind="kind" :settings="copilot" />
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
          支持已解锁关卡的悖论模拟作业和作业集（如 s123）。单个文件最多 1 MB。
        </n-text>
        <n-text v-else depth="3">
          支持普通自动战斗作业。导入作业集（如
          s123）时，普通作业和保全作业按顺序加入各自队列。同时支持普通和突袭的作业会加入两项。单个文件最多
          1 MB。
        </n-text>
        <n-alert v-if="backupWarning" type="warning">{{ backupWarning }}</n-alert>
        <CopilotRosterReport
          v-if="rosterReports.length"
          :scripts="rosterReports"
          :settings="configs.copilot.value"
        />
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
        <ol v-else class="queue-list" aria-label="执行队列">
          <li v-for="(item, index) in copilot.scripts" :key="index" class="queue-item">
            <div class="queue-row">
              <n-text class="queue-number" depth="3">{{ index + 1 }}</n-text>
              <div class="queue-script">
                <div class="queue-stage">
                  <n-text strong>{{
                    item.nav_name_override || scriptsById.get(item.id)?.stage_name
                  }}</n-text>
                  <n-tag
                    v-if="!paradox"
                    size="small"
                    :type="item.is_raid ? 'warning' : 'default'"
                    :bordered="false"
                  >
                    {{ item.is_raid ? '突袭' : '普通' }}
                  </n-tag>
                </div>
                <n-text depth="2" class="queue-title">{{
                  scriptsById.get(item.id)?.title || '作业文件缺失，请重新导入'
                }}</n-text>
              </div>
              <StageProgressButton
                v-if="queueProgress"
                :status="queueProgress.items[index]"
                :subject="`第 ${index + 1} 项作业`"
                :disabled="savingProgress"
                @set-completed="setCompleted(index, $event)"
              />
              <n-button
                circle
                quaternary
                class="queue-disclosure"
                :aria-label="`${expandedItem === item ? '收起' : '展开'}第 ${index + 1} 项作业设置`"
                :aria-expanded="expandedItem === item"
                @click="expandedItem = expandedItem === item ? null : item"
              >
                <template #icon
                  ><n-icon><ChevronDown /></n-icon
                ></template>
              </n-button>
            </div>
            <div v-if="expandedItem === item" class="queue-editor">
              <label v-if="!paradox" class="queue-navigation">
                导航关卡名
                <n-input
                  v-model:value="item.nav_name_override"
                  placeholder="留空时使用作业中的关卡名"
                />
              </label>
              <n-checkbox v-if="!paradox" v-model:checked="item.is_raid">突袭模式</n-checkbox>
              <n-flex align="center" size="small">
                <n-button size="small" :disabled="index === 0" @click="move(index, -1)"
                  >上移</n-button
                >
                <n-button
                  size="small"
                  :disabled="index === copilot.scripts.length - 1"
                  @click="move(index, 1)"
                  >下移</n-button
                >
                <n-button size="small" quaternary type="error" @click="remove(index)"
                  >移出队列</n-button
                >
              </n-flex>
            </div>
          </li>
        </ol>
        <n-text v-if="taskStatus?.detail && !queueProgress" type="warning">
          队列已变更，请刷新页面以查看当前作业进度。
        </n-text>
        <n-text depth="3">
          点击作业状态可切换「待执行」和「已完成」。调整队列会重新记录进度。
        </n-text>
      </n-flex>
    </n-form-item>
    <n-form-item v-if="!paradox" label="队列统一设置">
      <div class="queue-settings" role="group" aria-label="队列统一设置">
        <n-text depth="3">以下设置应用于全部作业，修改后保留已完成进度。</n-text>
        <n-flex align="center" :size="[20, 8]">
          <n-checkbox v-model:checked="copilot.use_sanity_potion">允许使用理智药</n-checkbox>
          <n-checkbox v-model:checked="copilot.formation">自动编队</n-checkbox>
        </n-flex>
        <template v-if="copilot.formation">
          <div class="formation-fields">
            <div class="formation-field">
              <span>使用编队</span>
              <n-select
                v-model:value="copilot.formation_index"
                :options="formation_options"
                aria-label="使用编队"
              />
            </div>
            <div class="formation-field">
              <span>助战方式</span>
              <n-select
                v-model:value="copilot.support_unit_usage"
                :options="support_options"
                aria-label="助战方式"
              />
            </div>
            <label v-if="copilot.support_unit_usage === 2" class="formation-field">
              指定助战
              <n-input v-model:value="copilot.support_unit_name" placeholder="干员中文名" />
            </label>
          </div>
          <n-flex :size="[20, 8]">
            <n-checkbox v-model:checked="copilot.add_trust">空位补充低信赖干员</n-checkbox>
            <n-checkbox v-model:checked="copilot.ignore_requirements"
              >忽略可跳过的干员练度要求</n-checkbox
            >
          </n-flex>
          <div class="formation-field">
            <span>补充干员</span>
            <div
              v-for="(item, index) in copilot.user_additional"
              :key="index"
              class="additional-operator"
            >
              <n-input v-model:value="item.name" placeholder="干员中文名" />
              <n-select
                v-model:value="item.skill"
                :options="skill_options"
                :aria-label="`第 ${index + 1} 名补充干员的技能`"
              />
              <n-button quaternary @click="copilot.user_additional.splice(index, 1)">移除</n-button>
            </div>
            <n-button
              v-if="copilot.user_additional.length < 12"
              class="add-operator"
              size="small"
              @click="add_operator"
              >添加干员</n-button
            >
          </div>
        </template>
      </div>
    </n-form-item>
  </n-form>
</template>

<style scoped>
.queue-settings {
  display: grid;
  gap: 12px;
  width: 100%;
  min-width: 0;
}
.formation-fields {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(min(100%, 200px), 1fr));
  align-items: start;
  gap: 12px;
}
.formation-field {
  display: grid;
  gap: 6px;
  min-width: 0;
}
.additional-operator {
  display: grid;
  grid-template-columns: minmax(0, 1fr) minmax(95px, 140px) auto;
  align-items: center;
  gap: 6px;
}
.add-operator {
  justify-self: start;
}
.queue-list {
  list-style: none;
  padding: 0;
  margin: 0;
  border: 1px solid v-bind('theme.dividerColor');
  border-radius: calc(10px * var(--mower-corner-scale, 1));
}
.queue-item + .queue-item {
  border-top: 1px solid v-bind('theme.dividerColor');
}
.queue-row {
  display: flex;
  gap: 10px;
  align-items: center;
  padding: 9px 10px;
}
.queue-number {
  min-width: 2ch;
  text-align: center;
  font-size: 12px;
  font-variant-numeric: tabular-nums;
}
.queue-script {
  flex: 1;
  min-width: 0;
  overflow-wrap: anywhere;
}
.queue-stage {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 6px;
  font-variant-numeric: tabular-nums;
}
.queue-title {
  display: block;
  margin-top: 2px;
  font-size: 13px;
}
.queue-disclosure {
  width: 40px;
  height: 40px;
}
.queue-disclosure[aria-expanded='true'] :deep(svg) {
  transform: rotate(180deg);
}
.queue-editor {
  display: grid;
  gap: 10px;
  padding: 4px 14px 14px 40px;
}
.queue-navigation {
  display: grid;
  gap: 4px;
}
@media (max-width: 600px) {
  .queue-row {
    gap: 6px;
    padding-inline: 6px;
  }
  .queue-editor {
    padding-inline: 12px;
  }
  .queue-row :deep(button),
  .queue-editor :deep(button) {
    min-height: 40px;
  }
}
</style>
