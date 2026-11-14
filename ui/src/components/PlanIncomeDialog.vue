<script setup>
import { useMessage } from 'naive-ui'
import { computed, inject, nextTick, onMounted, onBeforeUnmount, reactive, ref, watch } from 'vue'
import {
  defaultIncomeSettings,
  incomeMetrics,
  incomeRequest,
  incomeWorkspace,
  inventoryRequired,
  applyMowerIncomeSettings
} from '@/riic/income'
import { applyIncomeCache } from '@/riic/incomeCache'
import {
  loadIncomePreferences,
  saveIncomePreferences,
  clearIncomePreferences
} from '@/riic/incomePreferences'
import { incomeAlgorithms, incomeAlgorithmLabel, incomeSettingsUrl } from '@/utils/incomeSettings'
import { createIncomeSession } from '@/riic/incomeSession'
import { loadIncomeArchive, saveIncomeArchive } from '@/riic/incomeArchive'
import { incomeLogTime } from '@/riic/incomeLogs'
import IncomeTimeline from './IncomeTimeline.vue'
import IncomeActivity from './IncomeActivity.vue'
import IncomeDiagnostics from './IncomeDiagnostics.vue'
import IncomeValueEditor from './IncomeValueEditor.vue'
import { incomeScore, incomeScoreLabel } from '@/riic/incomeSanity'
import { validateRosterWorkspace } from '@/riic/vendor/workbench/validate'
import { renderIncomeImage, downloadIncomeImage, incomeImageFilename } from '@/riic/incomeImage'
import {
  MOWER_INVENTORY_ITEMS,
  MOWER_RAW_MATERIALS
} from '@/riic/vendor/domain/simulationInventory'

