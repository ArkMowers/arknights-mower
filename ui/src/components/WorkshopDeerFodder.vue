<template>
  <n-space vertical :size="12">
    <n-text depth="3">选择九色鹿使用的垫刀素材，并设置库存上下限。</n-text>
    <n-alert v-if="error" type="warning">
      {{ error }}
      <n-button text @click="loadOptions" class="fodder-button">重试</n-button>
    </n-alert>
    <n-card v-for="(item, index) in items" :key="index" size="small" :bordered="false">
      <n-space vertical :size="12">
        <div class="fodder-material">
          <n-select
            size="large"
            v-model:value="item.item_names"
            multiple
            filterable
            :options="options"
            :disabled="disabled || loading || !!error"
            placeholder="选择垫刀素材"
            :input-props="{ 'aria-label': `第 ${index + 1} 组垫刀素材` }"
          />
          <n-button :disabled="disabled" @click="items.splice(index, 1)" class="fodder-button">
            删除
          </n-button>
        </div>
        <div class="fodder-limits">
          <label>
            <n-text depth="3">子材料库存下限</n-text>
            <mower-input-number
              size="large"
              :value="item.children_lower_limit"
              @update:value="item.children_lower_limit = $event ?? 0"
              :min="0"
              :max="999999"
              :precision="0"
              :show-button="false"
              :disabled="disabled"
              :input-props="{ 'aria-label': '子材料库存下限' }"
            />
          </label>
          <label>
            <n-text depth="3">成品库存上限</n-text>
            <mower-input-number
              size="large"
              :value="item.self_upper_limit"
              @update:value="item.self_upper_limit = $event ?? 0"
              :min="0"
              :max="999999"
              :precision="0"
              :show-button="false"
              :disabled="disabled"
              :input-props="{ 'aria-label': '成品库存上限' }"
            />
          </label>
        </div>
      </n-space>
    </n-card>
    <n-button
      block
      secondary
      :disabled="disabled || loading || !!error"
      @click="items.push({ item_names: [], children_lower_limit: 0, self_upper_limit: 9999 })"
      class="fodder-button"
      >新增素材设置</n-button
    >
  </n-space>
</template>

<script setup>
import { inject, onMounted, ref } from 'vue'

defineProps({ disabled: Boolean })
const items = defineModel({ type: Array, default: () => [] })
const axios = inject('axios')
const options = ref([])
const loading = ref(false)
const error = ref('')

async function loadOptions() {
  loading.value = true
  error.value = ''
  try {
    const { data } = await axios.get(`${import.meta.env.VITE_HTTP_URL}/item`, {
      params: { kind: 'deer-fodder' }
    })
    if (!Array.isArray(data)) throw new Error('素材列表格式错误')
    options.value = data.map((name) => ({ label: name, value: name }))
  } catch (e) {
    error.value = `读取垫刀素材失败：${e.message}`
  } finally {
    loading.value = false
  }
}

onMounted(loadOptions)
</script>

<style scoped>
.fodder-material {
  display: flex;
  align-items: center;
  gap: 12px;
}
.fodder-material .n-select {
  flex: 1;
  min-width: 0;
}
.fodder-limits {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 12px;
  font-variant-numeric: tabular-nums;
}
.fodder-limits label {
  display: grid;
  gap: 4px;
}
.fodder-button {
  min-height: 40px;
  min-width: 40px;
}
@media (max-width: 480px) {
  .fodder-limits {
    grid-template-columns: 1fr;
  }
}
</style>
