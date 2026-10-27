<script setup>
import { i18n } from '@/i18n'
const { t } = i18n.global

import { computed, inject, onMounted, ref } from 'vue'

const axios = inject('axios')
const token = ref('')
const status = ref({ configured: false })
const busy = ref(false)
const feedbackKey = ref('')
const rawFeedback = ref('')
const feedback = computed(() => (feedbackKey.value ? t(feedbackKey.value) : rawFeedback.value))
const failed = ref(false)
const base = import.meta.env.VITE_HTTP_URL

async function loadStatus() {
  try {
    status.value = (await axios.get(`${base}/growth-sync-token`)).data
  } catch {
    failed.value = true
    feedbackKey.value = 'tasks.yituliuSettingsFailed'
  }
}

async function act(action) {
  if (busy.value) return
  busy.value = true
  failed.value = false
  feedbackKey.value = ''
  rawFeedback.value = ''
  try {
    if (action === 'save') {
      status.value = (
        await axios.put(`${base}/growth-sync-token`, { token: token.value.trim() })
      ).data
      token.value = ''
      feedbackKey.value = 'tasks.yituliuTokenSaved'
    } else if (action === 'clear') {
      status.value = (await axios.delete(`${base}/growth-sync-token`)).data
      token.value = ''
      feedbackKey.value = 'tasks.yituliuTokenCleared'
    } else if (action === 'sync') {
      feedbackKey.value = 'tasks.yituliuSyncing'
      const { data } = await axios.post(`${base}/growth-sync`, { confirmed: true })
      if (!data.success) throw new Error(t('tasks.syncUnconfirmed'))
      status.value = {
        ...status.value,
        last_synced_at: data.synced_at,
        last_synced_count: data.count,
        last_sync_error: null,
        last_attempt_at: data.synced_at
      }
      feedbackKey.value = ''
      rawFeedback.value = data.message
    }
  } catch (error) {
    failed.value = true
    const message = error.response?.data?.message
    feedbackKey.value = message ? '' : 'tasks.yituliuActionFailed'
    rawFeedback.value = message || ''
  } finally {
    busy.value = false
  }
}

onMounted(loadStatus)
</script>

<template>
  <n-card :title="t('tasks.yituliuSync')">
    <n-space vertical :size="14">
      <n-text depth="3"
        >{{ t('tasks.yituliuTokenHelp')
        }}<n-a href="https://auth.yituliu.cn" target="_blank" rel="noopener noreferrer">{{
          t('tasks.openYituliuUserCenter')
        }}</n-a>
      </n-text>
      <n-input
        v-model:value="token"
        type="password"
        show-password-on="click"
        autocomplete="new-password"
        :disabled="busy"
        :placeholder="
          status.configured ? t('tasks.tokenSavedPlaceholder') : t('tasks.pasteYituliuToken')
        "
        :aria-label="t('tasks.yituliuAccessToken')"
      />
      <n-space align="center" :size="8">
        <n-button :disabled="busy || !token.trim()" @click="act('save')">{{
          t('tasks.saveToken')
        }}</n-button>
        <n-button :disabled="busy || !status.configured" @click="act('clear')">{{
          t('tasks.clearLocalToken')
        }}</n-button>
        <n-button
          type="primary"
          :disabled="busy || !status.configured || !!token.trim()"
          :loading="busy"
          @click="act('sync')"
          >{{ t('tasks.syncNow') }}</n-button
        >
        <n-tag :bordered="false" :type="status.configured ? 'success' : 'default'">
          {{ status.configured ? t('tasks.automaticSyncEnabled') : t('tasks.notConfigured') }}
        </n-tag>
      </n-space>
      <n-alert type="info" :bordered="false">{{ t('tasks.yituliuSyncHelp') }}</n-alert>
      <n-text v-if="status.last_synced_at" depth="3"
        >{{ t('tasks.lastSync') }}{{ new Date(status.last_synced_at * 1000).toLocaleString() }} ·
        {{ status.last_synced_count }}{{ t('tasks.operatorsCountSuffix') }}</n-text
      >
      <n-text v-if="status.last_sync_error" type="warning"
        >{{ t('tasks.syncIncomplete') }}{{ status.last_sync_error }}
      </n-text>
      <n-text v-if="feedback" :type="failed ? 'error' : 'success'" aria-live="polite">
        {{ feedback }}
      </n-text>
    </n-space>
  </n-card>
</template>
