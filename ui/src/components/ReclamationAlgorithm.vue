<script setup>
import { i18n } from '@/i18n'
const { t } = i18n.global

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
    <n-form-item :label="t('tasks.timeout')">
      <mower-input-number v-model:value="ra_timeout">
        <template #suffix>{{ t('tasks.seconds') }}</template>
      </mower-input-number>
    </n-form-item>
  </n-form>
</template>
