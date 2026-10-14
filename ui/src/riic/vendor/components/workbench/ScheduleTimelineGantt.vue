<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { toPng, toBlob } from 'html-to-image'
import type { ScheduleSimulationReport } from '../../simulator/scheduleSimulation'
import {
  buildTimelineData,
  type TimelineDataset,
  type FacilityTrack,
  type OperatorTrack,
  type TimelineInterval,
  type TimelineMarkerEvent,
} from '../../workbench/timeline/timelineModel'
import { visibleTimelineIntervals, type TimelineDisplayInterval } from '../../workbench/timeline/timelineDisplay'

const props = withDefaults(defineProps<{
  report: ScheduleSimulationReport | null
  timelineData?: TimelineDataset | null
  initialWindowHours?: 24 | 72
  initiallyCollapsed?: boolean
}>(), {
  initialWindowHours: 72,
  initiallyCollapsed: false,
})

const emit = defineEmits<{
  (e: 'request-simulate'): void
}>()

// View mode: by facility or by operator
const viewMode = ref<'facility' | 'operator'>('facility')
const facilityFilter = ref<string>('all')
const searchQuery = ref('')
const showEventMarkers = ref(true)
const isTimelineExpanded = ref(!props.initiallyCollapsed)

// Time window zoom & navigation
const zoomPreset = ref<'6' | '12' | '24' | '48' | '72' | '168' | 'all'>(props.initialWindowHours === 24 ? '24' : '72')
const customWindowStart = ref(0)
const customWindowEnd = ref<number>(props.initialWindowHours)
const tracksContainerRef = ref<HTMLElement | null>(null)
const isDraggingTimeline = ref(false)

// Overview scrubber dragging state
const overviewTrackRef = ref<HTMLElement | null>(null)
const isDraggingOverview = ref(false)
let overviewDragStartX = 0
let overviewDragStartWindowStart = 0

// Export modal and state (Supports Full Sampling Phase & Multi-Day Volumes for 14+ days)
const showExportModal = ref(false)
const isExporting = ref(false)
const exportStatus = ref<{ type: 'success' | 'error'; message: string } | null>(null)
const exportCanvasRef = ref<HTMLDivElement | null>(null)
const exportScaleMode = ref<'standard' | 'compact'>('standard')

// Export scope modes for long timelines (<=72h defaults to full, >72h supports volumes/custom)
const exportScopeMode = ref<'full' | 'volume' | 'custom'>('full')
const exportVolumeDays = ref<number>(3)
const exportSelectedVolumeIndex = ref<number>(0)
const exportCustomStart = ref<number>(0)
const exportCustomEnd = ref<number>(72)

interface ExportVolume {
  index: number
  start: number
  end: number
  label: string
}

const exportVolumes = computed<ExportVolume[]>(() => {
  const total = totalObservedHours.value
  const volHours = Math.max(12, exportVolumeDays.value * 24)
  const count = Math.ceil(total / volHours)
  const list: ExportVolume[] = []
  for (let i = 0; i < count; i++) {
    const s = i * volHours
    const e = Math.min(total, s + volHours)
    const startDay = Math.floor(s / 24) + 1
    const endDay = Math.ceil(e / 24)
    list.push({
      index: i,
      start: s,
      end: e,
      label: `第 ${i + 1} 卷：第 ${startDay}~${endDay} 天 (T+${s.toFixed(0)}h ~ T+${e.toFixed(0)}h)`,
    })
  }
  return list
})

const activeExportStart = computed(() => {
  if (exportScopeMode.value === 'volume') {
    const vol = exportVolumes.value[exportSelectedVolumeIndex.value]
    return vol ? vol.start : 0
  }
  if (exportScopeMode.value === 'custom') {
    return Math.max(0, exportCustomStart.value)
  }
  return 0
})

const activeExportEnd = computed(() => {
  if (exportScopeMode.value === 'volume') {
    const vol = exportVolumes.value[exportSelectedVolumeIndex.value]
    return vol ? vol.end : totalObservedHours.value
  }
  if (exportScopeMode.value === 'custom') {
    return Math.min(totalObservedHours.value, Math.max(activeExportStart.value + 1, exportCustomEnd.value))
  }
  return totalObservedHours.value
})

const activeExportDuration = computed(() => {
  return Math.max(0.1, activeExportEnd.value - activeExportStart.value)
})

const exportPixelsPerHour = computed(() => {
  const dur = activeExportDuration.value
  const base = exportScaleMode.value === 'compact' ? 50 : 100
  const maxTrackWidth = 14000
  if (dur * base > maxTrackWidth) {
    return Math.max(20, Math.floor(maxTrackWidth / dur))
  }
  return base
})

const exportTrackWidthPx = computed(() => Math.round(activeExportDuration.value * exportPixelsPerHour.value))
const exportTotalWidthPx = computed(() => 190 + exportTrackWidthPx.value)

// Hover inspector state
const hoveredInterval = ref<TimelineDisplayInterval | null>(null)
const hoveredEvent = ref<TimelineMarkerEvent | null>(null)
const tooltipX = ref(0)
const tooltipY = ref(0)
const cursorTime = ref<number | null>(null)
const cursorXPercent = ref<number | null>(null)

// Highlighted operator when hovering an interval or searching
const highlightedOperatorId = computed(() => {
  if (hoveredInterval.value?.operatorId) return hoveredInterval.value.operatorId
  return null
})

// Build dataset
const dataset = computed(() => {
  if (props.timelineData) return props.timelineData
  if (!props.report) return null
  return buildTimelineData(props.report)
})

const totalObservedHours = computed(() => props.report?.observedHours ?? props.initialWindowHours)

watch(() => props.report, () => {
  isTimelineExpanded.value = !props.initiallyCollapsed
})

// Initialize zoom window based on report observed hours
watch(
  () => props.report?.observedHours,
  (hours) => {
    if (hours && hours > 0) {
      customWindowStart.value = 0
      const initialDur = Math.min(props.initialWindowHours, hours)
      customWindowEnd.value = Math.max(6, initialDur)
    }
  },
  { immediate: true },
)

const windowDuration = computed(() => {
  return Math.max(0.1, customWindowEnd.value - customWindowStart.value)
})

function setWindowDuration(targetDur: number): void {
  const maxH = totalObservedHours.value
  const dur = Math.max(6, Math.min(maxH, targetDur))
  let start = customWindowStart.value
  let end = start + dur
  if (end > maxH) {
    end = maxH
    start = Math.max(0, maxH - dur)
  }
  customWindowStart.value = Math.round(start * 10) / 10
  customWindowEnd.value = Math.round(end * 10) / 10
}

function onWindowSliderInput(e: Event): void {
  const val = Number((e.target as HTMLInputElement).value)
  if (!Number.isFinite(val)) return
  setWindowDuration(val)
}

function setZoomPreset(preset: '6' | '12' | '24' | '48' | '72' | '168' | 'all'): void {
  zoomPreset.value = preset
  if (preset === 'all') {
    setWindowDuration(totalObservedHours.value)
  } else {
    setWindowDuration(Number(preset))
  }
}

interface QuickPreset {
  key: string
  val: number
  label: string
}

const quickWindowPresets = computed<QuickPreset[]>(() => {
  const maxH = totalObservedHours.value
  const list: QuickPreset[] = [
    { key: '6', val: 6, label: '6h' },
    { key: '12', val: 12, label: '12h' },
    { key: '24', val: 24, label: '24h' },
    { key: '48', val: 48, label: '48h' },
    { key: 'all', val: maxH, label: '全周期' },
  ]
  return list.filter((p) => p.val <= maxH || p.key === 'all')
})

// Pan window forward or backward by delta hours
function panWindow(deltaHours: number): void {
  const maxH = totalObservedHours.value
  const dur = windowDuration.value
  let newStart = customWindowStart.value + deltaHours
  let newEnd = customWindowEnd.value + deltaHours

  if (newStart < 0) {
    newStart = 0
    newEnd = Math.min(maxH, dur)
  } else if (newEnd > maxH) {
    newEnd = maxH
    newStart = Math.max(0, maxH - dur)
  }

  customWindowStart.value = Math.round(newStart * 10) / 10
  customWindowEnd.value = Math.round(newEnd * 10) / 10
}

function panWindowTo(targetStart: number): void {
  const maxH = totalObservedHours.value
  const dur = windowDuration.value
  let start = Math.max(0, Math.min(maxH - dur, targetStart))
  let end = Math.min(maxH, start + dur)
  customWindowStart.value = Math.round(start * 10) / 10
  customWindowEnd.value = Math.round(end * 10) / 10
}

function jumpToStart(): void {
  const dur = windowDuration.value
  customWindowStart.value = 0
  customWindowEnd.value = Math.min(totalObservedHours.value, dur)
}

function jumpToEnd(): void {
  const maxH = totalObservedHours.value
  const dur = windowDuration.value
  customWindowStart.value = Math.max(0, maxH - dur)
  customWindowEnd.value = maxH
}

// Cycle options for dropdown selector
interface CycleOption {
  index: number
  label: string
  start: number
  end: number
}

const cycleOptions = computed<CycleOption[]>(() => {
  const total = totalObservedHours.value
  const dur = windowDuration.value
  if (dur >= total - 0.01) return []

  const cycles: CycleOption[] = []
  const count = Math.ceil(total / dur)
  for (let i = 0; i < count; i++) {
    const s = i * dur
    const e = Math.min(total, s + dur)
    const isDayUnit = Math.abs(dur - 24) < 0.1
    let label = ''
    if (isDayUnit) {
      label = `第 ${i + 1} 天 (T+${s.toFixed(0)}h ~ T+${e.toFixed(0)}h)`
    } else {
      label = `第 ${i + 1} 周期 (T+${s.toFixed(0)}h ~ T+${e.toFixed(0)}h)`
    }
    cycles.push({ index: i, label, start: s, end: e })
  }
  return cycles
})

const currentCycleIndex = computed(() => {
  const dur = windowDuration.value
  if (dur <= 0) return 0
  return Math.max(0, Math.min(cycleOptions.value.length - 1, Math.floor((customWindowStart.value + dur * 0.2) / dur)))
})

function onCycleSelectChange(e: Event): void {
  const idx = Number((e.target as HTMLSelectElement).value)
  const option = cycleOptions.value[idx]
  if (option) {
    panWindowTo(option.start)
  }
}

// Overview mini-map ticks
interface OverviewDayTick {
  day: number
  percent: number
  showLabel: boolean
}

