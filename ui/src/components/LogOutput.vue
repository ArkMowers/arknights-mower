<script setup>
import {
  computed,
  nextTick,
  onBeforeUnmount,
  onMounted,
  onUpdated,
  ref,
  shallowRef,
  watch
} from 'vue'
import { NScrollbar } from 'naive-ui'
import DetailChevron from '@vicons/ionicons5/es/ChevronDownOutline'
import logSheen from '@/assets/log/progress-sheen.svg?inline'
import JumpToLatestButton from '@/components/JumpToLatestButton.vue'
import LogOperator from '@/components/LogOperator.vue'
import LogInventory from '@/components/LogInventory.vue'
import LogItemToken from '@/components/LogItemToken.vue'
import LogStage from '@/components/LogStage.vue'
import TaskActionSubjects from '@/components/TaskActionSubjects.vue'
import { formatFacilityLabel } from '@/utils/base_facilities'
import { createLogRowPresenter } from '@/utils/logPresentation'
import { normalizeLogSource } from '@/utils/logSource'
import { lifecycleKey, trainingPositions } from '@/utils/logStructured'
import { analyzeLogTimeline, buildLogTimeline } from '@/utils/logTimeline'
import { WAIT_DISPLAY_DELAY, formatWaitDuration, scanSceneWaits } from '@/utils/logScenes'
import { logLayoutZoom } from '@/utils/logLayout'
import { useLogSheen } from '@/composables/logSheen'
import { useLogViewport } from '@/composables/logViewport'

const props = defineProps({
  lines: { type: Array, default: () => [] },
  operatorNames: { type: Array, default: () => [] },
  facilityPlan: { type: Object, default: () => ({}) },
  compact: Boolean,
  concise: Boolean,
  showAlternateView: Boolean,
  autoScroll: { type: Boolean, default: true },
  // 只在运行中显示等待状态，避免停止后残留一条永久“等待”。
  running: Boolean
})

// 一次追加超过这个行数多半是首屏历史或重连回放，不逐行播放淡入。
const MAX_BATCH_ANIMATION = 8

const output = ref(null)
const hiddenViewportHeight = ref(0)
watch(
  () => props.showAlternateView,
  (show) => {
    if (!show) return
    const scrollbar = output.value?.querySelector('.log-output__scroll')
    hiddenViewportHeight.value = scrollbar?.offsetHeight ?? 0
  }
)
const { filters: sheenFilters, refresh: refreshSheen } = useLogSheen(output)
const nowMs = ref(Date.now())
const expandedDetails = ref(new Set())
const collapsedDetails = ref(new Set())
const leavingDetails = ref(new Set())
const detailAnimations = new Map()
let nowTimer = null
const {
  stickyGroup,
  showJumpToLatest,
  jumpToLatest,
  noteScrollInput,
  startScrollbarDrag,
  preserveInventoryPosition: resizeInventory,
  startDetailResize,
  updateDetailResize,
  finishDetailResize,
  interruptDetailResize
} = useLogViewport(output, {
  autoScroll: () => props.autoScroll,
  renderInputs: () => [
    props.lines,
    props.operatorNames,
    props.facilityPlan,
    props.compact,
    props.concise,
    props.running,
    expandedDetails.value,
    collapsedDetails.value,
    leavingDetails.value
  ]
})

function returnToLatest(event) {
  if (event.currentTarget === globalThis.document?.activeElement) {
    output.value?.querySelector('.log-output__lines')?.focus({ preventScroll: true })
  }
  jumpToLatest()
}

function detailsExpanded(key) {
  return props.concise || key.startsWith('operation:')
    ? expandedDetails.value.has(key)
    : !collapsedDetails.value.has(key)
}

function detailsVisible(key) {
  return detailsExpanded(key) || leavingDetails.value.has(key)
}

function detailFrame(element) {
  const style = getComputedStyle(element)
  return {
    height: `${element.getBoundingClientRect().height / logLayoutZoom(element)}px`,
    opacity: style.opacity,
    marginBlockStart: style.marginBlockStart,
    marginBlockEnd: style.marginBlockEnd,
    paddingBlockStart: style.paddingBlockStart,
    paddingBlockEnd: style.paddingBlockEnd,
    boxSizing: 'border-box',
    minHeight: '0px',
    overflow: 'hidden'
  }
}

const collapsedDetailFrame = {
  height: '0px',
  opacity: 0,
  marginBlockStart: '0px',
  marginBlockEnd: '0px',
  paddingBlockStart: '0px',
  paddingBlockEnd: '0px',
  boxSizing: 'border-box',
  minHeight: '0px',
  overflow: 'hidden'
}

async function toggleDetails(key, animateHeight = false) {
  const opening = !detailsExpanded(key)
  const defaultOpen = !props.concise && !key.startsWith('operation:')
  const overrides = defaultOpen ? collapsedDetails : expandedDetails
  const animate =
    animateHeight &&
    typeof output.value?.animate === 'function' &&
    !globalThis.matchMedia?.('(prefers-reduced-motion: reduce)').matches
  if (animate) startDetailResize()
  const detailNodes = () =>
    [...(output.value?.querySelectorAll('[data-log-detail-owner]') ?? [])].filter(
      (element) => element.dataset.logDetailOwner === key
    )
  const activeAnimations = detailAnimations.get(key) ?? []
  const initial = new Map(
    animate && (!opening || activeAnimations.length)
      ? detailNodes().map((node) => [node, detailFrame(node)])
      : []
  )
  for (const animation of activeAnimations) animation.cancel()
  const animations = []
  detailAnimations.set(key, animations)

  const keys = new Set(items.value.map((item) => item.detailKey ?? item.key))
  if (!opening && initial.size) leavingDetails.value.add(key)
  else leavingDetails.value.delete(key)
  const changed = new Set([...overrides.value].filter((entry) => keys.has(entry)))
  if (opening === defaultOpen) changed.delete(key)
  else changed.add(key)
  overrides.value = changed

  await nextTick()
  if (detailAnimations.get(key) !== animations) return
  if (animate) {
    const targets = detailNodes()
    const frames = targets.map((node) => [
      node,
      initial.get(node) ?? collapsedDetailFrame,
      opening ? detailFrame(node) : collapsedDetailFrame
    ])
    for (const [node, from, to] of frames) {
      animations.push(
        node.animate([from, to], {
          duration: opening ? 200 : 160,
          easing: opening ? 'cubic-bezier(0.2, 0.8, 0.2, 1)' : 'cubic-bezier(0.32, 0.72, 0, 1)',
          fill: 'both'
        })
      )
    }
    updateDetailResize()
    await Promise.allSettled(animations.map((animation) => animation.finished))
    if (detailAnimations.get(key) !== animations) return
    leavingDetails.value.delete(key)
    await nextTick()
    if (detailAnimations.get(key) !== animations) return
    for (const animation of animations) animation.cancel()
  }
  detailAnimations.delete(key)
  if (!detailAnimations.size) finishDetailResize()
}

// 日志行可能是旧格式字符串，也可能是 store 的结构化记录。
const normalizedLines = computed(() => props.lines.map(normalizeLogSource))

const timelineAnalysis = computed(() => analyzeLogTimeline(normalizedLines.value))
const interruptedRescueStarts = new Map()
const rescueStartMarker = (lines, key) => {
  const record = [...lines]
    .reverse()
    .find((line) => lifecycleKey(line.event) === key && line.event.phase === 'started')
  return record ? (record.id ?? JSON.stringify([record.at, record.text, record.event])) : null
}
const interruptedLifecycleKeys = ref(new Set())
const interruptedRecruitmentIds = new Set()
watch(
  [() => props.running, normalizedLines],
  ([running, lines], previous) => {
    const retainedRecruitment = new Set(
      lines
        .filter((line) => line.event?.type === 'recruitment-slot' && line.event.phase === 'started')
        .map((line) => line.event.id)
    )
    for (const id of interruptedRecruitmentIds) {
      if (!retainedRecruitment.has(id)) interruptedRecruitmentIds.delete(id)
    }
    if (previous?.[0] && !running) {
      for (const id of retainedRecruitment) interruptedRecruitmentIds.add(id)
    }
    if (!running) {
      interruptedLifecycleKeys.value = timelineAnalysis.value.lifecycle.pendingKeys
      interruptedRescueStarts.clear()
      for (const key of interruptedLifecycleKeys.value) {
        if (key.startsWith('["rescue-staffing",'))
          interruptedRescueStarts.set(key, rescueStartMarker(lines, key))
      }
    } else {
      const retained = new Set(lines.map((line) => lifecycleKey(line.event)))
      interruptedLifecycleKeys.value = new Set(
        [...interruptedLifecycleKeys.value].filter(
          (id) =>
            retained.has(id) &&
            (!interruptedRescueStarts.has(id) ||
              rescueStartMarker(lines, id) === interruptedRescueStarts.get(id))
        )
      )
    }
  },
  { immediate: true, flush: 'sync' }
)

// 场景等待：一条场景行开启等待，直到出现场景号不同的下一条场景行。
const sceneWaits = computed(() => scanSceneWaits(normalizedLines.value))
const sceneWaitKey = computed(() => {
  const active = sceneWaits.value.active
  const line = active ? props.lines[active.index] : null
  return line?.id ?? line
})
const stoppedWaitKey = shallowRef(null)
watch(
  [() => props.running, sceneWaitKey],
  ([running, key]) => {
    if (!running) stoppedWaitKey.value = key
  },
  { immediate: true, flush: 'sync' }
)
const activeWait = computed(() => {
  const active = sceneWaits.value.active
  return active && Number.isFinite(active.at) && sceneWaitKey.value !== stoppedWaitKey.value
    ? active
    : null
})
const waitElapsed = computed(() =>
  activeWait.value ? Math.max(0, nowMs.value - activeWait.value.at) : 0
)
const showWait = computed(
  () => props.running && activeWait.value !== null && waitElapsed.value >= WAIT_DISPLAY_DELAY
)
const liveAnnouncement = ref('')

watch(showWait, (value, previous) => {
  if (value) liveAnnouncement.value = '正在等待场景加载'
  else if (previous) liveAnnouncement.value = '场景等待结束'
})

