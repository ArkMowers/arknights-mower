<script setup>
import { i18n } from '@/i18n'
import { reportErrorMessage } from '@/i18n/reports'
const { t } = i18n.global
import { computed, inject, onMounted, onUnmounted, ref } from 'vue'
import { useThemeVars } from 'naive-ui'

const axios = inject('axios')
const themeVars = useThemeVars()
const deleteDialogStyle = computed(() => ({
  width: 'min(440px, calc(100vw - 32px))',
  '--mower-control-surface': themeVars.value.actionColor,
  '--mower-error': themeVars.value.errorColor
}))
const queryAt = ref(Date.now())
const loadedAt = ref(queryAt.value)
const timeCenter = ref(queryAt.value)
const browseMode = ref('time')
const truncated = ref(false)
const events = ref([])
const logs = ref([])
const eventLoading = ref(false)
const logLoading = ref(false)
const eventError = ref('')
const logError = ref('')
const activeEventId = ref('')
const screenshots = ref([])
const imageIndex = ref(0)
const imageFailed = ref(false)
const searchText = ref('')
const levelFilter = ref('all')
const exporting = ref(false)
const exportError = ref('')
const selectedEventIds = ref([])
const pendingDeleteEvents = ref(null)
const showExportDialog = ref(false)
const exportCenter = ref(null)
const exportRange = ref(null)
const includeScreenshots = ref(true)
const deleting = ref(false)
const deleteError = ref('')
const analysisLoading = ref(false)
const analysisText = ref('')
const analysisError = ref('')
let requestVersion = 0
let eventRequestVersion = 0

const levelOptions = computed(() => [
  { label: t('reports.allLogLevels'), value: 'all' },
  { label: t('reports.errorLevel'), value: 'ERROR' },
  { label: t('reports.criticalLevel'), value: 'CRITICAL' },
  { label: t('reports.warningLevel'), value: 'WARNING' },
  { label: t('reports.infoLevel'), value: 'INFO' },
  { label: t('reports.debugLevel'), value: 'DEBUG' }
])

const selectedEvents = computed(() =>
  events.value.filter((event) => selectedEventIds.value.includes(event.id))
)
const allEventsSelected = computed(
  () => events.value.length > 0 && selectedEvents.value.length === events.value.length
)
const archiveBusy = computed(() => deleting.value || exporting.value)

const activeEvent = computed(() => events.value.find((event) => event.id === activeEventId.value))
const imagePath = computed(() => screenshots.value[imageIndex.value] || '')
const canExport = computed(
  () => !logLoading.value && !logError.value && (browseMode.value === 'time' || !!activeEvent.value)
)
const exportRangeError = computed(() => {
  const [start, end] = exportRange.value || []
  if (!Number.isFinite(start) || !Number.isFinite(end) || start < 0 || start >= end) {
    return t('reports.invalidExportRange')
  }
  if (end - start > 7 * 86400000) return t('reports.exportTooLong')
  if (end > Date.now() + 3600000) return t('reports.exportFutureEnd')
  return ''
})
const windowLabel = computed(() => {
  const first = activeEvent.value ? Number(activeEvent.value.time_ns) / 1e6 : loadedAt.value
  const last = activeEvent.value
    ? Number(activeEvent.value.last_error_ns || activeEvent.value.time_ns) / 1e6
    : first
  const format = (value) =>
    new Date(value).toLocaleString(i18n.global.locale.value, { hour12: false })
  return `${format(first - 300000)} — ${format(last + 300000)}`
})
const imageUrl = computed(() =>
  imagePath.value ? `${import.meta.env.VITE_HTTP_URL}/screenshots/${imagePath.value}` : ''
)
const visibleLogs = computed(() => {
  const search = searchText.value.trim().toLocaleLowerCase()
  return logs.value
    .map((row, index) => ({ ...row, index, ...parseLog(row.message) }))
    .filter(
      (row) =>
        (levelFilter.value === 'all' || row.level === levelFilter.value) &&
        (!search || row.message.toLocaleLowerCase().includes(search))
    )
})

function parseLog(message) {
  const firstLine = message.split('\n', 1)[0]
  const match = firstLine.match(
    /^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}(?:,\d+)? .*? (DEBUG|INFO|WARNING|ERROR|CRITICAL) [^:]*: (.*)$/
  )
  if (!match) {
    return { level: 'INFO', summary: firstLine, detail: message.slice(firstLine.length).trim() }
  }
  return {
    level: match[1],
    summary: match[2],
    detail: message.slice(firstLine.length).trim()
  }
}

function formatTime(timestampNs) {
  return new Date(Number(timestampNs) / 1000000).toLocaleString(i18n.global.locale.value, {
    hour12: false
  })
}

function imageTime(path) {
  const stem =
    path
      .split('/')
      .at(-1)
      ?.replace(/\.(jpg|png)$/, '') || ''
  return /^\d{18,}$/.test(stem) ? formatTime(stem) : stem
}