const overviewDayTicks = computed<OverviewDayTick[]>(() => {
  const total = totalObservedHours.value
  if (total <= 0) return []
  const totalDays = Math.ceil(total / 24)
  const ticks: OverviewDayTick[] = []
  const labelInterval = totalDays > 20 ? 5 : totalDays > 10 ? 2 : 1

  for (let d = 1; d <= totalDays; d++) {
    const t = d * 24
    if (t > total) break
    ticks.push({
      day: d,
      percent: (t / total) * 100,
      showLabel: d % labelInterval === 0,
    })
  }
  return ticks
})

// Overview scrubber dragging
function handleOverviewThumbMouseDown(e: MouseEvent): void {
  if (e.button !== 0) return
  e.stopPropagation()
  e.preventDefault()

  isDraggingOverview.value = true
  overviewDragStartX = e.clientX
  overviewDragStartWindowStart = customWindowStart.value

  const trackEl = overviewTrackRef.value
  const trackWidth = trackEl ? trackEl.getBoundingClientRect().width : 800

  const onMouseMove = (moveEv: MouseEvent) => {
    if (!isDraggingOverview.value) return
    const dx = moveEv.clientX - overviewDragStartX
    const timeDelta = (dx / trackWidth) * totalObservedHours.value
    panWindowTo(overviewDragStartWindowStart + timeDelta)
  }

  const onMouseUp = () => {
    isDraggingOverview.value = false
    window.removeEventListener('mousemove', onMouseMove)
    window.removeEventListener('mouseup', onMouseUp)
  }

  window.addEventListener('mousemove', onMouseMove)
  window.addEventListener('mouseup', onMouseUp)
}

function handleOverviewTrackMouseDown(e: MouseEvent): void {
  if (e.button !== 0) return
  const trackEl = overviewTrackRef.value
  if (!trackEl) return
  const rect = trackEl.getBoundingClientRect()
  const mouseX = Math.max(0, Math.min(rect.width, e.clientX - rect.left))
  const frac = mouseX / rect.width
  const clickHour = frac * totalObservedHours.value
  panWindowTo(clickHour - windowDuration.value / 2)

  isDraggingOverview.value = true
  overviewDragStartX = e.clientX
  overviewDragStartWindowStart = customWindowStart.value
  const trackWidth = rect.width

  const onMouseMove = (moveEv: MouseEvent) => {
    if (!isDraggingOverview.value) return
    const dx = moveEv.clientX - overviewDragStartX
    const timeDelta = (dx / trackWidth) * totalObservedHours.value
    panWindowTo(overviewDragStartWindowStart + timeDelta)
  }

  const onMouseUp = () => {
    isDraggingOverview.value = false
    window.removeEventListener('mousemove', onMouseMove)
    window.removeEventListener('mouseup', onMouseUp)
  }

  window.addEventListener('mousemove', onMouseMove)
  window.addEventListener('mouseup', onMouseUp)
}

// Export facility gantt (Supports Full Sampling Phase & Multi-Day Volumes)
function getExportOffsetPercent(time: number): number {
  const dur = activeExportDuration.value
  if (dur <= 0) return 0
  const rel = time - activeExportStart.value
  return Math.max(0, Math.min(100, (rel / dur) * 100))
}

function getExportWidthPercent(start: number, end: number): number {
  const dur = activeExportDuration.value
  if (dur <= 0) return 0
  const s = Math.max(activeExportStart.value, start)
  const e = Math.min(activeExportEnd.value, end)
  if (e <= s) return 0
  return ((e - s) / dur) * 100
}

const exportRulerTicks = computed<RulerTick[]>(() => {
  const start = activeExportStart.value
  const end = activeExportEnd.value
  const dur = activeExportDuration.value
  if (dur <= 0) return []
  const ticks: RulerTick[] = []

  // Adapt tick step based on export window duration
  const step = dur <= 72 ? 2 : dur <= 168 ? 4 : dur <= 336 ? 8 : 12
  const firstTick = Math.ceil(start / step) * step

  for (let t = firstTick; t <= end; t += step) {
    const isMajor = t % 24 === 0
    const day = Math.floor(t / 24) + 1
    const hourInDay = t % 24
    let label = `${t}h`
    if (isMajor) {
      label = `D${day} 00:00`
    } else {
      label = `${hourInDay < 10 ? '0' + hourInDay : hourInDay}:00`
    }
    ticks.push({
      time: t,
      percent: getExportOffsetPercent(t),
      label,
      isMajorDay: isMajor,
    })
  }

  const lastTick = ticks[ticks.length - 1]
  if (lastTick && end - lastTick.time > 0.5) {
    ticks.push({
      time: end,
      percent: 100,
      label: `T+${end.toFixed(0)}h`,
      isMajorDay: end % 24 === 0,
    })
  }
  return ticks
})

function openExportModal(): void {
  viewMode.value = 'facility'
  exportStatus.value = null
  if (totalObservedHours.value > 72) {
    // For long schedules (e.g. 14 days), start at full or volume mode
    exportSelectedVolumeIndex.value = 0
  }
  showExportModal.value = true
}

function closeExportModal(): void {
  showExportModal.value = false
  exportStatus.value = null
}

function getExportFilename(): string {
  if (exportScopeMode.value === 'volume') {
    return `基建排班甘特图_设施分道_第${exportSelectedVolumeIndex.value + 1}卷_T+${activeExportStart.value.toFixed(0)}h-${activeExportEnd.value.toFixed(0)}h.png`
  }
  if (exportScopeMode.value === 'custom') {
    return `基建排班甘特图_设施分道_时段_T+${activeExportStart.value.toFixed(0)}h-${activeExportEnd.value.toFixed(0)}h.png`
  }
  return `基建排班甘特图_设施分道_采样全周期_0h-${totalObservedHours.value.toFixed(0)}h.png`
}

async function handleDownloadGanttImage(): Promise<void> {
  if (!exportCanvasRef.value || isExporting.value) return
  isExporting.value = true
  exportStatus.value = null
  try {
    const totalW = exportTotalWidthPx.value
    const pixelRatio = totalW * 2 <= 16000 ? 2 : totalW * 1.5 <= 16000 ? 1.5 : 1
    const dataUrl = await toPng(exportCanvasRef.value, {
      pixelRatio,
      cacheBust: true,
      backgroundColor: '#0e1319',
    })
    const link = document.createElement('a')
    link.download = getExportFilename()
    link.href = dataUrl
    link.click()
    exportStatus.value = { type: 'success', message: '甘特图长图已成功导出下载！' }
  } catch (err: unknown) {
    const msg = err instanceof Error ? err.message : String(err)
    exportStatus.value = { type: 'error', message: `导出失败: ${msg}` }
  } finally {
    isExporting.value = false
  }
}

async function handleCopyGanttImage(): Promise<void> {
  if (!exportCanvasRef.value || isExporting.value) return
  isExporting.value = true
  exportStatus.value = null
  try {
    const totalW = exportTotalWidthPx.value
    const pixelRatio = totalW * 2 <= 16000 ? 2 : totalW * 1.5 <= 16000 ? 1.5 : 1
    const blob = await toBlob(exportCanvasRef.value, {
      pixelRatio,
      cacheBust: true,
      backgroundColor: '#0e1319',
    })
    if (!blob) throw new Error('无法生成图片数据')
    if (typeof navigator !== 'undefined' && navigator.clipboard?.write) {
      await navigator.clipboard.write([new ClipboardItem({ 'image/png': blob })])
      exportStatus.value = { type: 'success', message: '已成功将甘特图长图复制到剪贴板！' }
    } else {
      throw new Error('当前浏览器不支持直接写入剪贴板图片')
    }
  } catch (err: unknown) {
    const msg = err instanceof Error ? err.message : String(err)
    exportStatus.value = { type: 'error', message: `复制失败: ${msg}` }
  } finally {
    isExporting.value = false
  }
}

// Drag & Wheel interactions
let dragStartX = 0
let dragStartWindowStart = 0

function handleTimelineMouseDown(e: MouseEvent): void {
  if (e.button !== 0) return
  const target = e.target as HTMLElement
  if (target.closest('button, a, input, select, textarea, .event-marker, .gantt-block')) return

  isDraggingTimeline.value = true
  dragStartX = e.clientX
  dragStartWindowStart = customWindowStart.value

  const onMouseMove = (moveEvent: MouseEvent) => {
    if (!isDraggingTimeline.value) return
    const dx = moveEvent.clientX - dragStartX
    const containerWidth = tracksContainerRef.value?.clientWidth || 1000
    const timeDelta = -(dx / containerWidth) * windowDuration.value
    panWindowTo(dragStartWindowStart + timeDelta)
  }

  const onMouseUp = () => {
    isDraggingTimeline.value = false
    window.removeEventListener('mousemove', onMouseMove)
    window.removeEventListener('mouseup', onMouseUp)
  }

  window.addEventListener('mousemove', onMouseMove)
  window.addEventListener('mouseup', onMouseUp)
}

function handleTimelineWheel(e: WheelEvent): void {
  if (e.shiftKey || Math.abs(e.deltaX) > Math.abs(e.deltaY)) {
    const delta = e.deltaX !== 0 ? e.deltaX : e.deltaY
    const step = (delta / 400) * windowDuration.value
    panWindow(step)
    e.preventDefault()
  }
}

// Calculate percentage position and width on timeline
function getOffsetPercent(time: number): number {
  const rel = time - customWindowStart.value
  return Math.max(0, Math.min(100, (rel / windowDuration.value) * 100))
}

function getWidthPercent(start: number, end: number): number {
  const s = Math.max(customWindowStart.value, start)
  const e = Math.min(customWindowEnd.value, end)
  if (e <= s) return 0
  return ((e - s) / windowDuration.value) * 100
}

// Generate Ruler Ticks (Days & Hours)
interface RulerTick {
  time: number
  percent: number
  label: string
  isMajorDay: boolean
}

const rulerTicks = computed<RulerTick[]>(() => {
  const dur = windowDuration.value
  const start = customWindowStart.value
  const end = customWindowEnd.value
  const ticks: RulerTick[] = []

  let step = 6
  if (dur <= 6) step = 1
  else if (dur <= 12) step = 2
  else if (dur <= 24) step = 3
  else if (dur <= 48) step = 6
  else if (dur <= 120) step = 12
  else step = 24

  const firstTick = Math.ceil(start / step) * step
  for (let t = firstTick; t <= end; t += step) {
    const isMajor = t % 24 === 0
    const day = Math.floor(t / 24) + 1
    const hourInDay = t % 24
    let label = `${t}h`
    if (isMajor) {
      label = `D${day} 00:00`
    } else {
      label = `${hourInDay < 10 ? '0' + hourInDay : hourInDay}:00`
    }

    ticks.push({
      time: t,
      percent: getOffsetPercent(t),
      label,
      isMajorDay: isMajor,
    })
  }
  return ticks
})