// 有等待中的场景才需要滚动计时，其他时间不产生额外渲染。
watch(
  () => props.running && activeWait.value !== null,
  (active) => {
    if (active) {
      nowMs.value = Date.now()
      if (nowTimer === null) {
        nowTimer = setInterval(() => {
          nowMs.value = Date.now()
        }, 250)
      }
    } else if (nowTimer !== null) {
      clearInterval(nowTimer)
      nowTimer = null
    }
  },
  { immediate: true }
)

function facilityCopyIndices(node) {
  const anchor = node.getAttribute?.('data-facility-copy')
  return anchor != null
    ? timelineAnalysis.value.facility.byAnchor.get(Number(anchor))?.indices
    : null
}

function recruitmentCopyIndices(node) {
  const key = node.getAttribute?.('data-recruit-copy')
  return key != null ? items.value.find((item) => item.key === key)?.recruitSlot?.indices : null
}

function isCompleteLogText(node, text, range) {
  if (!node) return false
  if (node.textContent === text) return true
  if (!document.createRange) return false
  const time =
    node.getAttribute('data-log-copy-line') != null
      ? node.querySelector?.('.log-stamp__time')
      : null
  if (!time && !range?.compareBoundaryPoints) return false
  const bounds = document.createRange()
  bounds.selectNodeContents(node)
  if (time) bounds.setStart(time, 0)
  return (
    (time && bounds.toString() === text) ||
    (range?.compareBoundaryPoints &&
      range.compareBoundaryPoints(0, bounds) <= 0 &&
      range.compareBoundaryPoints(2, bounds) >= 0)
  )
}

function copyScopedSelection(selection, range, fragment) {
  const selectedRecruitment = Array.from(
    fragment.querySelectorAll?.('[data-recruit-copy]') ?? []
  ).filter((node) => node.getAttribute?.('data-recruit-copy') != null)
  if (
    !selectedRecruitment.length &&
    !timelineAnalysis.value.rescue.groups.size &&
    !props.concise &&
    !collapsedDetails.value.size
  )
    return null
  const element =
    range.commonAncestorContainer.nodeType === 1
      ? range.commonAncestorContainer
      : range.commonAncestorContainer.parentElement
  const inside = element?.closest?.('.log-rescue-block')
  const records = presentedLines.value
  const catalog = new Map(records.map((record) => [record.key, record]))
  const rescueBlocks = new Map(
    blocks.value.filter((block) => block.parent).map((block) => [block.parent.rescue.id, block])
  )
  const ownedKeys = new Set(
    [...rescueBlocks.values()].flatMap((block) => block.sources.map((entry) => entry.key))
  )
  if (
    !selectedRecruitment.length &&
    !inside &&
    !element?.closest?.('[data-facility-copy]') &&
    !fragment.querySelector?.(
      '.log-rescue-block, [data-log-rescue-mirror], [data-facility-copy]'
    ) &&
    !Array.from(fragment.querySelectorAll?.('[data-log-key]') ?? []).some((node) =>
      ownedKeys.has(node.getAttribute('data-log-key'))
    )
  )
    return null
  const liveBlocks = Array.from(output.value.querySelectorAll?.('.log-rescue-block') ?? [])
  if (inside) {
    let complete = selection.toString() === inside.textContent
    if (document.createRange && range.compareBoundaryPoints) {
      const bounds = document.createRange()
      bounds.selectNodeContents(inside)
      complete =
        range.compareBoundaryPoints(0, bounds) <= 0 && range.compareBoundaryPoints(2, bounds) >= 0
    }
    if (complete)
      return rescueBlocks
        .get(inside.getAttribute('data-rescue-id'))
        .sources.map((entry) => entry.text)
        .join('\n')
  }
  const live = new Map(
    Array.from(output.value.querySelectorAll?.('[data-log-key][data-log-source]') ?? [], (node) => [
      node.getAttribute('data-log-key'),
      node
    ])
  )
  const isComplete = (node) =>
    isCompleteLogText(live.get(node.getAttribute('data-log-key')), node.textContent)
  const recruitSummaries = new Map(
    selectedRecruitment.length
      ? Array.from(output.value.querySelectorAll('[data-recruit-copy]'), (node) => [
          node.getAttribute('data-recruit-copy'),
          node.textContent
        ])
      : []
  )
  const partialRecruitSources = new Set(
    selectedRecruitment
      .filter(
        (node) => node.textContent !== recruitSummaries.get(node.getAttribute('data-recruit-copy'))
      )
      .flatMap((node) => (recruitmentCopyIndices(node) ?? []).map((index) => records[index].key))
  )
  const liveDetails = new Map(
    Array.from(output.value.querySelectorAll?.('[data-log-detail-key]') ?? [], (node) => [
      node.getAttribute('data-log-detail-key'),
      node.textContent
    ])
  )
  const selectedHiddenSources = new Set(
    liveDetails.size
      ? Array.from(fragment.querySelectorAll('.log-line--source-only[data-log-key]'), (node) =>
          node.getAttribute('data-log-key')
        )
      : []
  )
  const partialDetails = new Set()
  const partialKeys = new Set(
    Array.from(fragment.querySelectorAll?.('[data-log-rescue-mirror]') ?? [])
      .filter((node) => !isComplete(node))
      .map((node) => node.getAttribute('data-log-rescue-mirror'))
  )
  const full = new Map(),
    pieces = []
  const ignored = [
    'log-date',
    'log-group',
    'log-recruit-slot',
    'log-wait-duration',
    'log-wait-loader',
    'log-detail-toggle',
    'log-history-link',
    'log-sr'
  ]
  const plain = (node) => {
    if (node.nodeType === 3) return node.textContent
    if (node.classList?.contains('log-hidden')) return node.getAttribute('data-log-copy-gap') ?? ''
    if (ignored.some((name) => node.classList?.contains(name))) return ''
    return Array.from(node.childNodes ?? [], plain).join('')
  }
  const add = (key) => {
    if (catalog.has(key) && !partialKeys.has(key)) full.set(key, catalog.get(key))
  }
  const walk = (node) => {
    if (node.nodeType === 3 || node.nodeType === 8) return
    const recruit = node.getAttribute?.('data-recruit-copy')
    if (recruitSummaries.has(recruit)) {
      const indices = recruitmentCopyIndices(node)
      if (node.textContent === recruitSummaries.get(recruit)) {
        for (const index of indices ?? []) add(records[index].key)
      } else if (indices?.length) {
        pieces.push({ index: indices[0], order: pieces.length, text: node.textContent })
      }
      return
    }
    if (ignored.some((name) => node.classList?.contains(name))) return
    const id = node.getAttribute?.('data-rescue-id')
    if (id) {
      const liveBlock = liveBlocks.find((entry) => entry.getAttribute('data-rescue-id') === id)
      if (liveBlock && node.textContent === liveBlock.textContent) {
        for (const source of rescueBlocks.get(id)?.sources ?? []) add(source.key)
        return
      }
    }
    const key = node.getAttribute?.('data-log-rescue-mirror') ?? node.getAttribute?.('data-log-key')
    const detailKey = node.getAttribute?.('data-log-detail-key')
    if (liveDetails.has(detailKey)) {
      if (node.textContent !== liveDetails.get(detailKey)) partialDetails.add(detailKey)
      else if (node.getAttribute('data-log-detail-source') != null) {
        add(detailKey)
        return
      }
      if (partialDetails.has(detailKey) || !selectedHiddenSources.has(detailKey)) {
        pieces.push({
          index: catalog.get(detailKey)?.index ?? 0,
          order: pieces.length,
          text: plain(node)
        })
      }
      return
    }
    const copyIndices = facilityCopyIndices(node)
    if (copyIndices && isComplete(node)) {
      for (const index of copyIndices) add(records[index].key)
      return
    }
    if (catalog.has(key)) {
      if (
        node.classList?.contains('log-line--source-only') &&
        (ownedKeys.has(key) || partialKeys.has(key) || partialRecruitSources.has(key))
      )
        return
      if (isComplete(node)) add(key)
      else pieces.push({ index: catalog.get(key).index, order: pieces.length, text: plain(node) })
      return
    }
    const staticParent = node.getAttribute?.('data-log-static-parent')
    if (staticParent) {
      if (!full.has(staticParent))
        pieces.push({
          index: Number(node.getAttribute('data-log-source-index')),
          order: pieces.length,
          text: plain(node)
        })
      return
    }
    if (node.classList?.contains('log-reset-group') && isComplete(node)) {
      for (const record of node.querySelectorAll?.('[data-log-key]') ?? [])
        add(record.getAttribute('data-log-key'))
      return
    }
    for (const child of node.childNodes ?? []) walk(child)
  }
  walk(fragment)
  const selected = [...full.values()]
    .filter((entry) => !partialDetails.has(entry.key))
    .map(({ index, line }) => ({ index, text: line.text, order: -1 }))
  selected.push(...pieces)
  if (!selected.length) return selection.toString()
  return selected
    .sort((a, b) => a.index - b.index || a.order - b.order)
    .map((entry) => entry.text)
    .filter(Boolean)
    .join('\n')
}

