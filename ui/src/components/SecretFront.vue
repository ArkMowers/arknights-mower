<script setup>
import { inject } from 'vue'

const mobile = inject('mobile')

import { storeToRefs } from 'pinia'
import { useConfigStore } from '@/stores/config'

const store = useConfigStore()

const { ra_timeout, sf_target } = storeToRefs(store)

const target_options = [
  { label: '1A→2A→3A→结局A', value: '结局A' },
  { label: '1A→2A→3A→结局B', value: '结局B' },
  { label: '1A→2A→3B→结局C', value: '结局C' },
  { label: '1A→2B→3C→结局D', value: '结局D' },
  { label: '1A→2B→3C→结局E', value: '结局E' }
]
</script>

<template>
  <n-form
    :label-placement="mobile ? 'top' : 'left'"
    :show-feedback="false"
    label-width="72"
    label-align="left"
  >
    <n-form-item label="超时时长">
      <n-input-number v-model:value="ra_timeout">
        <template #suffix>秒</template>
      </n-input-number>
    </n-form-item>
    <n-form-item label="选择路线">
      <n-select v-model:value="sf_target" :options="target_options" />
    </n-form-item>
  </n-form>
</template>
