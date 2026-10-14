<script setup>
import { computed, inject, onMounted, onBeforeUnmount, reactive, ref, watch } from 'vue'
import {
  defaultIncomeSettings,
  incomeFacilities,
  incomeMetrics,
  incomeRequest,
  inventoryRequired,
  applyMowerIncomeSettings
} from '@/riic/income'
import { applyIncomeCache } from '@/riic/incomeCache'
import { incomeAlgorithms, incomeAlgorithmLabel, incomeSettingsUrl } from '@/utils/incomeSettings'
import { createIncomeSession } from '@/riic/incomeSession'
import { loadIncomeArchive, saveIncomeArchive } from '@/riic/incomeArchive'
import { incomeLogTime } from '@/riic/incomeLogs'
import IncomeTimeline from './IncomeTimeline.vue'
import {
  renderIncomeImage,
  downloadIncomeImage,
  incomeReportLines,
  incomeImageFilename
} from '@/riic/incomeImage'
import { MOWER_INVENTORY_ITEMS } from '@/riic/vendor/domain/simulationInventory'

const props = defineProps({ snapshot: Object, preparing: Boolean, prepareError: String })
const emit = defineEmits(['close'])
const settings = reactive(defaultIncomeSettings())
const axios = inject('axios')
const cacheLoading = ref(false)
const cacheError = ref('')
const weightsBusy = ref(false)
const weightsError = ref('')
const submitting = ref(false)
const controller = new AbortController()
let alive = true
let sharedRatios = null
const stock = computed(() =>
  settings.inventorySource === 'cache' ? settings.cachedInventory : settings.initialInventory
)
const weightValues = computed(() =>
  settings.weightMode === 'mower' ? settings.mowerWeights : settings.productionWeights
)
const cachedRosterCount = computed(() => settings.cachedOperators?.length ?? 0)
async function readCache() {
  cacheLoading.value = true
  cacheError.value = ''
  try {
    const { data } = await axios.get(`${import.meta.env.VITE_HTTP_URL}/riic/income-cache`, {
      timeout: 15000,
      signal: controller.signal
    })
    if (alive) applyIncomeCache(settings, data)
  } catch (error) {
    if (alive) cacheError.value = '森空岛缓存读取失败，可重新读取或选择手动输入'
  } finally {
    if (alive) cacheLoading.value = false
  }
}
async function readWeights() {
  weightsBusy.value = true
  weightsError.value = ''
  try {
    const { data } = await axios.get(incomeSettingsUrl, {
      timeout: 15000,
      signal: controller.signal
    })
    if (alive) {
      applyMowerIncomeSettings(settings, data)
      sharedRatios = data.ratios
    }
  } catch (error) {
    if (alive) weightsError.value = 'Mower 收益设置读取失败，可重试或选择本次自定义'
    throw new Error('Mower 收益设置读取失败，可重试或选择本次自定义')
  } finally {
    if (alive) weightsBusy.value = false
  }
}
async function selectAlgorithm(value) {
  const preset = incomeAlgorithms.find((item) => item.value === value)
  if (!preset?.ratios || !sharedRatios || weightsBusy.value) return
  weightsBusy.value = true
  weightsError.value = ''
  try {
    const { data: latest } = await axios.get(incomeSettingsUrl, {
      timeout: 15000,
      signal: controller.signal
    })
    if (!alive) return
    const { data } = await axios.put(
      incomeSettingsUrl,
      {
        base_algorithm: value,
        ratios: { ...latest.ratios, ...preset.ratios }
      },
      { timeout: 15000, signal: controller.signal }
    )
    if (alive) {
      applyMowerIncomeSettings(settings, data)
      sharedRatios = data.ratios
    }
  } catch (error) {
    if (alive) weightsError.value = '算法保存失败，请重新读取 Mower 设置确认'
  } finally {
    if (alive) weightsBusy.value = false
  }
}
onMounted(() => Promise.allSettled([readCache(), readWeights(), restoreResult()]))
const state = reactive({
  running: false,
  result: null,
  error: null,
  progress: null,
  bottleneck: null,
  input: null
})
const exporting = ref(false)
const exportError = ref('')
const exported = ref(false)
const exportName = ref('')
const completedSnapshot = ref(null)
const archiveLoading = ref(true)
const archiveError = ref('')
const attemptDiagnostics = ref([])
const savedAt = ref(null)
let lastCompleted = null
let runSnapshot = null
const imageName = computed(
  () => exportName.value.trim() || completedSnapshot.value?.label || '排班'
)
const seconds = ref(0)
const activeTab = ref('settings')
const progressLog = ref([])
const logPage = ref(1)
const logSearch = ref('')
const filteredEvents = computed(() =>
  (state.result?.eventLog?.entries ?? []).filter((row) =>
    `${row.type} ${row.room} ${row.detail}`.toLowerCase().includes(logSearch.value.toLowerCase())
  )
)
const visibleEvents = computed(() =>
  filteredEvents.value.slice((logPage.value - 1) * 50, logPage.value * 50)
)
const reportLines = computed(() =>
  state.result?.success
    ? incomeReportLines(
        state.result,
        state.input.settings,
        state.input.plan,
        completedSnapshot.value?.label
      )
    : []
)
let started = 0
let lastProgress = 0
let exportGeneration = 0
const silent = computed(() => state.running && seconds.value - lastProgress >= 15)
const required = computed(() => (props.snapshot ? inventoryRequired(props.snapshot.plan) : false))
const targets = computed(() =>
  props.snapshot
    ? incomeFacilities(props.snapshot.plan).map((f) => ({ label: f.label, value: f.roomId }))
    : []
)
watch(
  () => props.snapshot,
  (snapshot) => {
    if (!snapshot) return
    settings.droneRoom = targets.value.some((target) => target.value === snapshot.droneRoom)
      ? snapshot.droneRoom
      : ''
  },
  { immediate: true }
)
const metrics = computed(() =>
  state.result?.success ? incomeMetrics(state.result.summary, state.result.observedHours / 24) : []
)
const summary = computed(() => state.bottleneck?.slowest ?? state.bottleneck?.latest)
const format = (value) => Number(value).toLocaleString('zh-CN', { maximumFractionDigits: 2 })
const weights = [
  ['exp', '经验'],
  ['gold', '赤金'],
  ['orders', '贸易'],
  ['fragments', '碎片'],
  ['orundum', '合成玉']
]
const timer = setInterval(() => {
  if (state.running) seconds.value = Math.floor((performance.now() - started) / 1000)
}, 1000)
const session = createIncomeSession({
  createWorker: () =>
    new Worker(new URL('../riic/incomeWorker.js', import.meta.url), { type: 'module' }),
  update(patch) {
    const displayed = { ...patch }
    if (lastCompleted && !patch.result?.success) {
      delete displayed.result
      delete displayed.input
    }
    Object.assign(state, displayed)
    if (patch.error) attemptDiagnostics.value = patch.result?.diagnostics ?? []
    if (patch.progress) {
      lastProgress = seconds.value
      const entry =
        patch.progress.label +
        (patch.progress.activity?.message ? ` · ${patch.progress.activity.message}` : '')
      if (progressLog.value.at(-1) !== entry)
        progressLog.value = [...progressLog.value.slice(-199), entry]
    }
    if (patch.result?.success) {
      completedSnapshot.value = runSnapshot
      savedAt.value = Date.now()
      lastCompleted = {
        result: patch.result,
        input: patch.input,
        snapshot: runSnapshot,
        bottleneck: patch.bottleneck,
        progressLog: [...progressLog.value],
        exportName: exportName.value,
        savedAt: savedAt.value
      }
      persistResult()
      activeTab.value = 'results'
    } else if (patch.error) activeTab.value = 'logs'
  }
})
async function restoreResult() {
  try {
    const record = await loadIncomeArchive()
    if (!alive || !record) return
    lastCompleted = record
    completedSnapshot.value = record.snapshot
    savedAt.value = record.savedAt
    exportName.value = record.exportName || ''
    progressLog.value = record.progressLog
    Object.assign(state, {
      result: record.result,
      input: record.input,
      bottleneck: record.bottleneck
    })
    activeTab.value = 'results'
  } catch (error) {
    if (alive) archiveError.value = `上次收益记录读取失败：${error.message}`
  } finally {
    if (alive) archiveLoading.value = false
  }
}
async function persistResult() {
  if (!lastCompleted) return
  lastCompleted = { ...lastCompleted, exportName: exportName.value }
  archiveError.value = ''
  try {
    await saveIncomeArchive(lastCompleted)
  } catch (error) {
    if (alive)
      archiveError.value = `收益记录保存失败：${error.message}。当前结果仍可导出，请重试保存。`
  }
}
function saveName() {
  if (lastCompleted && lastCompleted.exportName !== exportName.value) persistResult()
}
async function start() {
  if (archiveLoading.value || submitting.value || state.running || exporting.value) return
  submitting.value = true
  state.error = null
  attemptDiagnostics.value = []
  try {
    if (settings.weightMode === 'mower') await readWeights()
    if (!alive) return
    incomeRequest(props.snapshot.plan, settings)
    exportGeneration++
    exported.value = false
    exportError.value = ''
    seconds.value = 0
    lastProgress = 0
    started = performance.now()
    progressLog.value = []
    logPage.value = 1
    logSearch.value = ''
    activeTab.value = 'logs'
    const { image, ...snapshot } = props.snapshot
    runSnapshot = { ...JSON.parse(JSON.stringify(snapshot)), image }
    session.start(runSnapshot.plan, settings)
  } catch (error) {
    if (alive) state.error = error.message
  } finally {
    if (alive) submitting.value = false
  }
}
async function exportImage() {
  if (exporting.value || !state.result?.success) return
  const generation = ++exportGeneration
  exporting.value = true
  exportError.value = ''
  try {
    const name = imageName.value
    const blob = await renderIncomeImage(
      completedSnapshot.value.image,
      state.result,
      state.input.settings,
      state.input.plan,
      completedSnapshot.value.theme,
      completedSnapshot.value.roomBounds
    )
    if (generation !== exportGeneration) return
    downloadIncomeImage(blob, incomeImageFilename(name, state.result))
    exported.value = true
  } catch (error) {
    if (generation === exportGeneration) exportError.value = error.message
  } finally {
    if (generation === exportGeneration) exporting.value = false
  }
}
function close() {
  saveName()
  alive = false
  controller.abort()
  session.dispose()
  exportGeneration++
  emit('close')
}
onBeforeUnmount(() => {
  saveName()
  alive = false
  controller.abort()
  session.dispose()
  exportGeneration++
  clearInterval(timer)
})
</script>

