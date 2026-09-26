<script setup>
import { computed, inject, onMounted, ref } from 'vue'

const axios = inject('axios')
const queryAt = ref(Date.now())
const events = ref([])
const logs = ref([])
const eventLoading = ref(false)
const logLoading = ref(false)
const eventError = ref('')
const logError = ref('')
const activeEventId = ref('')
const archiveImages = ref([])
const imageIndex = ref(0)
const manualImage = ref('')
const imageFailed = ref(false)
const searchText = ref('')
const levelFilter = ref('all')
const exporting = ref(false)
const exportError = ref('')
const pendingDeleteEvent = ref(null)
const deleting = ref(false)
const deleteError = ref('')
let requestVersion = 0

const levelOptions = [
  { label: '全部级别', value: 'all' },
  { label: '错误', value: 'ERROR' },
  { label: '警告', value: 'WARNING' },
  { label: '信息', value: 'INFO' },
  { label: '调试', value: 'DEBUG' }
]

const activeEvent = computed(() => events.value.find((event) => event.id === activeEventId.value))
const imagePath = computed(() => manualImage.value || archiveImages.value[imageIndex.value] || '')
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
    /^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2} .*? (DEBUG|INFO|WARNING|ERROR|CRITICAL) .*?: (.*)$/
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
  return new Date(Number(timestampNs) / 1000000).toLocaleString('zh-CN', { hour12: false })
}

function imageTime(path) {
  const stem = path.split('/').at(-1)?.replace('.jpg', '') || ''
  return /^\d{18,}$/.test(stem) ? formatTime(stem) : stem
}

function imageAtEvent(event) {
  const images = event.screenshots || []
  if (!images.length) return 0
  let best = 0
  let distance = Infinity
  for (let index = 0; index < images.length; index++) {
    const timestamp = Number(images[index].split('/').at(-1).replace('.jpg', ''))
    const nextDistance = Math.abs(timestamp - Number(event.time_ns))
    if (nextDistance < distance) {
      best = index
      distance = nextDistance
    }
  }
  return best
}

async function loadEvents() {
  eventLoading.value = true
  eventError.value = ''
  try {
    const response = await axios.get(`${import.meta.env.VITE_HTTP_URL}/diagnostics/errors`)
    events.value = response.data.events || []
  } catch {
    eventError.value = '报错记录读取失败'
  } finally {
    eventLoading.value = false
  }
}

async function loadWindow() {
  if (!Number.isFinite(queryAt.value)) return
  const version = ++requestVersion
  logLoading.value = true
  logError.value = ''
  activeEventId.value = ''
  archiveImages.value = []
  manualImage.value = ''
  try {
    const response = await axios.get(`${import.meta.env.VITE_HTTP_URL}/diagnostics/timeline`, {
      params: { at: queryAt.value }
    })
    if (version === requestVersion) logs.value = response.data.logs || []
  } catch {
    if (version === requestVersion) logError.value = '该时段的日志读取失败，请重试'
  } finally {
    if (version === requestVersion) logLoading.value = false
  }
}

async function selectEvent(event) {
  const version = ++requestVersion
  activeEventId.value = event.id
  queryAt.value = Math.floor(event.time_ns / 1000000)
  archiveImages.value = event.screenshots || []
  imageIndex.value = imageAtEvent(event)
  manualImage.value = ''
  imageFailed.value = false
  logLoading.value = true
  logError.value = ''
  try {
    const response = await axios.get(
      `${import.meta.env.VITE_HTTP_URL}/diagnostics/errors/${event.id}/logs`
    )
    if (version === requestVersion) logs.value = response.data.logs || []
  } catch {
    if (version === requestVersion) logError.value = '报错时段的日志读取失败，请重试'
  } finally {
    if (version === requestVersion) logLoading.value = false
  }
}

function showScreenshot(path) {
  const index = archiveImages.value.indexOf(path)
  if (index >= 0) {
    imageIndex.value = index
    manualImage.value = ''
  } else {
    manualImage.value = path
  }
  imageFailed.value = false
}