// 复制时还原原始日志：房间标识、隐藏的日期与级别回到原文，日期分隔行不进入剪贴板。
function copySourceText(event) {
  if (props.showAlternateView) return
  const selection = globalThis.getSelection?.()
  if (selection?.rangeCount !== 1 || selection.isCollapsed || !event.clipboardData) return
  const range = selection.getRangeAt(0)
  if (!output.value?.contains?.(range.commonAncestorContainer)) return
  const ancestor = range.commonAncestorContainer
  const element = ancestor.nodeType === 1 ? ancestor : ancestor.parentElement
  const selectedText = selection.toString()
  const complete = element?.closest?.(
    '.log-inventory, .log-line--inventory, .log-reset-group, .log-arrangement, .log-forecast[data-log-source], .log-facility-heading[data-log-source], [data-recruit-copy], [data-log-detail-source], .log-line[data-log-copy-line][data-log-source]'
  )
  if (isCompleteLogText(complete, selectedText, range)) {
    const indices = facilityCopyIndices(complete) ?? recruitmentCopyIndices(complete)
    const source = indices
      ? indices.map((index) => normalizedLines.value[index].text).join('\n')
      : (complete.getAttribute('data-log-source') ??
        complete.getAttribute('data-log-detail-source'))
    event.clipboardData.setData('text/plain', source)
    event.preventDefault()
    return
  }
  if (complete?.getAttribute?.('data-recruit-copy') != null) return
  const selectedRoom = element?.closest?.('[data-room-id]')
  if (selectedRoom && selectedText === selectedRoom.textContent) {
    event.clipboardData.setData(
      'text/plain',
      selectedRoom.getAttribute('data-source-text') ?? selectedRoom.getAttribute('data-room-id')
    )
    event.preventDefault()
    return
  }
  const fragment = range.cloneContents()
  const scopedText = copyScopedSelection(selection, range, fragment)
  if (scopedText !== null) {
    event.clipboardData.setData('text/plain', scopedText)
    event.preventDefault()
    return
  }
  if (!fragment.querySelector('[data-room-id], .log-line, .log-stamp, .log-hidden, .log-date'))
    return

  const selectedDetails = Array.from(fragment.querySelectorAll?.('[data-log-detail-key]') ?? [])
  const selectedSourceKeys = new Set(
    Array.from(fragment.querySelectorAll?.('.log-line--source-only[data-log-key]') ?? [], (node) =>
      node.getAttribute('data-log-key')
    )
  )
  const detailText = new Map(
    Array.from(output.value?.querySelectorAll?.('[data-log-detail-key]') ?? [], (node) => [
      node.getAttribute('data-log-detail-key'),
      node.textContent
    ])
  )
  const partialDetailKeys = new Set(
    selectedDetails
      .filter(
        (node) => node.textContent !== detailText.get(node.getAttribute('data-log-detail-key'))
      )
      .map((node) => node.getAttribute('data-log-detail-key'))
  )
  const ignored = [
    'log-date',
    'log-group',
    'log-recruit-slot',
    'log-facility-heading',
    'log-wait-loader',
    'log-wait-duration',
    'log-detail-toggle',
    'log-history-link',
    'log-sr',
    'log-inventory__toggle'
  ]
  const sourceNodes = new Map(
    Array.from(
      output.value?.querySelectorAll?.(
        '.log-line[data-log-source], .log-reset-group[data-log-source], .log-inventory[data-log-source], .log-arrangement[data-log-source], .log-facility-heading[data-log-source]'
      ) ?? []
    ).map((line) => [line.getAttribute('data-log-key'), line])
  )
  function plainText(node) {
    if (node.nodeType === 3) return node.textContent
    const detailKey = node.getAttribute?.('data-log-detail-key')
    if (detailKey && selectedSourceKeys.has(detailKey) && !partialDetailKeys.has(detailKey))
      return ''
    const detailSource = node.getAttribute?.('data-log-detail-source')
    if (detailSource != null && !partialDetailKeys.has(detailKey)) return `${detailSource}\n`
    if (
      node.classList?.contains('log-line--source-only') &&
      partialDetailKeys.has(node.getAttribute?.('data-log-key'))
    )
      return ''
    const source = sourceNodes.get(node.getAttribute?.('data-log-key'))
    if (isCompleteLogText(source, node.textContent))
      return `${source.getAttribute('data-log-source')}\n`
    if (node.classList?.contains('log-hidden')) return node.getAttribute('data-log-copy-gap') ?? ''
    if (
      ignored.some(
        (name) =>
          node.classList?.contains(name) &&
          !(name === 'log-facility-heading' && node.getAttribute?.('data-log-source'))
      )
    )
      return ''
    const text = Array.from(node.childNodes ?? [], plainText).join('')
    return node.classList?.contains('log-line') || node.classList?.contains('log-facility-heading')
      ? `${text}\n`
      : text
  }

  event.clipboardData.setData('text/plain', plainText(fragment).replace(/\n$/, ''))
  event.preventDefault()
}

onMounted(() => {
  globalThis.document?.addEventListener('copy', copySourceText)
})
watch(
  () => props.concise,
  () => {
    for (const animations of detailAnimations.values()) {
      for (const animation of animations) animation.cancel()
    }
    detailAnimations.clear()
    leavingDetails.value.clear()
    interruptDetailResize()
  },
  { flush: 'pre' }
)
onUpdated(refreshSheen)
onBeforeUnmount(() => {
  globalThis.document?.removeEventListener('copy', copySourceText)
  for (const animations of detailAnimations.values()) {
    for (const animation of animations) animation.cancel()
  }
  detailAnimations.clear()
  if (nowTimer !== null) {
    clearInterval(nowTimer)
    nowTimer = null
  }
})

const rowPresenter = computed(() => createLogRowPresenter(props.operatorNames, props.facilityPlan))
const presentedLines = computed(() => rowPresenter.value.presentLines(normalizedLines.value))

// 只有首次渲染之后真正新增的行才播放淡入；首屏历史和重连回放保持静止。
const seenLineKeys = new Set()
const animatedLineKeys = new Set()
let renderPrimed = false

const timeline = computed(() => {
  const rows = presentedLines.value
  const retainedKeys = new Set(rows.map((entry) => entry.key))
  const freshKeys = [...retainedKeys].filter((key) => !seenLineKeys.has(key))
  for (const key of seenLineKeys) if (!retainedKeys.has(key)) seenLineKeys.delete(key)
  for (const key of animatedLineKeys) if (!retainedKeys.has(key)) animatedLineKeys.delete(key)

  const animateBatch =
    renderPrimed && freshKeys.length > 0 && freshKeys.length <= MAX_BATCH_ANIMATION
  const animateNow = new Set(animateBatch ? freshKeys : [])
  for (const key of freshKeys) {
    seenLineKeys.add(key)
    if (animateNow.has(key)) animatedLineKeys.add(key)
  }
  renderPrimed = true

  const result = buildLogTimeline(timelineAnalysis.value, {
    rows,
    present: rowPresenter.value.present,
    facilityPlan: props.facilityPlan,
    compact: props.compact,
    concise: props.concise,
    running: props.running,
    detailsVisible,
    waitDurations: sceneWaits.value.durations,
    waitingIndex: showWait.value ? activeWait.value?.index : undefined,
    interruptedLifecycleKeys: interruptedLifecycleKeys.value,
    interruptedRecruitmentIds,
    animatedLineKeys
  })
  for (const item of result.items) {
    if (item.sourceOnly) animatedLineKeys.delete(item.key)
  }
  return result
})
const items = computed(() => timeline.value.items)
const blocks = computed(() => timeline.value.blocks)

function rescueHeader(event) {
  if (event.phase === 'queued') return '已生成救急换班任务，等待执行'
  if (event.phase === 'completed') return '救急换班任务已完成'
  if (event.phase === 'failed' && event.detail) return `救急换班任务未完成，${event.detail}`
  return event.inProgress && props.running ? '正在执行救急换班任务' : '救急换班任务尚未完成'
}

function hasForecastDetails(forecast) {
  return Boolean(forecast.rooms.length || forecast.targets.length || forecast.backups.length)
}

function operationSummary(event) {
  if (!['started', 'updated'].includes(event.phase) || (event.inProgress && props.running))
    return event.summary
  return event.type === 'depot-scan' ? '仓库扫描尚未完成' : `${event.label}：心情推算尚未完成`
}

function arrangementPrefix(event) {
  if (event.phase === 'completed') return event.agents.length ? '已安排' : '已确认'
  if (event.inProgress && props.running) return event.agents.length ? '正在安排' : '正在调整'
  return '尚未确认'
}

function stampTitle(stamp) {
  return [stamp.date, stamp.time + stamp.fraction].filter(Boolean).join(' ')
}

function forecastWaitTitle(forecast) {
  return Number.isFinite(forecast.wait_seconds) && forecast.wait_seconds >= 0
    ? `预计休息 ${formatWaitDuration(forecast.wait_seconds * 1000)}（记录时）`
    : undefined
}

function levelName(level) {
  if (level === 'WARN') return 'warning'
  return level ? level.toLowerCase() : 'info'
}

function historyTime(item) {
  const at = normalizedLines.value[item.sourceIndex]?.at
  if (Number.isSafeInteger(at) && at > 0) return at
}

function lineClasses(row) {
  return {
    'log-line--detail': row.detail,
    'log-line--scene': /\bScene \d+:/u.test(row.text),
    'log-line--stamped': Boolean(row.stamp),
    'log-line--bare': !row.stamp,
    'log-line--forecast': Boolean(row.forecast)
  }
}
</script>