function imageNearest(center) {
  let best = 0
  let distance = Infinity
  for (let index = 0; index < screenshots.value.length; index++) {
    const timestamp =
      Number(
        screenshots.value[index]
          .split('/')
          .at(-1)
          .replace(/\.(jpg|png)$/, '')
      ) / 1e6
    const nextDistance = Math.abs(timestamp - center)
    if (nextDistance < distance) {
      best = index
      distance = nextDistance
    }
  }
  return best
}

async function loadEvents() {
  if (archiveBusy.value) return
  const version = ++eventRequestVersion
  eventLoading.value = true
  eventError.value = ''
  try {
    const response = await axios.get(`${import.meta.env.VITE_HTTP_URL}/diagnostics/errors`)
    if (version !== eventRequestVersion) return
    events.value = response.data.events || []
    selectedEventIds.value = selectedEvents.value.map((event) => event.id)
    if (browseMode.value === 'archives') {
      if (events.value.length) selectEvent(activeEvent.value || events.value[0])
      else {
        ++requestVersion
        activeEventId.value = ''
        logLoading.value = false
        clearEvidence()
      }
    }
  } catch {
    if (version === eventRequestVersion) eventError.value = t('reports.errorRecordsFailed')
  } finally {
    if (version === eventRequestVersion) eventLoading.value = false
  }
}

function clearEvidence() {
  showExportDialog.value = false
  logs.value = []
  screenshots.value = []
  imageIndex.value = 0
  imageFailed.value = false
  truncated.value = false
  logError.value = ''
  exportError.value = ''
  analysisText.value = ''
  analysisError.value = ''
}

async function loadLogs(center, event = null) {
  const version = ++requestVersion
  clearEvidence()
  activeEventId.value = event?.id || ''
  loadedAt.value = center
  logLoading.value = true
  const path = event ? `/diagnostics/errors/${event.id}/logs` : '/diagnostics/timeline'
  try {
    const response = await axios.get(`${import.meta.env.VITE_HTTP_URL}${path}`, {
      params: event ? undefined : { at: center }
    })
    if (version !== requestVersion) return
    logs.value = response.data.logs || []
    screenshots.value = event
      ? [...(event.screenshots || [])]
      : response.data.screenshots || [
          ...new Set(logs.value.map((row) => row.screenshot).filter(Boolean))
        ]
    imageIndex.value = imageNearest(center)
    truncated.value = !!response.data.truncated
  } catch {
    if (version === requestVersion) logError.value = t('reports.logsFailed')
  } finally {
    if (version === requestVersion) logLoading.value = false
  }
}

function loadWindow(center = queryAt.value) {
  if (!Number.isFinite(center)) return
  browseMode.value = 'time'
  queryAt.value = center
  timeCenter.value = center
  return loadLogs(center)
}

function selectEvent(event) {
  browseMode.value = 'archives'
  return loadLogs(Math.floor(event.time_ns / 1e6), event)
}

function setBrowseMode(mode) {
  if (mode === browseMode.value) return
  if (mode === 'time') return loadWindow(timeCenter.value)
  browseMode.value = 'archives'
  if (events.value.length) return selectEvent(events.value[0])
  ++requestVersion
  activeEventId.value = ''
  logLoading.value = false
  clearEvidence()
}

function moveWindow(step) {
  return loadWindow(Math.max(0, Math.min(Date.now(), loadedAt.value + step * 600000)))
}

function refreshLogs() {
  if (browseMode.value === 'archives' && !activeEvent.value) return
  return activeEvent.value ? selectEvent(activeEvent.value) : loadWindow(loadedAt.value)
}

function onTabKeydown(event) {
  if (!['ArrowLeft', 'ArrowRight', 'Home', 'End'].includes(event.key)) return
  event.preventDefault()
  const mode =
    event.key === 'Home'
      ? 'time'
      : event.key === 'End'
        ? 'archives'
        : browseMode.value === 'time'
          ? 'archives'
          : 'time'
  setBrowseMode(mode)
  event.currentTarget.parentElement
    .querySelector(`#${mode === 'time' ? 'time' : 'archives'}-tab`)
    .focus()
}

function showScreenshot(path) {
  let index = screenshots.value.indexOf(path)
  if (index < 0) {
    screenshots.value.push(path)
    index = screenshots.value.length - 1
  }
  imageIndex.value = index
  imageFailed.value = false
}

function moveImage(step) {
  imageIndex.value = Math.max(0, Math.min(screenshots.value.length - 1, imageIndex.value + step))
  imageFailed.value = false
}

function onImageSeek() {
  imageFailed.value = false
}

function jumpToNow() {
  return loadWindow(Date.now())
}

function setExportHours(hours) {
  exportRange.value = [
    Math.max(0, exportCenter.value - hours * 3600000),
    exportCenter.value + 300000
  ]
}

function beginExport() {
  if (!canExport.value || exporting.value) return
  if (activeEvent.value) return exportWindow()
  exportCenter.value = loadedAt.value
  setExportHours(1)
  exportError.value = ''
  showExportDialog.value = true
}