function moveImage(step) {
  imageIndex.value = Math.max(0, Math.min(archiveImages.value.length - 1, imageIndex.value + step))
  manualImage.value = ''
  imageFailed.value = false
}

function onImageSeek() {
  manualImage.value = ''
  imageFailed.value = false
}

function jumpToNow() {
  queryAt.value = Date.now()
  loadWindow()
}

async function exportWindow() {
  exporting.value = true
  exportError.value = ''
  const center = activeEvent.value ? Math.floor(activeEvent.value.time_ns / 1000000) : queryAt.value
  const path = activeEvent.value
    ? `/diagnostics/errors/${activeEvent.value.id}/export`
    : '/diagnostics/export'
  try {
    const response = await axios.get(`${import.meta.env.VITE_HTTP_URL}${path}`, {
      params: activeEvent.value ? undefined : { at: center },
      responseType: 'blob'
    })
    const url = URL.createObjectURL(response.data)
    const link = document.createElement('a')
    link.href = url
    const date = new Date(center)
    const stamp = `${date.getFullYear()}${String(date.getMonth() + 1).padStart(2, '0')}${String(date.getDate()).padStart(2, '0')}-${String(date.getHours()).padStart(2, '0')}${String(date.getMinutes()).padStart(2, '0')}${String(date.getSeconds()).padStart(2, '0')}`
    link.download = `日志调度-${stamp}.zip`
    document.body.appendChild(link)
    link.click()
    link.remove()
    setTimeout(() => URL.revokeObjectURL(url), 1000)
  } catch {
    exportError.value = '导出失败，请稍后重试'
  } finally {
    exporting.value = false
  }
}

function confirmDelete(event) {
  pendingDeleteEvent.value = event
  deleteError.value = ''
}

function handleDeleteModal(show) {
  if (!show && !deleting.value) {
    pendingDeleteEvent.value = null
    deleteError.value = ''
  }
}

async function deleteEvent() {
  const event = pendingDeleteEvent.value
  if (!event || deleting.value) return
  deleting.value = true
  deleteError.value = ''
  try {
    await axios.delete(`${import.meta.env.VITE_HTTP_URL}/diagnostics/errors/${event.id}`, {
      headers: { 'X-Mower-Diagnostics': '1' }
    })
    events.value = events.value.filter((item) => item.id !== event.id)
    pendingDeleteEvent.value = null
    if (activeEventId.value === event.id) {
      loadWindow()
    } else if (manualImage.value.startsWith(`errors/${event.id}/`)) {
      manualImage.value = ''
    }
  } catch {
    deleteError.value = '删除失败，请重试'
  } finally {
    deleting.value = false
  }
}

onMounted(() => {
  loadEvents()
  loadWindow()
})
</script>