// Filtered Facility Tracks
const filteredFacilityTracks = computed<FacilityTrack[]>(() => {
  if (!dataset.value) return []
  const q = searchQuery.value.trim().toLowerCase()
  return dataset.value.facilityTracks.filter((track) => {
    if (facilityFilter.value !== 'all') {
      if (facilityFilter.value === 'manufacture' && track.roomType !== 'manufacture') return false
      if (facilityFilter.value === 'trading' && track.roomType !== 'trading') return false
      if (facilityFilter.value === 'power' && track.roomType !== 'power') return false
      if (facilityFilter.value === 'central' && track.roomType !== 'central') return false
      if (facilityFilter.value === 'dormitory' && track.roomType !== 'dormitory') return false
      if (
        facilityFilter.value === 'auxiliary' &&
        ['manufacture', 'trading', 'power', 'central', 'dormitory'].includes(track.roomType)
      ) {
        return false
      }
    }
    if (!q) return true
    if (track.roomName.toLowerCase().includes(q)) return true
    if (track.roomId.toLowerCase().includes(q)) return true
    return track.slots.some((slot) =>
      slot.intervals.some((i) => i.operatorName.toLowerCase().includes(q)),
    )
  })
})

// Filtered Operator Tracks
const filteredOperatorTracks = computed<OperatorTrack[]>(() => {
  if (!dataset.value) return []
  const q = searchQuery.value.trim().toLowerCase()
  return dataset.value.operatorTracks.filter((track) => {
    if (!q) return true
    if (track.operatorName.toLowerCase().includes(q)) return true
    if (track.operatorId.toLowerCase().includes(q)) return true
    return track.intervals.some((i) => i.roomName.toLowerCase().includes(q))
  })
})

const visibleFacilityIntervals = computed(() => {
  const result = new Map<string, TimelineDisplayInterval[]>()
  for (const track of filteredFacilityTracks.value) for (const slot of track.slots) {
    result.set(slot.slotKey, visibleTimelineIntervals(slot.intervals, customWindowStart.value, customWindowEnd.value, 900))
  }
  return result
})

const visibleOperatorIntervals = computed(() => {
  const result = new Map<string, TimelineDisplayInterval[]>()
  for (const track of filteredOperatorTracks.value) {
    result.set(track.operatorId, visibleTimelineIntervals(track.intervals, customWindowStart.value, customWindowEnd.value, 900))
  }
  return result
})

const exportFacilityIntervals = computed(() => {
  const result = new Map<string, TimelineDisplayInterval[]>()
  for (const track of filteredFacilityTracks.value) for (const slot of track.slots) {
    result.set(slot.slotKey, visibleTimelineIntervals(slot.intervals, activeExportStart.value, activeExportEnd.value, exportTrackWidthPx.value))
  }
  return result
})

// Filtered Events within zoom window
const visibleEvents = computed<TimelineMarkerEvent[]>(() => {
  if (!dataset.value || !showEventMarkers.value) return []
  return dataset.value.events.filter(
    (e) => e.time >= customWindowStart.value && e.time <= customWindowEnd.value,
  )
})

// All backup plan and task events across the entire simulation
const backupEvents = computed<TimelineMarkerEvent[]>(() => {
  if (!dataset.value) return []
  return dataset.value.events.filter(e => e.type === 'backup-plan' || e.type === 'backup-task')
})

function jumpToNextBackupEvent(): void {
  const events = backupEvents.value
  if (!events.length) return
  const cur = customWindowStart.value
  const next = events.find(e => e.time > cur + 0.1) ?? events[0]
  if (next) {
    panWindowTo(Math.max(0, next.time - windowDuration.value / 3))
  }
}

// Track mouse cursor over timeline
function handleMouseMove(e: MouseEvent): void {
  const container = (e.currentTarget as HTMLElement)
  const rect = container.getBoundingClientRect()
  const mouseX = Math.max(0, Math.min(rect.width, e.clientX - rect.left))
  const frac = mouseX / rect.width
  cursorXPercent.value = frac * 100
  cursorTime.value = customWindowStart.value + frac * windowDuration.value
}

function handleMouseLeave(): void {
  cursorTime.value = null
  cursorXPercent.value = null
  hoveredInterval.value = null
  hoveredEvent.value = null
}

function handleIntervalHover(interval: TimelineDisplayInterval, e: MouseEvent): void {
  hoveredInterval.value = interval
  tooltipX.value = e.clientX + 12
  tooltipY.value = e.clientY + 12
}

function handleEventHover(event: TimelineMarkerEvent, e: MouseEvent): void {
  hoveredEvent.value = event
  tooltipX.value = e.clientX + 12
  tooltipY.value = e.clientY + 12
}

function formatHour(h: number | null | undefined): string {
  if (h === null || h === undefined || !Number.isFinite(h)) return '0.0h'
  return h.toFixed(1) + 'h'
}

function getStatusBadgeClass(status: TimelineInterval['status'], roomType: string): string {
  if (status === 'exhausted') return 'status-exhausted'
  if (status === 'resting') return 'status-resting'
  if (status === 'idle') return 'status-idle'
  return `type-${roomType}`
}
</script>

