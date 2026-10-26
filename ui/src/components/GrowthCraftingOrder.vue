<template>
  <n-button v-if="!hideTrigger" size="small" class="plan-trigger" @click="show = true">
    <template #icon><n-icon :component="List" /></template>
    养成计划
    <span v-if="count" class="plan-trigger__count gp-mono">{{ count }}</span>
  </n-button>

  <n-modal
    :show="show"
    :closable="!busy"
    :close-on-esc="!busy"
    :mask-closable="false"
    preset="card"
    class="growth-plan-modal"
    :style="{ width: 'min(760px, calc(100vw - 24px))' }"
    :content-style="{ minHeight: 0, overflowY: 'auto' }"
    @update:show="
      (value) => {
        if (!value) cancel()
      }
    "
  >
    <template #header>
      <div class="plan-head">
        <div class="plan-head__main">
          <span class="gp-kicker">Growth plan</span>
          <h2 class="plan-head__title">养成计划</h2>
          <p class="plan-head__sub">拖动排序；保存后同步到专精优先级与材料合成。</p>
        </div>
        <div class="plan-head__stats">
          <span class="gp-mono">{{ draftItems.length }} 项</span>
          <span class="gp-mono">{{ draftItems.filter((item) => item.locked).length }} 进行中</span>
          <span v-if="draftPreparedItems.length" class="gp-stamp gp-stamp--flat"
            >{{ draftPreparedItems.length }} 备齐</span
          >
        </div>
      </div>
    </template>

    <div class="plan-body">
      <section v-if="draftPreparedItems.length" class="plan-prepared">
        <header class="plan-prepared__head">
          <span class="gp-kicker">Ready</span>
          <h3>材料已备齐</h3>
          <p>完成养成并同步后移除此提示；已备齐的材料不会重复合成。</p>
        </header>
        <div class="plan-prepared__list">
          <div
            v-for="item in draftPreparedItems"
            :key="item.key"
            class="plan-row plan-row--prepared"
          >
            <n-avatar :src="'/avatar/' + item.char_name + '.webp'" :size="32" round />
            <div class="plan-row__text">
              <b>{{ item.char_name }}</b>
              <span class="plan-row__label">{{ item.label }}</span>
              <span v-if="item.reason" class="plan-row__status">{{ item.reason }}</span>
            </div>
            <n-button size="tiny" quaternary :disabled="!editable" @click="remove(item)"
              >移除</n-button
            >
          </div>
        </div>
      </section>

      <div class="plan-toolbar">
        <n-input
          v-model:value="search"
          size="small"
          clearable
          placeholder="查找计划中的干员或项目"
          aria-label="查找养成计划"
          class="plan-search"
        />
        <div class="plan-toolbar__actions">
          <n-button
            size="small"
            quaternary
            :disabled="!editable || dragging || !!search.trim()"
            @click="organize"
          >
            按职业整理
          </n-button>
          <n-button
            size="small"
            quaternary
            :disabled="!editable || dragging || !!search.trim()"
            @click="prioritizeSkills"
          >
            专精优先
          </n-button>
          <n-button size="small" quaternary :disabled="busy || dragging || dirty" @click="refresh()"
            >刷新</n-button
          >
        </div>
      </div>

      <p v-if="search.trim()" class="plan-hint">搜索期间暂停拖动；清除搜索后可调整完整顺序。</p>
      <p v-if="draftItems.some((item) => item.locked)" class="plan-hint">
        进行中的专精固定在队首，不能移动或移除；清空仅移除其他项目。
      </p>

      <n-spin :show="busy">
        <div class="plan-list">
          <draggable
            v-if="sortableItems.length"
            :model-value="sortableItems"
            item-key="key"
            handle=".order-drag-handle"
            :animation="dragAnimation"
            easing="cubic-bezier(0.2, 0, 0, 1)"
            :force-fallback="true"
            :fallback-on-body="true"
            :fallback-tolerance="5"
            ghost-class="mower-drag-ghost"
            chosen-class="mower-drag-chosen"
            fallback-class="mower-drag-fallback"
            :disabled="!editable || !!search.trim()"
            :move="canDrag"
            class="crafting-order"
            role="list"
            aria-label="养成计划顺序"
            @update:model-value="commitDrag"
            @start="startDrag"
            @end="finishDrag"
          >
            <template #item="{ element: item, index }">
              <div v-show="matchesSearch(item)" class="plan-row" role="listitem">
                <span
                  :class="item.locked ? 'order-drag-locked' : 'order-drag-handle'"
                  :tabindex="item.locked || !editable || !!search.trim() ? -1 : 0"
                  :aria-label="
                    item.locked
                      ? '进行中，顺序已固定'
                      : '拖动排序 ' + item.char_name + ' ' + item.label
                  "
                  :aria-disabled="item.locked || !editable || !!search.trim()"
                  role="button"
                  @keydown.up.prevent="keyboardMove(index, -1)"
                  @keydown.down.prevent="keyboardMove(index, 1)"
                  >⠿</span
                >
                <span class="plan-row__index gp-mono">{{
                  String(index + 1).padStart(2, '0')
                }}</span>
                <n-avatar :src="'/avatar/' + item.char_name + '.webp'" :size="34" round />
                <div class="plan-row__text">
                  <span class="plan-row__name">
                    <b>{{ item.char_name }}</b>
                    <em>{{ projectText(item).name }}</em>
                  </span>
                  <span
                    class="plan-row__status"
                    :class="{ 'is-waiting': item.status === 'waiting' }"
                  >
                    <template v-if="projectText(item).target"
                      >{{ projectText(item).target }} ·
                    </template>
                    {{ projectStatus(item) }}
                  </span>
                </div>
                <n-button
                  size="tiny"
                  quaternary
                  :disabled="!editable || item.locked"
                  @click="remove(item)"
                  >移除</n-button
                >
              </div>
            </template>
          </draggable>

          <div
            v-else-if="loaded && !draftFailedItems.length && !draftPreparedItems.length"
            class="plan-empty"
          >
            <p class="plan-empty__title">还没有养成目标</p>
            <p class="plan-empty__text">先在干员档案里加入专精、模组或等级目标。</p>
          </div>

          <div v-if="draftFailedItems.length" class="plan-failed">
            <span class="plan-failed__label">失败计划</span>
            <div
              v-for="item in draftFailedItems"
              v-show="matchesSearch(item)"
              :key="item.key"
              class="plan-row"
            >
              <n-avatar :src="'/avatar/' + item.char_name + '.webp'" :size="34" round />
              <div class="plan-row__text">
                <span class="plan-row__name"
                  ><b>{{ item.char_name }}</b
                  ><em>{{ item.label }}</em></span
                >
                <span class="plan-row__status is-failed">{{ item.reason }}</span>
              </div>
              <n-button size="tiny" quaternary :disabled="!editable" @click="remove(item)"
                >移除</n-button
              >
            </div>
          </div>
        </div>
      </n-spin>

      <p v-if="feedback" class="plan-feedback" :class="{ 'is-failed': failed }" aria-live="polite">
        {{ feedback }}
      </p>
    </div>

    <template #footer>
      <div class="plan-footer">
        <n-button
          size="small"
          quaternary
          :disabled="
            !editable || (!draftItems.some((item) => !item.locked) && !draftFailedItems.length)
          "
          @click="clear"
          >清空计划</n-button
        >
        <div class="plan-footer__actions">
          <n-button size="small" :disabled="busy" @click="cancel">取消</n-button>
          <n-button
            size="small"
            type="primary"
            :loading="busy"
            :disabled="!editable || !dirty || dragging"
            @click="save"
          >
            保存变更
          </n-button>
        </div>
      </div>
    </template>
  </n-modal>
