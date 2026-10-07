<script setup>
import { ref, watch } from 'vue'
import axios from 'axios'
import { SwapVertical } from '@vicons/ionicons5'
import draggable from 'vuedraggable'

const props = defineProps({ revision: { type: String, default: '' } })
const emit = defineEmits(['changed'])
const show = ref(false)
const items = ref([])
const preparedItems = ref([])
const custom = ref(false)
const busy = ref(false)
const loaded = ref(false)
const dragging = ref(false)
const feedback = ref('')
const failed = ref(false)
const endpoint = `${import.meta.env.VITE_HTTP_URL}/growth-crafting-order`
let refreshPending = false

function accept(data) {
  if (data.error) throw new Error(data.error)
  items.value = data.items
  preparedItems.value = data.prepared_items || []
  custom.value = data.custom
  loaded.value = true
}

async function refresh() {
  if (!show.value) return
  if (busy.value || dragging.value) {
    refreshPending = true
    loaded.value = false
    return
  }
  busy.value = true
  loaded.value = false
  feedback.value = ''
  failed.value = false
  try {
    accept((await axios.get(endpoint)).data)
  } catch (error) {
    failed.value = true
    feedback.value = error.response?.data?.error || error.message || '合成顺序读取失败，请重试'
  } finally {
    busy.value = false
    await refreshIfPending()
  }
}

async function refreshIfPending() {
  if (!refreshPending) return
  refreshPending = false
  await refresh()
}

function canDrag(event) {
  const { element, futureIndex } = event.draggedContext
  const lockedCount = items.value.filter((item) => item.locked).length
  return (
    loaded.value &&
    !busy.value &&
    !element.locked &&
    futureIndex >= lockedCount &&
    futureIndex < items.value.length
  )
}

function projectText(item) {
  const split = item.label.lastIndexOf(' · ')
  return split < 0
    ? { name: item.label, target: '' }
    : { name: item.label.slice(0, split), target: item.label.slice(split + 3) }
}

function projectStatus(item) {
  return item.reason || (item.locked ? '进行中 · 固定优先' : '待备料')
}

async function save(order) {
  if (busy.value || !loaded.value) return
  busy.value = true
  feedback.value = ''
  failed.value = false
  try {
    const response = order ? await axios.put(endpoint, { order }) : await axios.delete(endpoint)
    accept(response.data)
    feedback.value = order ? '合成顺序已保存' : '已恢复专精优先顺序'
    emit('changed')
  } catch (error) {
    failed.value = true
    feedback.value = error.response?.data?.error || error.message || '合成顺序保存失败，请重试'
  } finally {
    busy.value = false
    await refreshIfPending()
  }
}

async function commitDrag(nextItems) {
  if (busy.value || !loaded.value) return
  const order = nextItems.map((item) => item.key)
  const original = items.value.map((item) => item.key)
  if (
    order.length !== original.length ||
    new Set(order).size !== original.length ||
    order.some((key) => !original.includes(key)) ||
    items.value.some((item, index) => item.locked && order[index] !== item.key) ||
    order.every((key, index) => key === original[index])
  )
    return
  await save(order)
}

async function finishDrag() {
  dragging.value = false
  await refreshIfPending()
}

async function keyboardMove(index, direction) {
  if (!canDrag({ draggedContext: { element: items.value[index], futureIndex: index + direction } }))
    return
  const destination = index + direction
  if (destination >= items.value.length) return
  const nextItems = [...items.value]
  const [item] = nextItems.splice(index, 1)
  nextItems.splice(destination, 0, item)
  await commitDrag(nextItems)
}

watch([show, () => props.revision], () => {
  if (show.value) refresh()
})
</script>

<template>
  <n-button size="small" @click="show = true">
    <template #icon><n-icon :component="SwapVertical" /></template>
    合成顺序
  </n-button>
  <n-modal
    v-model:show="show"
    preset="card"
    title="养成材料合成顺序"
    size="small"
    :style="{ width: 'min(620px, calc(100vw - 32px))', maxHeight: 'calc(100dvh - 48px)' }"
    :content-style="{ minHeight: 0, overflowY: 'auto' }"
  >
    <div class="order-content">
      <n-alert v-if="preparedItems.length" type="success" :show-icon="false" :bordered="false">
        <n-text strong>材料已备齐，待完成养成</n-text>
        <n-scrollbar style="max-height: 144px">
          <div v-for="item in preparedItems" :key="item.key" class="prepared-project">
            <n-avatar :src="'/avatar/' + item.char_name + '.webp'" :size="28" round />
            <div class="order-description">
              <n-text strong>{{ item.char_name }} · {{ item.label }}</n-text>
              <n-text v-if="item.reason" depth="3" class="order-label">{{ item.reason }}</n-text>
            </div>
          </div>
        </n-scrollbar>
        <n-text depth="3" class="order-label">
          完成养成并同步后移除此提示；已备齐的材料不会重复合成。
        </n-text>
      </n-alert>
      <div class="order-help">
        <n-text depth="3"
          >拖动调整合成顺序，松开自动保存，不改变专精队列；默认专精优先，缺料项目本轮跳过。</n-text
        >
        <n-text depth="3"
          >前置随项目准备，共用费用只计一次；纯等级提升不参与排序，模组前置仅准备至精二一级。</n-text
        >
      </div>
      <n-space justify="space-between" align="center" :size="8">
        <n-tag size="small" :bordered="false">{{ custom ? '自定义顺序' : '默认顺序' }}</n-tag>
        <n-space :size="8">
          <n-button size="small" :disabled="busy || dragging" @click="refresh">刷新</n-button>
          <n-button
            size="small"
            :disabled="busy || dragging || !loaded || items.length < 2"
            @click="save()"
          >
            恢复专精优先
          </n-button>
        </n-space>
      </n-space>
      <n-text v-if="items.some((item) => item.locked)" depth="3" class="order-help">
        进行中的专精固定优先，其他项目可拖动。
      </n-text>
      <n-spin :show="busy">
        <div class="order-list">
          <draggable
            v-if="items.length"
            :model-value="items"
            item-key="key"
            handle=".order-drag-handle"
            :disabled="busy || !loaded"
            :move="canDrag"
            class="crafting-order"
            role="list"
            aria-label="养成材料合成顺序"
            @update:model-value="commitDrag"
            @start="dragging = true"
            @end="finishDrag"
          >
            <template #item="{ element: item, index }">
              <div class="crafting-order-row" role="listitem">
                <span
                  :class="item.locked ? 'order-drag-locked' : 'order-drag-handle'"
                  :tabindex="item.locked || busy || !loaded ? -1 : 0"
                  :aria-label="
                    item.locked ? '进行中，顺序已固定' : `拖动排序 ${item.char_name} ${item.label}`
                  "
                  :aria-disabled="item.locked || busy || !loaded"
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
              </div>
            </template>
          </draggable>
          <n-empty v-else-if="loaded" description="尚未选择养成项目" />
        </div>
      </n-spin>
      <n-text v-if="feedback" :type="failed ? 'error' : 'success'" aria-live="polite">
        {{ feedback }}
      </n-text>
    </div>
  </n-modal>
</template>

<style scoped>
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