<template>
  <n-modal
    :show="true"
    preset="card"
    title="计算收益"
    class="income-dialog"
    style="width: 760px; max-width: 95vw; max-height: 90vh"
    :content-style="{ overflowY: 'auto' }"
    :mask-closable="false"
    @update:show="!$event && close()"
  >
    <n-spin v-if="preparing" description="正在准备原排班图片和数据" />
    <n-alert v-if="prepareError" type="error">{{ prepareError }}</n-alert>
    <n-alert v-if="archiveError" type="warning" class="notice">
      {{ archiveError }}
      <n-button v-if="state.result?.success" size="small" @click="persistResult">重试保存</n-button>
    </n-alert>
    <p v-if="archiveLoading">正在读取上次收益记录…</p>
    <p v-else-if="savedAt">
      保留的成功演算：{{
        new Date(savedAt).toLocaleString('zh-CN')
      }}。结果和导出使用该次排班；重新演算使用当前排班。记录保存在本浏览器。
    </p>
    <template v-if="snapshot || state.result?.success">
      <div v-if="state.running" class="notice" role="status" aria-live="polite">
        <n-progress type="line" :percentage="Math.floor((state.progress?.fraction ?? 0) * 100)" />
        <p>{{ state.progress?.label || '正在准备演算' }} · 已用 {{ seconds }} 秒</p>
        <n-alert v-if="silent || state.progress?.activity?.status === 'slow'" type="warning">{{
          state.progress?.activity?.message || '暂未收到新的进度，可以继续等待或停止演算。'
        }}</n-alert>
      </div>
      <n-alert v-if="state.error" class="notice" type="error">
        {{ state.error }}
        <p v-for="(d, i) in attemptDiagnostics" :key="i">{{ d.message }}</p>
      </n-alert>
      <n-alert v-if="exportError" class="notice" type="error"
        >图片导出失败：{{ exportError }}。计算结果已保留，可以重新导出。</n-alert
      >
      <n-tabs v-model:value="activeTab" type="line" animated>
        <n-tab-pane name="settings" tab="参数配置">
          <n-alert class="notice" type="info">
            使用打开窗口时的完整排班快照；预热不计收益。演算采用固定版本的离线模型和理想跑单，结果不代表实测收入。
            初始心情为
            24；设施等级读取排班保存值，未设置时推断；宿舍氛围按等级上限。导入收益图可恢复完整排班及高级设置。
          </n-alert>
          <n-form
            :disabled="state.running || exporting || submitting || weightsBusy"
            label-placement="left"
            label-width="150"
            :show-feedback="false"
          >
            <div class="two-columns">
              <n-form-item label="预热天数"
                ><n-input-number
                  v-model:value="settings.warmupDays"
                  :min="0"
                  :max="30"
                  :precision="0"
              /></n-form-item>
              <n-form-item label="统计天数"
                ><n-input-number
                  v-model:value="settings.sampleDays"
                  :min="1"
                  :max="90"
                  :precision="0"
              /></n-form-item>
            </div>
            <p>
              演算共 {{ (settings.warmupDays ?? 0) + (settings.sampleDays ?? 0) }} 天，仅统计后
              {{ settings.sampleDays }} 天收益。
            </p>
            <n-form-item label="无人机加速目标"
              ><n-select
                v-model:value="settings.droneRoom"
                :options="[{ label: '不使用无人机', value: '' }, ...targets]"
            /></n-form-item>
            <n-form-item label="随机种子"
              ><n-input-number
                v-model:value="settings.seed"
                :min="0"
                :max="4294967295"
                :precision="0"
            /></n-form-item>
            <n-form-item label="干员练度"
              ><n-select
                v-model:value="settings.operatorMode"
                :options="[
                  { label: '使用森空岛缓存练度', value: 'cache' },
                  { label: '全部干员满配（模型假设）', value: 'maximum' },
                  { label: '填写实际拥有及练度', value: 'custom' }
                ]"
            /></n-form-item>
            <p v-if="settings.operatorMode === 'cache'">
              {{
                settings.cachedOperators
                  ? `缓存包含 ${cachedRosterCount} 名已拥有干员；使用各自精英阶段和等级。`
                  : '尚无可用练度缓存，请先在 Mower 同步森空岛。'
              }}
            </p>
            <n-alert v-if="cacheError" type="warning">{{ cacheError }}</n-alert>
            <n-button
              size="small"
              :loading="cacheLoading"
              :disabled="state.running || exporting || submitting || weightsBusy"
              @click="readCache"
              >重新读取缓存</n-button
            >
            <n-form-item v-if="settings.operatorMode === 'custom'" label="干员名单"
              ><n-input
                v-model:value="settings.operatorText"
                type="textarea"
                placeholder="每行：干员代号,精英阶段,等级。未列出视为未拥有。例如：阿米娅,2,80"
                :autosize="{ minRows: 3, maxRows: 8 }"
            /></n-form-item>
            <n-form-item label="孑精零"
              ><n-switch v-model:value="settings.jayeElite0"
            /></n-form-item>
            <n-form-item label="使用有限库存"
              ><n-switch
                :value="required || settings.finiteInventory"
                :disabled="required || state.running || exporting || submitting || weightsBusy"
                @update:value="settings.finiteInventory = $event"
            /></n-form-item>
            <template v-if="required || settings.finiteInventory">
              <n-form-item label="库存来源">
                <n-select
                  v-model:value="settings.inventorySource"
                  :options="[
                    { label: '沿用森空岛缓存（可补填修改）', value: 'cache' },
                    { label: '手动设定', value: 'manual' }
                  ]"
                />
              </n-form-item>
              <p v-if="settings.inventorySource === 'cache'">
                {{
                  settings.cachedInventory
                    ? '未提供的数量保持空白，请补填后演算。重新读取会替换本次缓存修改。'
                    : '没有可用库存缓存，请同步或选择手动设定。'
                }}
                {{
                  settings.cacheObservedAt
                    ? `库存同步时间：${new Date(settings.cacheObservedAt * 1000).toLocaleString('zh-CN')}`
                    : ''
                }}
              </p>
              <n-form-item label="允许赤金透支"
                ><n-switch v-model:value="settings.allowGoldDebt"
              /></n-form-item>
            </template>
            <p v-if="required || settings.finiteInventory">
              {{
                required ? '副表含库存条件，必须预设库存。' : ''
              }}不添加外源收入，预热与统计连续记账。{{
                settings.allowGoldDebt
                  ? '赤金可因交付扣为负数，负数表示缺口；其他材料不足时停产或暂停交付。'
                  : '材料不足时停产或暂停交付。'
              }}回收站仅计产出次数，不计随机材料或材料价值。
            </p>
            <div v-if="required || settings.finiteInventory" class="two-columns">
              <n-form-item
                v-for="item in MOWER_INVENTORY_ITEMS"
                :key="item.resource"
                :label="item.label"
                ><n-input-number
                  :value="
                    stock?.[item.resource] ?? (settings.inventorySource === 'manual' ? 0 : null)
                  "
                  :disabled="!stock || state.running || exporting || submitting || weightsBusy"
                  placeholder="缓存未提供，请补填"
                  :min="0"
                  :max="Number.MAX_SAFE_INTEGER"
                  :precision="0"
                  @update:value="stock[item.resource] = $event"
              /></n-form-item>
            </div>
            <n-collapse
              ><n-collapse-item title="产出权重" name="weights">
                <n-form-item label="权重来源"
                  ><n-select
                    v-model:value="settings.weightMode"
                    :options="[
                      { label: '同步 Mower 基报算法', value: 'mower' },
                      { label: '本次自定义', value: 'custom' }
                    ]"
                /></n-form-item>
                <template v-if="settings.weightMode === 'mower'">
                  <n-form-item label="基报算法"
                    ><n-select
                      :value="settings.mowerAlgorithm"
                      :options="
                        incomeAlgorithms.filter(
                          (row) => row.value !== -1 || settings.mowerAlgorithm === -1
                        )
                      "
                      :loading="weightsBusy"
                      :disabled="
                        !settings.mowerWeights ||
                        weightsBusy ||
                        state.running ||
                        exporting ||
                        submitting
                      "
                      @update:value="selectAlgorithm"
                  /></n-form-item>
                  <p>
                    切换算法会同步保存至 Mower 设置；每次演算前重新读取最新设置。自定义系数可在
                    Mower 设置中修改。
                  </p>
                </template>
                <n-alert v-if="weightsError" type="warning">{{ weightsError }}</n-alert>
                <div v-if="weightValues" class="two-columns">
                  <n-form-item
                    v-for="[key, label] in weights.filter(
                      ([key]) =>
                        settings.weightMode === 'custom' || !['fragments', 'orundum'].includes(key)
                    )"
                    :key="key"
                    :label="label"
                    ><n-input-number
                      v-model:value="weightValues[key]"
                      :min="0"
                      :disabled="
                        settings.weightMode === 'mower' ||
                        state.running ||
                        exporting ||
                        submitting ||
                        weightsBusy
                      "
                  /></n-form-item></div></n-collapse-item
            ></n-collapse>
          </n-form>
        </n-tab-pane>
        <n-tab-pane name="results" tab="收益数据">
          <n-empty v-if="!state.result?.success" description="演算完成后显示收益数据" />
          <template v-if="state.result?.success">
            <n-form-item label="排班名称" :show-feedback="false"
              ><n-input
                v-model:value="exportName"
                @change="saveName"
                :placeholder="completedSnapshot?.label || '排班'"
                :maxlength="60"
                :disabled="exporting"
            /></n-form-item>
            <p>排班名称仅用于 JPG 文件名，后附日均加权收益和采样天数；图片不显示名称。</p>
            <p>
              本次结果：预热 {{ state.input.settings.warmupDays }} 天、统计
              {{ state.input.settings.sampleDays }} 天。修改参数后需重新演算；再次导出使用本次结果。
            </p>
            <p v-if="state.result.inventoryMode === 'finite'">
              赤金余额：初始 {{ format(state.result.goldInventory.initial) }}，统计开始
              {{ format(state.result.goldInventory.sampleOpening) }}，期末
              {{ format(state.result.goldInventory.closing) }}。负数表示赤金缺口。
            </p>
            <p>
              权重：{{
                state.input.settings.weightMode === 'mower'
                  ? incomeAlgorithmLabel(state.input.settings.mowerAlgorithm)
                  : '本次自定义'
              }}；回收站仅计产出次数。
            </p>
            <h3>日均加权产出 {{ format(state.result.summary.totalScore82) }}</h3>
            <n-table size="small"
              ><thead>
                <tr>
                  <th>产出</th>
                  <th>日均</th>
                  <th>统计期合计</th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="row in metrics" :key="row.label">
                  <td>{{ row.label }}</td>
                  <td>{{ format(row.daily) }}</td>
                  <td>{{ format(row.total) }} {{ row.unit }}</td>
                </tr>
              </tbody></n-table
            >
            <p v-if="exported" role="status">收益图片已生成并发起下载。</p>
            <n-collapse class="notice">
              <n-collapse-item title="设施数据" name="rooms">
                <n-table size="small"
                  ><thead>
                    <tr>
                      <th>设施</th>
                      <th>平均效率</th>
                      <th>有人进驻时长</th>
                    </tr>
                  </thead>
                  <tbody>
                    <tr v-for="room in state.result.rooms" :key="room.roomId">
                      <td>{{ room.roomId }}</td>
                      <td>{{ format(room.averageEfficiencyPercent) }}%</td>
                      <td>{{ format(room.occupiedHours) }} 小时</td>
                    </tr>
                  </tbody></n-table
                >
              </n-collapse-item>
              <n-collapse-item
                v-if="state.result.inventoryMode === 'finite'"
                title="统计期库存收支"
                name="stock"
              >
                <n-table size="small"
                  ><thead>
                    <tr>
                      <th>资源</th>
                      <th>开始</th>
                      <th>收入</th>
                      <th>支出</th>
                      <th>期末</th>
                    </tr>
                  </thead>
                  <tbody>
                    <tr v-for="item in MOWER_INVENTORY_ITEMS" :key="item.resource">
                      <td>{{ item.label }}</td>
                      <td>{{ format(state.result.resources?.opening[item.resource] ?? 0) }}</td>
                      <td>{{ format(state.result.resources?.inflows[item.resource] ?? 0) }}</td>
                      <td>{{ format(state.result.resources?.outflows[item.resource] ?? 0) }}</td>
                      <td>{{ format(state.result.resources?.closing[item.resource] ?? 0) }}</td>
                    </tr>
                  </tbody></n-table
                >
              </n-collapse-item>
              <n-collapse-item title="本次参数与模型说明" name="assumptions"
                ><p v-for="line in reportLines" :key="line">{{ line }}</p></n-collapse-item
              >
            </n-collapse>
            <n-collapse class="notice"
              ><n-collapse-item
                :title="`演算诊断（${state.result.diagnostics.length} 条）`"
                name="diagnostics"
                ><p v-for="(d, i) in state.result.diagnostics" :key="i">
                  {{ d.message }}
                </p></n-collapse-item
              ></n-collapse
            >
          </template>
        </n-tab-pane>
        <n-tab-pane name="timeline" tab="排班甘特图" display-directive="show:lazy">
          <IncomeTimeline
            v-if="
              state.result?.success && state.result.simulationReport && state.result.timelineData
            "
            :report="state.result.simulationReport"
            :timeline-data="state.result.timelineData"
          />
          <n-empty
            v-else
            :description="
              state.result?.success
                ? '这份历史演算记录不含甘特图，请重新演算。原收益和排班图片仍可查看、导出。'
                : '演算完成后显示排班甘特图'
            "
          />
        </n-tab-pane>
        <n-tab-pane name="logs" tab="演算日志">
          <n-alert
            v-if="state.bottleneck"
            class="notice"
            :type="state.error ? 'warning' : 'info'"
            title="本次演算观察"
          >
            <p>
              已用 {{ format(state.bottleneck.elapsedSeconds) }} 秒；{{
                state.bottleneck.progressLabel
              }}。
            </p>
            <p v-if="state.bottleneck.silence">
              结束前 {{ state.bottleneck.silence.seconds }} 秒未收到进度；尚不能确定原因。
            </p>
            <template v-if="summary">
              <p>{{ summary.activity.message }}</p>
              <p v-if="summary.activity.task">
                任务：{{ summary.activity.task.type }} {{ summary.activity.task.metadata }}
              </p>
              <p v-for="op in summary.activity.operators" :key="op.id">
                {{ op.name }} · 心情 {{ format(op.morale) }} · {{ op.room }} ·
                {{ op.groups.join('、') }}
              </p>
              <p>这些活动与慢速时段相关，不能仅据此认定某位干员是原因。</p>
            </template>
            <p v-for="(item, i) in state.bottleneck.diagnostics" :key="i">{{ item.message }}</p>
          </n-alert>

          <n-collapse v-if="progressLog.length" class="notice"
            ><n-collapse-item title="计算进度记录（最近 200 条）" name="progress"
              ><div class="income-log">
                <p v-for="(line, i) in progressLog" :key="i">{{ line }}</p>
              </div></n-collapse-item
            ></n-collapse
          >
          <template v-if="state.result?.eventLog">
            <p>
              统计期事件 {{ state.result.eventLog.total }} 条，保留最近
              {{ state.result.eventLog.entries.length }}
              条。时间从统计期开始计算，按发生时间倒序显示。
            </p>
            <n-input
              v-model:value="logSearch"
              placeholder="搜索干员、设施或事件"
              clearable
              @update:value="logPage = 1"
            />
            <div class="income-log">
              <n-table size="small"
                ><thead>
                  <tr>
                    <th>时间</th>
                    <th>事件</th>
                    <th>详情</th>
                  </tr>
                </thead>
                <tbody>
                  <tr v-for="(row, i) in visibleEvents" :key="i">
                    <td class="event-time">{{ incomeLogTime(row.hours) }}</td>
                    <td>{{ row.type }}</td>
                    <td>{{ row.room }} {{ row.detail }}</td>
                  </tr>
                </tbody></n-table
              >
            </div>
            <n-pagination
              v-model:page="logPage"
              :page-size="50"
              :item-count="filteredEvents.length"
            />
          </template>
          <n-empty
            v-else-if="!state.running && !state.error"
            description="开始演算后显示进度与日志"
          />
        </n-tab-pane>
      </n-tabs>
    </template>
    <template #footer
      ><n-space justify="end">
        <n-button @click="close">{{ state.running ? '停止并关闭' : '关闭' }}</n-button>
        <n-button v-if="state.running" type="warning" @click="session.cancel">停止演算</n-button>
        <n-button
          v-if="state.result?.success"
          :loading="exporting"
          :disabled="state.running || exporting || submitting || weightsBusy"
          @click="exportImage"
          >{{ exported ? '再次导出收益图' : '导出收益图' }}</n-button
        >
        <n-button
          type="primary"
          :disabled="
            archiveLoading ||
            !snapshot ||
            preparing ||
            state.running ||
            exporting ||
            submitting ||
            weightsBusy ||
            cacheLoading
          "
          :loading="submitting"
          @click="start"
          >{{ state.result?.success ? '重新演算' : '开始演算' }}</n-button
        >
      </n-space></template
    >
  </n-modal>
</template>

<style scoped>
.income-log {
  max-height: 360px;
  overflow: auto;
  margin: 12px 0;
}
.event-time {
  white-space: nowrap;
}
.notice {
  margin: 14px 0;
}
.two-columns {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  align-items: start;
  gap: 12px;
}
.n-form-item {
  margin: 0 0 12px;
  min-width: 0;
}
.two-columns > .n-form-item {
  margin-top: 0;
}
.n-input-number {
  width: 100%;
}
p {
  line-height: 1.7;
}
@media (max-width: 650px) {
  .two-columns {
    grid-template-columns: 1fr;
  }
}
</style>