</template>

<script setup>
import { computed, ref, watch } from 'vue'
import axios from 'axios'
import List from '@vicons/carbon/es/List'
import draggable from 'vuedraggable'
import { interleaveMasteryPlans } from '@/utils/masteryPlanOrder'
import { pinyin_match } from '@/utils/common'
import { normalizeSortablePreview } from '@/utils/sortablePreview'
import '@/styles/drag.css'

const dragAnimation =
  typeof window !== 'undefined' && window.matchMedia?.('(prefers-reduced-motion: reduce)').matches
    ? 0
    : 180
const props = defineProps({
  revision: { type: String, default: '' },
  recommendations: { type: Array, default: () => [] },
  count: { type: Number, default: 0 },
  hideTrigger: Boolean
})
const emit = defineEmits(['changed'])
const show = ref(false)
const items = ref([])
const draftItems = ref([])
const preparedItems = ref([])
const failedItems = ref([])
const draftFailedItems = ref([])
const busy = ref(false)
const loaded = ref(false)
const dragging = ref(false)
const search = ref('')
const stale = ref(false)
const feedback = ref('')
const failed = ref(false)
const base = import.meta.env.VITE_HTTP_URL
const endpoint = `${base}/growth-crafting-order`
let refreshPending = false
const dirty = computed(
  () =>
    draftItems.value.length !== items.value.length ||
    draftItems.value.some((item, index) => item.key !== items.value[index]?.key) ||
    draftFailedItems.value.length !== failedItems.value.length
)
const editable = computed(() => loaded.value && !busy.value && !stale.value)
const preparedByKey = computed(() => new Map(preparedItems.value.map((item) => [item.key, item])))
const draftPreparedItems = computed(() =>
  draftItems.value
    .filter((item) => !item.locked && preparedByKey.value.has(item.key))
    .map((item) => ({ ...item, ...preparedByKey.value.get(item.key) }))
)
const sortableItems = computed(() =>
  draftItems.value.filter((item) => item.locked || !preparedByKey.value.has(item.key))
)