async function exportWindow() {
  if (!canExport.value || exporting.value) return
  const event = activeEvent.value
  if (!event && (!showExportDialog.value || exportRangeError.value)) return
  exporting.value = true
  exportError.value = ''
  const center = event ? Math.floor(event.time_ns / 1000000) : exportCenter.value
  const path = event ? `/diagnostics/errors/${event.id}/export` : '/diagnostics/export'
  const params = event
    ? undefined
    : {
        at: center,
        start: exportRange.value[0],
        end: exportRange.value[1],
        screenshots: includeScreenshots.value ? '1' : '0'
      }
  try {
    const response = await axios.get(`${import.meta.env.VITE_HTTP_URL}${path}`, {
      params,
      responseType: 'blob'
    })
    const date = new Date(center)
    const stamp = `${date.getFullYear()}${String(date.getMonth() + 1).padStart(2, '0')}${String(date.getDate()).padStart(2, '0')}-${String(date.getHours()).padStart(2, '0')}${String(date.getMinutes()).padStart(2, '0')}${String(date.getSeconds()).padStart(2, '0')}`
    downloadBundle(response.data, `${t('reports.logScheduleTitle')}-${stamp}.zip`)
    showExportDialog.value = false
  } catch {
    exportError.value = t('reports.exportFailed')
  } finally {
    exporting.value = false
  }
}

function downloadBundle(blob, filename) {
  const url = URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = url
  link.download = filename
  document.body.appendChild(link)
  link.click()
  link.remove()
  setTimeout(() => URL.revokeObjectURL(url), 1000)
}

function toggleEvent(id, checked) {
  if (archiveBusy.value) return
  const ids = new Set(selectedEventIds.value)
  if (checked) ids.add(id)
  else ids.delete(id)
  selectedEventIds.value = [...ids]
}

function toggleAllEvents(checked) {
  if (archiveBusy.value) return
  selectedEventIds.value = checked ? events.value.map((event) => event.id) : []
}

async function exportSelected() {
  if (archiveBusy.value || eventLoading.value || !selectedEvents.value.length) return
  const targets = [...selectedEvents.value]
  exporting.value = true
  exportError.value = ''
  let writer
  try {
    const { BlobReader, BlobWriter, ZipWriter } = await import('@zip.js/zip.js')
    writer = new ZipWriter(new BlobWriter('application/zip'), { useWebWorkers: false })
    for (const event of targets) {
      const response = await axios.get(
        `${import.meta.env.VITE_HTTP_URL}/diagnostics/errors/${event.id}/export`,
        { responseType: 'blob' }
      )
      await writer.add(
        `${t('reports.errorArchives')}-${event.id}.zip`,
        new BlobReader(response.data),
        { level: 0 }
      )
    }
    const blob = await writer.close()
    writer = null
    downloadBundle(blob, `${t('reports.selectedArchivesFilename', { count: targets.length })}.zip`)
  } catch {
    exportError.value = t('reports.archiveExportFailed')
  } finally {
    if (writer) await writer.close().catch(() => {})
    exporting.value = false
  }
}

async function analyzeEvent() {
  const event = activeEvent.value
  if (!event || analysisLoading.value) return
  analysisLoading.value = true
  analysisError.value = ''
  analysisText.value = ''
  try {
    const response = await axios.post(
      `${import.meta.env.VITE_HTTP_URL}/diagnostics/errors/${event.id}/analyze`,
      {},
      { headers: { 'X-Mower-Diagnostics': '1' } }
    )
    if (activeEventId.value === event.id) analysisText.value = response.data.analysis || ''
  } catch (error) {
    if (activeEventId.value === event.id) {
      analysisError.value = error.response?.data?.error || t('reports.aiAnalysisFailed')
    }
  } finally {
    analysisLoading.value = false
  }
}

function confirmDeleteSelected() {
  if (archiveBusy.value || eventLoading.value || !selectedEvents.value.length) return
  pendingDeleteEvents.value = [...selectedEvents.value]
  deleteError.value = ''
}

function handleDeleteModal(show) {
  if (!show && !deleting.value) {
    pendingDeleteEvents.value = null
    deleteError.value = ''
  }
}

async function deleteEvent() {
  const targets = [...(pendingDeleteEvents.value || [])]
  if (!targets.length || archiveBusy.value) return
  deleting.value = true
  deleteError.value = ''
  ++eventRequestVersion
  eventLoading.value = false
  const removed = new Set()
  const failed = []
  try {
    for (const event of targets) {
      try {
        await axios.delete(`${import.meta.env.VITE_HTTP_URL}/diagnostics/errors/${event.id}`, {
          headers: { 'X-Mower-Diagnostics': '1' }
        })
        removed.add(event.id)
      } catch (error) {
        if (error.response?.status === 404) removed.add(event.id)
        else failed.push(event)
      }
    }
    events.value = events.value.filter((item) => !removed.has(item.id))
    selectedEventIds.value = selectedEventIds.value.filter((id) => !removed.has(id))
    pendingDeleteEvents.value = failed.length ? failed : null
    if (failed.length)
      deleteError.value = t('reports.deleteArchivesFailed', {
        removed: removed.size,
        failed: failed.length
      })
    if (removed.has(activeEventId.value)) {
      if (events.value.length) await selectEvent(events.value[0])
      else {
        ++requestVersion
        activeEventId.value = ''
        logLoading.value = false
        clearEvidence()
      }
    }
  } finally {
    deleting.value = false
  }
}

