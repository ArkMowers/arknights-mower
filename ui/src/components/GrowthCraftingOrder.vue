<script setup>
import { ref, watch } from 'vue'
import axios from 'axios'
import { ArrowUp, ArrowDown, SwapVertical } from '@vicons/ionicons5'

const props = defineProps({ revision: { type: String, default: '' } })
const emit = defineEmits(['changed'])
const show = ref(false)
const items = ref([])
const custom = ref(false)
const busy = ref(false)
const loaded = ref(false)
const feedback = ref('')
const failed = ref(false)
const endpoint = `${import.meta.env.VITE_HTTP_URL}/growth-crafting-order`
let refreshPending = false

function accept(data) {
  if (data.error) throw new Error(data.error)
  items.value = data.items
  custom.value = data.custom
  loaded.value = true
}

async function refresh() {
  if (!show.value) return
  if (busy.value) {
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

function canMove(index, direction) {
  const destination = index + direction
  return (
    loaded.value &&
    !busy.value &&
    !items.value[index]?.locked &&
    destination >= 0 &&
    destination < items.value.length &&
    !items.value[destination].locked
  )
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

async function move(index, direction) {
  if (!canMove(index, direction)) return
  const order = items.value.map((item) => item.key)
  const destination = index + direction
  ;[order[index], order[destination]] = [order[destination], order[index]]
  await save(order)
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
    :style="{ width: 'min(620px, calc(100vw - 32px))' }"
  >
    <n-space vertical :size="12">
      <n-text depth="3" class="order-help">
        默认专精优先；缺材料的项目本轮跳过，前置未完成仍可备料。每个项目先准备最低前置材料，共用前置只计算一次。训练中的计划固定在前。调整后自动保存，仅改变合成顺序。
      </n-text>
      <n-space justify="space-between" align="center" :size="8">
        <n-tag size="small" :bordered="false">{{ custom ? '自定义顺序' : '默认顺序' }}</n-tag>
        <n-space :size="8">
          <n-button size="small" :disabled="busy" @click="refresh">刷新</n-button>
          <n-button size="small" :disabled="busy || !loaded || items.length < 2" @click="save()">
            恢复专精优先
          </n-button>
        </n-space>
      </n-space>
      <n-text v-if="items.some((item) => item.locked)" depth="3" class="order-help">
        进行中的专精固定优先，其他项目可上下移动。
      </n-text>
      <n-spin :show="busy">
        <n-scrollbar style="max-height: min(56vh, 480px)">
          <ol v-if="items.length" class="crafting-order" aria-label="养成材料合成顺序">
            <li v-for="(item, index) in items" :key="item.key" class="crafting-order-row">
              <span class="order-position">{{ index + 1 }}</span>
              <div class="order-description">
                <n-text strong>{{ item.char_name }}</n-text>
                <n-text depth="3" class="order-label">{{ item.label }}</n-text>
                <n-text
                  v-if="item.reason"
                  :type="item.status === 'waiting' ? 'warning' : 'info'"
                  class="order-label"
                >
                  {{ item.reason }}
                </n-text>
              </div>
              <n-tag v-if="item.locked" size="small" type="info" :bordered="false">进行中</n-tag>
              <div class="order-actions">
                <n-button
                  size="small"
                  :disabled="!canMove(index, -1)"
                  :aria-label="`上移 ${item.char_name} ${item.label}`"
                  @click="move(index, -1)"
                >
                  <template #icon><n-icon :component="ArrowUp" /></template>
                  上移
                </n-button>
                <n-button
                  size="small"
                  :disabled="!canMove(index, 1)"
                  :aria-label="`下移 ${item.char_name} ${item.label}`"
                  @click="move(index, 1)"
                >
                  <template #icon><n-icon :component="ArrowDown" /></template>
                  下移
                </n-button>
              </div>
            </li>
          </ol>
          <n-empty v-else-if="loaded" description="尚未选择养成项目" />
        </n-scrollbar>
      </n-spin>
      <n-text v-if="feedback" :type="failed ? 'error' : 'success'" aria-live="polite">
        {{ feedback }}
      </n-text>
    </n-space>
  </n-modal>
</template>

<style scoped>
.order-help,
.order-label {
  font-size: 12px;
}
.crafting-order {
  display: flex;
  flex-direction: column;
  gap: 8px;
  padding: 0;
  margin: 0;
  list-style: none;
}
.crafting-order-row {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 6px 0;
}
.order-position {
  width: 24px;
  flex-shrink: 0;
  text-align: center;
  font-variant-numeric: tabular-nums;
}
.order-description {
  display: flex;
  flex: 1;
  min-width: 0;
  flex-direction: column;
  overflow-wrap: anywhere;
}
.order-actions {
  display: flex;
  gap: 6px;
  flex-shrink: 0;
}
@media (max-width: 480px) {
  .order-actions {
    flex-direction: column;
  }
}
</style>