<template>
  <div class="schedule-timeline-gantt" data-test="schedule-timeline-gantt">
    <!-- Header & Controls -->
    <div class="gantt-header">
      <div class="gantt-title-row">
        <div class="gantt-title-group">
          <h4 class="gantt-title">排班甘特图 / 时间轴可视化</h4>
          <span class="gantt-subtitle">多周期离散事件演化、干员轮换在岗时段与实时工休轨迹；小于屏幕像素的连续切换会合并显示</span>
        </div>
        <div class="gantt-title-actions">
          <button
            type="button"
            class="export-gantt-btn"
            data-test="toggle-gantt-visibility"
            :aria-expanded="isTimelineExpanded"
            aria-controls="gantt-visualization"
            @click="isTimelineExpanded = !isTimelineExpanded"
          >
            {{ isTimelineExpanded ? '收起图表' : '展开图表' }}
          </button>
          <button
            type="button"
            class="export-gantt-btn"
            data-test="export-gantt-btn"
            title="以标准 12h 视窗导出设施分道甘特图高清图片"
            @click="openExportModal"
          >
            📷 导出设施甘特图
          </button>
          <div v-if="isTimelineExpanded" class="view-mode-toggle">
            <button
              type="button"
              class="toggle-btn"
              :class="{ active: viewMode === 'facility' }"
              data-test="view-mode-facility"
              @click="viewMode = 'facility'"
            >
              🏢 设施分道
            </button>
            <button
              type="button"
              class="toggle-btn"
              :class="{ active: viewMode === 'operator' }"
              data-test="view-mode-operator"
              @click="viewMode = 'operator'"
            >
              👤 干员分道
            </button>
          </div>
        </div>
      </div>

      <!-- Filter and Zoom Bar -->
      <div v-if="isTimelineExpanded" class="gantt-controls-bar">
        <!-- Facility Filter (facility view only) -->
        <div v-if="viewMode === 'facility'" class="filter-chips">
          <button
            v-for="[key, label] in [
              ['all', '全部设施'],
              ['manufacture', '制造站'],
              ['trading', '贸易站'],
              ['power', '发电站'],
              ['central', '控制中枢'],
              ['dormitory', '宿舍'],
              ['auxiliary', '其他辅助'],
            ]"
            :key="key"
            type="button"
            class="chip-btn"
            :class="{ active: facilityFilter === key }"
            @click="facilityFilter = key"
          >
            {{ label }}
          </button>
        </div>

        <!-- Search Bar -->
        <div class="search-wrap">
          <input
            v-model="searchQuery"
            type="text"
            class="gantt-search-input"
            :placeholder="viewMode === 'facility' ? '搜索设施或在岗干员...' : '搜索干员名称...'"
          />
          <button v-if="searchQuery" type="button" class="search-clear-btn" @click="searchQuery = ''">✕</button>
        </div>

        <!-- Window Size Slider Group (Req 1) -->
        <div class="window-slider-group" data-test="window-slider-group">
          <span class="ctrl-label">时间窗:</span>
          <input
            type="range"
            class="window-size-slider"
            data-test="window-size-slider"
            :min="6"
            :max="totalObservedHours"
            :step="1"
            :value="windowDuration"
            @input="onWindowSliderInput"
          />
          <span class="slider-val-badge">
            {{ windowDuration >= totalObservedHours - 0.05 ? `全周期 (${totalObservedHours.toFixed(0)}h)` : `${windowDuration.toFixed(0)}h` }}
          </span>
          <div class="slider-quick-chips">
            <button
              v-for="p in quickWindowPresets"
              :key="p.key"
              type="button"
              class="zoom-btn zoom-chip"
              :class="{ active: Math.abs(windowDuration - p.val) < 0.5 }"
              @click="setZoomPreset(p.key as any)"
            >
              {{ p.label }}
            </button>
          </div>
        </div>

        <!-- Event markers toggle -->
        <label class="event-toggle-label">
          <input v-model="showEventMarkers" type="checkbox" />
          <span>事件标记</span>
        </label>

        <!-- Jump to backup plan events -->
        <button
          v-if="backupEvents.length > 0"
          type="button"
          class="backup-events-pill"
          data-test="jump-backup-event-btn"
          :title="`共检测到 ${backupEvents.length} 次副表调度事件，点击跳转至下一个副表事件`"
          @click="jumpToNextBackupEvent"
        >
          🔄 副表事件 ({{ backupEvents.length }}次) →
        </button>
      </div>

      <!-- Window Navigation Toolbar -->
      <div v-if="isTimelineExpanded" class="gantt-window-nav-bar" data-test="gantt-window-nav-bar">
        <div class="nav-btn-group">
          <button
            type="button"
            class="nav-btn jump-btn"
            title="移至最初 (T+0h)"
            :disabled="customWindowStart <= 0.01"
            data-test="nav-jump-start"
            @click="jumpToStart"
          >
            ⏮ 最初
          </button>
          <button
            type="button"
            class="nav-btn step-btn"
            :title="`后退半窗 (-${(windowDuration / 2).toFixed(0)}h)`"
            :disabled="customWindowStart <= 0.01"
            data-test="nav-step-back"
            @click="panWindow(-windowDuration / 2)"
          >
            ‹ -{{ (windowDuration / 2).toFixed(0) }}h
          </button>
          <button
            type="button"
            class="nav-btn pan-btn"
            title="上一周期"
            :disabled="customWindowStart <= 0.01"
            data-test="nav-prev-window"
            @click="panWindow(-windowDuration)"
          >
            ◀ 上一周期
          </button>

          <!-- Cycle Dropdown Selector -->
          <div v-if="cycleOptions.length > 1" class="cycle-picker-wrap">
            <select
              class="cycle-select"
              data-test="cycle-select"
              :value="currentCycleIndex"
              @change="onCycleSelectChange"
            >
              <option v-for="c in cycleOptions" :key="c.index" :value="c.index">
                {{ c.label }}
              </option>
            </select>
          </div>

          <button
            type="button"
            class="nav-btn pan-btn"
            title="下一周期"
            :disabled="customWindowEnd >= totalObservedHours - 0.01"
            data-test="nav-next-window"
            @click="panWindow(windowDuration)"
          >
            下一周期 ▶
          </button>
          <button
            type="button"
            class="nav-btn step-btn"
            :title="`前进半窗 (+${(windowDuration / 2).toFixed(0)}h)`"
            :disabled="customWindowEnd >= totalObservedHours - 0.01"
            data-test="nav-step-forward"
            @click="panWindow(windowDuration / 2)"
          >
            +{{ (windowDuration / 2).toFixed(0) }}h ›
          </button>
          <button
            type="button"
            class="nav-btn jump-btn"
            :title="`移至最终 (T+${totalObservedHours.toFixed(0)}h)`"
            :disabled="customWindowEnd >= totalObservedHours - 0.01"
            data-test="nav-jump-end"
            @click="jumpToEnd"
          >
            最终 ⏭
          </button>
        </div>
      </div>

      <!-- Overview Scrubber Track (visible when total > window, Req 4) -->
      <div
        v-if="isTimelineExpanded && totalObservedHours > windowDuration"
        class="gantt-overview-scrubber"
        data-test="gantt-overview-scrubber"
      >
        <div class="overview-header-row">
          <span class="overview-title">
            全景概览（共 {{ totalObservedHours.toFixed(0) }}h / {{ (totalObservedHours / 24).toFixed(1) }} 天 · 支持拖拽滑块实时滑动预览）：
          </span>
          <span class="overview-pct">
            视窗覆盖 {{ ((windowDuration / totalObservedHours) * 100).toFixed(0) }}% ({{ windowDuration.toFixed(1) }}h)
          </span>
        </div>
        <div
          ref="overviewTrackRef"
          class="overview-track"
          :class="{ 'is-dragging': isDraggingOverview }"
          @mousedown="handleOverviewTrackMouseDown"
        >
          <!-- Day divider lines -->
          <div
            v-for="d in overviewDayTicks"
            :key="d.day"
            class="overview-day-tick"
            :style="{ left: `${d.percent}%` }"
          >
            <span v-if="d.showLabel" class="overview-tick-label">D{{ d.day }}</span>
          </div>

          <!-- Viewport highlight thumb (draggable) -->
          <div
            class="overview-window-viewport"
            :class="{ 'is-dragging': isDraggingOverview }"
            :style="{
              left: `${(customWindowStart / totalObservedHours) * 100}%`,
              width: `${((customWindowEnd - customWindowStart) / totalObservedHours) * 100}%`,
            }"
            @mousedown.stop="handleOverviewThumbMouseDown"
          >
            <span class="viewport-tag">
              T+{{ customWindowStart.toFixed(0) }}h ~ T+{{ customWindowEnd.toFixed(0) }}h
            </span>
          </div>
        </div>
      </div>

      <!-- Time Window Info Bar -->
      <div v-if="isTimelineExpanded" class="time-window-info">
        <span>当前视窗：<strong>T+{{ customWindowStart.toFixed(1) }}h</strong> 至 <strong>T+{{ customWindowEnd.toFixed(1) }}h</strong>（共 {{ windowDuration.toFixed(1) }} 小时 / {{ (windowDuration / 24).toFixed(1) }} 天 · 按住鼠标左键可拖拽时间轴平移）</span>
        <span v-if="cursorTime !== null" class="cursor-info">
          🎯 光标定位：<strong>T+{{ cursorTime.toFixed(2) }}h</strong>（第 {{ Math.floor(cursorTime / 24) + 1 }} 天 {{ String(Math.floor(cursorTime % 24)).padStart(2, '0') }}:{{ String(Math.floor((cursorTime % 1) * 60)).padStart(2, '0') }}）
        </span>
      </div>
    </div>

    <!-- Empty State -->
    <div v-if="isTimelineExpanded && (!dataset || dataset.facilityTracks.length === 0)" id="gantt-visualization" class="gantt-empty-state">
      <div class="empty-icon">📊</div>
      <p class="empty-title">暂无时间轴数据</p>
      <p class="empty-desc">运行基建排班仿真计算后，系统将自动记录并呈现全周期干员工休及设施运转甘特图。</p>
      <button type="button" class="run-sim-btn" @click="emit('request-simulate')">
        立即运行排班模拟
      </button>
    </div>

    <!-- Gantt Chart Main Area -->
    <div v-else-if="isTimelineExpanded" id="gantt-visualization" class="gantt-container" data-test="gantt-container">
      <div class="gantt-scroll-wrapper">
        <!-- Ruler Row (Sticky Header) -->
        <div class="gantt-ruler-row">
          <div class="gantt-axis-label-col">
            <span class="axis-title">{{ viewMode === 'facility' ? '设施 / 槽位' : '干员名单' }}</span>
          </div>
          <div
            class="gantt-timeline-track ruler-track"
            @mousemove="handleMouseMove"
            @mouseleave="handleMouseLeave"
            @mousedown="handleTimelineMouseDown"
          >
            <!-- Ruler Ticks -->
            <div
              v-for="tick in rulerTicks"
              :key="tick.time"
              class="ruler-tick"
              :class="{ 'major-day': tick.isMajorDay }"
              :style="{ left: `${tick.percent}%` }"
            >
              <div class="tick-line" />
              <span class="tick-label">{{ tick.label }}</span>
            </div>

            <!-- Visible Event Markers on Ruler -->
            <div
              v-for="(ev, idx) in visibleEvents"
              :key="idx"
              class="event-marker"
              :style="{ left: `${getOffsetPercent(ev.time)}%`, backgroundColor: ev.color }"
              @mouseenter="handleEventHover(ev, $event)"
              @mouseleave="hoveredEvent = null"
            >
              <span class="marker-icon">{{ ev.icon }}</span>
            </div>

            <!-- Vertical Hairline Cursor -->
            <div
              v-if="cursorXPercent !== null"
              class="scrubber-cursor"
              :style="{ left: `${cursorXPercent}%` }"
            >
              <span class="scrubber-badge">T+{{ cursorTime?.toFixed(1) }}h</span>
            </div>
          </div>
        </div>

        <!-- Tracks Body -->
        <div
          ref="tracksContainerRef"
          class="gantt-tracks-body"
          :class="{ 'is-dragging': isDraggingTimeline }"
          @mousemove="handleMouseMove"
          @mouseleave="handleMouseLeave"
          @mousedown="handleTimelineMouseDown"
          @wheel.passive="handleTimelineWheel"
        >
          <!-- Background Grid Lines -->
          <div class="gantt-grid-overlay">
            <div
              v-for="tick in rulerTicks"
              :key="tick.time"
              class="grid-line"
              :class="{ 'major-grid': tick.isMajorDay }"
              :style="{ left: `${tick.percent}%` }"
            />
            <div
              v-if="cursorXPercent !== null"
              class="scrubber-line"
              :style="{ left: `${cursorXPercent}%` }"
            />
          </div>

          <!-- FACILITY VIEW -->
          <template v-if="viewMode === 'facility'">
            <div
              v-for="facility in filteredFacilityTracks"
              :key="facility.roomId"
              class="facility-group"
              :class="`room-${facility.roomType}`"
            >
              <!-- Facility Subheader -->
              <div class="facility-group-header">
                <div class="group-title-col">
                  <span class="facility-tag" :class="facility.roomType">{{ facility.roomType }}</span>
                  <span class="facility-name">{{ facility.roomName }}</span>
                  <span class="facility-eff">+{{ facility.averageEfficiency.toFixed(1) }}%</span>
                </div>
                <div class="group-track-spacer" />
              </div>

              <!-- Slots of this facility -->
              <div
                v-for="slot in facility.slots"
                :key="slot.slotKey"
                class="track-row"
              >
                <div class="track-label-col slot-label-col">
                  <span class="slot-badge">槽位 {{ slot.slotIndex + 1 }}</span>
                  <span v-if="slot.role === 'dorm-keeper'" class="role-badge keeper">宿管</span>
                  <span v-else-if="slot.role === 'fiammetta'" class="role-badge fiammetta">互换</span>
                </div>

                <div class="track-content-lane">
                  <div
                    v-for="interval in visibleFacilityIntervals.get(slot.slotKey) ?? []"
                    :key="interval.id"
                    class="gantt-block"
                    :class="[
                      getStatusBadgeClass(interval.status, interval.roomType),
                      {
                        highlighted: highlightedOperatorId === interval.operatorId && interval.operatorId,
                        dimmed: highlightedOperatorId && highlightedOperatorId !== interval.operatorId,
                        'status-condensed': Boolean(interval.condensedCount),
                      },
                    ]"
                    :style="{
                      left: `${getOffsetPercent(interval.start)}%`,
                      width: `${getWidthPercent(interval.start, interval.end)}%`,
                    }"
                    @mouseenter="handleIntervalHover(interval, $event)"
                    @mouseleave="hoveredInterval = null"
                  >
                    <div class="block-content">
                      <img
                        v-if="interval.avatarUrl"
                        :src="interval.avatarUrl"
                        :alt="interval.operatorName"
                        class="block-avatar"
                        onerror="this.style.display='none'"
                      />
                      <span class="block-name">{{ interval.operatorName || '空置' }}</span>
                      <span v-if="interval.duration >= 3" class="block-duration">
                        {{ formatHour(interval.duration) }}
                      </span>
                    </div>
                  </div>
                </div>
              </div>
            </div>
          </template>

          <!-- OPERATOR VIEW -->
          <template v-else>
            <div
              v-for="op in filteredOperatorTracks"
              :key="op.operatorId"
              class="track-row operator-track-row"
            >
              <div class="track-label-col op-label-col">
                <img
                  v-if="op.avatarUrl"
                  :src="op.avatarUrl"
                  :alt="op.operatorName"
                  class="op-avatar"
                  onerror="this.style.display='none'"
                />
                <div class="op-info">
                  <span class="op-name">{{ op.operatorName }}</span>
                  <span class="op-duty-badge">
                    {{ (op.workFraction * 100).toFixed(0) }}% 工时 ({{ op.workHours.toFixed(1) }}h)
                  </span>
                </div>
              </div>

              <div class="track-content-lane">
                <div
                  v-for="interval in visibleOperatorIntervals.get(op.operatorId) ?? []"
                  :key="interval.id"
                  class="gantt-block"
                  :class="[
                    getStatusBadgeClass(interval.status, interval.roomType),
                    {
                        highlighted: highlightedOperatorId === interval.operatorId && interval.operatorId,
                        dimmed: highlightedOperatorId && highlightedOperatorId !== interval.operatorId,
                        'status-condensed': Boolean(interval.condensedCount),
                    },
                  ]"
                  :style="{
                    left: `${getOffsetPercent(interval.start)}%`,
                    width: `${getWidthPercent(interval.start, interval.end)}%`,
                  }"
                  @mouseenter="handleIntervalHover(interval, $event)"
                  @mouseleave="hoveredInterval = null"
                >
                  <div class="block-content">
                    <span class="block-status-icon">
                      {{ interval.status === 'working' ? '💼' : interval.status === 'resting' ? '🛏️' : interval.status === 'exhausted' ? '⚠️' : '💤' }}
                    </span>
                    <span class="block-name">{{ interval.condensedCount ? interval.operatorName : interval.roomName }}</span>
                    <span v-if="interval.duration >= 3" class="block-duration">
                      {{ formatHour(interval.duration) }}
                    </span>
                  </div>
                </div>
              </div>
            </div>
          </template>
        </div>
      </div>
    </div>

    <!-- Floating Inspector Tooltip -->
    <div
      v-if="isTimelineExpanded && hoveredInterval"
      class="gantt-tooltip"
      :style="{ left: `${tooltipX}px`, top: `${tooltipY}px` }"
    >
      <div class="tooltip-header">
        <img
          v-if="hoveredInterval.avatarUrl"
          :src="hoveredInterval.avatarUrl"
          :alt="hoveredInterval.operatorName"
          class="tooltip-avatar"
        />
        <div class="tooltip-title-box">
          <span class="tooltip-title">{{ hoveredInterval.operatorName || '空置槽位' }}</span>
          <span class="tooltip-subtitle">{{ hoveredInterval.roomName }} · 槽位 {{ hoveredInterval.slotIndex + 1 }}</span>
        </div>
        <span class="tooltip-status-tag" :class="hoveredInterval.status">
          {{ hoveredInterval.condensedCount ? `${hoveredInterval.condensedCount} 段合并显示` : hoveredInterval.status === 'working' ? '在岗作业' : hoveredInterval.status === 'resting' ? '宿舍恢复' : hoveredInterval.status === 'exhausted' ? '疲劳工作' : '待机闲置' }}
        </span>
      </div>
      <div class="tooltip-body">
        <div class="tooltip-row">
          <span class="row-label">时间区间：</span>
          <span class="row-val">T+{{ hoveredInterval.start.toFixed(2) }}h ~ T+{{ hoveredInterval.end.toFixed(2) }}h</span>
        </div>
        <div class="tooltip-row">
          <span class="row-label">持续时长：</span>
          <span class="row-val highlight">{{ hoveredInterval.duration.toFixed(2) }} 小时</span>
        </div>
        <div v-if="hoveredInterval.startMorale !== undefined" class="tooltip-row">
          <span class="row-label">心情演化：</span>
          <span class="row-val">
            {{ hoveredInterval.startMorale.toFixed(1) }} → {{ hoveredInterval.endMorale?.toFixed(1) }} / 24
          </span>
        </div>
        <div v-if="hoveredInterval.efficiencyPercent !== undefined" class="tooltip-row">
          <span class="row-label">设施效率：</span>
          <span class="row-val eff-val">+{{ hoveredInterval.efficiencyPercent.toFixed(1) }}%</span>
        </div>
      </div>
    </div>

    <!-- Event Tooltip -->
    <div
      v-if="isTimelineExpanded && hoveredEvent"
      class="gantt-tooltip event-tooltip"
      :style="{ left: `${tooltipX}px`, top: `${tooltipY}px` }"
    >
      <div class="tooltip-header">
        <span class="event-icon">{{ hoveredEvent.icon }}</span>
        <span class="tooltip-title">{{ hoveredEvent.label }}</span>
        <span class="tooltip-time">T+{{ hoveredEvent.time.toFixed(2) }}h</span>
      </div>
      <div class="tooltip-body">
        <p class="event-desc">{{ hoveredEvent.description }}</p>
      </div>
    </div>

    <!-- Export Modal for Facility Swimlane Gantt (Full Sampling Phase) -->
    <div
      v-if="showExportModal"
      class="gantt-export-modal-overlay"
      data-test="gantt-export-modal"
      @click.self="closeExportModal"
    >
      <div class="gantt-export-modal-card">
        <div class="export-modal-header">
          <div class="export-header-left">
            <h3 class="export-modal-title">📷 导出设施甘特图 (采样阶段完整长图)</h3>
            <span class="export-modal-subtitle">
              全周期共 {{ totalObservedHours.toFixed(0) }} 小时（T+0h 至 T+{{ totalObservedHours.toFixed(0) }}h），以 12h 视窗标准尺度生成高清晰度设施分道排班长图
            </span>
          </div>
          <div class="export-header-actions">
            <!-- Scope selector for long timelines (>72h) -->
            <div v-if="totalObservedHours > 72" class="scale-mode-selector scope-selector" data-test="scope-mode-selector">
              <span class="scale-title">范围:</span>
              <button
                type="button"
                class="scale-btn"
                :class="{ active: exportScopeMode === 'full' }"
                data-test="scope-btn-full"
                @click="exportScopeMode = 'full'"
              >
                全周期总览
              </button>
              <button
                type="button"
                class="scale-btn"
                :class="{ active: exportScopeMode === 'volume' }"
                data-test="scope-btn-volume"
                @click="exportScopeMode = 'volume'"
              >
                分卷超清 (推荐)
              </button>
              <button
                type="button"
                class="scale-btn"
                :class="{ active: exportScopeMode === 'custom' }"
                data-test="scope-btn-custom"
                @click="exportScopeMode = 'custom'"
              >
                自定义
              </button>
            </div>

            <!-- Volume Picker -->
            <div v-if="exportScopeMode === 'volume'" class="volume-picker-wrap">
              <select
                v-model.number="exportSelectedVolumeIndex"
                class="volume-select"
                data-test="volume-select"
              >
                <option v-for="vol in exportVolumes" :key="vol.index" :value="vol.index">
                  {{ vol.label }}
                </option>
              </select>
              <select v-model.number="exportVolumeDays" class="volume-select mini" data-test="volume-days-select">
                <option :value="2">每卷 2 天</option>
                <option :value="3">每卷 3 天</option>
                <option :value="7">每卷 7 天</option>
              </select>
            </div>

            <!-- Custom Range -->
            <div v-if="exportScopeMode === 'custom'" class="custom-range-wrap">
              <input v-model.number="exportCustomStart" type="number" min="0" :max="totalObservedHours - 1" class="custom-range-input" />
              <span class="range-sep">~</span>
              <input v-model.number="exportCustomEnd" type="number" min="1" :max="totalObservedHours" class="custom-range-input" />
              <span class="range-unit">h</span>
            </div>

            <div class="scale-mode-selector">
              <span class="scale-title">图像比例:</span>
              <button
                type="button"
                class="scale-btn"
                :class="{ active: exportScaleMode === 'standard' }"
                data-test="scale-btn-standard"
                @click="exportScaleMode = 'standard'"
              >
                标准 (12h视窗基准 · 100px/h)
              </button>
              <button
                type="button"
                class="scale-btn"
                :class="{ active: exportScaleMode === 'compact' }"
                data-test="scale-btn-compact"
                @click="exportScaleMode = 'compact'"
              >
                紧凑 (50px/h)
              </button>
            </div>

            <button
              type="button"
              class="export-action-btn primary"
              :disabled="isExporting"
              data-test="download-gantt-btn"
              @click="handleDownloadGanttImage"
            >
              {{ isExporting ? '生成中...' : '📥 下载 PNG 长图' }}
            </button>
            <button
              type="button"
              class="export-action-btn secondary"
              :disabled="isExporting"
              data-test="copy-gantt-btn"
              @click="handleCopyGanttImage"
            >
              📋 复制长图
            </button>
            <button type="button" class="export-close-btn" @click="closeExportModal">✕</button>
          </div>
        </div>

        <div v-if="exportStatus" class="export-status-alert" :class="exportStatus.type">
          {{ exportStatus.message }}
        </div>

        <div class="export-modal-body">
          <div class="export-canvas-scroll-container">
            <div
              ref="exportCanvasRef"
              class="export-canvas"
              :style="{ width: `${exportTotalWidthPx}px`, minWidth: `${exportTotalWidthPx}px` }"
            >
              <div class="export-banner">
                <div class="banner-title-group">
                  <h2 class="banner-title">罗德岛基建排班甘特图 · 设施分道</h2>
                  <span class="banner-time-badge">
                    {{ exportScopeMode === 'volume' ? `分卷排班（第 ${exportSelectedVolumeIndex + 1} / ${exportVolumes.length} 卷）：` : exportScopeMode === 'custom' ? '自定义时段排班：' : '采样阶段全周期：' }}
                    T+{{ activeExportStart.toFixed(1) }}h 至 T+{{ activeExportEnd.toFixed(1) }}h（共 {{ activeExportDuration.toFixed(0) }} 小时 / {{ (activeExportDuration / 24).toFixed(1) }} 天）· 比例尺：{{ exportPixelsPerHour }}px/h（以 12h 视窗为基准）
                  </span>
                </div>
                <div class="banner-legend">
                  <span class="legend-item"><span class="legend-dot status-working" />在岗工作</span>
                  <span class="legend-item"><span class="legend-dot status-resting" />宿舍休整</span>
                  <span class="legend-item"><span class="legend-dot status-exhausted" />疲劳溢出</span>
                </div>
              </div>

              <!-- Ruler Row -->
              <div class="export-ruler-row">
                <div class="export-axis-col">
                  <span>设施 / 槽位</span>
                </div>
                <div class="export-timeline-track" :style="{ width: `${exportTrackWidthPx}px` }">
                  <div
                    v-for="tick in exportRulerTicks"
                    :key="tick.time"
                    class="ruler-tick"
                    :class="{ 'major-day': tick.isMajorDay }"
                    :style="{ left: `${tick.percent}%` }"
                  >
                    <div class="tick-line" />
                    <span class="tick-label">{{ tick.label }}</span>
                  </div>
                </div>
              </div>

              <!-- Tracks Body -->
              <div class="export-tracks-body">
                <div class="gantt-grid-overlay">
                  <div
                    v-for="tick in exportRulerTicks"
                    :key="tick.time"
                    class="grid-line"
                    :class="{ 'major-grid': tick.isMajorDay }"
                    :style="{ left: `${tick.percent}%` }"
                  />
                </div>

                <!-- Facilities -->
                <div
                  v-for="facility in filteredFacilityTracks"
                  :key="facility.roomId"
                  class="facility-group"
                  :class="`room-${facility.roomType}`"
                >
                  <div class="facility-group-header">
                    <div class="group-title-col">
                      <span class="facility-tag" :class="facility.roomType">{{ facility.roomType }}</span>
                      <span class="facility-name">{{ facility.roomName }}</span>
                      <span class="facility-eff">+{{ facility.averageEfficiency.toFixed(1) }}%</span>
                    </div>
                    <div class="group-track-spacer" />
                  </div>

                  <div
                    v-for="slot in facility.slots"
                    :key="slot.slotKey"
                    class="track-row"
                  >
                    <div class="track-label-col slot-label-col">
                      <span class="slot-badge">槽位 {{ slot.slotIndex + 1 }}</span>
                      <span v-if="slot.role === 'dorm-keeper'" class="role-badge keeper">宿管</span>
                      <span v-else-if="slot.role === 'fiammetta'" class="role-badge fiammetta">互换</span>
                    </div>

                    <div class="track-content-lane" :style="{ width: `${exportTrackWidthPx}px` }">
                      <div
                        v-for="interval in exportFacilityIntervals.get(slot.slotKey) ?? []"
                        :key="interval.id"
                        class="gantt-block"
                        :class="[getStatusBadgeClass(interval.status, interval.roomType), { 'status-condensed': Boolean(interval.condensedCount) }]"
                        :style="{
                          left: `${getExportOffsetPercent(interval.start)}%`,
                          width: `${getExportWidthPercent(interval.start, interval.end)}%`,
                        }"
                      >
                        <div class="block-content">
                          <img
                            v-if="interval.avatarUrl"
                            :src="interval.avatarUrl"
                            :alt="interval.operatorName"
                            class="block-avatar"
                            onerror="this.style.display='none'"
                          />
                          <span class="block-name">{{ interval.operatorName || '空置' }}</span>
                          <span v-if="interval.duration >= 0.8" class="block-duration">
                            {{ formatHour(interval.duration) }}
                          </span>
                        </div>
                      </div>
                    </div>
                  </div>
                </div>
              </div>

              <div class="export-canvas-footer">
                <span>明日方舟基建排班与全动态模拟测算器 · R.I.I.C-Calculator</span>
                <span>采样全周期甘特图 · 小于像素的连续切换合并显示</span>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.schedule-timeline-gantt {
  width: 100%;
  background: #141920;
  border: 1px solid rgba(255, 255, 255, 0.08);
  border-radius: 6px;
  color: #e9f2f4;
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, monospace;
  box-sizing: border-box;
  margin: 16px 0;
  overflow: hidden;
}

