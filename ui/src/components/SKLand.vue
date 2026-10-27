<script setup>
import { i18n } from '@/i18n'
const { t } = i18n.global

import { inject, ref, computed } from 'vue'
import { copyMowerTestText } from '../utils/copyMowerTestText'
const axios = inject('axios')

import { useConfigStore } from '@/stores/config'
const store = useConfigStore()

import { storeToRefs } from 'pinia'
const { skland_info } = storeToRefs(store)

function add_account() {
  return {
    arknights_isCheck: true,
    endfield_isCheck: true,
    account: '',
    password: '',
    sign_in_official: true,
    sign_in_bilibili: true,
    sign_in_endfield_official: true,
    sign_in_endfield_bilibili: true,
    cultivate_select: true
  }
}

const maa_msg = ref('')
const copying = ref(false)
const copy_status = ref('')
const testing = ref(false)

async function test_maa() {
  testing.value = true
  copy_status.value = ''
  maa_msg.value = t('tasks.testing')
  try {
    const response = await axios.get(`${import.meta.env.VITE_HTTP_URL}/check-skland`)
    maa_msg.value = Array.isArray(response.data)
      ? response.data.join('\n')
      : String(response.data ?? '')
  } catch (error) {
    maa_msg.value = t('tasks.testFailedMessage', {
      message: error.response?.data?.message || error.message || String(error)
    })
  } finally {
    testing.value = false
  }
}

async function copy_result() {
  if (!maa_msg.value) return
  copying.value = true
  try {
    copy_status.value = (await copyMowerTestText(maa_msg.value))
      ? t('tasks.copied')
      : t('tasks.copyFailed')
  } catch {
    copy_status.value = t('tasks.copyFailed')
  } finally {
    copying.value = false
  }
}

const enable_test = computed(() => {
  return skland_info.value.some((item) => {
    return item.account?.trim() && item.password?.trim()
  })
})
</script>

<template>
  <n-card>
    <template #header>
      <div class="card-title">{{ t('tasks.sklandAccount') }}</div>
      <help-text>
        <div>{{ t('tasks.connectionFailureSteps') }}</div>
        <ol style="margin: 0">
          <li>{{ t('tasks.syncClockRetry') }}</li>
          <li>{{ t('tasks.checkCredentials') }}</li>
          <li>{{ t('tasks.disableProxyHelp') }}</li>
          <li>{{ t('tasks.sklandCaptchaHelp') }}</li>
        </ol>
      </help-text>
    </template>
    <n-dynamic-input v-model:value="skland_info" :on-create="add_account" show-sort-button>
      <template #default="{ value }">
        <div style="display: flex; align-items: center; width: 100%">
          <n-input
            style="margin-right: 10px"
            v-model:value="value.account"
            type="text"
            :placeholder="t('tasks.account')"
          />
          <n-input
            v-model:value="value.password"
            type="password"
            show-password-on="click"
            :placeholder="t('tasks.password')"
          />
        </div>
      </template>
    </n-dynamic-input>
    <div class="misc-container">
      <n-button :disabled="!enable_test || testing" :loading="testing" @click="test_maa">{{
        t('tasks.testSettings')
      }}</n-button>
      <n-button :disabled="!maa_msg || testing || copying" @click="copy_result">{{
        t('tasks.copyResult')
      }}</n-button>
      <span aria-live="polite">{{ copy_status }}</span>
      <n-card
        content-scrollable
        class="skland-test-result"
        segmented
        :content-style="{
          whiteSpace: 'pre-wrap',
          overflow: 'auto',
          overflowWrap: 'anywhere',
          userSelect: 'text'
        }"
      >
        <div>{{ maa_msg }}</div>
      </n-card>
    </div>
  </n-card>
</template>

<style>
.skland-test-result {
  max-height: 230px;
  min-width: 0;
  max-width: 100%;
  flex: 1 1 320px;
}

.misc-container {
  margin-top: 12px;
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 12px;
}
</style>
