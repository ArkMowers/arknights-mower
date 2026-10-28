<script setup>
import { i18n } from '@/i18n'
const { t } = i18n.global

import { inject } from 'vue'

const mobile = inject('mobile')

import { storeToRefs } from 'pinia'
import { useConfigStore } from '@/stores/config'

const store = useConfigStore()

const { ra_timeout, sf_target } = storeToRefs(store)

const target_options = [
  {
    get label() {
      return t('tasks.endingRouteA')
    },
    value: '结局A'
  },
  {
    get label() {
      return t('tasks.endingRouteB')
    },
    value: '结局B'
  },
  {
    get label() {
      return t('tasks.endingRouteC')
    },
    value: '结局C'
  },
  {
    get label() {
      return t('tasks.endingRouteD')
    },
    value: '结局D'
  },
  {
    get label() {
      return t('tasks.endingRouteE')
    },
    value: '结局E'
  }
]
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
    <n-form-item :label="t('tasks.selectRoute')">
      <n-select v-model:value="sf_target" :options="target_options" />
    </n-form-item>
  </n-form>
</template>