.gantt-header {
  padding: 16px 20px 12px;
  background: #1a222c;
  border-bottom: 1px solid rgba(255, 255, 255, 0.08);
}

.gantt-title-row {
  display: flex;
  justify-content: space-between;
  align-items: center;
  flex-wrap: wrap;
  gap: 12px;
  margin-bottom: 12px;
}

.gantt-title-actions {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
}

.export-gantt-btn {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 5px 12px;
  background: linear-gradient(135deg, rgba(66, 214, 199, 0.15), rgba(38, 166, 154, 0.22));
  border: 1px solid rgba(66, 214, 199, 0.45);
  border-radius: 4px;
  color: #42d6c7;
  font-size: 12px;
  font-weight: 500;
  cursor: pointer;
  transition: all 0.2s;
  white-space: nowrap;
}

.export-gantt-btn:hover {
  background: linear-gradient(135deg, rgba(66, 214, 199, 0.25), rgba(38, 166, 154, 0.35));
  border-color: #42d6c7;
  color: #ffffff;
  box-shadow: 0 0 10px rgba(66, 214, 199, 0.3);
}

.gantt-title {
  margin: 0;
  font-size: 16px;
  font-weight: 600;
  color: #ffffff;
  letter-spacing: 0.5px;
}

.gantt-subtitle {
  font-size: 12px;
  color: #8da5ac;
  display: block;
  margin-top: 2px;
}