function accept(data) {
  if (data.error) throw new Error(data.error)
  items.value = data.planning_items || data.items
  draftItems.value = [...items.value]
  preparedItems.value = data.prepared_items || []
  failedItems.value = data.failed_items || []
  draftFailedItems.value = [...failedItems.value]
  loaded.value = true
  stale.value = false
}

async function readState() {
  const [order, plans] = await Promise.all([axios.get(endpoint), axios.get(`${base}/mastery-plan`)])
  if (plans.data?.error) throw new Error(plans.data.error)
  const planned = new Set(
    (order.data.planning_items || order.data.items || []).map((item) => item.plan_id)
  )
  return {
    ...order.data,
    failed_items: (plans.data.plans || [])
      .filter((plan) => plan.status === 'failed' && !planned.has(plan.id))
      .map((plan) => ({
        key: `failed:${plan.id}`,
        kind: 'skill',
        failedPlan: true,
        locked: false,
        plan_id: plan.id,
        char_id: plan.char_id,
        char_name: plan.name,
        label: `${plan.skill_name} · 专${plan.target_level || 3}`,
        reason: plan.failed_reason || '执行失败，等待重试'
      }))
  }
}

async function refresh(keepFeedback = false) {
  if (!show.value) return
  if (busy.value || dragging.value) {
    refreshPending = true
    return
  }
  if (dirty.value) {
    stale.value = true
    failed.value = true
    feedback.value = '计划已在其他位置变更，请取消后重新打开，再调整顺序。'
    return
  }
  busy.value = true
  loaded.value = false
  if (!keepFeedback) {
    feedback.value = ''
    failed.value = false
  }
  try {
    accept(await readState())
  } catch (error) {
    failed.value = true
    feedback.value = error.response?.data?.error || error.message || '养成计划读取失败，请重试'
  } finally {
    busy.value = false
    await refreshIfPending()
  }
}

async function refreshIfPending() {
  if (!refreshPending) return
  refreshPending = false
  await refresh(true)
}

function canDrag(event) {
  const { element, futureIndex } = event.draggedContext
  const lockedCount = sortableItems.value.filter((item) => item.locked).length
  return (
    editable.value &&
    !search.value.trim() &&
    !element.locked &&
    futureIndex >= lockedCount &&
    futureIndex < sortableItems.value.length
  )
}

function projectText(item) {
  const split = item.label.lastIndexOf(' · ')
  return split < 0
    ? { name: item.label, target: '' }
    : { name: item.label.slice(0, split), target: item.label.slice(split + 3) }
}

function projectStatus(item) {
  const reason = item.reason || (item.locked ? '进行中 · 固定优先' : '待执行')
  return item.crafting_required === false ? item.reason || '纯等级提升，不需要合成' : reason
}

function matchesSearch(item) {
  const query = search.value.trim().toLowerCase()
  return (
    !query ||
    `${item.char_name} ${item.label}`.toLowerCase().includes(query) ||
    !!pinyin_match(item.char_name, query)
  )
}

function commitDrag(nextItems) {
  if (!editable.value || search.value.trim()) return
  const order = nextItems.map((item) => item.key)
  const original = sortableItems.value.map((item) => item.key)
  if (
    order.length !== original.length ||
    new Set(order).size !== original.length ||
    order.some((key) => !original.includes(key)) ||
    sortableItems.value.some((item, index) => item.locked && order[index] !== item.key)
  )
    return
  const sortableKeys = new Set(original)
  let index = 0
  draftItems.value = draftItems.value.map((item) =>
    sortableKeys.has(item.key) ? nextItems[index++] : item
  )
}

async function finishDrag() {
  dragging.value = false
  await refreshIfPending()
}

function startDrag(event) {
  normalizeSortablePreview(event)
  dragging.value = true
}

function keyboardMove(index, direction) {
  if (
    !canDrag({
      draggedContext: { element: sortableItems.value[index], futureIndex: index + direction }
    })
  )
    return
  const nextItems = [...sortableItems.value]
  const [item] = nextItems.splice(index, 1)
  nextItems.splice(index + direction, 0, item)
  commitDrag(nextItems)
}

