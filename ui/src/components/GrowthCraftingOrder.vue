<script setup>
import { computed, ref, watch } from 'vue'
import axios from 'axios'
import { List } from '@vicons/carbon'
import draggable from 'vuedraggable'
import { interleaveMasteryPlans } from '@/utils/masteryPlanOrder'
import { pinyin_match } from '@/utils/common'

const props = defineProps({
  revision: { type: String, default: '' },
  recommendations: { type: Array, default: () => [] },
  count: { type: Number, default: 0 }
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
</script>

<template>
  <n-button size="small" @click="show = true">
    <template #icon><n-icon :component="List" /></template>
    养成计划
    <n-badge v-if="count" :value="count" :max="99" style="margin-left: 4px" />
  </n-button>
  <n-modal
    :show="show"
    :closable="!busy"
    :close-on-esc="!busy"
    :mask-closable="false"
    @update:show="
      (value) => {
        if (!value) cancel()
      }
    "
    preset="card"
    title="养成计划"
    size="small"
    :style="{ width: 'min(620px, calc(100vw - 32px))', maxHeight: 'calc(100dvh - 48px)' }"
    :content-style="{ minHeight: 0, overflowY: 'auto' }"
  >
    <div class="order-content">
      <n-alert v-if="draftPreparedItems.length" type="success" :show-icon="false" :bordered="false">
        <n-text strong>材料已备齐，待完成养成</n-text>
        <n-scrollbar style="max-height: 144px">
          <div v-for="item in draftPreparedItems" :key="item.key" class="prepared-project">
            <n-avatar :src="'/avatar/' + item.char_name + '.webp'" :size="28" round />
            <div class="order-description">
              <n-text strong>{{ item.char_name }} · {{ item.label }}</n-text>
              <n-text v-if="item.reason" depth="3" class="order-label">{{ item.reason }}</n-text>
            </div>
            <n-button size="small" quaternary :disabled="!editable" @click="remove(item)">
              移除
            </n-button>
          </div>
        </n-scrollbar>
        <n-text depth="3" class="order-label">
          完成养成并同步后移除此提示；已备齐的材料不会重复合成。
        </n-text>
      </n-alert>
      <div class="order-help">
        <n-text depth="3"
          >拖动调整养成顺序，保存后同步用于专精与材料合成；缺料项目本轮跳过。</n-text
        >
        <n-text depth="3"
          >前置随项目准备，共用费用只计一次；纯升级不生成合成任务，模组前置仅准备至精二一级。</n-text
        >
      </div>
      <div class="plan-tools">
        <n-input
          v-model:value="search"
          size="small"
          clearable
          placeholder="查找计划中的干员 / 项目"
          aria-label="查找养成计划"
          class="plan-search"
        />
        <n-button
          size="small"
          :disabled="!editable || dragging || !!search.trim()"
          @click="organize"
          >按职业整理</n-button
        >
        <n-button
          size="small"
          :disabled="!editable || dragging || !!search.trim()"
          @click="prioritizeSkills"
          >专精优先</n-button
        >
        <n-button size="small" :disabled="busy || dragging || dirty" @click="refresh()"
          >刷新</n-button
        >
      </div>
      <n-text v-if="search.trim()" depth="3" class="order-label"
        >搜索时暂不能拖动，清除搜索后可调整完整顺序。</n-text
      >
      <n-text v-if="draftItems.some((item) => item.locked)" depth="3" class="order-label">
        进行中的专精固定优先，不能移动或移除；清空仅移除其他项目。
      </n-text>
      <n-spin :show="busy">
        <div class="order-list">
          <draggable
            v-if="sortableItems.length"
            :model-value="sortableItems"
            item-key="key"
            handle=".order-drag-handle"
            :disabled="!editable || !!search.trim()"
            :move="canDrag"
            class="crafting-order"
            role="list"
            aria-label="养成计划顺序"
            @update:model-value="commitDrag"
            @start="dragging = true"
            @end="finishDrag"
          >
            <template #item="{ element: item, index }">
              <div v-show="matchesSearch(item)" class="crafting-order-row" role="listitem">
                <span
                  :class="item.locked ? 'order-drag-locked' : 'order-drag-handle'"
                  :tabindex="item.locked || !editable || !!search.trim() ? -1 : 0"
                  :aria-label="
                    item.locked ? '进行中，顺序已固定' : `拖动排序 ${item.char_name} ${item.label}`
                  "
                  :aria-disabled="item.locked || !editable || !!search.trim()"
                  role="button"
                  @keydown.up.prevent="keyboardMove(index, -1)"
                  @keydown.down.prevent="keyboardMove(index, 1)"
                  >⠿</span
                >
                <span class="order-position">{{ index + 1 }}</span>
                <n-avatar :src="'/avatar/' + item.char_name + '.webp'" :size="36" round />
                <div class="order-description">
                  <n-text strong>
                    {{ item.char_name }}
                    <n-text depth="3">· {{ projectText(item).name }}</n-text>
                  </n-text>
                  <n-text
                    :type="item.status === 'waiting' ? 'warning' : undefined"
                    depth="3"
                    class="order-label"
                  >
                    <template v-if="projectText(item).target"
                      >{{ projectText(item).target }} ·
                    </template>
                    {{ projectStatus(item) }}
                  </n-text>
                </div>
                <n-button
                  size="small"
                  quaternary
                  :disabled="!editable || item.locked"
                  @click="remove(item)"
                  >移除</n-button
                >
              </div>
            </template>
          </draggable>
          <n-empty
            v-else-if="loaded && !draftFailedItems.length && !draftPreparedItems.length"
            description="还没有养成目标"
          />
          <div v-if="draftFailedItems.length" class="failed-plans">
            <n-text strong>失败计划</n-text>
            <div
              v-for="item in draftFailedItems"
              v-show="matchesSearch(item)"
              :key="item.key"
              class="crafting-order-row"
            >
              <n-avatar :src="'/avatar/' + item.char_name + '.webp'" :size="36" round />
              <div class="order-description">
                <n-text strong>{{ item.char_name }} · {{ item.label }}</n-text>
                <n-text type="warning" class="order-label">{{ item.reason }}</n-text>
              </div>
              <n-button size="small" quaternary :disabled="!editable" @click="remove(item)"
                >移除</n-button
              >
            </div>
          </div>
        </div>
      </n-spin>
      <n-text v-if="feedback" :type="failed ? 'error' : 'success'" aria-live="polite">
        {{ feedback }}
      </n-text>
    </div>
    <template #footer>
      <div class="plan-footer">
        <n-button
          size="small"
          :disabled="
            !editable || (!draftItems.some((item) => !item.locked) && !draftFailedItems.length)
          "
          @click="clear"
          >清空计划</n-button
        >
        <div class="plan-tools">
          <n-button size="small" :disabled="busy" @click="cancel">取消</n-button>
          <n-button
            size="small"
            type="primary"
            :loading="busy"
            :disabled="!editable || !dirty || dragging"
            @click="save"
            >保存变更</n-button
          >
        </div>
      </div>
    </template>
  </n-modal>
</template>

<style scoped>
.plan-tools,
.plan-footer {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}
.plan-footer {
  justify-content: space-between;
}
.plan-search {
  width: 200px;
  flex: 1 1 180px;
}
.order-content {
  display: flex;
  flex-direction: column;
  gap: 10px;
}
.order-help {
  display: flex;
  flex-direction: column;
  gap: 4px;
}
.order-help,
.order-label {
  font-size: 12px;
}
.prepared-project {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 6px 0;
}
.crafting-order-row {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 8px 6px;
  border-radius: 10px;
}
.order-position {
  min-width: 18px;
  flex-shrink: 0;
  font-size: 12px;
  opacity: 0.55;
  font-variant-numeric: tabular-nums;
}
.order-description {
  display: flex;
  flex: 1;
  min-width: 0;
  flex-direction: column;
  gap: 4px;
  overflow-wrap: anywhere;
}
.order-drag-handle,
.order-drag-locked {
  font-size: 22px;
  opacity: 0.5;
  padding: 8px;
  touch-action: none;
}
.order-drag-handle {
  cursor: grab;
}
.order-drag-handle:active {
  cursor: grabbing;
}
.order-drag-locked {
  cursor: not-allowed;
  opacity: 0.2;
}
@media (max-width: 480px) {
  .crafting-order-row {
    gap: 8px;
    padding-inline: 0;
  }
}
</style>
