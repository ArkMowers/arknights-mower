<script setup>
import { i18n } from '@/i18n'
import { incomeDisplayMessage, incomeRoomName } from '@/i18n/income'
import { planDisplayName, planValidationMessage } from '@/i18n/plans'
const { t, locale } = i18n.global
import { computed, inject, nextTick, onMounted, onBeforeUnmount, reactive, ref, watch } from 'vue'
import {
  defaultIncomeSettings,
  incomeFacilities,
  incomeMetrics,
  incomeRequest,
  incomeWorkspace,
  inventoryRequired,
  applyMowerIncomeSettings
} from '@/riic/income'
import { applyIncomeCache } from '@/riic/incomeCache'
import { incomeAlgorithms, incomeAlgorithmLabel, incomeSettingsUrl } from '@/utils/incomeSettings'
import { createIncomeSession } from '@/riic/incomeSession'
import { loadIncomeArchive, saveIncomeArchive } from '@/riic/incomeArchive'
import { incomeLogTime } from '@/riic/incomeLogs'
import IncomeTimeline from './IncomeTimeline.vue'
import IncomeActivity from './IncomeActivity.vue'
import { validateRosterWorkspace } from '@/riic/vendor/workbench/validate'
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
const cacheFailed = ref(false)
const cacheError = computed(() => (cacheFailed.value ? t('plans.cacheFailed') : ''))
const weightsBusy = ref(false)
const weightsFailure = ref('')
const weightsError = computed(() =>
  weightsFailure.value === 'read'
    ? t('plans.weightsFailed')
    : weightsFailure.value === 'save'
      ? t('plans.algorithmFailed')
      : ''
)
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
  settings.weightMode === 'mower' ? settings.mowerWeights : settings.productionWeights
)
const cachedRosterCount = computed(() => settings.cachedOperators?.length ?? 0)
async function readCache() {
  cacheLoading.value = true
  cacheFailed.value = false
  try {
    const { data } = await axios.get(`${import.meta.env.VITE_HTTP_URL}/riic/income-cache`, {
      timeout: 15000,
      signal: controller.signal
    })
    if (alive) applyIncomeCache(settings, data)
  } catch {
    if (alive) cacheFailed.value = true
  } finally {
    if (alive) cacheLoading.value = false
  }
}
async function readWeights() {
  weightsBusy.value = true
  weightsFailure.value = ''
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
    if (alive) weightsFailure.value = 'read'
    throw new Error(t('plans.weightsFailed'), { cause: error })
  } finally {
    if (alive) weightsBusy.value = false
  }
}
async function selectAlgorithm(value) {
  const preset = incomeAlgorithms.find((item) => item.value === value)
  if (!preset?.ratios || !sharedRatios || weightsBusy.value) return
  weightsBusy.value = true
  weightsFailure.value = ''
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
  } catch {
    if (alive) weightsFailure.value = 'save'
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
const exportDetails = reactive({ author: '', remarks: '' })
const completedSnapshot = ref(null)
const archiveLoading = ref(true)
const archiveFailure = ref(null)
const archiveError = computed(() =>
  archiveFailure.value
    ? t(archiveFailure.value.key, { detail: incomeDisplayMessage(archiveFailure.value.detail) })
    : ''
)
const attemptDiagnostics = ref([])
const savedAt = ref(null)
let lastCompleted = null
let runSnapshot = null
const imageName = computed(
  () => exportName.value.trim() || completedSnapshot.value?.label || t('plans.planFallback')
)
const seconds = ref(0)
const activeTab = ref('settings')
const progressLog = ref([])
const logPage = ref(1)
const logSearch = ref('')
const filteredEvents = computed(() => {
  const rows = state.result?.eventLog?.entries ?? []
  const query = logSearch.value.toLowerCase()
  return query
    ? rows.filter((row) =>
        `${row.type} ${incomeDisplayMessage(row.type)} ${row.room} ${row.room ? incomeRoomName(row.room) : ''} ${row.detail}`
          .toLowerCase()
          .includes(query)
      )
    : rows
})
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
const planIssues = computed(() => {
  if (!props.snapshot) return []
  const validation = validateRosterWorkspace(incomeWorkspace(props.snapshot.plan))
  return validation.issues.map((issue) => ({
    ...issue,
    message: incomeDisplayMessage(planValidationMessage(issue, validation.power))
  }))
})
const format = (value) => Number(value).toLocaleString(locale.value, { maximumFractionDigits: 2 })
const weights = computed(() => [
  ['exp', t('plans.experience')],
  ['gold', t('plans.pureGold')],
  ['orders', t('plans.trading')],
  ['fragments', t('plans.shards')],
  ['orundum', t('plans.orundum')]
])
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
    if (alive) archiveFailure.value = { key: 'plans.archiveReadError', detail: error.message }
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
  archiveFailure.value = null
  try {
    await saveIncomeArchive(lastCompleted)
  } catch (error) {
    if (alive) archiveFailure.value = { key: 'plans.archiveSaveError', detail: error.message }
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
  if (archiveLoading.value || submitting.value || state.running || exporting.value) return
  submitting.value = true
  state.error = null
  attemptDiagnostics.value = []
  try {
    if (settings.weightMode === 'mower') await readWeights()
    if (!alive) return
    const { image, ...snapshot } = props.snapshot
    const captured = { ...JSON.parse(JSON.stringify(snapshot)), image }
    const runSettings = JSON.parse(JSON.stringify(settings))
    incomeRequest(captured.plan, runSettings)
    validating.value = true
    const { data: validation } = await axios.post(
      `${import.meta.env.VITE_HTTP_URL}/validate-plan`,
      { plan: captured.plan, operatorMode: runSettings.operatorMode },
      { timeout: 0, signal: controller.signal }
    )
    validating.value = false
    if (!alive) return
    if (validation.success !== true)
      throw new Error(validation.message || t('plans.validationFailed'))
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
    :title="t('plans.calculateIncome')"
    class="income-dialog"
    :content-style="{
      overflowY: 'auto',
      paddingBottom: activeTab === 'timeline' ? '0' : undefined
    }"
    :mask-closable="false"
    @update:show="!$event && close()"
  >
    <n-spin v-if="preparing" :description="t('plans.preparingSnapshot')" />
    <n-alert v-if="prepareError" type="error">{{ incomeDisplayMessage(prepareError) }}</n-alert>
    <n-alert v-if="archiveError" type="warning" class="notice">
      {{ archiveError }}
      <n-button v-if="state.result?.success" size="small" @click="persistResult">{{
        t('plans.retrySave')
      }}</n-button>
    </n-alert>
    <p v-if="archiveLoading">{{ t('plans.loadingArchive') }}</p>
    <p v-else-if="savedAt">
      {{ t('plans.retainedResult', { date: new Date(savedAt).toLocaleString(locale) }) }}
    </p>
    <template v-if="snapshot || state.result?.success">
      <div v-if="state.running" class="notice" role="status" aria-live="polite">
        <n-progress type="line" :percentage="Math.floor((state.progress?.fraction ?? 0) * 100)" />
        <p>
          {{
            t('plans.simulationProgress', {
              label: incomeDisplayMessage(state.progress?.label) || t('plans.preparingSimulation'),
              seconds
            })
          }}
        </p>
        <n-alert v-if="silent || state.progress?.activity?.status === 'slow'" type="warning">{{
          state.progress?.activity?.status === 'slow'
            ? t('plans.slowSimulation')
            : t('plans.noProgress')
        }}</n-alert>
      </div>
      <n-alert v-if="validating" class="notice" type="info" role="status">{{
        t('plans.validatingCombination')
      }}</n-alert>
      <n-alert v-if="state.error" ref="errorAlert" role="alert" class="notice" type="error">
        {{ incomeDisplayMessage(state.error) }}
        <p v-for="(d, i) in attemptDiagnostics" :key="i">{{ incomeDisplayMessage(d.message) }}</p>
      </n-alert>
      <n-alert v-if="exportError" class="notice" type="error">{{
        t('plans.exportFailed', { detail: incomeDisplayMessage(exportError) })
      }}</n-alert>
      <n-tabs v-model:value="activeTab" type="line" animated>
        <n-tab-pane name="settings" :tab="t('plans.parametersTab')">
          <n-alert
            v-if="planIssues.length"
            class="notice"
            type="warning"
            :title="t('plans.validationNotice')"
          >
            <p>{{ t('plans.backupValidationHelp') }}</p>
            <ul>
              <li v-for="(issue, i) in planIssues" :key="i">{{ issue.message }}</li>
            </ul>
          </n-alert>
          <n-alert class="notice" type="info">{{ t('plans.simulationHelp') }}</n-alert>
          <n-form
            :disabled="state.running || exporting || submitting || weightsBusy"
            label-placement="left"
            label-width="150"
            :show-feedback="false"
          >
            <div class="two-columns">
              <n-form-item :label="t('plans.warmupDays')"
                ><n-input-number
                  v-model:value="settings.warmupDays"
                  :min="0"
                  :max="30"
                  :precision="0"
              /></n-form-item>
              <n-form-item :label="t('plans.sampleDays')"
                ><n-input-number
                  v-model:value="settings.sampleDays"
                  :min="1"
                  :max="90"
                  :precision="0"
              /></n-form-item>
            </div>
            <p>
              {{
                t('plans.simulationDays', {
                  total: (settings.warmupDays ?? 0) + (settings.sampleDays ?? 0),
                  sample: settings.sampleDays
                })
              }}
            </p>
            <n-form-item :label="t('plans.droneTarget')"
              ><n-select
                v-model:value="settings.droneRoom"
                :options="[{ label: t('plans.noDrones'), value: '' }, ...targets]"
            /></n-form-item>
            <n-form-item :label="t('plans.randomSeed')"
              ><n-input-number
                v-model:value="settings.seed"
                :min="0"
                :max="4294967295"
                :precision="0"
            /></n-form-item>
            <n-form-item :label="t('plans.operatorDevelopment')"
              ><n-select
                v-model:value="settings.operatorMode"
                :options="[
                  { label: t('plans.cachedDevelopment'), value: 'cache' },
                  { label: t('plans.maximumDevelopment'), value: 'maximum' },
                  { label: t('plans.customDevelopment'), value: 'custom' }
                ]"
            /></n-form-item>
            <p v-if="settings.operatorMode === 'cache'">
              {{
                settings.cachedOperators
                  ? t('plans.cachedRosterCount', { count: cachedRosterCount })
                  : t('plans.noRosterCache')
              }}
            </p>
            <n-alert v-if="cacheError" type="warning">{{ cacheError }}</n-alert>
            <n-button
              size="small"
              :loading="cacheLoading"
              :disabled="state.running || exporting || submitting || weightsBusy"
              @click="readCache"
              >{{ t('plans.reloadCache') }}</n-button
            >
            <n-form-item
              v-if="settings.operatorMode === 'custom'"
              :label="t('plans.operatorRoster')"
              ><n-input
                v-model:value="settings.operatorText"
                type="textarea"
                :placeholder="t('plans.rosterPlaceholder')"
                :autosize="{ minRows: 3, maxRows: 8 }"
            /></n-form-item>
            <n-form-item :label="t('plans.jayeEliteZero')"
              ><n-switch v-model:value="settings.jayeElite0"
            /></n-form-item>
            <n-form-item :label="t('plans.finiteInventory')"
              ><n-switch
                :value="required || settings.finiteInventory"
                :disabled="required || state.running || exporting || submitting || weightsBusy"
                @update:value="settings.finiteInventory = $event"
            /></n-form-item>
            <template v-if="required || settings.finiteInventory">
              <n-form-item :label="t('plans.inventorySource')">
                <n-select
                  v-model:value="settings.inventorySource"
                  :options="[
                    { label: t('plans.cachedInventory'), value: 'cache' },
                    { label: t('plans.manualInventory'), value: 'manual' }
                  ]"
                />
              </n-form-item>
              <p v-if="settings.inventorySource === 'cache'">
                {{
                  settings.cachedInventory
                    ? t('plans.inventoryCacheHelp')
                    : t('plans.noInventoryCache')
                }}
                {{
                  settings.cacheObservedAt
                    ? t('plans.inventorySyncedAt', {
                        date: new Date(settings.cacheObservedAt * 1000).toLocaleString(locale)
                      })
                    : ''
                }}
              </p>
              <n-form-item :label="t('plans.goldOverdraft')"
                ><n-switch v-model:value="settings.allowGoldDebt"
              /></n-form-item>
            </template>
            <p v-if="required || settings.finiteInventory">
              {{
                t('plans.inventoryExplanation', {
                  requirement: required ? t('plans.requiredInventory') : '',
                  shortage: settings.allowGoldDebt
                    ? t('plans.goldDebtHelp')
                    : t('plans.shortageHelp')
                })
              }}
            </p>
            <div v-if="required || settings.finiteInventory" class="two-columns">
              <n-form-item
                v-for="item in MOWER_INVENTORY_ITEMS"
                :key="item.resource"
                :label="planDisplayName(item.label)"
                ><n-input-number
                  :value="stock?.[item.resource] ?? 0"
                  :disabled="!stock || state.running || exporting || submitting || weightsBusy"
                  placeholder="0"
                  :min="0"
                  :max="Number.MAX_SAFE_INTEGER"
                  :precision="0"
                  @update:value="stock[item.resource] = $event"
              /></n-form-item>
            </div>
            <n-collapse
              ><n-collapse-item :title="t('plans.outputWeights')" name="weights">
                <n-form-item :label="t('plans.weightSource')"
                  ><n-select
                    v-model:value="settings.weightMode"
                    :options="[
                      { label: t('plans.mowerWeights'), value: 'mower' },
                      { label: t('plans.customWeights'), value: 'custom' }
                    ]"
                /></n-form-item>
                <template v-if="settings.weightMode === 'mower'">
                  <n-form-item :label="t('plans.incomeAlgorithm')"
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
                  <p>{{ t('plans.algorithmSaveHelp') }}</p>
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
        <n-tab-pane name="results" :tab="t('plans.incomeTab')">
          <n-empty v-if="!state.result?.success" :description="t('plans.incomeEmpty')" />
          <template v-if="state.result?.success">
            <n-form-item :label="t('plans.planName')" :show-feedback="false"
              ><n-input
                v-model:value="exportName"
                @change="saveName"
                :placeholder="completedSnapshot?.label || t('plans.planFallback')"
                :maxlength="60"
                :disabled="exporting"
            /></n-form-item>
            <p>{{ t('plans.filenameHelp') }}</p>
            <n-form-item :label="t('plans.author')" :show-feedback="false">
              <n-input
                v-model:value="exportDetails.author"
                @change="saveName"
                :placeholder="t('plans.authorPlaceholder')"
                :maxlength="40"
                :disabled="exporting"
              />
            </n-form-item>
            <n-form-item :label="t('plans.remarks')" :show-feedback="false">
              <n-input
                v-model:value="exportDetails.remarks"
                @change="saveName"
                type="textarea"
                :placeholder="t('plans.remarksPlaceholder')"
                :maxlength="300"
                show-count
                :autosize="{ minRows: 2, maxRows: 4 }"
                :disabled="exporting"
              />
            </n-form-item>
            <p>{{ t('plans.exportDetailsHelp') }}</p>
            <p>
              {{
                t('plans.resultDays', {
                  warmup: state.input.settings.warmupDays,
                  sample: state.input.settings.sampleDays
                })
              }}
            </p>
            <p v-if="state.result.inventoryMode === 'finite'">
              {{
                t('plans.goldBalances', {
                  initial: format(state.result.goldInventory.initial),
                  opening: format(state.result.goldInventory.sampleOpening),
                  closing: format(state.result.goldInventory.closing)
                })
              }}
            </p>
            <p>
              {{
                t('plans.resultWeights', {
                  label:
                    state.input.settings.weightMode === 'mower'
                      ? incomeAlgorithmLabel(state.input.settings.mowerAlgorithm)
                      : t('plans.customWeights')
                })
              }}
            </p>
            <p>
              {{ t('plans.goldEquivalentHelp')
              }}<span v-if="state.result.inventoryMode === 'finite'">{{
                t('plans.finiteBalanceHelp')
              }}</span>
            </p>
            <h3>
              {{
                t('plans.dailyWeightedOutputValue', {
                  value: format(state.result.summary.totalScore82)
                })
              }}
            </h3>
            <n-table size="small"
              ><thead>
                <tr>
                  <th>{{ t('plans.output') }}</th>
                  <th>{{ t('plans.dailyAverage') }}</th>
                  <th>{{ t('plans.sampleTotal') }}</th>
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
            <p v-if="exported" role="status">{{ t('plans.exportStarted') }}</p>
            <n-collapse class="notice">
              <n-collapse-item :title="t('plans.facilityData')" name="rooms">
                <n-table size="small"
                  ><thead>
                    <tr>
                      <th>{{ t('plans.facility') }}</th>
                      <th>{{ t('plans.averageEfficiency') }}</th>
                      <th>{{ t('plans.occupiedDuration') }}</th>
                    </tr>
                  </thead>
                  <tbody>
                    <tr v-for="room in state.result.rooms" :key="room.roomId">
                      <td>{{ incomeRoomName(room.roomId) }}</td>
                      <td>{{ format(room.averageEfficiencyPercent) }}%</td>
                      <td>{{ t('plans.hoursValue', { value: format(room.occupiedHours) }) }}</td>
                    </tr>
                  </tbody></n-table
                >
              </n-collapse-item>
              <n-collapse-item
                v-if="state.result.inventoryMode === 'finite'"
                :title="t('plans.inventoryFlow')"
                name="stock"
              >
                <n-table size="small"
                  ><thead>
                    <tr>
                      <th>{{ t('plans.resource') }}</th>
                      <th>{{ t('plans.opening') }}</th>
                      <th>{{ t('plans.income') }}</th>
                      <th>{{ t('plans.expense') }}</th>
                      <th>{{ t('plans.closing') }}</th>
                    </tr>
                  </thead>
                  <tbody>
                    <tr v-for="item in MOWER_INVENTORY_ITEMS" :key="item.resource">
                      <td>{{ planDisplayName(item.label) }}</td>
                      <td>{{ format(state.result.resources?.opening[item.resource] ?? 0) }}</td>
                      <td>{{ format(state.result.resources?.inflows[item.resource] ?? 0) }}</td>
                      <td>{{ format(state.result.resources?.outflows[item.resource] ?? 0) }}</td>
                      <td>{{ format(state.result.resources?.closing[item.resource] ?? 0) }}</td>
                    </tr>
                  </tbody></n-table
                >
              </n-collapse-item>
              <n-collapse-item :title="t('plans.modelAssumptions')" name="assumptions"
                ><p v-for="line in reportLines" :key="line">{{ line }}</p></n-collapse-item
              >
            </n-collapse>
            <n-collapse class="notice"
              ><n-collapse-item
                :title="
                  t('plans.simulationDiagnostics', { count: state.result.diagnostics.length })
                "
                name="diagnostics"
                ><p v-for="(d, i) in state.result.diagnostics" :key="i">
                  {{ incomeDisplayMessage(d.message) }}
                </p></n-collapse-item
              ></n-collapse
            >
          </template>
        </n-tab-pane>
        <n-tab-pane name="timeline" :tab="t('plans.workRecords')" display-directive="show:lazy">
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
              state.result?.success ? t('plans.missingWorkRecords') : t('plans.workRecordsEmpty')
            "
          />
        </n-tab-pane>
        <n-tab-pane name="logs" :tab="t('plans.simulationLogs')">
          <n-alert
            v-if="state.running && state.progress?.activity"
            class="notice"
            :type="state.progress.activity.status === 'slow' ? 'warning' : 'info'"
            :title="t('plans.runningActivity')"
          >
            <IncomeActivity :activity="state.progress.activity" />
          </n-alert>
          <n-alert
            v-if="state.bottleneck"
            class="notice"
            :type="state.error ? 'warning' : 'info'"
            :title="t('plans.resultActivity')"
          >
            <p>
              {{
                t('plans.bottleneckProgress', {
                  seconds: format(state.bottleneck.elapsedSeconds),
                  label: incomeDisplayMessage(state.bottleneck.progressLabel)
                })
              }}
            </p>
            <p v-if="state.bottleneck.silence">
              {{ t('plans.bottleneckSilence', { seconds: state.bottleneck.silence.seconds }) }}
            </p>
            <IncomeActivity v-if="summary" :activity="summary.activity" />
            <p v-for="(item, i) in state.bottleneck.diagnostics" :key="i">
              {{ incomeDisplayMessage(item.message) }}
            </p>
          </n-alert>

          <n-collapse v-if="progressLog.length" class="notice"
            ><n-collapse-item :title="t('plans.progressRecords')" name="progress"
              ><div class="income-log">
                <p v-for="(line, i) in progressLog" :key="i">{{ line }}</p>
              </div></n-collapse-item
            ></n-collapse
          >
          <template v-if="state.result?.eventLog">
            <p>
              {{
                t('plans.eventCount', {
                  total: state.result.eventLog.total,
                  retained: state.result.eventLog.entries.length
                })
              }}
            </p>
            <n-input
              v-model:value="logSearch"
              :placeholder="t('plans.searchEvents')"
              clearable
              @update:value="logPage = 1"
            />
            <div class="income-log">
              <n-table size="small"
                ><thead>
                  <tr>
                    <th>{{ t('plans.time') }}</th>
                    <th>{{ t('plans.event') }}</th>
                    <th>{{ t('plans.detail') }}</th>
                  </tr>
                </thead>
                <tbody>
                  <tr v-for="(row, i) in visibleEvents" :key="i">
                    <td class="event-time">{{ incomeLogTime(row.hours) }}</td>
                    <td>{{ incomeDisplayMessage(row.type) }}</td>
                    <td>{{ row.room ? incomeRoomName(row.room) : row.room }} {{ row.detail }}</td>
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
          <n-empty v-else-if="!state.running && !state.error" :description="t('plans.logsEmpty')" />
        </n-tab-pane>
      </n-tabs>
    </template>
    <template #footer
      ><n-space justify="end">
        <n-button @click="close">{{
          validating
            ? t('plans.cancelWaitClose')
            : state.running
              ? t('plans.stopClose')
              : t('plans.close')
        }}</n-button>
        <n-button v-if="state.running" type="warning" @click="session.cancel">{{
          t('plans.stopSimulation')
        }}</n-button>
        <n-button
          v-if="state.result?.success"
          :loading="exporting"
          :disabled="state.running || exporting || submitting || weightsBusy"
          @click="exportImage"
          >{{ exported ? t('plans.exportAgain') : t('plans.exportIncome') }}</n-button
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
          >{{
            validating
              ? t('plans.validatingPlan')
              : state.result?.success
                ? t('plans.rerun')
                : t('plans.startSimulation')
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