function remove(item) {
  if (!editable.value || item.locked) return
  if (item.failedPlan)
    draftFailedItems.value = draftFailedItems.value.filter((entry) => entry.key !== item.key)
  else draftItems.value = draftItems.value.filter((entry) => entry.key !== item.key)
}

function clear() {
  if (!editable.value) return
  draftItems.value = draftItems.value.filter((item) => item.locked)
  draftFailedItems.value = []
}

function organize() {
  if (!editable.value || search.value.trim()) return
  const movable = sortableItems.value.filter((item) => !item.locked)
  const byKey = new Map(movable.map((item) => [item.key, item]))
  const ordered = interleaveMasteryPlans(
    movable.map((item) => ({
      ...item,
      status: 'idle',
      profession:
        item.profession ||
        props.recommendations.find((op) => op.char_id === item.char_id)?.profession
    }))
  ).map((item) => byKey.get(item.key))
  commitDrag([...sortableItems.value.filter((item) => item.locked), ...ordered])
}

function prioritizeSkills() {
  if (!editable.value || search.value.trim()) return
  commitDrag([
    ...sortableItems.value.filter((item) => item.locked),
    ...sortableItems.value.filter((item) => !item.locked && item.kind === 'skill'),
    ...sortableItems.value.filter((item) => !item.locked && item.kind !== 'skill')
  ])
}

function cancel() {
  if (busy.value) return
  draftItems.value = [...items.value]
  draftFailedItems.value = [...failedItems.value]
  search.value = ''
  stale.value = false
  show.value = false
}

async function save() {
  if (!editable.value || dragging.value || !dirty.value) return
  busy.value = true
  feedback.value = ''
  failed.value = false
  const order = draftItems.value.map((item) => item.key)
  const retainedFailures = new Set(draftFailedItems.value.map((item) => item.key))
  const removed = [
    ...items.value.filter((item) => !order.includes(item.key)),
    ...failedItems.value.filter((item) => !retainedFailures.has(item.key))
  ]
  let deleted = 0
  try {
    for (const item of removed) {
      if (item.locked) throw new Error('进行中的计划不能移除')
      let response
      if (item.kind === 'skill') {
        if (!item.plan_id) throw new Error('缺少专精计划编号，请刷新后重试')
        response = await axios.delete(`${base}/mastery-plan`, { data: { id: item.plan_id } })
      } else {
        response = await axios.post(`${base}/growth-plan`, {
          char_id: item.char_id,
          module_id: item.module_id,
          selected: false
        })
      }
      if (response.data?.error) throw new Error(response.data.error)
      deleted++
    }
    const response = await axios.put(endpoint, { order })
    accept({ ...response.data, failed_items: draftFailedItems.value })
    show.value = false
    search.value = ''
    emit('changed')
  } catch (error) {
    const reason = error.response?.data?.error || error.message || '请求失败'
    failed.value = true
    const prefix = deleted ? `已确认移除 ${deleted} 项，保存未完整确认。` : '保存未完成。'
    try {
      accept(await readState())
      feedback.value = `${prefix}已重新读取实际计划：${reason}`
    } catch {
      loaded.value = false
      feedback.value = `${prefix}实际计划读取失败，请取消后重新打开核对：${reason}`
    }
    emit('changed')
  } finally {
    busy.value = false
    refreshPending = false
  }
}

watch([show, () => props.revision], ([opened], [wasOpened]) => {
  if (opened) refresh(wasOpened)
})

function open() {
  show.value = true
}

defineExpose({ open })
</script>

<style scoped>
.growth-plan-modal {
  background: var(--gp-surface-2);
}

.growth-plan-modal :deep(.n-card-header) {
  padding: 18px 22px 12px;
  background: var(--gp-surface-2);
  border-bottom: 1px solid var(--gp-hair-soft);
}

.growth-plan-modal :deep(.n-card__content) {
  padding: 0 22px 16px;
}

.growth-plan-modal :deep(.n-card__footer) {
  padding: 12px 22px;
  background: var(--gp-surface-2);
  border-top: 1px solid var(--gp-hair-soft);
}

.plan-trigger__count {
  margin-left: 6px;
  padding: 0 5px;
  border-radius: 4px;
  background: var(--gp-surface-3);
  color: var(--gp-muted);
  font-size: 10px;
  line-height: 16px;
}

.plan-head {
  display: flex;
  align-items: flex-end;
  justify-content: space-between;
  gap: 16px;
}

.plan-head__title {
  margin: 4px 0 2px;
  font-size: 22px;
  font-weight: 700;
  letter-spacing: -0.02em;
  line-height: 1.2;
}