<template>
  <div
    ref="output"
    class="log-output"
    :class="{ 'log-output--compact': compact, 'log-output--alternate': showAlternateView }"
  >
    <slot name="header" />
    <div class="log-output__body">
      <svg class="log-sheen-filter" width="0" height="0" aria-hidden="true" focusable="false">
        <defs>
          <filter
            v-for="sheen in sheenFilters"
            :id="sheen.id"
            :key="sheen.id"
            x="0"
            y="0"
            width="1"
            height="1"
            filterUnits="objectBoundingBox"
            primitiveUnits="objectBoundingBox"
            color-interpolation-filters="sRGB"
          >
            <feImage
              v-for="(line, index) in sheen.lines"
              :key="index"
              :href="logSheen"
              :x="line.from"
              y="-2"
              :width="line.width"
              :height="line.height"
              preserveAspectRatio="none"
              :result="`band-${index}`"
            >
              <animate
                v-if="running"
                attributeName="x"
                :begin="sheen.begin"
                :values="line.values"
                :keyTimes="line.keyTimes"
                dur="3.5s"
                repeatCount="indefinite"
              />
              <animate
                v-if="running"
                attributeName="y"
                :begin="sheen.begin"
                :values="line.yValues"
                :keyTimes="line.keyTimes"
                calcMode="discrete"
                dur="3.5s"
                repeatCount="indefinite"
              />
            </feImage>
            <feMerge result="band">
              <feMergeNode v-for="(_, index) in sheen.lines" :key="index" :in="`band-${index}`" />
            </feMerge>
            <feGaussianBlur
              in="band"
              stdDeviation="0.015 0"
              x="0"
              y="0"
              width="1"
              height="1"
              result="soft-band"
            />
            <template v-if="sheen.protectedRegions.length">
              <feFlood
                v-for="(region, index) in sheen.protectedRegions"
                :key="index"
                v-bind="region"
                flood-color="white"
                :result="`protected-${index}`"
              />
              <feMerge result="protected-shape">
                <feMergeNode
                  v-for="(_, index) in sheen.protectedRegions"
                  :key="index"
                  :in="`protected-${index}`"
                />
              </feMerge>
              <feFlood flood-color="white" style="flood-opacity: var(--log-sheen-protection)" />
              <feComposite in2="protected-shape" operator="in" result="protected-mask" />
              <feComposite in="soft-band" in2="protected-mask" operator="out" result="muted-band" />
            </template>
            <feFlood flood-color="white" style="flood-opacity: var(--log-sheen-opacity)" />
            <feComposite
              :in2="sheen.protectedRegions.length ? 'muted-band' : 'soft-band'"
              operator="in"
            />
            <feComposite in2="SourceAlpha" operator="in" />
            <feBlend in2="SourceGraphic" mode="screen" />
          </filter>
        </defs>
      </svg>
      <!-- 当前分组随滚动更新，标题位于正文滚动区之外。 -->
      <div
        v-if="!compact || running || $slots.title || items.some((item) => item.groupBar)"
        class="log-sticky"
        :class="{ 'log-sticky--titled': compact || $slots.title }"
        :aria-hidden="$slots.title ? undefined : true"
      >
        <slot v-if="$slots.title" name="title" />
        <span v-else-if="compact" class="log-sticky__title">{{ running ? '运行日志' : '' }}</span>
        <template v-if="!showAlternateView && stickyGroup">
          <span v-if="!compact && !$slots.title" class="log-sticky__lead" aria-hidden="true"></span>
          <span class="log-sticky__label" aria-hidden="true">{{ stickyGroup }}</span>
          <span v-if="!compact && !$slots.title" class="log-sticky__rule" aria-hidden="true"></span>
        </template>
      </div>
      <n-scrollbar
        class="log-output__scroll"
        :class="{ 'log-output__scroll--hidden': showAlternateView }"
        :style="showAlternateView ? { height: `${hiddenViewportHeight}px` } : undefined"
        :inert="showAlternateView || undefined"
        :x-scrollable="false"
        :container-style="{ overflowX: 'hidden', overscrollBehaviorX: 'none' }"
        @wheel.passive="noteScrollInput"
        @touchmove.passive="noteScrollInput"
        @keydown="noteScrollInput"
        @focusin="noteScrollInput"
        @mousedown.capture="startScrollbarDrag"
      >
        <div class="log-output__lines" role="region" aria-label="实时日志" tabindex="-1">
          <div
            v-for="block in blocks"
            :key="block.key"
            class="log-display-block"
            :class="{ 'log-rescue-block': Boolean(block.parent) }"
            :data-rescue-id="block.parent?.rescue.id"
          >
            <div
              v-if="block.parent"
              class="log-facility-heading log-rescue-parent"
              :class="{
                'log-facility-heading--stamped': block.parent.headingStamp,
                'log-heading--unstamped': !block.parent.headingStamp
              }"
              :data-log-key="block.parent.key"
              :data-log-anchor="block.parent.key"
              :data-log-source="block.parent.row.text"
              :data-log-source-index="block.parent.sourceIndex"
            >
              <span
                v-if="block.parent.headingStamp"
                class="log-stamp"
                :title="stampTitle(block.parent.headingStamp)"
                >{{ block.parent.headingStamp.time }}</span><span
                class="log-rescue-summary log-lifecycle-text"
                :class="{ 'log-lifecycle-active': block.parent.rescue.inProgress && running }"
                :data-rescue-phase="block.parent.rescue.phase"
                >{{ rescueHeader(block.parent.rescue) }}</span
              >
              <button
                type="button"
                class="log-detail-toggle"
                :aria-expanded="detailsExpanded(block.parent.detailKey)"
                :aria-label="detailsExpanded(block.parent.detailKey) ? '收起详情' : '展开详情'"
                :title="detailsExpanded(block.parent.detailKey) ? '收起详情' : '展开详情'"
                @click="toggleDetails(block.parent.detailKey)"
              >
                <DetailChevron aria-hidden="true" />
              </button>
            </div>
            <div :class="{ 'log-rescue-rooms': Boolean(block.parent) }">
              <template v-for="item in block.items" :key="item.key">
                <!-- 日期分隔 -->
                <div v-if="item.date" class="log-date" aria-hidden="true">
                  <span class="log-date__label">{{ item.date }}</span>
                </div>
                <!-- 子系统分组：一条淡淡的隔断线，线上写子系统名 -->
                <div v-else-if="item.groupBar" class="log-group" :data-group="item.groupBar">
                  <span class="log-group__lead" aria-hidden="true"></span>
                  <span class="log-group__label">{{ item.meta.label }}</span>
                  <span class="log-group__rule" aria-hidden="true"></span>
                </div>
                <div
                  v-else-if="item.rescueRoom"
                  class="log-rescue-room"
                  :data-rescue-room="item.rescueRoom.room"
                  :data-rescue-status="item.rescueRoom.status"
                  :data-log-static-parent="item.staticParentKey"
                  :data-log-source-index="item.sourceIndex"
                >
                  <span class="log-forecast__room-label">{{ item.rescueRoom.label }}</span><span
                    class="log-forecast__agents"
                    ><log-operator
                      v-for="(name, index) in item.rescueRoom.agents"
                      :key="index"
                      :name="name || '_'"
                      :size="24"
                      show-name
                      class="log-token log-token--operator"
                    /><span class="log-rescue-state">{{
                      {
                        pending: '待执行',
                        active: '执行中',
                        completed: '已完成',
                        unconfirmed: '未确认'
                      }[item.rescueRoom.status]
                    }}</span></span
                  >
                </div>
                <template v-else-if="item.facilityHeading || item.calculation || item.depot">
                  <div
                    class="log-facility-heading"
                    :data-log-key="item.row ? item.key : undefined"
                    :data-log-anchor="item.row ? item.key : undefined"
                    :data-log-source="item.row?.text"
                    :data-facility-copy="item.facilityCopy"
                    :data-log-rescue-mirror="item.mirror ? item.sourceKey : undefined"
                    :data-log-source-index="item.sourceIndex"
                    :class="{
                      'log-heading--unstamped': !item.headingStamp,
                      'log-facility-heading--stamped': item.row && item.headingStamp,
                      'log-rescue-entry': item.mirror,
                      'log-rescue-history': item.history
                    }"
                    :aria-hidden="item.row ? undefined : true"
                  >
                    <span
                      v-if="item.headingStamp"
                      class="log-stamp"
                      :title="stampTitle(item.headingStamp)"
                      ><span class="log-stamp__time">{{ item.headingStamp.time }}</span></span
                    >
                    <span
                      v-if="item.production || item.orderRead || item.observation"
                      class="log-lifecycle-text"
                      :class="{
                        'log-production-switch': Boolean(item.production),
                        'log-order-read': Boolean(item.orderRead),
                        'log-order-read--routine':
                          item.orderRead?.phase === 'completed' &&
                          item.orderRead.rooms.every((room) => room.status === 'read'),
                        'log-facility-observation': Boolean(item.observation),
                        'log-lifecycle-active':
                          (item.production ?? item.orderRead ?? item.observation).inProgress &&
                          running
                      }"
                      :data-production-phase="item.production?.phase"
                      :data-order-phase="item.orderRead?.phase"
                      :data-observation-phase="item.observation?.phase"
                    >
                      <template
                        v-for="(token, index) in item.productionTokens ??
                        item.orderTokens ??
                        item.observationTokens"
                        :key="index"
                      >
                        <log-operator
                          v-if="token.type === 'operator'"
                          class="log-token log-token--operator"
                          :name="token.name"
                          :size="16"
                          show-name
                        />
                        <log-item-token
                          v-else-if="token.type === 'item'"
                          :token="token"
                          mute-experience
                        />
                        <span
                          v-else
                          class="log-token"
                          :class="{
                            'log-token--room': ['production-room', 'order-room', 'room'].includes(
                              token.type
                            ),
                            'log-order-room': token.type === 'order-room'
                          }"
                          :data-room-id="token.roomId"
                          :data-source-text="token.roomId ? token.text : undefined"
                          >{{ token.text }}</span
                        >
                      </template>
                    </span>
                    <span
                      v-else-if="item.calculation || item.depot"
                      class="log-mood-calculation log-lifecycle-text"
                      :class="{
                        'log-lifecycle-active':
                          (item.calculation ?? item.depot).inProgress && running,
                        'log-depot-scan': Boolean(item.depot)
                      }"
                      :data-calculation-phase="item.calculation?.phase"
                      :data-depot-phase="item.depot?.phase"
                      >{{ operationSummary(item.calculation ?? item.depot) }}</span
                    >
                    <span
                      v-else-if="item.arrangement"
                      class="log-arrangement log-lifecycle-text"
                      :class="{
                        'log-arrangement--active': item.arrangement.inProgress && running,
                        'log-lifecycle-active': item.arrangement.inProgress && running
                      }"
                      :data-arrangement-phase="item.arrangement.phase"
                      :data-log-source="item.row.text"
                      :data-facility-copy="item.facilityCopy"
                      :data-log-rescue-mirror="item.mirror ? item.sourceKey : undefined"
                      :data-log-source-index="item.sourceIndex"
                      :data-log-key="`arrangement:${item.key}`"
                      ><template v-if="item.arrangementTokens"
                        ><template v-for="(token, index) in item.arrangementTokens" :key="index"
                          ><log-operator
                            v-if="token.type === 'operator'"
                            class="log-token log-token--operator"
                            :name="token.name"
                            :size="16"
                            show-name
                          /><span
                            v-else-if="token.type === 'room'"
                            class="log-token--room"
                            :data-room-id="item.arrangement.room"
                            :data-source-text="token.text"
                            >{{ token.text }}</span
                          ><template v-else>{{ token.text }}</template></template
                        ></template
                      ><template v-else
                        >{{ arrangementPrefix(item.arrangement)
                        }}<template v-if="trainingPositions(item.arrangement)"
                          ><template
                            v-for="(position, index) in trainingPositions(item.arrangement)"
                            :key="position.index"
                            ><template v-if="index">、</template
                            ><log-operator
                              class="log-token log-token--operator"
                              :name="position.agent"
                              :size="16"
                              show-name
                            />进驻<span class="log-token--room">{{ item.arrangement.label }}</span
                            >{{ position.index === 0 ? '协助位' : '训练位' }}</template
                          ></template
                        ><template v-else
                          ><template v-for="(name, index) in item.arrangement.agents" :key="index"
                            ><template v-if="index">、</template
                            ><log-operator
                              class="log-token log-token--operator"
                              :name="name"
                              :size="16"
                              show-name /></template
                          ><template v-if="item.arrangement.agents.length">进驻</template
                          ><span class="log-token--room">{{ item.arrangement.label }}</span
                          ><template v-if="!item.arrangement.agents.length"
                            >驻员安排</template
                          ></template
                        ></template
                      ><template v-if="item.idleNames?.length"
                        >，<template v-for="(name, index) in item.idleNames" :key="name"
                          ><template v-if="index">、</template
                          ><log-operator
                            class="log-token log-token--operator"
                            :name="name"
                            :size="16"
                            show-name /></template
                        >转为空闲</template
                      ></span
                    >
                    <span v-else class="log-heading__title">{{ item.facilityHeading }}</span>
                    <button
                      v-if="item.expandable"
                      type="button"
                      class="log-detail-toggle"
                      :aria-expanded="detailsExpanded(item.detailKey)"
                      :aria-label="detailsExpanded(item.detailKey) ? '收起详情' : '展开详情'"
                      :title="detailsExpanded(item.detailKey) ? '收起详情' : '展开详情'"
                      @click="toggleDetails(item.detailKey)"
                    >
                      <DetailChevron aria-hidden="true" />
                    </button>
                  </div>
                </template>
                <div
                  v-else-if="item.recruitSlot"
                  class="log-recruit-slot"
                  :class="{
                    'log-recruit-slot--stamped': item.headingStamp,
                    'log-heading--unstamped': !item.headingStamp
                  }"
                  :data-log-key="item.key"
                  :data-log-anchor="item.key"
                  :data-recruit-copy="item.key"
                  :data-recruit-phase="item.recruitSlot.phase"
                >
                  <span
                    v-if="item.headingStamp"
                    class="log-stamp"
                    :title="stampTitle(item.headingStamp)"
                    ><span class="log-stamp__time">{{ item.headingStamp.time }}</span></span
                  ><span
                    class="log-recruit-slot__lead log-lifecycle-text"
                    :class="{ 'log-lifecycle-active': item.recruitActive }"
                    ><span class="log-heading__title">{{ item.recruitSlot.slot }}号公招位</span
                    ><span v-if="item.recruitStatus" class="log-recruit-slot__summary">
                      · {{ item.recruitStatus }}</span
                    ><span v-if="item.recruitSlot.operator" class="log-recruit-slot__summary">
                      · 获得
                      <log-operator
                        class="log-token--operator"
                        :name="item.recruitSlot.operator"
                        :size="16"
                        show-name
                      /> </span
                    ><span
                      v-if="item.recruitSlot.decision || item.expandable"
                      class="log-recruit-slot__summary"
                      ><template v-if="item.recruitSlot.decision">
                        ·
                        {{
                          compact && item.recruitSlot.decision === '招募券不足，跳过'
                            ? '券不足，跳过'
                            : item.recruitSlot.decision
                        }}</template
                      ><button
                        v-if="item.expandable"
                        type="button"
                        class="log-detail-toggle"
                        :aria-expanded="detailsExpanded(item.detailKey)"
                        :aria-label="detailsExpanded(item.detailKey) ? '收起详情' : '展开详情'"
                        :title="detailsExpanded(item.detailKey) ? '收起详情' : '展开详情'"
                        @click="toggleDetails(item.detailKey)"
                      >
                        <DetailChevron aria-hidden="true" />
                      </button> </span
                  ></span>
                </div>
                <div
                  v-else-if="item.sourceOnly"
                  class="log-line log-line--source-only"
                  :data-log-key="item.key"
                  :data-log-source="item.row.text"
                  :data-log-rescue-mirror="item.mirror ? item.sourceKey : undefined"
                  :data-log-source-index="item.sourceIndex"
                  aria-hidden="true"
                >
                  {{ item.row.text }}
                </div>
                <!-- 日志行 -->
                <div
                  v-else-if="item.resetRows"
                  class="log-reset-group"
                  :class="[lineClasses(item.row), { 'log-line--nested': item.nested }]"
                  :data-log-key="item.key"
                  :data-log-source="item.source"
                  :data-log-detail-owner="item.detailOwner"
                >
                  <span
                    v-if="item.resetRows[0].row.stamp"
                    class="log-stamp"
                    :title="stampTitle(item.resetRows[0].row.stamp)"
                    >{{ item.resetRows[0].row.stamp.time }}</span
                  >
                  <span>重设 </span
                  ><template v-for="(record, index) in item.resetRows" :key="record.key"
                    ><span v-if="index">、</span
                    ><span
                      class="log-line log-reset-record"
                      :data-log-key="record.key"
                      :data-log-anchor="record.key"
                      :data-log-source="record.row.text"
                      :data-log-level="record.row.level"
                      :title="record.row.stamp ? stampTitle(record.row.stamp) : undefined"
                      ><log-operator
                        class="log-token log-token--operator"
                        :name="record.resetName"
                        show-name
                        :size="16" /></span></template
                  ><span> 至空闲</span>
                </div>
                <div
                  v-else-if="item.row"
                  class="log-line"
                  :class="[
                    lineClasses(item.row),
                    {
                      'log-line--enter': item.animate,
                      'log-line--nested': item.nested,
                      'log-line--inventory': Boolean(item.inventory),
                      'log-rescue-entry': item.mirror,
                      'log-rescue-history': item.history
                    }
                  ]"
                  :data-log-level="item.row.level"
                  :data-log-key="item.key"
                  :data-log-anchor="item.key"
                  :data-log-source="item.row.text"
                  :data-log-rescue-mirror="item.mirror ? item.sourceKey : undefined"
                  :data-log-source-index="item.sourceIndex"
                  :data-log-detail-owner="item.detailOwner"
                  :data-log-copy-line="!item.mirror ? true : undefined"
                >
                  <template v-if="item.parts">
                    <span class="log-stamp" :title="stampTitle(item.row.stamp)"
                      ><span class="log-hidden">{{ item.parts.head }}</span
                      ><span class="log-stamp__time">{{ item.parts.time }}</span
                      ><span class="log-hidden">{{ item.parts.tail }}</span></span
                    ><span
                      v-if="item.parts.quiet"
                      class="log-hidden"
                      :data-log-copy-gap="item.parts.quietGap"
                      >{{ item.parts.quiet }}</span
                    ><span
                      v-if="item.parts.label"
                      class="log-level"
                      :class="`log-level--${levelName(item.parts.label)}`"
                      >{{ item.parts.label }}</span
                    ><template v-if="item.parts.gap">{{ item.parts.gap }}</template>
                  </template>
                  <span v-if="item.hiddenPrefix" class="log-hidden">{{ item.hiddenPrefix }}</span>
                  <log-inventory
                    v-if="item.inventory"
                    :items="item.inventory"
                    :source="item.row.text"
                    :data-log-key="`inventory:${item.key}`"
                    @resize="resizeInventory"
                  />
                  <span
                    v-else-if="item.row.forecast"
                    class="log-forecast"
                    :data-log-source="item.row.text"
                  >
                    <span
                      class="log-forecast__header"
                      :title="forecastWaitTitle(item.row.forecast)"
                    >
                      <template v-for="(token, index) in item.forecastTokens" :key="index">
                        <log-operator
                          v-if="token.type === 'operator'"
                          class="log-token log-token--operator"
                          :name="token.name"
                          show-name
                          :size="16"
                        />
                        <task-action-subjects
                          v-else-if="token.type === 'group'"
                          :actions="[{ kind: 'group', subject: token.text, action: '' }]"
                          :facility-plan="facilityPlan"
                          :size="16"
                        />
                        <log-item-token
                          v-else-if="token.type === 'item' || token.type === 'order-operator'"
                          :token="token"
                          mute-experience
                        />
                        <span v-else class="log-token" :class="`log-token--${token.type}`">{{
                          token.text
                        }}</span>
                      </template>
                      <template v-if="item.row.forecast.actionPrefix">
                        <task-action-subjects
                          :actions="item.row.forecast.actions"
                          :facility-plan="facilityPlan"
                          :size="24"
                          show-names
                          inline-single-operator
                        />
                        <template
                          v-for="(token, index) in item.row.forecast.actionSuffix"
                          :key="index"
                        >
                          <task-action-subjects
                            v-if="token.type === 'group'"
                            :actions="[{ kind: 'group', subject: token.text, action: '' }]"
                            :facility-plan="facilityPlan"
                            :size="16"
                          />
                          <log-item-token
                            v-else-if="token.type === 'item' || token.type === 'order-operator'"
                            :token="token"
                          />
                          <span v-else class="log-token" :class="`log-token--${token.type}`">{{
                            token.text
                          }}</span>
                        </template>
                      </template>
                    </span>
                    <button
                      v-if="hasForecastDetails(item.row.forecast)"
                      type="button"
                      class="log-detail-toggle"
                      :aria-expanded="detailsExpanded(item.key)"
                      :aria-label="detailsExpanded(item.key) ? '收起详情' : '展开详情'"
                      :title="detailsExpanded(item.key) ? '收起详情' : '展开详情'"
                      @click="toggleDetails(item.key, true)"
                    >
                      <DetailChevron aria-hidden="true" />
                    </button>
                    <span
                      v-if="detailsVisible(item.key) && hasForecastDetails(item.row.forecast)"
                      class="log-forecast__details"
                      :data-log-detail-owner="item.key"
                    >
                      <span v-if="item.row.forecast.activated" class="log-forecast__backups"
                        >预计激活的副表：<template
                          v-for="(backup, index) in item.row.forecast.backups.filter(
                            (entry) => entry.active
                          )"
                          :key="backup.name"
                          ><template v-if="index">、</template
                          ><span class="log-token--backup">{{ backup.name }}</span></template
                        ></span
                      >
                      <span v-if="item.row.forecast.deactivated" class="log-forecast__backups"
                        >预计停用的副表：<template
                          v-for="(backup, index) in item.row.forecast.backups.filter(
                            (entry) => !entry.active
                          )"
                          :key="backup.name"
                          ><template v-if="index">、</template
                          ><span class="log-token--backup">{{ backup.name }}</span></template
                        ></span
                      >
                      <span
                        v-if="item.row.forecast.rooms.length"
                        class="log-forecast__rooms"
                        :class="{
                          'log-forecast__rooms--aligned': item.row.forecast.rooms.length >= 2
                        }"
                      >
                        <span
                          v-for="room in item.row.forecast.rooms"
                          :key="room.id"
                          class="log-forecast__room"
                        >
                          <span
                            class="log-forecast__room-label"
                            :data-room-id="room.id"
                            :data-source-text="room.label"
                            :title="room.id"
                            >{{ room.label }}</span
                          >
                          <span class="log-forecast__agents">
                            <log-operator
                              v-for="(name, index) in room.agents"
                              :key="index"
                              class="log-token log-token--operator"
                              :name="name || '_'"
                              show-name
                              :size="24"
                            />
                          </span>
                        </span>
                      </span>
                      <span
                        v-else-if="item.row.forecast.targets.length"
                        class="log-forecast__targets"
                      >
                        <template v-for="(room, index) in item.row.forecast.targets" :key="room.id"
                          ><template v-if="index">、</template
                          ><span
                            class="log-forecast__room-label"
                            :data-room-id="room.id"
                            :data-source-text="room.label"
                            :title="room.id"
                            >{{ room.label }}</span
                          ></template
                        >
                      </span>
                    </span>
                  </span>
                  <span v-else class="log-message log-lifecycle-text"
                    ><template v-for="(token, index) in item.displayTokens" :key="index">
                      <log-operator
                        v-if="token.type === 'operator'"
                        class="log-token log-token--operator"
                        :name="token.name"
                        show-name
                        :size="16"
                      />
                      <task-action-subjects
                        v-else-if="token.type === 'group'"
                        :actions="[{ kind: 'group', subject: token.text, action: '' }]"
                        :facility-plan="facilityPlan"
                        :size="16"
                      />
                      <log-stage
                        v-else-if="token.type === 'stage'"
                        :code="token.code"
                        :drops="token.drops"
                      />
                      <span
                        v-else-if="token.type === 'inventory-change'"
                        class="log-token log-token--inventory-change"
                        :data-change-direction="token.delta > 0 ? 'increase' : 'decrease'"
                        ><img
                          :src="token.icon"
                          width="16"
                          height="16"
                          alt=""
                          aria-hidden="true"
                          @error="$event.target.hidden = true"
                        />{{ token.text }}</span
                      >
                      <log-item-token
                        v-else-if="token.type === 'item' || token.type === 'order-operator'"
                        :token="token"
                        mute-experience
                      />
                      <span
                        v-else-if="token.type === 'recruit-combinations'"
                        class="log-token log-recruit-tags log-recruit-combinations"
                        ><template
                          v-for="(choice, choiceIndex) in token.combinations"
                          :key="choiceIndex"
                          ><template v-if="choiceIndex">；</template
                          ><span
                            class="log-recruit-combinations__group"
                            :data-recruit-rarity="choice.rarity"
                            :title="`${choice.rarity}星标签组合`"
                            >{{ choice.tags.join('＋') }}</span
                          ></template
                        ></span
                      >
                      <span
                        v-else-if="token.type === 'recruit-tags'"
                        class="log-token log-recruit-tags"
                        :data-recruit-rarity="token.rarity ?? undefined"
                        :title="token.rarity ? `${token.rarity}星标签组合` : undefined"
                        ><template v-for="(tag, tagIndex) in token.tags" :key="tag"
                          ><template v-if="tagIndex">、</template
                          ><span class="log-recruit-tags__name">{{ tag }}</span></template
                        ></span
                      >
                      <span
                        v-else
                        class="log-token"
                        :class="[
                          `log-token--${token.type}`,
                          token.type === 'level'
                            ? `log-token--${levelName(item.row.level)}`
                            : undefined
                        ]"
                        :data-room-id="
                          token.type === 'room' ? (token.roomId ?? token.text) : undefined
                        "
                        :data-recruit-rarity="token.rarity ?? undefined"
                        :data-source-text="token.type === 'room' ? token.text : undefined"
                        :title="token.type === 'room' ? (token.roomId ?? token.text) : undefined"
                        >{{
                          token.type === 'room'
                            ? (token.roomLabel ??
                              formatFacilityLabel(token.roomId ?? token.text, facilityPlan))
                            : token.text
                        }}</span
                      >
                    </template></span
                  >
                  <!-- 等待结束后把时长贴回开启等待的那条场景行；纯文本，不打徽章。 -->
                  <span v-if="item.sceneWaiting" class="log-wait-loader" aria-hidden="true">
                    <span class="log-wait-loader__paint" />
                  </span>
                  <span
                    v-else-if="item.waitMs !== null"
                    class="log-wait-duration"
                    title="场景等待时长"
                    >等待 {{ formatWaitDuration(item.waitMs) }}</span
                  >
                  <slot
                    v-if="
                      $slots.history &&
                      ['WARN', 'WARNING', 'ERROR', 'CRITICAL'].includes(item.row.level) &&
                      historyTime(item)
                    "
                    name="history"
                    :at="historyTime(item)"
                  />
                </div>
                <div
                  v-if="item.lifecycleDetail"
                  class="log-lifecycle-detail"
                  :class="
                    item.lifecycleDetail.preview
                      ? [
                          'log-live-detail',
                          'log-line--nested',
                          lineClasses(item.lifecycleDetail.row)
                        ]
                      : 'log-line'
                  "
                  :data-log-detail-key="item.lifecycleDetail.key"
                  :data-log-detail-source="item.lifecycleDetail.row?.text"
                  :data-log-level="item.lifecycleDetail.row?.level"
                >
                  <span
                    v-if="item.lifecycleDetail.parts"
                    class="log-stamp"
                    :title="stampTitle(item.lifecycleDetail.row.stamp)"
                    >{{ item.lifecycleDetail.parts.time }}</span
                  >
                  <template v-for="(token, index) in item.lifecycleDetail.tokens" :key="index">
                    <log-operator
                      v-if="token.type === 'operator'"
                      class="log-token log-token--operator"
                      :name="token.name"
                      :size="16"
                      show-name
                    />
                    <log-item-token v-else-if="token.type === 'item'" :token="token" />
                    <span v-else>{{ token.text }}</span>
                  </template>
                </div>
              </template>
            </div>
          </div>
          <p class="log-sr" role="status" aria-live="polite">{{ liveAnnouncement }}</p>
        </div>
      </n-scrollbar>
      <jump-to-latest-button
        v-if="showJumpToLatest && !showAlternateView"
        class="log-jump-latest"
        @click="returnToLatest"
      />
      <div v-if="showAlternateView" class="log-output__alternate">
        <slot name="alternate" />
      </div>
    </div>
  </div>