onUnmounted(() => {
  ++requestVersion
  ++eventRequestVersion
})

onMounted(() => {
  loadEvents()
  loadWindow()
})
</script>

<template>
  <main class="schedule-page">
    <header class="page-heading">
      <div>
        <h1>{{ t('reports.logScheduleTitle') }}</h1>
        <p>{{ t('reports.logScheduleHelp') }}</p>
      </div>
      <SessionLink class="back-link" to="/">{{ t('reports.backToLogs') }}</SessionLink>
    </header>

    <div class="browse-tabs" role="tablist" :aria-label="t('reports.logSource')">
      <button
        id="time-tab"
        type="button"
        role="tab"
        :aria-selected="browseMode === 'time'"
        :tabindex="browseMode === 'time' ? 0 : -1"
        aria-controls="log-workspace"
        @click="setBrowseMode('time')"
        @keydown="onTabKeydown"
      >
        {{ t('reports.browseByTime') }}
      </button>
      <button
        id="archives-tab"
        type="button"
        role="tab"
        :aria-selected="browseMode === 'archives'"
        :tabindex="browseMode === 'archives' ? 0 : -1"
        aria-controls="log-workspace"
        @click="setBrowseMode('archives')"
        @keydown="onTabKeydown"
      >
        {{ t('reports.errorArchives') }}<span>{{ events.length }}</span>
      </button>
    </div>

    <section class="time-bar mower-surface-panel" :aria-label="t('reports.logActions')">
      <template v-if="browseMode === 'time'">
        <n-button secondary :disabled="loadedAt <= 0" @click="moveWindow(-1)">{{
          t('reports.previousTenMinutes')
        }}</n-button>
        <div class="time-field">
          <label for="schedule-time">{{ t('reports.viewTime') }}</label>
          <n-date-picker
            id="schedule-time"
            v-model:value="queryAt"
            type="datetime"
            :clearable="false"
          />
        </div>
        <n-button type="primary" :loading="logLoading" @click="loadWindow()">{{
          t('reports.view')
        }}</n-button>
        <n-button secondary :disabled="loadedAt >= Date.now()" @click="moveWindow(1)">{{
          t('reports.nextTenMinutes')
        }}</n-button>
        <n-button secondary @click="jumpToNow">{{ t('reports.jumpNow') }}</n-button>
      </template>
      <n-button
        secondary
        :loading="logLoading"
        :disabled="browseMode === 'archives' && !activeEvent"
        @click="refreshLogs"
        >{{ t('reports.refreshLogs') }}</n-button
      >
      <n-button
        v-if="browseMode === 'time'"
        class="export-button"
        secondary
        :disabled="!canExport"
        :loading="exporting"
        @click="beginExport"
        >{{ t('reports.exportLogsScreenshots') }}</n-button
      >
      <div v-else class="archive-actions">
        <n-button
          secondary
          type="error"
          :disabled="eventLoading || archiveBusy || !selectedEvents.length"
          @click="confirmDeleteSelected"
          >{{ t('reports.deleteSelected') }}</n-button
        >
        <n-button
          secondary
          :disabled="eventLoading || archiveBusy || !selectedEvents.length"
          :loading="exporting"
          @click="exportSelected"
          >{{ t('reports.exportSelected') }}</n-button
        >
      </div>
    </section>
    <p v-if="exportError && !showExportDialog" class="export-error" role="alert">
      {{ reportErrorMessage(exportError) }}
    </p>

    <n-modal
      v-model:show="showExportDialog"
      preset="card"
      :title="t('reports.chooseExportRange')"
      style="width: min(600px, calc(100vw - 32px))"
      :closable="!exporting"
      :mask-closable="!exporting"
      :close-on-esc="!exporting"
    >
      <n-space vertical :size="16">
        <p class="export-hint">{{ t('reports.exportRangeHelp') }}</p>
        <n-space>
          <n-button
            v-for="hours in [1, 6, 24]"
            :key="hours"
            :disabled="exporting"
            @click="setExportHours(hours)"
            >{{ t('reports.beforeViewingTime') }}{{ hours }}{{ t('reports.hours') }}</n-button
          >
        </n-space>
        <div>
          <label for="export-time-range">{{ t('reports.exportTimeRange') }}</label>
          <n-date-picker
            id="export-time-range"
            v-model:value="exportRange"
            type="datetimerange"
            :clearable="false"
            :disabled="exporting"
          />
        </div>
        <n-checkbox v-model:checked="includeScreenshots" :disabled="exporting">{{
          t('reports.includeScreenshots')
        }}</n-checkbox>
        <p class="export-hint">{{ t('reports.retainedExportHelp') }}</p>
        <p v-if="exportRangeError || exportError" class="export-error" role="alert">
          {{ exportRangeError || exportError }}
        </p>
      </n-space>
      <template #action>
        <n-space justify="end">
          <n-button :disabled="exporting" @click="showExportDialog = false">{{
            t('reports.cancel')
          }}</n-button>
          <n-button
            type="primary"
            :loading="exporting"
            :disabled="!!exportRangeError"
            @click="exportWindow"
            >{{ t('reports.exportRange') }}</n-button
          >
        </n-space>
      </template>
    </n-modal>

    <div
      id="log-workspace"
      class="workspace"
      :class="{ 'with-archives': browseMode === 'archives' }"
      role="tabpanel"
      :aria-labelledby="browseMode === 'time' ? 'time-tab' : 'archives-tab'"
    >
      <aside
        v-if="browseMode === 'archives'"
        class="panel events-panel mower-surface-panel"
        :aria-label="t('reports.errorRecords')"
      >
        <div class="panel-heading">
          <div>
            <span class="section-kicker">{{ t('reports.archivedPrefix') }}</span>
            <h2>{{ t('reports.errorRecords') }}</h2>
          </div>
          <n-button secondary :loading="eventLoading" :disabled="archiveBusy" @click="loadEvents">{{
            t('reports.refreshArchives')
          }}</n-button>
        </div>
        <p class="panel-intro">{{ t('reports.chooseArchiveHelp') }}</p>
        <div v-if="eventError" class="state-message error" role="alert">
          {{ reportErrorMessage(eventError) }}
        </div>
        <div v-else-if="eventLoading" class="state-message">{{ t('reports.loadingErrors') }}</div>
        <div v-else-if="!events.length" class="state-message">{{ t('reports.noErrors') }}</div>
        <div v-else class="event-list">
          <n-checkbox
            :checked="allEventsSelected"
            :indeterminate="selectedEvents.length > 0 && !allEventsSelected"
            :disabled="archiveBusy"
            @update:checked="toggleAllEvents"
            >{{ t('reports.selectAllPrefix') }}{{ selectedEvents.length }} / {{ events.length }}）
          </n-checkbox>
          <div v-for="event in events" :key="event.id" class="event-row">
            <n-checkbox
              :checked="selectedEventIds.includes(event.id)"
              :disabled="archiveBusy"
              :aria-label="t('reports.selectErrorRecord', { time: formatTime(event.time_ns) })"
              @update:checked="toggleEvent(event.id, $event)"
            />
            <button
              type="button"
              class="event-card"
              :class="{ selected: activeEventId === event.id }"
              :aria-pressed="activeEventId === event.id"
              @click="selectEvent(event)"
            >
              <span class="event-time">{{ formatTime(event.time_ns) }}</span>
              <span class="event-message">{{ event.message }}</span>
              <span class="event-foot">
                <template v-if="event.error_count > 1"
                  >{{ event.error_count }}{{ t('reports.errorsScreenshotsSeparator') }}</template
                >
                {{ event.screenshots.length }}{{ t('reports.screenshotsUnit') }}</span
              >
              <span class="event-arrow" aria-hidden="true">{{ t('reports.viewRecord') }}</span>
            </button>
          </div>
        </div>
      </aside>

      <section class="panel logs-panel mower-surface-panel" :aria-label="t('reports.logTimeline')">
        <div class="panel-heading">
          <div>
            <span class="section-kicker">{{
              activeEvent ? t('reports.errorWindow') : t('reports.timeWindow')
            }}</span>
            <h2>{{ t('reports.logTimeline') }}</h2>
          </div>
          <span class="count-pill">{{ visibleLogs.length }}</span>
        </div>
        <p class="panel-intro">
          {{ browseMode === 'archives' && !activeEvent ? t('reports.chooseError') : windowLabel }}
        </p>
        <div v-if="activeEvent" class="ai-analysis">
          <n-button type="primary" secondary :loading="analysisLoading" @click="analyzeEvent">{{
            t('reports.aiAnalysis')
          }}</n-button>
          <p>{{ t('reports.aiAnalysisHelp') }}</p>
          <p v-if="analysisError" class="state-message error" role="alert">
            {{ reportErrorMessage(analysisError) }}
          </p>
          <pre v-if="analysisText" class="ai-analysis-result">{{ analysisText }}</pre>
        </div>
        <div class="log-filters">
          <n-input
            v-model:value="searchText"
            clearable
            :placeholder="t('reports.searchLogs')"
            :aria-label="t('reports.searchLogs')"
          />
          <n-select
            v-model:value="levelFilter"
            :options="levelOptions"
            :aria-label="t('reports.filterLogLevel')"
          />
        </div>
        <p v-if="activeEvent?.truncated" class="window-notice">
          {{ t('alphaPages.archiveTruncatedHelp') }}
        </p>
        <p v-if="truncated" class="window-notice">{{ t('reports.truncatedLogsHelp') }}</p>
        <div v-if="logError" class="state-message error" role="alert">
          {{ reportErrorMessage(logError) }}
        </div>
        <div v-else-if="logLoading" class="state-message">{{ t('reports.loadingLogs') }}</div>
        <div v-else-if="!visibleLogs.length" class="state-message">
          {{
            logs.length
              ? t('reports.noFilteredLogs')
              : browseMode === 'archives' && !activeEvent
                ? t('reports.noSelectedError')
                : t('reports.noLogsInWindow')
          }}
        </div>
        <div v-else class="log-list">
          <article v-for="entry in visibleLogs" :key="entry.index" class="log-entry">
            <div class="log-meta">
              <time :title="entry.time">{{ entry.time.slice(11) }}</time>
              <span class="level" :class="entry.level.toLowerCase()">{{ entry.level }}</span>
            </div>
            <div class="log-body">
              <p>{{ entry.summary }}</p>
              <details v-if="entry.detail">
                <summary>{{ t('reports.viewDetails') }}</summary>
                <pre>{{ entry.detail }}</pre>
              </details>
            </div>
            <button
              v-if="entry.screenshot"
              type="button"
              class="image-action"
              @click="showScreenshot(entry.screenshot)"
            >
              {{ t('reports.viewScreenshot') }}
            </button>
          </article>
        </div>
      </section>

      <section
        class="panel image-panel mower-surface-panel"
        :aria-label="t('reports.relatedScreenshots')"
      >
        <div class="panel-heading">
          <div>
            <span class="section-kicker">{{ t('reports.screenshotEvidence') }}</span>
            <h2>{{ t('reports.relatedScreenshots') }}</h2>
          </div>
          <span v-if="screenshots.length" class="count-pill">
            {{ imageIndex + 1 }} / {{ screenshots.length }}
          </span>
        </div>
        <p class="panel-intro">
          {{ imagePath ? imageTime(imagePath) : t('reports.noWindowScreenshot') }}
        </p>
        <div class="image-stage">
          <div v-if="!imagePath" class="image-empty">
            <strong>{{
              logLoading ? t('reports.loadingScreenshots') : t('reports.noScreenshots')
            }}</strong>
            <span>{{ t('reports.screenshotRetentionHelp') }}</span>
          </div>
          <div v-else-if="imageFailed" class="image-empty">
            {{ t('reports.screenshotUnavailable') }}
          </div>
          <img
            v-else
            :key="imagePath"
            class="shot-image"
            :src="imageUrl"
            :alt="t('reports.gameScreenshot')"
            @error="imageFailed = true"
          />
        </div>
        <div v-if="screenshots.length" class="image-navigation">
          <n-button secondary :disabled="imageIndex === 0" @click="moveImage(-1)">{{
            t('reports.previousImage')
          }}</n-button>
          <input
            v-model.number="imageIndex"
            type="range"
            min="0"
            :max="screenshots.length - 1"
            :aria-label="t('reports.chooseScreenshot')"
            @input="onImageSeek"
          />
          <n-button
            secondary
            :disabled="imageIndex === screenshots.length - 1"
            @click="moveImage(1)"
            >{{ t('reports.nextImage') }}</n-button
          >
        </div>
        <a
          v-if="imagePath"
          class="open-image"
          :href="imageUrl"
          target="_blank"
          rel="noopener noreferrer"
          >{{ t('reports.openOriginal') }}</a
        >
      </section>
    </div>

    <n-modal
      :show="pendingDeleteEvents !== null"
      preset="card"
      :title="t('reports.deleteArchives')"
      :style="deleteDialogStyle"
      :closable="!deleting"
      :mask-closable="!deleting"
      :close-on-esc="!deleting"
      @update:show="handleDeleteModal"
    >
      <p v-if="pendingDeleteEvents !== null" class="delete-prompt">
        {{ t('reports.deleteArchivesPrefix') }}{{ pendingDeleteEvents.length
        }}{{ t('reports.deleteArchivesSuffix') }}
      </p>
      <p v-if="deleteError" class="delete-error" role="alert">
        {{ reportErrorMessage(deleteError) }}
      </p>
      <template #footer>
        <div class="delete-actions">
          <n-button :disabled="deleting" @click="handleDeleteModal(false)">{{
            t('reports.cancel')
          }}</n-button>
          <n-button type="error" :loading="deleting" @click="deleteEvent">{{
            t('reports.deleteSelected')
          }}</n-button>
        </div>
      </template>
    </n-modal>
  </main>
