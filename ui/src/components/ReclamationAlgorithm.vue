<script setup>
import { inject } from 'vue'

const mobile = inject('mobile')

import { storeToRefs } from 'pinia'
import { useConfigStore } from '@/stores/config'

const store = useConfigStore()

const { ra_timeout } = storeToRefs(store)
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
  </n-form>
</template>