const message = useMessage()
const props = defineProps({ snapshot: Object, preparing: Boolean, prepareError: String })
const emit = defineEmits(['close'])
const preferences = loadIncomePreferences()
const settings = reactive({ ...defaultIncomeSettings(), ...preferences.settings })
const preferencesError = ref('')
let cachedInventoryOverrides = preferences.cachedInventoryOverrides
let cachedInventoryBaseline = null
let cachedInventoryValues = null
let applyingPreferences = false
const axios = inject('axios')
const cacheLoading = ref(false)
const cacheError = ref('')
const weightsBusy = ref(false)
const valuesBusy = ref(false)
const valuation = ref(null)
const weightsError = ref('')
const submitting = ref(false)
const validating = ref(false)
const errorAlert = ref(null)
const controller = new AbortController()
let alive = true
let sharedRatios = null
const stock = computed(() =>
  settings.inventorySource === 'cache' ? settings.cachedInventory : settings.initialInventory
)
const weightValues = computed(() =>
  settings.weightMode === 'sanity'
    ? null
    : settings.weightMode === 'mower'
      ? settings.mowerWeights
      : settings.productionWeights
)
const cachedRosterCount = computed(() => settings.cachedOperators?.length ?? 0)
async function readCache({ preserveOverrides = false } = {}) {
  cacheLoading.value = true
  cacheError.value = ''
  try {
    const { data } = await axios.get(`${import.meta.env.VITE_HTTP_URL}/riic/income-cache`, {
      timeout: 15000,
      signal: controller.signal
    })
    if (alive) {
      applyingPreferences = true
      try {
        if (!preserveOverrides) cachedInventoryOverrides = {}
        applyIncomeCache(settings, data)
        if (valuation.value) applyMowerIncomeSettings(settings, valuation.value)
        cachedInventoryBaseline = settings.cachedInventory ? { ...settings.cachedInventory } : null
        if (settings.cachedInventory)
          Object.assign(settings.cachedInventory, cachedInventoryOverrides)
        cachedInventoryValues = settings.cachedInventory ? { ...settings.cachedInventory } : null
      } finally {
        applyingPreferences = false
      }
      persistPreferences()
    }
  } catch {
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
      valuation.value = data
      applyMowerIncomeSettings(settings, data)
      sharedRatios = data.ratios
    }
  } catch (error) {
    if (alive) weightsError.value = 'Mower 收益设置读取失败，可重试或选择自定义权重'
    throw new Error('Mower 收益设置读取失败，可重试或选择自定义权重', { cause: error })
  } finally {
    if (alive) weightsBusy.value = false
  }
}
async function selectAlgorithm(value) {
  const preset = incomeAlgorithms.find((item) => item.value === value)
  if (!preset?.ratios || !sharedRatios || weightsBusy.value || valuesBusy.value) return
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
      valuation.value = data
      applyMowerIncomeSettings(settings, data)
      sharedRatios = data.ratios
    }
  } catch {
    if (alive) weightsError.value = '算法保存失败，请重新读取 Mower 设置确认'
  } finally {
    if (alive) weightsBusy.value = false
  }
}
onMounted(() =>
  Promise.allSettled([readCache({ preserveOverrides: true }), readWeights(), restoreResult()])
)
function applySavedValues(data) {
  valuation.value = data
  applyMowerIncomeSettings(settings, data)
  sharedRatios = data.ratios
}
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
const exportDetails = reactive({ author: '', remarks: '' })
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
let started = 0
let lastProgress = 0
let exportGeneration = 0
const silent = computed(() => state.running && seconds.value - lastProgress >= 15)
const required = computed(() => (props.snapshot ? inventoryRequired(props.snapshot.plan) : false))
function persistPreferences() {
  if (applyingPreferences) return
  if (cachedInventoryBaseline && settings.cachedInventory) {
    for (const { resource } of MOWER_INVENTORY_ITEMS) {
      const value = settings.cachedInventory[resource] ?? 0
      if (value === cachedInventoryValues?.[resource]) continue
      if (value === cachedInventoryBaseline[resource]) delete cachedInventoryOverrides[resource]
      else cachedInventoryOverrides[resource] = value
    }
    cachedInventoryValues = { ...settings.cachedInventory }
  }
  preferencesError.value = saveIncomePreferences(settings, cachedInventoryOverrides)
    ? ''
    : '参数修改未能保存到本浏览器，当前窗口仍可使用。'
}
function resetSettings() {
  if (state.running || exporting.value || submitting.value || weightsBusy.value || valuesBusy.value)
    return
  applyingPreferences = true
  try {
    const current = {
      cachedOperators: settings.cachedOperators,
      cachedInventory: cachedInventoryBaseline ? { ...cachedInventoryBaseline } : null,
      cacheObservedAt: settings.cacheObservedAt,
      mowerWeights: settings.mowerWeights,
      mowerAlgorithm: settings.mowerAlgorithm,
      cachedRecruitment: settings.cachedRecruitment,
      sanityValuation: settings.sanityValuation
    }
    Object.assign(settings, defaultIncomeSettings(), current)
    cachedInventoryOverrides = {}
    cachedInventoryValues = current.cachedInventory ? { ...current.cachedInventory } : null
  } finally {
    applyingPreferences = false
  }
  preferencesError.value = clearIncomePreferences()
    ? ''
    : '本次已恢复默认，浏览器中保留的参数未能清除。'
}
watch(settings, persistPreferences, { deep: true, flush: 'sync' })
const metrics = computed(() =>
  state.result?.success ? incomeMetrics(state.result.summary, state.result.observedHours / 24) : []
)
const summary = computed(() => state.bottleneck?.slowest ?? state.bottleneck?.latest)
const attemptDetails = computed(() => {
  // A failed attempt owns its diagnostics even while an older successful result remains visible.
  const diagnostics = state.error ? attemptDiagnostics.value : (state.result?.diagnostics ?? [])
  return diagnostics.length ? diagnostics : (state.bottleneck?.diagnostics ?? [])
})
const outcomeLabel = computed(
  () =>
    ({
      completed: '演算已完成',
      failed: '演算未完成',
      cancelled: '演算已停止',
      changed: '排班已变更'
    })[state.bottleneck?.outcome] ?? '演算已结束'
)
const planIssues = computed(() =>
  props.snapshot ? validateRosterWorkspace(incomeWorkspace(props.snapshot.plan)).issues : []
)
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
    exportDetails.author = record.exportDetails?.author || ''
    exportDetails.remarks = record.exportDetails?.remarks || ''
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
  lastCompleted = {
    ...lastCompleted,
    exportName: exportName.value,
    exportDetails: { ...exportDetails }
  }
  archiveError.value = ''
  try {
    await saveIncomeArchive(lastCompleted)
  } catch (error) {
    if (alive)
      archiveError.value = `收益记录保存失败：${error.message}。当前结果仍可导出，请重试保存。`
  }
}
function saveName() {
  if (
    lastCompleted &&
    (lastCompleted.exportName !== exportName.value ||
      (lastCompleted.exportDetails?.author || '') !== exportDetails.author ||
      (lastCompleted.exportDetails?.remarks || '') !== exportDetails.remarks)
  )
    persistResult()
}
async function start() {
  if (
    archiveLoading.value ||
    submitting.value ||
    state.running ||
    exporting.value ||
    valuesBusy.value
  )
    return
  submitting.value = true
  state.error = null
  state.bottleneck = null
  attemptDiagnostics.value = []
  try {
    if (settings.weightMode === 'mower' || settings.weightMode === 'sanity') await readWeights()
    if (
      settings.weightMode === 'sanity' &&
      valuation.value?.income_options?.potential_preset === 'skland'
    ) {
      await readCache({ preserveOverrides: true })
      if (cacheError.value) throw new Error(cacheError.value)
    }
    if (!alive) return
    const { image, ...snapshot } = props.snapshot
    const captured = { ...JSON.parse(JSON.stringify(snapshot)), image }
    const runSettings = JSON.parse(JSON.stringify(settings))
    const production = incomeRequest(captured.plan, runSettings).options.simulationOptions
      .production
    runSettings.droneRoom = production.droneRoomId ?? ''
    runSettings.expectationMode = production.expectationMode
    if (!production.expectationMode) runSettings.seed = production.seed
    validating.value = true
    const { data: validation } = await axios.post(
      `${import.meta.env.VITE_HTTP_URL}/validate-plan`,
      { plan: captured.plan, operatorMode: runSettings.operatorMode },
      { timeout: 0, signal: controller.signal }
    )
    validating.value = false
    if (!alive) return
    for (const warning of validation.warnings || []) {
      message.warning(warning, { duration: 0, closable: true })
    }
    if (validation.success !== true)
      throw new Error(validation.message || '排班校验未通过，尚未开始演算')
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
    runSnapshot = captured
    session.start(runSnapshot.plan, runSettings)
  } catch (error) {
    if (alive) {
      state.error = error.message
      await nextTick()
      if (alive) errorAlert.value?.$el?.scrollIntoView?.({ block: 'nearest' })
    }
  } finally {
    validating.value = false
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
      completedSnapshot.value.roomBounds,
      { ...exportDetails }
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
    :content-style="{
      overflowY: 'auto',
      paddingBottom: activeTab === 'timeline' ? '0' : undefined
    }"
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
          state.progress?.activity?.status === 'slow'
            ? '演算推进较慢，具体任务与校验记录见“演算日志”。'
            : '暂未收到新的进度，可以继续等待或停止演算。'
        }}</n-alert>
      </div>
      <n-alert v-if="validating" class="notice" type="info" role="status">
        正在校验排班组合，完成后自动开始演算。可关闭窗口取消等待。
      </n-alert>
      <n-alert v-if="state.error" ref="errorAlert" role="alert" class="notice" type="error">
        {{ state.error }}
      </n-alert>
      <n-alert v-if="exportError" class="notice" type="error"
        >图片导出失败：{{ exportError }}。计算结果已保留，可以重新导出。</n-alert
      >
      <n-tabs v-model:value="activeTab" type="line" animated>
        <n-tab-pane name="settings" tab="参数配置">
          <div class="settings-actions">
            <span>参数修改会保留在本浏览器，下次打开继续使用。</span>
            <n-button
              size="small"
              :disabled="state.running || exporting || submitting || weightsBusy || valuesBusy"
              @click="resetSettings"
              >恢复默认</n-button
            >
          </div>
          <n-alert v-if="preferencesError" type="warning" class="notice">{{
            preferencesError
          }}</n-alert>
          <n-alert v-if="planIssues.length" class="notice" type="warning" title="排班校验提示">
            <p>副表单独生效的警告仅供检查，实际组合仍在切表前校验。</p>
            <ul>
              <li v-for="(issue, i) in planIssues" :key="i">{{ issue.message }}</li>
            </ul>
          </n-alert>
          <n-alert class="notice" type="info">
            使用打开窗口时的排班，无人机加速跟随排班表中的高级设置，校验通过后开始演算。预热不计收益，结果为离线估算。
          </n-alert>
          <n-form
            :disabled="state.running || exporting || submitting || weightsBusy || valuesBusy"
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
            <n-form-item label="理论期望模式">
              <n-switch
                :value="settings.expectationMode"
                @update:value="settings.expectationMode = $event"
              />
            </n-form-item>
            <n-form-item v-if="!settings.expectationMode" label="固定种子">
              <n-input-number
                v-model:value="settings.fixedSeed"
                placeholder="留空时每次随机生成"
                clearable
                :min="0"
                :max="4294967295"
                :precision="0"
              />
            </n-form-item>
            <p>
              {{
                settings.expectationMode
                  ? '按换班、心情、技能和资源事件快算，忽略页面操作时间；各项产出与材料消耗累计小数期望，无人机按生成能力和当前目标分段计算，不受无人机库存、阈值及检查间隔限制。单裁缝概率按工作满整小时等幅递增，不随机抽单；暂不支持同站多名裁缝同时影响订单概率；暖机、初始心情和轮换阶段仍会影响结果。'
                  : '按概率随机抽单；固定种子留空时每次随机生成，填写后使用指定种子。结果保留本次种子以供复现。'
              }}
            </p>
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
              :disabled="state.running || exporting || submitting || weightsBusy || valuesBusy"
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
                :disabled="
                  required || state.running || exporting || submitting || weightsBusy || valuesBusy
                "
                @update:value="settings.finiteInventory = $event"
            /></n-form-item>
            <template v-if="required || settings.finiteInventory">
              <n-form-item label="库存来源">
                <n-select
                  v-model:value="settings.inventorySource"
                  :options="[
                    { label: '沿用森空岛缓存（可修改）', value: 'cache' },
                    { label: '手动设定', value: 'manual' }
                  ]"
                />
              </n-form-item>
              <p v-if="settings.inventorySource === 'cache'">
                {{
                  settings.cachedInventory
                    ? '未提供的数量按 0 计算，可手动修改。重新读取会清除手动修改并使用最新缓存。'
                    : '没有可用库存缓存，请同步或选择手动设定。'
                }}
                {{
                  settings.cacheObservedAt
                    ? `库存同步时间：${new Date(settings.cacheObservedAt * 1000).toLocaleString('zh-CN')}`
                    : ''
                }}
              </p>
              <n-form-item label="允许原材料亏空"
                ><n-switch v-model:value="settings.allowMaterialDebt"
              /></n-form-item>
            </template>
            <p v-if="required || settings.finiteInventory">
              {{
                required ? '副表含库存条件，必须预设库存。' : ''
              }}预热与统计连续记账，外源材料按日均设置持续补入且不计收益。{{
                settings.allowMaterialDebt
                  ? '原材料可扣为负数，负数表示缺口；制造与交付不因缺料停止。'
                  : '材料不足时停产或暂停交付。'
              }}回收站仅计产出次数，不计随机材料或材料价值。
            </p>
            <div v-if="required || settings.finiteInventory" class="two-columns">
              <n-form-item
                v-for="item in MOWER_INVENTORY_ITEMS"
                :key="item.resource"
                :label="item.label"
                ><n-input-number
                  :value="stock?.[item.resource] ?? 0"
                  :disabled="
                    !stock || state.running || exporting || submitting || weightsBusy || valuesBusy
                  "
                  placeholder="0"
                  :min="0"
                  :max="Number.MAX_SAFE_INTEGER"
                  :precision="0"
                  @update:value="stock[item.resource] = $event"
              /></n-form-item>
            </div>
            <n-collapse v-if="required || settings.finiteInventory">
              <n-collapse-item title="日均外源材料" name="external-materials">
                <p>按每天的数量均匀补入，预热与统计均生效；外源补入不计产出和加权收益。</p>
                <div class="two-columns">
                  <n-form-item
                    v-for="item in MOWER_RAW_MATERIALS"
                    :key="item.resource"
                    :label="`${item.label} / 天`"
                  >
                    <n-input-number
                      :value="settings.dailyExternalResources[item.resource] ?? 0"
                      :min="0"
                      :max="Number.MAX_SAFE_INTEGER"
                      :precision="4"
                      @update:value="settings.dailyExternalResources[item.resource] = $event ?? 0"
                    />
                  </n-form-item>
                </div>
              </n-collapse-item>
            </n-collapse>
            <n-collapse
              ><n-collapse-item title="收益算法与产出权重" name="weights">
                <n-form-item label="收益算法"
                  ><n-select
                    v-model:value="settings.weightMode"
                    :disabled="
                      weightsBusy || valuesBusy || state.running || exporting || submitting
                    "
                    :options="[
                      { label: '同步 Mower 基报算法', value: 'mower' },
                      { label: '理智算法', value: 'sanity' },
                      { label: '自定义', value: 'custom' }
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
                        valuesBusy ||
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
                <IncomeValueEditor
                  v-if="settings.weightMode === 'sanity'"
                  :valuation="valuation"
                  :recruitment="settings.cachedRecruitment"
                  :disabled="weightsBusy || state.running || exporting || submitting"
                  @saved="applySavedValues"
                  @busy="valuesBusy = $event" />
                <n-alert v-if="weightsError" type="warning"
                  >{{ weightsError }}
                  <n-button
                    size="small"
                    :disabled="weightsBusy || valuesBusy || submitting || state.running"
                    @click="readWeights().catch(() => undefined)"
                    >重新读取</n-button
                  >
                </n-alert>
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
            <p>排班名称仅用于 JPG 文件名，后附本次日均收益和采样天数；图片不显示名称。</p>
            <n-form-item label="作者" :show-feedback="false">
              <n-input
                v-model:value="exportDetails.author"
                @change="saveName"
                placeholder="可选，显示在收益与订单统计下方"
                :maxlength="40"
                :disabled="exporting"
              />
            </n-form-item>
            <n-form-item label="备注" :show-feedback="false">
              <n-input
                v-model:value="exportDetails.remarks"
                @change="saveName"
                type="textarea"
                placeholder="可填写排班版本、适用条件或使用说明"
                :maxlength="300"
                show-count
                :autosize="{ minRows: 2, maxRows: 4 }"
                :disabled="exporting"
              />
            </n-form-item>
            <p>
              作者和备注随收益记录保存，导出时显示在收益与订单统计下方；留空不占空间，无需重新演算。
            </p>
            <p>
              本次结果：预热 {{ state.input.settings.warmupDays }} 天、统计
              {{ state.input.settings.sampleDays }} 天，
              {{
                state.result.simulationReport?.production?.assumptions.expectationMode
                  ? state.result.modelProvenance?.timingModel === 'theoretical-events-v1'
                    ? '理论期望模式'
                    : state.result.simulationReport?.production?.expected
                      ? '数学期望模式（连续产出）'
                      : '数学期望模式（平均订单模型）'
                  : '随机抽单模式'
              }}。 修改参数后需重新演算；再次导出使用本次结果。
            </p>
            <p v-if="state.result.inventoryMode === 'finite'">
              赤金余额：初始 {{ format(state.result.goldInventory.initial) }}，统计开始
              {{ format(state.result.goldInventory.sampleOpening) }}，期末
              {{ format(state.result.goldInventory.closing) }}。负数表示赤金缺口。
            </p>
            <p>
              算法：{{
                state.input.settings.weightMode === 'mower'
                  ? incomeAlgorithmLabel(state.input.settings.mowerAlgorithm)
                  : state.input.settings.weightMode === 'sanity'
                    ? '理智算法'
                    : '自定义'
              }}。<span v-if="!state.result.summary.sanity">回收站仅计产出次数。</span>
            </p>
            <p>
              赤金等价龙门币 = 制造赤金 × 500 + 龙舌兰等特殊订单溢价；不扣除交付消耗的赤金。
              <span v-if="state.result.inventoryMode === 'finite'">实际消耗及余额见库存收支。</span>
            </p>
            <h3>{{ incomeScoreLabel(state.result) }} {{ format(incomeScore(state.result)) }}</h3>
            <template v-if="state.result.summary.sanity">
              <p v-if="state.result.summary.sanity.credits">
                会客室日均信用：{{ format(state.result.summary.sanity.credits.produced) }}，其中
                {{ format(state.result.summary.sanity.credits.valued) }}
                计入估值。假设自搜线索全部赠送、好友补齐线索并连续交流；有效单价按每日额度折算。
              </p>
              <n-alert v-if="state.result.summary.sanity.partial" type="warning"
                >以下产出或消耗尚未估值，当前总额仅包含已估值部分：{{
                  state.result.summary.sanity.unpriced.join('、')
                }}。可在理智算法设置中填写后重新演算。</n-alert
              >
              <n-collapse
                ><n-collapse-item title="理智收益明细（每日）" name="sanity-breakdown">
                  <n-table size="small" :single-line="false"
                    ><thead>
                      <tr>
                        <th>产出</th>
                        <th>净数量</th>
                        <th>有效理智单价</th>
                        <th>理智收益</th>
                      </tr>
                    </thead>
                    <tbody>
                      <tr v-for="part in state.result.summary.sanity.parts" :key="part.key">
                        <td>{{ part.label }}</td>
                        <td>{{ format(part.quantity) }}</td>
                        <td>{{ part.unitValue === null ? '未估值' : format(part.unitValue) }}</td>
                        <td>{{ part.value === null ? '未估值' : format(part.value) }}</td>
                      </tr>
                    </tbody></n-table
                  >
                </n-collapse-item></n-collapse
              >
            </template>
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
              <n-collapse-item
                v-if="state.result.stability"
                title="轮换与无人机边界观察"
                name="stability"
              >
                <p>
                  将统计期等分为两个 {{ format(state.result.stability.halfHours) }} 小时区间比较。
                  干员驻岗占比最大相差
                  {{ format(state.result.stability.maxWorkFractionDifference * 100) }} 个百分点。
                  初始满心情及轮换阶段的影响不能直接从收益扣除；前后半段接近也不证明已达到稳态。
                  可调整预热和统计天数比较，有限库存耗尽时可能不存在稳定产出。
                </p>
                <n-table size="small">
                  <thead>
                    <tr>
                      <th>设施</th>
                      <th>前半段平均效率</th>
                      <th>后半段平均效率</th>
                    </tr>
                  </thead>
                  <tbody>
                    <tr v-for="room in state.result.stability.roomComparisons" :key="room.roomId">
                      <td>{{ room.roomId }}</td>
                      <td>{{ format(room.firstEfficiency) }}%</td>
                      <td>{{ format(room.secondEfficiency) }}%</td>
                    </tr>
                  </tbody>
                </n-table>
                <p
                  v-if="
                    state.result.simulationReport?.production?.assumptions.droneAllocationModel ===
                    'generated-capacity-v1'
                  "
                >
                  统计期无人机能力：生成
                  {{
                    format(state.result.simulationReport.production.expected.droneGenerated)
                  }}，有效分配
                  {{
                    format(state.result.simulationReport.production.expected.droneAllocated)
                  }}，其中切产物
                  {{
                    format(
                      state.result.simulationReport.production.expected.droneSwitchAllocated ?? 0
                    )
                  }}；损耗
                  {{
                    format(state.result.simulationReport.production.expected.droneLost ?? 0)
                  }}，未利用
                  {{
                    format(state.result.simulationReport.production.expected.droneUnallocated ?? 0)
                  }}；期末待结算切产物份额
                  {{
                    format(
                      state.result.simulationReport.production.expected.pendingSwitchDrones ?? 0
                    )
                  }}
                  架。以上是无人机等效数量，不代表实物库存。
                  按当前主副表生效的目标分段分配；切产物提前使用的加速份额由后续生成能力优先结算，未结算部分不计收入。
                  原材料、驻员和有效工作继续约束产出。
                </p>
                <p v-else-if="state.result.stability.drones">
                  无人机期初 {{ format(state.result.stability.drones.opening) }}，期末
                  {{ format(state.result.stability.drones.closing) }}， 差额
                  {{ format(state.result.stability.drones.change) }}；期间生成
                  {{ format(state.result.stability.drones.generated) }}、 消耗
                  {{ format(state.result.stability.drones.consumed) }}、溢出
                  {{ format(state.result.stability.drones.overflow) }} 架。
                  <template
                    v-if="
                      state.result.simulationReport?.production?.assumptions
                        .droneAllocationModel === 'threshold-v1'
                    "
                  >
                    无人机按配置间隔和阈值使用，本次计入收益的有效加速为
                    {{ format(state.result.simulationReport.production.expected.droneAllocated) }}
                    架；先消耗期初库存且不计其收益，采样期新生成部分在使用时计入当时产物，未使用部分保留库存。
                  </template>
                  <template v-else-if="state.result.simulationReport?.production?.expected">
                    收益按统计期生成的加速能力计入所选设施，已折算
                    {{ format(state.result.simulationReport.production.expected.droneAllocated) }}
                    架；期初库存与实际使用不重复计入收益。上表仅用于观察调度库存。
                  </template>
                  <template v-else>
                    差额保留为库存，不强行使用或按固定价格计入收益；其生产价值取决于加速目标、材料和停工条件。
                  </template>
                </p>
              </n-collapse-item>
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
                :title="
                  state.result.simulationReport?.production?.expected
                    ? '统计期调度库存收支（用于资源约束）'
                    : '统计期库存收支'
                "
                name="stock"
              >
                <n-table size="small"
                  ><thead>
                    <tr>
                      <th>资源</th>
                      <th>开始</th>
                      <th>收入</th>
                      <th v-if="state.result.resources?.external">其中外源补入</th>
                      <th>支出</th>
                      <th>期末</th>
                    </tr>
                  </thead>
                  <tbody>
                    <tr v-for="item in MOWER_INVENTORY_ITEMS" :key="item.resource">
                      <td>{{ item.label }}</td>
                      <td>{{ format(state.result.resources?.opening[item.resource] ?? 0) }}</td>
                      <td>{{ format(state.result.resources?.inflows[item.resource] ?? 0) }}</td>
                      <td v-if="state.result.resources?.external">
                        {{ format(state.result.resources.external[item.resource] ?? 0) }}
                      </td>
                      <td>{{ format(state.result.resources?.outflows[item.resource] ?? 0) }}</td>
                      <td>{{ format(state.result.resources?.closing[item.resource] ?? 0) }}</td>
                    </tr>
                  </tbody></n-table
                >
              </n-collapse-item>
            </n-collapse>
            <IncomeDiagnostics class="notice" :diagnostics="state.result.diagnostics" />
          </template>
        </n-tab-pane>
        <n-tab-pane name="timeline" tab="工作记录" display-directive="show:lazy">
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
                ? '这份历史演算记录不含工作记录，请重新演算。原收益和排班图片仍可查看、导出。'
                : '演算完成后显示工作记录'
            "
          />
        </n-tab-pane>
        <n-tab-pane name="logs" tab="演算日志">
          <n-alert
            v-if="state.running && state.progress?.activity"
            class="notice"
            :type="state.progress.activity.status === 'slow' ? 'warning' : 'info'"
            title="运行中的演算观察"
          >
            <IncomeActivity :activity="state.progress.activity" />
          </n-alert>
          <n-alert
            v-if="state.bottleneck"
            class="notice"
            :type="state.error ? 'warning' : 'info'"
            title="本次演算观察"
          >
            <p>
              {{ outcomeLabel }}。已用
              {{ format(state.bottleneck.elapsedSeconds) }} 秒；最后进度：{{
                state.bottleneck.progressLabel
              }}。
            </p>
            <p v-if="state.bottleneck.silence">
              结束前 {{ state.bottleneck.silence.seconds }} 秒未收到进度；尚不能确定原因。
            </p>
            <n-collapse v-if="summary">
              <n-collapse-item
                :title="
                  state.bottleneck.slowest ? '运行期间最慢时段的观察' : '结束前的任务与干员观察'
                "
                name="activity"
              >
                <IncomeActivity :activity="summary.activity" historical />
              </n-collapse-item>
            </n-collapse>
          </n-alert>
          <IncomeDiagnostics v-if="!state.running" class="notice" :diagnostics="attemptDetails" />

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
        <n-button @click="close">{{
          validating ? '取消等待并关闭' : state.running ? '停止并关闭' : '关闭'
        }}</n-button>
        <n-button v-if="state.running" type="warning" @click="session.cancel">停止演算</n-button>
        <n-button
          v-if="state.result?.success"
          :loading="exporting"
          :disabled="state.running || exporting || submitting || weightsBusy || valuesBusy"
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
            valuesBusy ||
            cacheLoading
          "
          :loading="submitting"
          @click="start"
          >{{
            validating ? '正在校验排班' : state.result?.success ? '重新演算' : '开始演算'
          }}</n-button
        >
      </n-space></template
    >
  </n-modal>
</template>

<style scoped>
:global(.income-dialog.n-card) {
  width: calc(98vw / var(--mower-zoom, 1));
  height: calc(96vh / var(--mower-zoom, 1));
  height: calc(96dvh / var(--mower-zoom, 1));
  max-width: none;
}
:global(.income-dialog .n-card-content) {
  min-height: 0;
}
:global(.income-dialog .n-tabs-pane-wrapper),
:global(.income-dialog .n-tab-pane) {
  overflow: visible;
}

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
  grid-template-columns: repeat(auto-fit, minmax(min(100%, 240px), 1fr));
  align-items: start;
  gap: 12px;
}
.settings-actions {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  margin: 0 0 14px;
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