.view-mode-toggle {
  display: flex;
  background: rgba(0, 0, 0, 0.35);
  padding: 3px;
  border-radius: 5px;
  border: 1px solid rgba(255, 255, 255, 0.1);
}

.toggle-btn {
  padding: 5px 14px;
  font-size: 12px;
  font-weight: 500;
  border: none;
  background: transparent;
  color: #8da5ac;
  border-radius: 3px;
  cursor: pointer;
  transition: all 0.2s;
}

.toggle-btn.active {
  background: #42d6c7;
  color: #0b1e1b;
  font-weight: 600;
  box-shadow: 0 1px 4px rgba(66, 214, 199, 0.3);
}

.gantt-controls-bar {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 12px;
  margin-bottom: 10px;
}

.filter-chips {
  display: flex;
  gap: 6px;
  flex-wrap: wrap;
}

.chip-btn {
  padding: 3px 10px;
  font-size: 11px;
  border-radius: 3px;
  background: rgba(255, 255, 255, 0.05);
  border: 1px solid rgba(255, 255, 255, 0.1);
  color: #b6c6d1;
  cursor: pointer;
  transition: all 0.15s;
}

.chip-btn:hover {
  background: rgba(255, 255, 255, 0.12);
  color: #fff;
}

.chip-btn.active {
  background: rgba(66, 214, 199, 0.15);
  border-color: #42d6c7;
  color: #42d6c7;
  font-weight: 600;
}

.search-wrap {
  position: relative;
  display: flex;
  align-items: center;
}

.gantt-search-input {
  height: 26px;
  padding: 0 24px 0 8px;
  background: rgba(0, 0, 0, 0.25);
  border: 1px solid rgba(255, 255, 255, 0.15);
  border-radius: 3px;
  color: #fff;
  font-size: 11px;
  width: 170px;
  outline: none;
}

.gantt-search-input:focus {
  border-color: #42d6c7;
}

.search-clear-btn {
  position: absolute;
  right: 6px;
  background: transparent;
  border: none;
  color: #8da5ac;
  cursor: pointer;
  font-size: 10px;
}

.window-slider-group {
  display: flex;
  align-items: center;
  gap: 8px;
  background: #141b24;
  padding: 3px 10px;
  border-radius: 4px;
  border: 1px solid rgba(255, 255, 255, 0.08);
}

.window-size-slider {
  width: 120px;
  accent-color: #42d6c7;
  cursor: pointer;
  height: 4px;
}

.slider-val-badge {
  font-size: 11px;
  color: #42d6c7;
  font-weight: 600;
  min-width: 48px;
  text-align: right;
  white-space: nowrap;
}

.slider-quick-chips {
  display: flex;
  gap: 3px;
  margin-left: 4px;
}

.zoom-chip {
  padding: 2px 6px;
  font-size: 10px;
  border-radius: 3px;
  background: rgba(255, 255, 255, 0.04);
  color: #8da5ac;
  border: 1px solid rgba(255, 255, 255, 0.06);
  cursor: pointer;
  transition: all 0.15s;
}

.zoom-chip:hover {
  background: rgba(255, 255, 255, 0.08);
  color: #ffffff;
}

.zoom-chip.active {
  background: rgba(66, 214, 199, 0.18);
  color: #42d6c7;
  border-color: rgba(66, 214, 199, 0.4);
  font-weight: 600;
}

.ctrl-label {
  font-size: 11px;
  color: #8da5ac;
}

.zoom-btn {
  padding: 3px 8px;
  font-size: 11px;
  background: rgba(255, 255, 255, 0.06);
  border: 1px solid rgba(255, 255, 255, 0.1);
  color: #b6c6d1;
  border-radius: 3px;
  cursor: pointer;
}

.zoom-btn.active {
  background: rgba(66, 214, 199, 0.2);
  border-color: #42d6c7;
  color: #42d6c7;
  font-weight: 600;
}

.event-toggle-label {
  display: flex;
  align-items: center;
  gap: 4px;
  font-size: 11px;
  color: #8da5ac;
  cursor: pointer;
}

/* Window Navigation Toolbar */
.gantt-window-nav-bar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  flex-wrap: wrap;
  gap: 10px;
  padding: 8px 0;
  border-top: 1px solid rgba(255, 255, 255, 0.06);
  margin-top: 6px;
}

.nav-btn-group {
  display: flex;
  align-items: center;
  gap: 4px;
  flex-wrap: wrap;
}

.nav-btn {
  padding: 4px 9px;
  font-size: 11px;
  font-weight: 500;
  background: rgba(255, 255, 255, 0.06);
  border: 1px solid rgba(255, 255, 255, 0.12);
  color: #d1e2e7;
  border-radius: 3px;
  cursor: pointer;
  transition: all 0.15s;
  user-select: none;
}

.nav-btn:hover:not(:disabled) {
  background: rgba(66, 214, 199, 0.15);
  border-color: #42d6c7;
  color: #ffffff;
}

.nav-btn:disabled {
  opacity: 0.35;
  cursor: not-allowed;
  border-color: rgba(255, 255, 255, 0.05);
}

.nav-btn.pan-btn {
  background: rgba(66, 214, 199, 0.08);
  color: #42d6c7;
  font-weight: 600;
}

.nav-btn.step-btn {
  color: #8da5ac;
  font-size: 10px;
  padding: 4px 6px;
}

.cycle-picker-wrap {
  display: inline-flex;
}

.cycle-select {
  padding: 3px 6px;
  font-size: 11px;
  font-weight: 500;
  background: #141920;
  border: 1px solid rgba(66, 214, 199, 0.4);
  color: #42d6c7;
  border-radius: 3px;
  outline: none;
  cursor: pointer;
  max-width: 220px;
}

.cycle-select:focus {
  border-color: #42d6c7;
  box-shadow: 0 0 0 1px rgba(66, 214, 199, 0.3);
}


/* Overview Scrubber Track */
.gantt-overview-scrubber {
  margin: 6px 0 8px;
  padding: 8px 10px;
  background: rgba(0, 0, 0, 0.25);
  border: 1px solid rgba(255, 255, 255, 0.06);
  border-radius: 4px;
}

.overview-header-row {
  display: flex;
  justify-content: space-between;
  align-items: center;
  font-size: 10px;
  color: #8da5ac;
  margin-bottom: 5px;
}

.overview-title {
  color: #a4b9c0;
}

.overview-pct {
  color: #42d6c7;
}

.overview-track {
  position: relative;
  height: 20px;
  background: rgba(255, 255, 255, 0.04);
  border: 1px solid rgba(255, 255, 255, 0.1);
  border-radius: 3px;
  cursor: pointer;
  overflow: hidden;
}