.plan-head__sub {
  margin: 0;
  color: var(--gp-muted);
  font-size: 11.5px;
}

.plan-head__stats {
  display: flex;
  align-items: center;
  gap: 10px;
  color: var(--gp-muted);
  font-size: 10.5px;
  white-space: nowrap;
}

.plan-body {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.plan-prepared {
  display: flex;
  flex-direction: column;
  gap: 8px;
  padding: 12px 14px;
  border-radius: 14px;
  background: var(--gp-accent-block);
}

.plan-prepared__head h3 {
  margin: 3px 0 2px;
  color: var(--gp-accent-ink);
  font-size: 14px;
  font-weight: 700;
}

.plan-prepared__head p {
  margin: 0;
  color: var(--gp-muted);
  font-size: 10.5px;
  line-height: 1.5;
}

.plan-prepared__list {
  display: flex;
  flex-direction: column;
  gap: 2px;
  max-height: 148px;
  overflow-y: auto;
}

.plan-toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  flex-wrap: wrap;
  padding-top: 4px;
}

.plan-search {
  width: 230px;
  flex: 1 1 200px;
}

.plan-toolbar__actions {
  display: flex;
  align-items: center;
  gap: 2px;
}

.plan-hint {
  margin: 0;
  color: var(--gp-faint);
  font-size: 10.5px;
}

.plan-list {
  display: flex;
  flex-direction: column;
  gap: 4px;
  max-height: min(46vh, 430px);
  overflow-y: auto;
  padding-right: 2px;
}

.plan-row {
  display: flex;
  align-items: center;
  gap: 10px;
  min-height: 56px;
  padding: 7px 8px;
  border-radius: 10px;
  background: var(--gp-surface-2);
}

.plan-row--prepared {
  background: var(--gp-surface);
}

.plan-row__index {
  width: 20px;
  flex: none;
  color: var(--gp-faint);
  font-size: 10px;
}

.plan-row__text {
  display: flex;
  flex: 1;
  min-width: 0;
  flex-direction: column;
  gap: 2px;
}

.plan-row__name {
  display: flex;
  align-items: baseline;
  gap: 6px;
  min-width: 0;
}

.plan-row__name b {
  overflow: hidden;
  font-size: 13px;
  font-weight: 700;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.plan-row__name em {
  overflow: hidden;
  color: var(--gp-muted);
  font-size: 11px;
  font-style: normal;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.plan-row__label {
  color: var(--gp-muted);
  font-size: 11px;
}

.plan-row__status {
  overflow: hidden;
  color: var(--gp-faint);
  font-size: 10.5px;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.plan-row__status.is-waiting {
  color: var(--gp-warn);
}

.plan-row__status.is-failed {
  color: var(--gp-signal);
}

.order-drag-handle,
.order-drag-locked {
  flex: none;
  padding: 6px 4px;
  color: var(--gp-faint);
  font-size: 15px;
  line-height: 1;
  touch-action: none;
  user-select: none;
}

.order-drag-handle {
  cursor: grab;
}

.order-drag-handle:active {
  cursor: grabbing;
}

.order-drag-handle:focus-visible {
  outline: 2px solid var(--gp-accent);
  outline-offset: 1px;
  border-radius: 3px;
}

.order-drag-locked {
  cursor: not-allowed;
  opacity: 0.3;
}

.plan-empty {
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: 4px;
  padding: 28px 16px;
  border-radius: 12px;
  background: var(--gp-surface-2);
}

.plan-empty__title {
  margin: 0;
  font-size: 14px;
  font-weight: 700;
}

.plan-empty__text {
  margin: 0;
  color: var(--gp-muted);
  font-size: 11px;
}

.plan-failed {
  display: flex;
  flex-direction: column;
  gap: 4px;
  margin-top: 8px;
  padding-top: 10px;
  border-top: 1px solid var(--gp-hair-soft);
}

.plan-failed__label {
  color: var(--gp-signal);
  font-size: 10.5px;
  font-weight: 700;
  letter-spacing: 0.06em;
}

.plan-feedback {
  margin: 0;
  color: var(--gp-accent-ink);
  font-size: 11px;
}

.plan-feedback.is-failed {
  color: var(--gp-signal);
}

.plan-footer {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
}

.plan-footer__actions {
  display: flex;
  align-items: center;
  gap: 6px;
}

@media (max-width: 560px) {
  .plan-head {
    flex-direction: column;
    align-items: flex-start;
    gap: 8px;
  }
  .plan-search {
    width: 100%;
    flex-basis: 100%;
  }
  .plan-list {
    max-height: 52vh;
  }
}
</style>
