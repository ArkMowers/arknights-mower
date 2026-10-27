<template>
  <n-space vertical :size="12">
    <n-text depth="3">{{ t('tasks.deerFodderHelp') }}</n-text>
    <n-alert v-if="error" type="warning">
      {{ error }}
      <n-button text @click="loadOptions" class="fodder-button">{{ t('tasks.retry') }}</n-button>
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
            :placeholder="t('tasks.selectFodder')"
            :input-props="{ 'aria-label': t('tasks.fodderGroup', { index: index + 1 }) }"
          />
          <n-button :disabled="disabled" @click="items.splice(index, 1)" class="fodder-button">{{
            t('tasks.delete')
          }}</n-button>
        </div>
        <div class="fodder-limits">
          <label>
            <n-text depth="3">{{ t('tasks.ingredientStockMinimum') }}</n-text>
            <mower-input-number
              size="large"
              :value="item.children_lower_limit"
              @update:value="item.children_lower_limit = $event ?? 20"
              :min="0"
              :max="999999"
              :precision="0"
              :show-button="false"
              :disabled="disabled"
              :input-props="{ 'aria-label': t('tasks.ingredientStockMinimum') }"
            />
          </label>
          <label>
            <n-text depth="3">{{ t('tasks.productStockMaximum') }}</n-text>
            <mower-input-number
              size="large"
              :value="item.self_upper_limit"
              @update:value="item.self_upper_limit = $event ?? 0"
              :min="0"
              :max="999999"
              :precision="0"
              :show-button="false"
              :disabled="disabled"
              :input-props="{ 'aria-label': t('tasks.productStockMaximum') }"
            />
          </label>
        </div>
      </n-space>
    </n-card>
    <n-button
      block
      secondary
      :disabled="disabled || loading || !!error"
      @click="items.push({ item_names: [], children_lower_limit: 20, self_upper_limit: 9999 })"
      class="fodder-button"
      >{{ t('tasks.addFodder') }}</n-button
    >
  </n-space>
</template>

<script setup>
import { i18n } from '@/i18n'
const { t } = i18n.global

import { computed, inject, onMounted, ref } from 'vue'
import { itemDisplayName } from '@/i18n/gameNames'

defineProps({ disabled: Boolean })
const items = defineModel({ type: Array, default: () => [] })
const axios = inject('axios')
const sourceOptions = ref([])
const options = computed(() =>
  sourceOptions.value.map((name) => ({ label: itemDisplayName(name), value: name }))
)
const loading = ref(false)
const error = ref('')

async function loadOptions() {
  loading.value = true
  error.value = ''
  try {
    const { data } = await axios.get(`${import.meta.env.VITE_HTTP_URL}/item`, {
      params: { kind: 'deer-fodder' }
    })
    if (!Array.isArray(data)) throw new Error(t('tasks.invalidMaterialList'))
    sourceOptions.value = data
  } catch (e) {
    error.value = t('tasks.fodderReadFailed', { message: e.message })
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