<template>
  <main class="schedule-page">
    <header class="page-heading">
      <div>
        <div class="eyebrow">运行记录 / 问题回看</div>
        <h1>日志调度</h1>
        <p>按时间查看日志与画面。发生错误时，前后各 5 分钟的截图会单独保存。</p>
      </div>
      <router-link class="back-link" to="/">返回运行日志</router-link>
    </header>

    <section class="time-bar mower-surface-panel" aria-label="时间筛选">
      <div class="time-field">
        <label for="schedule-time">查看时间</label>
        <n-date-picker
          id="schedule-time"
          v-model:value="queryAt"
          type="datetime"
          :clearable="false"
        />
      </div>
      <n-button type="primary" :loading="logLoading" @click="loadWindow">查看前后 5 分钟</n-button>
      <n-button secondary @click="jumpToNow">跳到现在</n-button>
      <n-button class="export-button" secondary :loading="exporting" @click="exportWindow">
        导出日志与截图
      </n-button>
    </section>
    <p v-if="exportError" class="export-error" role="alert">{{ exportError }}</p>

    <div class="workspace">
      <aside class="panel events-panel mower-surface-panel" aria-label="报错记录">
        <div class="panel-heading">
          <div>
            <span class="section-kicker">已归档</span>
            <h2>报错记录</h2>
          </div>
          <span class="count-pill">{{ events.length }}</span>
        </div>
        <p class="panel-intro">选择记录，查看对应日志和留存画面。</p>
        <div v-if="eventError" class="state-message error" role="alert">{{ eventError }}</div>
        <div v-else-if="eventLoading" class="state-message">正在读取报错记录…</div>
        <div v-else-if="!events.length" class="state-message">暂无报错记录</div>
        <div v-else class="event-list">
          <div v-for="event in events" :key="event.id" class="event-row">
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
                <template v-if="event.error_count > 1">{{ event.error_count }} 次报错 · </template>
                {{ event.screenshots.length }} 张截图
              </span>
              <span class="event-arrow" aria-hidden="true">查看记录 →</span>
            </button>
            <n-button
              class="event-delete"
              quaternary
              type="error"
              :aria-label="`删除 ${formatTime(event.time_ns)} 的报错记录`"
              @click="confirmDelete(event)"
            >
              删除
            </n-button>
          </div>
        </div>
      </aside>

      <section class="panel logs-panel mower-surface-panel" aria-label="日志时间线">
        <div class="panel-heading">
          <div>
            <span class="section-kicker">{{ activeEvent ? '报错窗口' : '时间窗口' }}</span>
            <h2>日志时间线</h2>
          </div>
          <span class="count-pill">{{ visibleLogs.length }}</span>
        </div>
        <p class="panel-intro">
          {{
            activeEvent
              ? activeEvent.error_count > 1
                ? `${formatTime(activeEvent.time_ns)} 至 ${formatTime(activeEvent.last_error_ns)}`
                : formatTime(activeEvent.time_ns)
              : new Date(queryAt).toLocaleString('zh-CN')
          }}
          附近的运行记录
        </p>
        <div class="log-filters">
          <n-input
            v-model:value="searchText"
            clearable
            placeholder="搜索日志内容"
            aria-label="搜索日志内容"
          />
          <n-select v-model:value="levelFilter" :options="levelOptions" aria-label="筛选日志级别" />
        </div>
        <div v-if="logError" class="state-message error" role="alert">{{ logError }}</div>
        <div v-else-if="logLoading" class="state-message">正在读取日志…</div>
        <div v-else-if="!visibleLogs.length" class="state-message">
          {{ logs.length ? '没有符合筛选条件的日志' : '这个时间段没有日志' }}
        </div>
        <div v-else class="log-list">
          <article v-for="entry in visibleLogs" :key="entry.index" class="log-entry">
            <div class="log-meta">
              <time>{{ entry.time.slice(11) }}</time>
              <span class="level" :class="entry.level.toLowerCase()">{{ entry.level }}</span>
            </div>
            <div class="log-body">
              <p>{{ entry.summary }}</p>
              <details v-if="entry.detail">
                <summary>查看详细信息</summary>
                <pre>{{ entry.detail }}</pre>
              </details>
            </div>
            <button
              v-if="entry.screenshot"
              type="button"
              class="image-action"
              @click="showScreenshot(entry.screenshot)"
            >
              查看画面 →
            </button>
          </article>
        </div>
      </section>

      <section class="panel image-panel mower-surface-panel" aria-label="关联截图">
        <div class="panel-heading">
          <div>
            <span class="section-kicker">画面证据</span>
            <h2>关联截图</h2>
          </div>
          <span v-if="archiveImages.length" class="count-pill">
            {{ imageIndex + 1 }} / {{ archiveImages.length }}
          </span>
        </div>
        <p class="panel-intro">
          {{ imagePath ? imageTime(imagePath) : '选择报错记录或日志中的“查看画面”' }}
        </p>
        <div class="image-stage">
          <div v-if="!imagePath" class="image-empty">
            <strong>暂无选中截图</strong>
            <span>从报错记录或日志中选择画面</span>
          </div>
          <div v-else-if="imageFailed" class="image-empty">截图文件暂时无法读取</div>
          <img
            v-else
            :key="imagePath"
            class="shot-image"
            :src="imageUrl"
            alt="所选时间的游戏截图"
            @error="imageFailed = true"
          />
        </div>
        <div v-if="archiveImages.length" class="image-navigation">
          <n-button secondary :disabled="imageIndex === 0" @click="moveImage(-1)">上一张</n-button>
          <input
            v-model.number="imageIndex"
            type="range"
            min="0"
            :max="archiveImages.length - 1"
            aria-label="选择报错窗口中的截图"
            @input="onImageSeek"
          />
          <n-button
            secondary
            :disabled="imageIndex === archiveImages.length - 1"
            @click="moveImage(1)"
          >
            下一张
          </n-button>
        </div>
        <a
          v-if="imagePath"
          class="open-image"
          :href="imageUrl"
          target="_blank"
          rel="noopener noreferrer"
        >
          打开原图 ↗
        </a>
      </section>
    </div>

    <n-modal
      :show="pendingDeleteEvent !== null"
      preset="card"
      title="删除报错记录"
      style="width: min(440px, calc(100vw - 32px))"
      :closable="!deleting"
      :mask-closable="!deleting"
      :close-on-esc="!deleting"
      @update:show="handleDeleteModal"
    >
      <template v-if="pendingDeleteEvent">
        <p class="delete-prompt">确定删除这条报错记录及其归档日志、截图吗？删除后无法恢复。</p>
        <div class="delete-target">
          <time>{{ formatTime(pendingDeleteEvent.time_ns) }}</time>
          <strong>{{ pendingDeleteEvent.message }}</strong>
          <span>
            <template v-if="pendingDeleteEvent.error_count > 1">
              {{ pendingDeleteEvent.error_count }} 次报错 ·
            </template>
            {{ pendingDeleteEvent.screenshots.length }} 张归档截图
          </span>
        </div>
      </template>
      <p v-if="deleteError" class="delete-error" role="alert">{{ deleteError }}</p>
      <template #footer>
        <div class="delete-actions">
          <n-button :disabled="deleting" @click="handleDeleteModal(false)">取消</n-button>
          <n-button type="error" :loading="deleting" @click="deleteEvent">删除记录</n-button>
        </div>
      </template>
    </n-modal>
  </main>