</template>

<style scoped>
.archive-actions {
  margin-left: auto;
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.events-panel .panel-heading {
  flex-wrap: wrap;
}

.export-hint {
  margin: 0;
  line-height: 1.6;
}

.ai-analysis {
  margin: 12px 0;
}

.ai-analysis p {
  margin: 8px 0;
  font-size: 12px;
  opacity: 0.8;
}

.ai-analysis-result {
  white-space: pre-wrap;
  overflow-wrap: anywhere;
  font: inherit;
  line-height: 1.6;
}

.schedule-page {
  box-sizing: border-box;
  width: 100%;
  max-width: 1760px;
  min-height: 100%;
  margin: 0 auto;
  padding: clamp(16px, 2.5vw, 30px);
  padding-inline: clamp(16px, 3.33cqi, 40px);
}

.page-heading,
.time-bar,
.panel-heading,
.log-meta,
.image-navigation {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.page-heading {
  flex-wrap: wrap;
  gap: 12px 20px;
  margin-bottom: 20px;
}
.section-kicker {
  color: var(--mower-primary);
  font-size: 12px;
  font-weight: 700;
  letter-spacing: 0.06em;
}
h1 {
  margin: 5px 0 6px;
  font-size: clamp(25px, 2.5vw, 32px);
  line-height: 1.2;
  text-wrap: balance;
}
h2 {
  margin: 4px 0 0;
  font-size: 17px;
  line-height: 1.3;
}
.page-heading p,
.panel-intro {
  margin: 0;
  opacity: 0.65;
  text-wrap: pretty;
}
.back-link,
.open-image {
  color: var(--mower-primary);
  text-decoration: none;
  white-space: nowrap;
}
.back-link {
  flex-shrink: 0;
  margin-left: auto;
  padding: 10px;
  min-height: 40px;
  box-sizing: border-box;
}
.back-link:hover,
.open-image:hover {
  text-decoration: underline;
}

.time-bar {
  flex-wrap: wrap;
  justify-content: flex-start;
  gap: 10px;
  padding: 14px 16px;
  margin-bottom: 16px;
  border-radius: 14px;
}
.time-field {
  display: flex;
  align-items: center;
  gap: 10px;
}
.time-field label {
  font-weight: 600;
  white-space: nowrap;
}
.time-field :deep(.n-date-picker) {
  min-width: 210px;
}
.browse-tabs {
  display: flex;
  gap: 6px;
  margin-bottom: 14px;
}
.browse-tabs button {
  min-height: 40px;
  padding: 8px 16px;
  border: 0;
  border-radius: 8px;
  background: transparent;
  color: inherit;
  font: inherit;
  cursor: pointer;
}
.browse-tabs button:hover {
  background: var(--mower-control-hover);
}
.browse-tabs button[aria-selected='true'] {
  background: var(--mower-control-surface);
  color: var(--mower-primary);
  font-weight: 700;
  box-shadow: inset 0 -2px var(--mower-primary);
}
.browse-tabs button:focus-visible {
  outline: 2px solid var(--mower-primary);
  outline-offset: 2px;
}
.browse-tabs span {
  margin-left: 4px;
  font-size: 12px;
  font-variant-numeric: tabular-nums;
}
.window-notice {
  color: var(--mower-warning);
  font-size: 12px;
  line-height: 1.5;
}
.export-button {
  margin-left: auto;
}
.export-error {
  margin: -6px 0 14px;
  color: var(--mower-error);
  font-size: 13px;
}

.workspace {
  display: grid;
  grid-template-columns: minmax(0, 1.5fr) minmax(280px, 1fr);
  align-items: start;
  gap: 16px;
}
.workspace.with-archives {
  grid-template-columns: minmax(215px, 0.7fr) minmax(330px, 1.3fr) minmax(310px, 1fr);
}
.panel {
  min-width: 0;
  padding: 18px;
  border-radius: 16px;
  box-shadow: 0 2px 12px rgba(0, 0, 0, 0.035);
}
.panel-heading {
  gap: 12px;
}
.count-pill {
  min-width: 28px;
  padding: 4px 9px;
  border-radius: 99px;
  background: var(--mower-control-surface);
  font-size: 12px;
  font-variant-numeric: tabular-nums;
  text-align: center;
}
.panel-intro {
  min-height: 34px;
  margin-top: 8px;
  font-size: 12px;
}
.event-list,
.log-list {
  max-height: min(68vh, 700px);
  overflow-y: auto;
  scrollbar-width: thin;
}
.event-list {
  display: grid;
  gap: 0;
}
.event-row {
  display: flex;
  align-items: center;
  gap: 4px;
  border-top: 1px solid var(--mower-divider);
}
.event-card {
  display: grid;
  grid-template-columns: 1fr auto;
  flex: 1;
  min-width: 0;
  gap: 5px 10px;
  padding: 12px 8px;
  border: 0;
  background: transparent;
  color: inherit;
  font: inherit;
  text-align: left;
  cursor: pointer;
  transition-property: background-color, box-shadow, scale;
  transition-duration: 0.16s;
}
.event-card:hover {
  background: var(--mower-control-hover);
}
.event-card:active {
  scale: 0.96;
}
.event-card:focus-visible,
.image-action:focus-visible {
  outline: 2px solid var(--mower-primary);
  outline-offset: 2px;
}
.event-card.selected {
  background: var(--mower-control-surface);
  box-shadow: inset 3px 0 var(--mower-primary);
}
.delete-prompt {
  margin: 0 0 14px;
  line-height: 1.55;
}
.delete-error {
  margin: 12px 0 0;
  color: var(--mower-error);
}
.delete-actions {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
}
.event-time,
.log-meta time {
  font-size: 12px;
  font-variant-numeric: tabular-nums;
  opacity: 0.7;
}
.event-message {
  grid-column: 1 / -1;
  display: -webkit-box;
  overflow: hidden;
  -webkit-box-orient: vertical;
  -webkit-line-clamp: 2;
  font-weight: 600;
  line-height: 1.45;
  overflow-wrap: anywhere;
}
.event-foot {
  color: var(--mower-primary);
  font-size: 12px;
  font-variant-numeric: tabular-nums;
}
.event-arrow {
  grid-column: 2;
  grid-row: 3;
  color: var(--mower-primary);
  font-size: 12px;
}

.log-filters {
  display: grid;
  grid-template-columns: minmax(0, 1fr) 120px;
  gap: 8px;
  margin: 4px 0 12px;
}
.log-entry {
  display: grid;
  grid-template-columns: 78px minmax(0, 1fr);
  gap: 6px 12px;
  padding: 12px 2px;
  border-top: 1px solid var(--mower-divider);
}
.log-meta {
  align-items: flex-start;
  flex-direction: column;
  justify-content: flex-start;
  gap: 5px;
}
.level {
  font-size: 10px;
  font-weight: 700;
  letter-spacing: 0.02em;
}
.level.error,
.level.critical {
  color: var(--mower-error);
}
.level.warning {
  color: var(--mower-warning);
}
.level.info {
  color: var(--mower-primary);
}
.log-body {
  min-width: 0;
}
.log-body p {
  margin: 0;
  line-height: 1.5;
  overflow-wrap: anywhere;
  user-select: text;
}
.log-body details {
  margin-top: 7px;
  opacity: 0.75;
}
.log-body summary {
  width: fit-content;
  cursor: pointer;
  font-size: 12px;
}
.log-body pre {
  max-height: 240px;
  overflow: auto;
  white-space: pre-wrap;
  overflow-wrap: anywhere;
  font-size: 11px;
  user-select: text;
}
.image-action {
  grid-column: 2;
  width: fit-content;
  min-height: 40px;
  padding: 0 8px;
  border: 0;
  border-radius: 6px;
  background: none;
  color: var(--mower-primary);
  font: inherit;
  font-size: 12px;
  cursor: pointer;
}
.image-action:hover {
  background: var(--mower-control-hover);
}
.state-message {
  padding: 28px 12px;
  border-radius: 10px;
  background: var(--mower-control-surface);
  text-align: center;
  opacity: 0.7;
}
.state-message.error {
  color: var(--mower-error);
  opacity: 1;
}

.image-stage {
  display: grid;
  min-height: 250px;
  max-height: min(56vh, 600px);
  place-items: center;
  overflow: hidden;
  border-radius: 10px;
  background: var(--mower-control-surface);
}
.image-empty {
  display: grid;
  gap: 6px;
  max-width: 240px;
  padding: 32px;
  text-align: center;
}
.image-empty strong {
  font-size: 14px;
}
.image-empty span {
  font-size: 12px;
  opacity: 0.6;
}
.shot-image {
  display: block;
  max-width: 100%;
  max-height: min(56vh, 600px);
  object-fit: contain;
  border-radius: 4px;
  outline: 1px solid rgba(0, 0, 0, 0.1);
}
:global(html[data-mower-theme='dark']) .shot-image {
  outline-color: rgba(255, 255, 255, 0.1);
}
.image-navigation {
  gap: 8px;
  margin-top: 12px;
}
.image-navigation input {
  flex: 1;
  min-width: 40px;
  min-height: 40px;
  accent-color: var(--mower-primary);
}
.open-image {
  display: inline-flex;
  align-items: center;
  min-height: 40px;
  margin-top: 10px;
}

@container main-content (max-width: 1160px) {
  .workspace,
  .workspace.with-archives {
    grid-template-columns: minmax(0, 1.5fr) minmax(0, 1fr);
  }
  .events-panel {
    grid-column: 1 / -1;
  }
  .event-list {
    max-height: 200px;
    overflow-y: auto;
  }
  .event-card {
    grid-template-columns: 150px minmax(0, 1fr) auto auto;
    align-items: center;
    gap: 12px;
  }
  .event-message,
  .event-arrow {
    grid-column: auto;
    grid-row: auto;
  }
  .event-message {
    -webkit-line-clamp: 1;
  }
  .logs-panel {
    grid-column: 1;
  }
  .image-panel {
    grid-column: 2;
  }
}

@container main-content (max-width: 730px) {
  .workspace,
  .workspace.with-archives {
    grid-template-columns: minmax(0, 1fr);
  }
  .events-panel,
  .logs-panel,
  .image-panel {
    grid-column: 1;
  }
  .image-panel {
    grid-row: 2;
  }
  .logs-panel {
    grid-row: 1;
  }
  .with-archives .events-panel {
    grid-row: 1;
  }
  .with-archives .logs-panel {
    grid-row: 2;
  }
  .with-archives .image-panel {
    grid-row: 3;
  }
  .log-list {
    max-height: 480px;
  }
  .event-card {
    grid-template-columns: 1fr auto;
  }
  .event-message {
    grid-column: 1 / -1;
    -webkit-line-clamp: 2;
  }
  .event-arrow {
    grid-column: 2;
    grid-row: 3;
  }
  .export-button,
  .archive-actions {
    margin-left: 0;
  }
}

@container main-content (max-width: 440px) {
  .page-heading {
    align-items: flex-start;
  }
  .time-field {
    width: 100%;
    align-items: flex-start;
    flex-direction: column;
  }
  .time-field :deep(.n-date-picker) {
    width: 100%;
  }
  .panel {
    padding: 14px;
  }
}
</style>