.overview-track.is-dragging {
  cursor: grabbing !important;
  user-select: none;
}

.overview-day-tick {
  position: absolute;
  top: 0;
  bottom: 0;
  width: 1px;
  background: rgba(255, 255, 255, 0.12);
  pointer-events: none;
}

.overview-tick-label {
  position: absolute;
  top: 2px;
  left: 2px;
  font-size: 8px;
  color: rgba(255, 255, 255, 0.35);
  line-height: 1;
}

.overview-window-viewport {
  position: absolute;
  top: 0;
  bottom: 0;
  background: rgba(66, 214, 199, 0.25);
  border: 1px solid #42d6c7;
  border-radius: 2px;
  display: flex;
  align-items: center;
  justify-content: center;
  cursor: grab;
  box-shadow: 0 0 6px rgba(66, 214, 199, 0.25);
  min-width: 6px;
  transition: background 0.15s;
}

.overview-window-viewport.is-dragging {
  cursor: grabbing !important;
  background: rgba(66, 214, 199, 0.45);
}

.overview-window-viewport:hover {
  background: rgba(66, 214, 199, 0.35);
}

.viewport-tag {
  font-size: 9px;
  color: #ffffff;
  font-weight: 600;
  white-space: nowrap;
  pointer-events: none;
  text-shadow: 0 1px 2px rgba(0, 0, 0, 0.8);
  padding: 0 4px;
}

.gantt-tracks-body.is-dragging {
  cursor: grabbing !important;
  user-select: none;
}

.time-window-info {
  display: flex;
  align-items: center;
  justify-content: space-between;
  flex-wrap: wrap;
  gap: 8px;
  font-size: 11px;
  color: #8da5ac;
  padding-top: 6px;
  border-top: 1px solid rgba(255, 255, 255, 0.05);
}

.time-window-info strong {
  color: #e9f2f4;
}

.cursor-info strong {
  color: #42d6c7;
}

/* Empty State */
.gantt-empty-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 48px 20px;
  text-align: center;
}

.empty-icon {
  font-size: 40px;
  opacity: 0.6;
  margin-bottom: 12px;
}

.empty-title {
  margin: 0 0 6px;
  font-size: 15px;
  font-weight: 600;
  color: #ffffff;
}

.empty-desc {
  font-size: 12px;
  color: #8da5ac;
  max-width: 440px;
  line-height: 1.6;
  margin: 0 0 16px;
}

.run-sim-btn {
  padding: 8px 18px;
  background: #42d6c7;
  color: #0c201d;
  font-weight: 600;
  font-size: 12px;
  border: none;
  border-radius: 4px;
  cursor: pointer;
  transition: opacity 0.2s;
}

.run-sim-btn:hover {
  opacity: 0.9;
}

/* Gantt Scroll Container */
.gantt-container {
  position: relative;
  overflow-x: auto;
  overflow-y: hidden;
  scrollbar-width: none;
  -ms-overflow-style: none;
}

.gantt-container::-webkit-scrollbar {
  display: none;
  width: 0;
  height: 0;
}

.gantt-scroll-wrapper {
  min-width: 860px;
}

/* Ruler Row */
.gantt-ruler-row {
  display: flex;
  height: 38px;
  background: #10151c;
  border-bottom: 1px solid rgba(255, 255, 255, 0.1);
  position: sticky;
  top: 0;
  z-index: 10;
}

.gantt-axis-label-col {
  width: 190px;
  min-width: 190px;
  padding: 0 14px;
  display: flex;
  align-items: center;
  border-right: 1px solid rgba(255, 255, 255, 0.08);
  background: #10151c;
  z-index: 11;
}

.axis-title {
  font-size: 11px;
  font-weight: 600;
  color: #8da5ac;
  text-transform: uppercase;
  letter-spacing: 0.5px;
}

.gantt-timeline-track {
  position: relative;
  flex: 1;
  overflow: hidden;
  user-select: none;
}

.ruler-track {
  height: 100%;
}

.ruler-tick {
  position: absolute;
  top: 0;
  bottom: 0;
  transform: translateX(-50%);
  display: flex;
  flex-direction: column;
  align-items: center;
  pointer-events: none;
}

.tick-line {
  width: 1px;
  height: 6px;
  background: rgba(255, 255, 255, 0.2);
}

.major-day .tick-line {
  height: 10px;
  background: #42d6c7;
  width: 2px;
}

.tick-label {
  font-size: 10px;
  color: #8da5ac;
  margin-top: 4px;
  white-space: nowrap;
}

.major-day .tick-label {
  color: #42d6c7;
  font-weight: 600;
}

/* Event marker on ruler */
.event-marker {
  position: absolute;
  top: 4px;
  transform: translateX(-50%);
  padding: 2px 5px;
  border-radius: 10px;
  font-size: 10px;
  cursor: pointer;
  z-index: 5;
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.5);
  display: flex;
  align-items: center;
}

.marker-icon {
  font-size: 10px;
}

/* Scrubber / Crosshair */
.scrubber-cursor {
  position: absolute;
  top: 0;
  bottom: 0;
  width: 1px;
  background: #42d6c7;
  pointer-events: none;
  z-index: 20;
}

.scrubber-badge {
  position: absolute;
  top: 2px;
  left: 3px;
  background: #42d6c7;
  color: #0b1e1b;
  font-size: 9px;
  font-weight: 700;
  padding: 1px 4px;
  border-radius: 2px;
  white-space: nowrap;
}

/* Tracks Body */
.gantt-tracks-body {
  position: relative;
  min-height: 280px;
}

.gantt-grid-overlay {
  position: absolute;
  top: 0;
  left: 190px;
  right: 0;
  bottom: 0;
  pointer-events: none;
  z-index: 1;
}

.grid-line {
  position: absolute;
  top: 0;
  bottom: 0;
  width: 1px;
  background: rgba(255, 255, 255, 0.03);
}

.major-grid {
  background: rgba(66, 214, 199, 0.08);
}

.scrubber-line {
  position: absolute;
  top: 0;
  bottom: 0;
  width: 1px;
  background: rgba(66, 214, 199, 0.6);
  box-shadow: 0 0 6px rgba(66, 214, 199, 0.4);
}

/* Facility Group */
.facility-group {
  border-bottom: 1px solid rgba(255, 255, 255, 0.06);
}

.facility-group-header {
  display: flex;
  height: 28px;
  background: rgba(255, 255, 255, 0.02);
  align-items: center;
}

.group-title-col {
  width: 190px;
  min-width: 190px;
  padding: 0 14px;
  display: flex;
  align-items: center;
  gap: 8px;
  border-right: 1px solid rgba(255, 255, 255, 0.06);
}

.facility-tag {
  font-size: 9px;
  text-transform: uppercase;
  padding: 1px 4px;
  border-radius: 2px;
  font-weight: 600;
  background: rgba(255, 255, 255, 0.1);
}