</template>

<style scoped>
.schedule-page {
  box-sizing: border-box;
  width: 100%;
  max-width: 1760px;
  min-height: 100%;
  margin: 0 auto;
  padding: clamp(16px, 2.5vw, 30px);
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
  gap: 20px;
  margin-bottom: 20px;
}
.eyebrow,
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
  grid-template-columns: minmax(215px, 0.7fr) minmax(330px, 1.3fr) minmax(310px, 1fr);
  align-items: start;
  gap: 16px;
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
.event-delete {
  flex: 0 0 auto;
  min-width: 48px;
  min-height: 40px;
}
.delete-prompt {
  margin: 0 0 14px;
  line-height: 1.55;
}
.delete-target {
  display: grid;
  gap: 5px;
  padding: 12px;
  border-radius: 10px;
  background: var(--mower-control-surface);
  overflow-wrap: anywhere;
}
.delete-target time,
.delete-target span {
  font-size: 12px;
  font-variant-numeric: tabular-nums;
  opacity: 0.7;
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
  accent-color: var(--mower-primary);
}
.open-image {
  display: inline-flex;
  align-items: center;
  min-height: 40px;
  margin-top: 10px;
}

@container main-content (max-width: 1160px) {
  .workspace {
    grid-template-columns: minmax(0, 1.15fr) minmax(0, 1fr);
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
  .workspace {
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
  .export-button {
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