</template>

<style scoped>
.log-output {
  --log-inset: var(--log-row-inset, 4px);
  --log-gutter: 66px;
  --log-scroll-padding: 12px;
  --log-detail-toggle-width: 18px;
  --log-detail-toggle-gap: 5px;
  --log-muted-ink: #8a9099;
  --log-detail-ink: #7d838c;
  --log-time-ink: #2f7fd8;
  --log-room-ink: #13834a;
  --log-operator-ink: #c43c5a;
  --log-warning-ink: #b96f00;
  --log-error-ink: #cc2f4e;
  --log-warning-tint: rgb(240 160 32 / 12%);
  --log-error-tint: rgb(208 48 80 / 11%);
  --log-hover-tint: rgb(128 128 128 / 7%);
  --log-ink: var(--mower-text, #333639);
  --log-group-rule: color-mix(in srgb, var(--log-ink) 16%, transparent);
  --log-body-weight: 400;
  --log-label-weight: 600;
  --log-alert-weight: 700;
  --log-sheen-opacity: 0.75;
  --log-sheen-protection: 0.15;
  display: flex;
  flex-direction: column;
  height: 100%;
  min-height: 0;
  overflow: hidden;
  color: var(--log-ink);
}

.log-output--compact {
  --log-gutter: var(--log-compact-time-column, 64px);
}

.log-output__body {
  position: relative;
  display: grid;
  flex: 1 1 0;
  grid-template: auto minmax(0, 1fr) / minmax(0, 1fr);
  min-height: 0;
}

.log-output--alternate .log-output__body {
  flex-basis: auto;
}

.log-jump-latest {
  z-index: 2;
}

.log-jump-latest:focus-visible {
  outline: 2px solid var(--lg-focus);
  outline-offset: 2px;
}

.log-output--compact .log-jump-latest {
  min-height: 44px;
}

.log-output__body > :deep(.log-output__scroll),
.log-output__alternate {
  grid-area: 2 / 1;
  min-width: 0;
  min-height: 0;
}

.log-output__body > :deep(.log-output__scroll--hidden) {
  position: absolute;
  inset-inline: 0;
  inset-block-start: 0;
  visibility: hidden;
}

.log-output__lines {
  overflow-anchor: none;
  min-width: 0;
  /* 为叠加式滚动条永久留出空间，显示或隐藏时不改变换行。 */
  padding-inline: calc(var(--log-inset) - 4px) var(--log-scroll-padding);
  padding-bottom: 4px;
  font-family: var(--log-mono-font, monospace);
  font-size: 13px;
  font-weight: var(--log-body-weight);
  user-select: text;
}

.log-sticky {
  grid-area: 1 / 1;
  background: transparent;
  position: relative;
  z-index: 1;
  display: flex;
  flex: none;
  align-items: flex-start;
  gap: 8px;
  height: 18px;
  margin: 0 4px;
  color: var(--log-ink);
  font-size: 11px;
  line-height: 14px;
  font-weight: var(--log-label-weight);
  letter-spacing: 0.06em;
  pointer-events: none;
  user-select: none;
}

.log-sticky__label {
  flex: none;
  max-width: 50%;
  color: var(--log-detail-ink);
  font-weight: 400;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.log-sticky__lead {
  flex: 0 0 calc(var(--log-gutter) - 8px);
}

.log-sticky__rule {
  flex: 1 1 auto;
}

.log-sticky__lead,
.log-sticky__rule {
  height: var(--log-hairline, 1px);
  margin-block-start: 7px;
  background: var(--log-group-rule);
}

@media (prefers-reduced-motion: no-preference) {
  .log-sticky__lead,
  .log-sticky__label,
  .log-sticky__rule {
    animation: log-sticky-in 120ms ease-out;
  }
}

@keyframes log-sticky-in {
  from {
    opacity: 0;
  }
}

.log-line,
.log-live-detail {
  position: relative;
  min-height: 1.6em;
  padding-inline: 4px;
  border-radius: 4px;
  line-height: 1.6;
  white-space: pre-wrap;
  overflow-wrap: anywhere;
}

.log-reset-group {
  line-height: 1.6;
  padding-inline: 4px;
  overflow-wrap: anywhere;
}
.log-reset-record {
  display: inline;
  padding: 0;
  min-height: 0;
}

.log-forecast {
  display: inline;
  box-sizing: border-box;
  text-indent: 0;
  vertical-align: top;
}

.log-detail-toggle {
  --log-detail-toggle-height: 16px;
  display: inline-grid;
  place-items: center;
  inline-size: var(--log-detail-toggle-width);
  block-size: var(--log-detail-toggle-height);
  margin-inline-start: var(--log-detail-toggle-gap);
  padding: 0;
  border: 0;
  border-radius: 3px;
  background: none;
  color: var(--log-muted-ink);
  cursor: pointer;
  font-size: inherit;
  vertical-align: calc(0.4em - var(--log-detail-toggle-height) / 2);
  user-select: none;
  touch-action: manipulation;
}
/* 把按钮的宽度留在行尾，避免它被单独挤到下一行。 */
.log-facility-heading:has(> .log-detail-toggle),
.log-line:has(> .log-forecast > .log-detail-toggle) {
  padding-inline-end: calc(var(--log-detail-toggle-width) + var(--log-detail-toggle-gap));
}
.log-facility-heading > .log-detail-toggle,
.log-forecast > .log-detail-toggle {
  margin-inline-end: calc(-1 * (var(--log-detail-toggle-width) + var(--log-detail-toggle-gap)));
}
@media (hover: hover) and (pointer: fine) {
  .log-detail-toggle:hover {
    color: var(--log-ink);
    background: var(--log-hover-tint);
  }
}

.log-detail-toggle:active {
  color: var(--log-ink);
  background: color-mix(in srgb, var(--log-ink) 12%, transparent);
  transition-duration: var(--log-press-time, 60ms);
}
.log-detail-toggle:focus-visible {
  outline: 1px solid currentColor;
}
.log-detail-toggle svg {
  width: 14px;
  height: 14px;
  transform: rotate(-90deg);
}
.log-detail-toggle[aria-expanded='true'] svg {
  transform: none;
}
@media (prefers-reduced-motion: no-preference) {
  .log-detail-toggle {
    transition:
      background-color var(--log-feedback-time, 120ms) var(--log-feedback-ease, ease-out),
      color var(--log-feedback-time, 120ms) var(--log-feedback-ease, ease-out);
  }

  .log-detail-toggle svg {
    transition: transform var(--log-feedback-time, 120ms) var(--log-feedback-ease, ease-out);
  }
}
.log-forecast__details {
  display: block;
  margin-top: 4px;
  padding: 3px 0 4px 12px;
  border-inline-start: var(--log-hairline, 1px) solid
    color-mix(in srgb, var(--log-ink) 13%, transparent);
}

.log-forecast__details > :first-child {
  margin-top: 0;
}

.log-forecast__backups + .log-forecast__rooms {
  margin-top: 8px;
}

.log-forecast__header,
.log-forecast__backups,
.log-forecast__targets {
  display: block;
}

.log-forecast__header {
  display: inline;
}

.log-token--backup {
  color: var(--log-room-ink);
}
.log-recruit-slot,
.log-facility-heading {
  margin: 5px 4px 1px;
  color: var(--log-ink);
  font-size: inherit;
  font-weight: var(--log-label-weight);
}
.log-facility-heading {
  color: var(--log-room-ink);
}
.log-facility-heading:not(.log-rescue-parent) {
  margin-block: 0;
  min-height: 1.6em;
  line-height: 1.6;
}
.log-facility-heading--stamped,
.log-recruit-slot--stamped {
  padding-inline-start: var(--log-gutter);
  text-indent: calc(-1 * var(--log-gutter));
  overflow-wrap: anywhere;
}
.log-heading--unstamped {
  padding-inline-start: var(--log-gutter);
}
.log-recruit-slot .log-stamp,
.log-facility-heading .log-stamp {
  font-weight: 400;
}

.log-recruit-slot__summary {
  display: inline-block;
  font-weight: 400;
  text-indent: 0;
  white-space: nowrap;
}

.log-output--compact .log-recruit-slot__summary {
  font-size: 12px;
}

.log-forecast__backups,
.log-forecast__targets {
  margin-top: 5px;
}

.log-forecast__backups {
  color: var(--log-ink);
  font-size: 12px;
}

.log-forecast__rooms {
  display: grid;
  grid-template-columns: fit-content(40%) minmax(0, 1fr);
  gap: 10px 8px;
}

.log-forecast__room {
  display: grid;
  grid-column: 1 / -1;
  grid-template-columns: subgrid;
  gap: 4px 8px;
  align-items: start;
}

.log-forecast__room-label {
  display: inline-flex;
  align-items: center;
  min-height: 24px;
  line-height: 1;
  color: var(--log-room-ink);
  flex: 0 1 auto;
  min-width: 0;
  max-width: 100%;
  white-space: normal;
  overflow-wrap: anywhere;
}

.log-forecast__agents {
  display: flex;
  flex-wrap: wrap;
  gap: 4px 12px;
  align-items: center;
  min-width: 0;
  flex: 1 1 10em;
}

.log-forecast__agents :deep(.log-operator) {
  display: inline-flex;
  align-items: center;
  min-height: 24px;
  line-height: 1;
}

.log-forecast__rooms--aligned .log-forecast__room > .log-forecast__agents {
  display: grid;
  grid-template-columns: repeat(auto-fill, min(100%, calc(28px + 7ch)));
  column-gap: 8px;
  justify-items: start;
}

.log-forecast__room > .log-forecast__agents :deep(.log-operator) {
  max-width: 100%;
  white-space: normal;
  overflow-wrap: anywhere;
}

.log-forecast__room > .log-forecast__agents :deep(.log-operator__avatar) {
  flex-shrink: 0;
}

/* 新日志只做极短的透明度淡入，不做位移，避免与自动滚动叠加成闪烁。 */
.log-line--enter {
  animation: log-line-in 180ms ease-out;
}

@keyframes log-line-in {
  from {
    opacity: 0;
  }
}

/* 子系统分组：一条淡淡的隔断线，文字对齐正文列（时间之后）。 */
.log-group {
  display: flex;
  align-items: center;
  gap: 8px;
  height: 20px;
  margin: 10px 4px 0;
  color: var(--log-muted-ink);
  font-size: 11px;
  font-weight: var(--log-label-weight);
  letter-spacing: 0.06em;
  user-select: none;
}

.log-group__lead {
  flex: 0 0 calc(var(--log-gutter) - 8px);
}

.log-group__label {
  flex: none;
  max-width: 50%;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.log-group__rule {
  flex: 1 1 auto;
}

.log-group__lead,
.log-group__rule {
  height: var(--log-hairline, 1px);
  background: var(--log-group-rule);
}

.log-sticky--titled {
  align-items: baseline;
  gap: 0;
  height: auto;
  min-height: 22px;
  margin-inline: var(--log-inset) var(--log-scroll-padding);
  padding-block: 3px 4px;
  letter-spacing: normal;
}

.log-sticky__title {
  flex: 0 0 var(--log-gutter);
  font-size: 12px;
  white-space: nowrap;
}

.log-sticky--titled .log-sticky__label {
  flex: 0 1 auto;
}

.log-output--compact .log-group {
  height: 16px;
  margin-block-start: 6px;
}

.log-wait-loader {
  position: relative;
  top: -1px;
  display: inline-block;
  width: 16px;
  height: 16px;
  margin-inline-start: 8px;
  background: transparent;
  color: var(--log-detail-ink);
  vertical-align: middle;
  user-select: none;
}
.log-wait-loader__paint {
  position: absolute;
  top: 50%;
  left: 50%;
  width: 36px;
  height: 36px;
  overflow: hidden;
  pointer-events: none;
  transform: translate(-50%, -50%);
}
.log-wait-loader__paint::before,
.log-wait-loader__paint::after {
  content: '';
  position: absolute;
  top: 50%;
  left: 50%;
  box-sizing: border-box;
  width: 8px;
  height: 8px;
  border: 1px solid currentColor;
  transform: translate(-50%, -50%) rotate(45deg);
}
.log-wait-loader__paint::after {
  width: 24px;
  height: 24px;
  animation: log-wait-ripple 1.2s ease-out infinite;
}
@keyframes log-wait-ripple {
  from {
    opacity: 0.8;
    transform: translate(-50%, -50%) rotate(45deg) scale(0.3333);
  }
  to {
    opacity: 0;
    transform: translate(-50%, -50%) rotate(45deg) scale(1);
  }
}
@media (prefers-reduced-motion: reduce) {
  .log-wait-loader {
    display: none;
  }

  .log-wait-loader__paint::after {
    animation: none;
  }
}
/* 等待结束后写在场景行尾部的纯文本时长。 */
.log-wait-duration {
  margin-inline-start: 8px;
  color: var(--log-muted-ink);
  font-size: 11px;
  font-variant-numeric: tabular-nums;
  white-space: nowrap;
  user-select: none;
}

.log-sr {
  position: absolute;
  width: 1px;
  height: 1px;
  overflow: hidden;
  clip-path: inset(50%);
  white-space: nowrap;
}

@media (prefers-reduced-motion: reduce) {
  .log-line--enter {
    animation: none;
  }
}

/* 时间单独占一列，换行后的内容与首行消息对齐。 */
.log-line--stamped {
  padding-inline-start: calc(4px + var(--log-gutter));
  text-indent: calc(-1 * var(--log-gutter));
}

.log-line--bare {
  padding-inline-start: calc(4px + var(--log-gutter));
}

.log-line--nested {
  padding-inline-start: 16px;
}
.log-line--nested.log-line--stamped {
  padding-inline-start: calc(16px + var(--log-gutter));
  text-indent: calc(-1 * (var(--log-gutter) + 12px));
}
.log-line--nested.log-line--bare {
  padding-inline-start: calc(16px + var(--log-gutter));
}
.log-line--nested .log-stamp {
  width: calc(var(--log-gutter) + 12px);
}

.log-stamp {
  display: inline-block;
  width: var(--log-gutter);
  color: var(--log-muted-ink);
  font-size: 12px;
  font-variant-numeric: tabular-nums;
  text-indent: 0;
  vertical-align: baseline;
  white-space: nowrap;
}

.log-output--compact .log-stamp {
  font-size: 11px;
}

/* 隐藏片段保持行内，复制和读屏仍得到原文，不会在时间和消息之间插入换行。 */
.log-hidden {
  display: inline-block;
  width: 1px;
  height: 1px;
  margin-inline-end: -1px;
  overflow: hidden;
  clip-path: inset(50%);
  vertical-align: baseline;
  white-space: pre;
}

.log-level {
  margin-inline-end: 2px;
  font-size: 11px;
  font-weight: var(--log-alert-weight);
  letter-spacing: 0.04em;
}

.log-level--warning {
  color: var(--log-warning-ink);
}

.log-level--error,
.log-level--critical {
  color: var(--log-error-ink);
}

.log-level--debug {
  color: var(--log-muted-ink);
}

.log-line[data-log-level='WARNING'] {
  background: linear-gradient(90deg, var(--log-warning-tint), transparent 72%);
}

.log-line:is([data-log-level='ERROR'], [data-log-level='CRITICAL']) {
  background: linear-gradient(90deg, var(--log-error-tint), transparent 72%);
}

@media (hover: hover) and (pointer: fine) {
  .log-line:hover {
    background-color: var(--log-hover-tint);
  }
}

.log-date {
  display: flex;
  align-items: center;
  gap: 10px;
  margin: 10px 4px 4px;
  color: var(--log-muted-ink);
  font-size: 11px;
  letter-spacing: 0.08em;
  user-select: none;
}

.log-date:first-child {
  margin-top: 2px;
}

.log-date::after {
  content: '';
  flex: 1 1 auto;
  height: var(--log-hairline, 1px);
  background: linear-gradient(
    90deg,
    color-mix(in srgb, currentColor 35%, transparent),
    transparent
  );
}

.log-token--date,
.log-token--time {
  color: var(--log-time-ink);
  font-variant-numeric: tabular-nums;
}

.log-token--room {
  color: var(--log-room-ink);
  font-weight: var(--log-label-weight);
  white-space: nowrap;
}

.log-output--compact
  :is(
    .log-token--room,
    .log-token--item,
    .log-recruit-slot__summary,
    .log-recruit-tags__name,
    .log-recruit-combinations__group
  ) {
  display: inline-block;
  max-width: 100%;
  text-indent: 0;
  white-space: normal;
  overflow-wrap: anywhere;
}

.log-token--group {
  color: var(--log-room-ink);
  font-weight: var(--log-label-weight);
}

.log-arrangement,
.log-facility-observation,
.log-production-switch,
.log-order-read,
.log-rescue-summary {
  color: var(--log-ink);
  font-weight: var(--log-body-weight);
}
.log-mood-calculation,
.log-order-read--routine {
  color: var(--log-detail-ink);
  font-weight: 400;
}
.log-depot-scan[data-depot-phase='completed'] {
  color: var(--log-ink);
}
.log-arrangement :deep(.log-operator__avatar) {
  vertical-align: calc(0.4em - var(--log-operator-size) / 2);
}
.log-order-room {
  display: inline-block;
  max-width: 100%;
  text-indent: 0;
  overflow-wrap: anywhere;
}
.log-lifecycle-detail {
  padding-inline-start: calc(16px + var(--log-gutter));
  color: var(--log-detail-ink);
  font-weight: 400;
}
.log-live-detail {
  contain: inline-size;
  color: var(--log-ink);
  line-height: 1.6;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.log-lifecycle-text {
  transition: color 180ms ease-out;
}
.log-lifecycle-active {
  color: var(--log-ink);
}
.log-sheen-filter {
  position: absolute;
  pointer-events: none;
}
@media (prefers-reduced-motion: no-preference) {
  .log-lifecycle-active {
    filter: var(--log-sheen-filter, none);
  }
}
.log-display-block {
  display: contents;
}
.log-rescue-block {
  display: block;
  min-width: 0;
}
.log-rescue-rooms {
  display: grid;
  grid-template-columns: fit-content(40%) minmax(0, 1fr);
  column-gap: 8px;
  margin-inline-start: calc(var(--log-gutter) + 16px);
}
.log-rescue-rooms > * {
  grid-column: 1 / -1;
  min-width: 0;
}
.log-rescue-room {
  display: grid;
  grid-template-columns: subgrid;
  align-items: start;
  column-gap: 8px;
  margin-block-start: 5px;
}
.log-rescue-rooms > .log-rescue-entry {
  --log-rescue-indent: 20px;
  margin-inline-start: calc(8px - var(--log-gutter));
  margin-inline-end: 0;
}
.log-rescue-rooms > .log-live-detail {
  margin-inline-start: calc(-1 * (var(--log-gutter) + 16px));
}
.log-rescue-state {
  color: var(--log-ink);
  font-size: 11px;
  white-space: nowrap;
}
.log-rescue-rooms > .log-rescue-history {
  --log-rescue-indent: 32px;
  margin-inline-start: calc(20px - var(--log-gutter));
}
/* 扩展消息前的行内间距，时间仍回到全页共同的时间列。 */
.log-rescue-rooms > .log-rescue-entry.log-facility-heading--stamped {
  margin-inline-start: calc(4px - var(--log-gutter) - 16px);
  padding-inline-start: calc(var(--log-gutter) + var(--log-rescue-indent));
  text-indent: calc(-1 * (var(--log-gutter) + var(--log-rescue-indent)));
}
.log-rescue-entry.log-facility-heading--stamped > .log-stamp {
  width: calc(var(--log-gutter) + var(--log-rescue-indent));
}
.log-rescue-rooms > .log-rescue-entry:is(.log-line--stamped, .log-line--bare) {
  margin-inline-start: calc(-1 * (var(--log-gutter) + 16px));
  padding-inline-start: calc(4px + var(--log-gutter) + var(--log-rescue-indent) + 16px);
}
.log-rescue-rooms > .log-rescue-entry.log-line--stamped {
  text-indent: calc(-1 * (var(--log-gutter) + var(--log-rescue-indent) + 16px));
}
.log-rescue-entry.log-line--stamped > .log-stamp {
  width: calc(var(--log-gutter) + var(--log-rescue-indent) + 16px);
}
.log-line--source-only {
  position: absolute;
  width: 1px;
  height: 1px;
  min-height: 0;
  padding: 0;
  overflow: hidden;
  clip-path: inset(50%);
  white-space: pre;
}
.log-token--inventory-change {
  white-space: nowrap;
}
.log-token--inventory-change img {
  vertical-align: middle;
  margin-inline-end: 3px;
  object-fit: contain;
}
.log-token--inventory-change[data-change-direction='increase'] {
  color: var(--log-error-ink);
}
.log-token--inventory-change[data-change-direction='decrease'] {
  color: var(--log-room-ink);
}

.log-token--operator {
  color: var(--log-operator-ink);
}

.log-recruit-tags {
  padding: 1px 4px;
  border-radius: 3px;
  background: color-mix(in srgb, currentColor 6%, transparent);
  -webkit-box-decoration-break: clone;
  box-decoration-break: clone;
}

.log-recruit-tags__name,
.log-recruit-combinations__group,
.log-token--recruit-duration {
  white-space: nowrap;
}

.log-recruit-tags[data-recruit-rarity],
.log-recruit-combinations__group,
.log-token--recruit-notice {
  font-weight: var(--log-label-weight);
}

[data-recruit-rarity='1'] {
  color: var(--log-recruit-one-ink, #5a6b78);
}

[data-recruit-rarity='4'] {
  color: var(--log-recruit-four-ink, #8550ad);
}

[data-recruit-rarity='5'] {
  color: var(--log-recruit-five-ink, #957408);
}

[data-recruit-rarity='6'] {
  color: var(--log-recruit-six-ink, #ad6417);
}

.log-token--warning {
  color: var(--log-warning-ink);
  font-weight: var(--log-alert-weight);
}

.log-token--error,
.log-token--critical {
  color: var(--log-error-ink);
  font-weight: var(--log-alert-weight);
}

.log-line--detail {
  color: var(--log-detail-ink);
}

.log-line--detail:is([data-log-detail-owner], .log-rescue-entry) {
  color: var(--log-ink);
}

.log-line--detail > .log-message {
  font-size: 12px;
}

.log-line--scene .log-token--text {
  font-style: italic;
}

/* 深色主题的正文用暖白而非纯白，长时间阅读不刺眼。 */
html[data-mower-theme='dark'] .log-output,
html[data-window-shell-theme='dark'] .log-output {
  --log-ink: #e5e1d6;
  --log-body-weight: 375;
  --log-label-weight: 500;
  --log-alert-weight: 600;
  --log-sheen-opacity: 1;
  --log-sheen-protection: 0.2;
  --log-muted-ink: #868d97;
  --log-detail-ink: #959ca6;
  --log-time-ink: #7cb8f2;
  --log-room-ink: #74d3a3;
  --log-operator-ink: #f598ae;
  --log-recruit-one-ink: #abc5d7;
  --log-recruit-four-ink: #c6a1e8;
  --log-recruit-five-ink: #e5d36b;
  --log-recruit-six-ink: #f1b35f;
  --log-warning-ink: #f1bd5d;
  --log-error-ink: #ff8fa6;
  --log-warning-tint: rgb(241 189 93 / 12%);
  --log-error-tint: rgb(255 143 166 / 12%);
  --log-hover-tint: rgb(255 255 255 / 5%);
}
</style>