.facility-tag.manufacture { background: rgba(16, 185, 129, 0.2); color: #34d399; }
.facility-tag.trading { background: rgba(245, 158, 11, 0.2); color: #fbbf24; }
.facility-tag.power { background: rgba(14, 165, 233, 0.2); color: #38bdf8; }
.facility-tag.central { background: rgba(139, 92, 246, 0.2); color: #a78bfa; }
.facility-tag.dormitory { background: rgba(99, 102, 241, 0.2); color: #818cf8; }

.facility-name {
  font-size: 11px;
  font-weight: 600;
  color: #ffffff;
}

.facility-eff {
  font-size: 10px;
  color: #42d6c7;
  margin-left: auto;
}

.group-track-spacer {
  flex: 1;
}

/* Track Row */
.track-row {
  display: flex;
  height: 34px;
  border-bottom: 1px solid rgba(255, 255, 255, 0.04);
}

.track-row:hover {
  background: rgba(255, 255, 255, 0.02);
}

.track-label-col {
  width: 190px;
  min-width: 190px;
  padding: 0 14px;
  display: flex;
  align-items: center;
  border-right: 1px solid rgba(255, 255, 255, 0.06);
  background: #141920;
  z-index: 2;
  gap: 6px;
}

.slot-badge {
  font-size: 10px;
  color: #8da5ac;
}

.role-badge {
  font-size: 9px;
  padding: 1px 4px;
  border-radius: 2px;
}

.role-badge.keeper { background: rgba(139, 92, 246, 0.2); color: #c4b5fd; }
.role-badge.fiammetta { background: rgba(245, 158, 11, 0.2); color: #fde68a; }

.op-label-col {
  gap: 8px;
}

.op-avatar {
  width: 22px;
  height: 22px;
  border-radius: 3px;
  object-fit: cover;
  background: #2a3440;
}

.op-info {
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.op-name {
  font-size: 11px;
  font-weight: 600;
  color: #e9f2f4;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.op-duty-badge {
  font-size: 9px;
  color: #8da5ac;
}

.track-content-lane {
  position: relative;
  flex: 1;
  height: 100%;
  overflow: hidden;
  z-index: 3;
}

/* Gantt Block */
.gantt-block {
  position: absolute;
  top: 4px;
  bottom: 4px;
  border-radius: 3px;
  padding: 0 6px;
  display: flex;
  align-items: center;
  cursor: pointer;
  transition: transform 0.1s, opacity 0.2s, box-shadow 0.2s;
  box-sizing: border-box;
  overflow: hidden;
  border: 1px solid rgba(255, 255, 255, 0.15);
}

.gantt-block:hover {
  transform: translateY(-1px);
  z-index: 10;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.5);
}

.gantt-block.highlighted {
  border-color: #fff !important;
  box-shadow: 0 0 10px rgba(66, 214, 199, 0.7);
  z-index: 12;
}

.gantt-block.dimmed {
  opacity: 0.35;
}

.block-content {
  display: flex;
  align-items: center;
  gap: 5px;
  white-space: nowrap;
  overflow: hidden;
}

.block-avatar {
  width: 16px;
  height: 16px;
  border-radius: 2px;
  object-fit: cover;
}

.block-name {
  font-size: 11px;
  font-weight: 500;
  color: #ffffff;
  overflow: hidden;
  text-overflow: ellipsis;
}

.block-duration {
  font-size: 9px;
  opacity: 0.8;
  margin-left: 4px;
}

.block-status-icon {
  font-size: 10px;
}

/* Category Color Coding */
.type-manufacture {
  background: linear-gradient(90deg, #064e3b, #047857);
  border-color: #10b981;
}

.type-trading {
  background: linear-gradient(90deg, #78350f, #b45309);
  border-color: #f59e0b;
}

.type-power {
  background: linear-gradient(90deg, #0c4a6e, #0369a1);
  border-color: #0ea5e9;
}

.type-central {
  background: linear-gradient(90deg, #4c1d95, #6d28d9);
  border-color: #8b5cf6;
}

.status-resting {
  background: linear-gradient(90deg, #312e81, #4338ca);
  border-color: #6366f1;
}

.status-exhausted {
  background: repeating-linear-gradient(45deg, #7f1d1d, #7f1d1d 8px, #991b1b 8px, #991b1b 16px);
  border-color: #ef4444;
}

.status-idle {
  background: #1e293b;
  border-color: #475569;
  border-style: dashed;
}

.gantt-block.status-condensed {
  background: repeating-linear-gradient(45deg, #334155, #334155 5px, #64748b 5px, #64748b 10px);
  border-color: #cbd5e1;
}

/* Floating Tooltip */
.gantt-tooltip {
  position: fixed;
  z-index: 1000;
  background: #1a222c;
  border: 1px solid rgba(66, 214, 199, 0.5);
  box-shadow: 0 4px 20px rgba(0, 0, 0, 0.6);
  border-radius: 4px;
  padding: 10px 12px;
  pointer-events: none;
  font-size: 11px;
  color: #e9f2f4;
  min-width: 200px;
  max-width: 280px;
}

.tooltip-header {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 8px;
  padding-bottom: 6px;
  border-bottom: 1px solid rgba(255, 255, 255, 0.08);
}

.tooltip-avatar {
  width: 28px;
  height: 28px;
  border-radius: 3px;
  object-fit: cover;
}

.tooltip-title-box {
  display: flex;
  flex-direction: column;
}

.tooltip-title {
  font-size: 13px;
  font-weight: 600;
  color: #fff;
}

.tooltip-subtitle {
  font-size: 10px;
  color: #8da5ac;
}

.tooltip-status-tag {
  margin-left: auto;
  font-size: 10px;
  padding: 1px 5px;
  border-radius: 2px;
  font-weight: 600;
}

.tooltip-status-tag.working { background: rgba(16, 185, 129, 0.2); color: #34d399; }
.tooltip-status-tag.resting { background: rgba(99, 102, 241, 0.2); color: #818cf8; }
.tooltip-status-tag.exhausted { background: rgba(239, 68, 68, 0.2); color: #f87171; }
.tooltip-status-tag.idle { background: rgba(255, 255, 255, 0.1); color: #94a3b8; }

.tooltip-body {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.tooltip-row {
  display: flex;
  justify-content: space-between;
}

.row-label {
  color: #8da5ac;
}

.row-val {
  color: #e9f2f4;
  font-family: Consolas, monospace;
}

.row-val.highlight {
  color: #f0bd5b;
  font-weight: 600;
}

.row-val.eff-val {
  color: #42d6c7;
  font-weight: 600;
}

.event-tooltip .event-desc {
  margin: 0;
  line-height: 1.5;
  color: #cbd5e1;
}

.tooltip-time {
  margin-left: auto;
  color: #f0bd5b;
  font-family: Consolas, monospace;
}

.backup-events-pill {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 3px 8px;
  background: rgba(139, 92, 246, 0.2);
  border: 1px solid rgba(139, 92, 246, 0.4);
  border-radius: 12px;
  color: #c4b5fd;
  font-size: 11px;
  font-weight: 500;
  cursor: pointer;
  transition: all 0.15s ease;
}

.backup-events-pill:hover {
  background: rgba(139, 92, 246, 0.35);
  border-color: #8b5cf6;
  color: #fff;
}

/* Export Modal & Canvas Styles (Req 3) */
.gantt-export-modal-overlay {
  position: fixed;
  inset: 0;
  background: rgba(0, 0, 0, 0.78);
  backdrop-filter: blur(4px);
  z-index: 2000;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 24px;
}

.gantt-export-modal-card {
  width: 96vw;
  max-width: 1440px;
  max-height: 92vh;
  background: #11171f;
  border: 1px solid rgba(66, 214, 199, 0.35);
  border-radius: 8px;
  box-shadow: 0 20px 60px rgba(0, 0, 0, 0.7);
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.export-modal-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 12px 20px;
  background: #161f2a;
  border-bottom: 1px solid rgba(255, 255, 255, 0.08);
  gap: 12px;
  flex-wrap: wrap;
}

.export-header-left {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.export-modal-title {
  margin: 0;
  font-size: 15px;
  font-weight: 600;
  color: #ffffff;
}

.export-modal-subtitle {
  font-size: 11px;
  color: #8da5ac;
}

.export-header-actions {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
}

.scale-mode-selector {
  display: flex;
  align-items: center;
  gap: 4px;
  background: rgba(255, 255, 255, 0.05);
  padding: 2px 4px;
  border-radius: 4px;
  border: 1px solid rgba(255, 255, 255, 0.1);
}

.scale-title {
  font-size: 11px;
  color: #8da5ac;
  margin-right: 2px;
}

.scale-btn {
  padding: 4px 8px;
  font-size: 11px;
  font-weight: 500;
  border: none;
  background: transparent;
  color: #8da5ac;
  border-radius: 3px;
  cursor: pointer;
  transition: all 0.2s;
  user-select: none;
}

.scale-btn:hover {
  color: #ffffff;
}

.scale-btn.active {
  background: #42d6c7;
  color: #0b1e1b;
  font-weight: 600;
  box-shadow: 0 1px 4px rgba(66, 214, 199, 0.3);
}

.volume-picker-wrap,
.custom-range-wrap {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  background: rgba(255, 255, 255, 0.05);
  padding: 2px 6px;
  border-radius: 4px;
  border: 1px solid rgba(255, 255, 255, 0.1);
  font-size: 11px;
  color: #8da5ac;
}

.volume-select {
  padding: 3px 6px;
  font-size: 11px;
  background: #0f141b;
  border: 1px solid rgba(66, 214, 199, 0.4);
  color: #42d6c7;
  border-radius: 3px;
  outline: none;
  cursor: pointer;
}

.volume-select.mini {
  max-width: 90px;
}

.custom-range-input {
  width: 54px;
  padding: 2px 4px;
  font-size: 11px;
  background: #0f141b;
  border: 1px solid rgba(66, 214, 199, 0.4);
  color: #42d6c7;
  border-radius: 3px;
  text-align: center;
  outline: none;
}

.range-sep {
  color: #8da5ac;
}

.range-unit {
  color: #42d6c7;
}

.export-action-btn {
  padding: 5px 14px;
  font-size: 12px;
  font-weight: 500;
  border-radius: 4px;
  cursor: pointer;
  transition: all 0.2s;
  border: none;
  user-select: none;
}

.export-action-btn.primary {
  background: #42d6c7;
  color: #0c1f1c;
  font-weight: 600;
}

.export-action-btn.primary:hover:not(:disabled) {
  background: #5eead4;
  box-shadow: 0 0 10px rgba(66, 214, 199, 0.4);
}

.export-action-btn.secondary {
  background: rgba(255, 255, 255, 0.08);
  color: #e9f2f4;
  border: 1px solid rgba(255, 255, 255, 0.15);
}

.export-action-btn.secondary:hover:not(:disabled) {
  background: rgba(255, 255, 255, 0.15);
  border-color: #42d6c7;
  color: #42d6c7;
}

.export-action-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.export-close-btn {
  background: transparent;
  border: none;
  color: #8da5ac;
  font-size: 16px;
  cursor: pointer;
  padding: 4px 8px;
  border-radius: 4px;
}

.export-close-btn:hover {
  color: #fff;
  background: rgba(255, 255, 255, 0.1);
}

.export-status-alert {
  padding: 8px 20px;
  font-size: 12px;
  font-weight: 500;
  text-align: center;
}

.export-status-alert.success {
  background: rgba(16, 185, 129, 0.2);
  color: #34d399;
  border-bottom: 1px solid rgba(16, 185, 129, 0.3);
}

.export-status-alert.error {
  background: rgba(239, 68, 68, 0.2);
  color: #f87171;
  border-bottom: 1px solid rgba(239, 68, 68, 0.3);
}

.export-modal-body {
  flex: 1;
  overflow: auto;
  padding: 20px;
  background: #090c10;
}

.export-canvas-scroll-container {
  display: inline-block;
  min-width: 100%;
}

.export-canvas {
  background: #0e1319;
  border: 1px solid rgba(255, 255, 255, 0.12);
  border-radius: 6px;
  padding: 24px;
  box-shadow: 0 8px 32px rgba(0, 0, 0, 0.6);
  color: #e9f2f4;
  box-sizing: border-box;
}

.export-banner {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding-bottom: 16px;
  border-bottom: 1px solid rgba(255, 255, 255, 0.1);
  margin-bottom: 16px;
}

.banner-title-group {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.banner-title {
  margin: 0;
  font-size: 18px;
  font-weight: 700;
  color: #ffffff;
  letter-spacing: 0.5px;
}

.banner-time-badge {
  font-size: 12px;
  color: #42d6c7;
  font-weight: 500;
}

.banner-legend {
  display: flex;
  align-items: center;
  gap: 16px;
  font-size: 11px;
  color: #8da5ac;
}

.legend-item {
  display: inline-flex;
  align-items: center;
  gap: 5px;
}

.legend-dot {
  width: 10px;
  height: 10px;
  border-radius: 2px;
}

.legend-dot.status-working {
  background: #1e3a36;
  border: 1px solid #42d6c7;
}

.legend-dot.status-resting {
  background: #172d3e;
  border: 1px solid #38bdf8;
}

.legend-dot.status-exhausted {
  background: #3b1f24;
  border: 1px solid #f87171;
}

.export-ruler-row {
  display: flex;
  height: 38px;
  background: #131a22;
  border: 1px solid rgba(255, 255, 255, 0.1);
  border-bottom: none;
}

.export-axis-col {
  width: 190px;
  min-width: 190px;
  padding: 0 14px;
  display: flex;
  align-items: center;
  border-right: 1px solid rgba(255, 255, 255, 0.1);
  font-size: 11px;
  color: #8da5ac;
  font-weight: 600;
  background: #131a22;
}

.export-timeline-track {
  position: relative;
  flex: 1;
  overflow: hidden;
}

.export-tracks-body {
  position: relative;
  background: #111720;
  border: 1px solid rgba(255, 255, 255, 0.1);
}

.export-tracks-body .major-grid {
  background: rgba(66, 214, 199, 0.25);
  width: 2px;
}

.export-canvas-footer {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding-top: 14px;
  margin-top: 16px;
  border-top: 1px solid rgba(255, 255, 255, 0.08);
  font-size: 11px;
  color: #64748b;
}
</style>
