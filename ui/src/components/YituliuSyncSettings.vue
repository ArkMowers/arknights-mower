<script setup>
import { inject, onMounted, ref } from 'vue'

const axios = inject('axios')
const token = ref('')
const status = ref({ configured: false })
const busy = ref(false)
const feedback = ref('')
const failed = ref(false)
const base = import.meta.env.VITE_HTTP_URL

async function loadStatus() {
  try {
    status.value = (await axios.get(`${base}/growth-sync-token`)).data
  } catch {
    failed.value = true
    feedback.value = '一图流同步设置读取失败，请刷新后重试'
  }
}

async function act(action) {
  if (busy.value) return
  busy.value = true
  failed.value = false
  feedback.value = ''
  try {
    if (action === 'save') {
      status.value = (
        await axios.put(`${base}/growth-sync-token`, { token: token.value.trim() })
      ).data
      token.value = ''
      feedback.value = '只写 Token 已保存，下次森空岛刷新成功后自动同步'
    } else if (action === 'clear') {
      status.value = (await axios.delete(`${base}/growth-sync-token`)).data
      token.value = ''
      feedback.value = '已清除本地 Token，自动同步已停止'
    } else if (action === 'sync') {
      const { data } = await axios.post(`${base}/growth-sync`, { confirmed: true })
      if (!data.success) throw new Error('同步结果未确认')
      status.value = {
        ...status.value,
        last_synced_at: data.synced_at,
        last_synced_count: data.count,
        last_sync_error: null,
        last_attempt_at: data.synced_at
      }
      feedback.value = data.message
    }
  } catch (error) {
    failed.value = true
    feedback.value = error.response?.data?.message || '操作未成功，请检查本地连接或只写 Token'
  } finally {
    busy.value = false
  }
}

onMounted(loadStatus)
</script>

<template>
  <n-card title="一图流干员同步">
    <n-space vertical :size="14">
      <n-text depth="3">
        在一图流账号页生成“干员数据写入”权限的只写 Token
        后填入。保存后，成功刷新森空岛数据时自动检查同步；与上次成功上传的内容相同则不传输。清除
        Token 即可停止。保存本身不会上传。
        <n-a href="https://ark.yituliu.cn" target="_blank" rel="noopener noreferrer"
          >打开一图流</n-a
        >
      </n-text>
      <n-input
        v-model:value="token"
        type="password"
        show-password-on="click"
        autocomplete="new-password"
        :disabled="busy"
        :placeholder="
          status.configured ? '••••••••（已保存，输入新 Token 可替换）' : '粘贴一图流只写 Token'
        "
        aria-label="一图流只写 Token"
      />
      <n-space align="center" :size="8">
        <n-button :disabled="busy || !token.trim()" @click="act('save')">保存 Token</n-button>
        <n-button :disabled="busy || !status.configured" @click="act('clear')"
          >清除本地 Token</n-button
        >
        <n-button
          type="primary"
          :disabled="busy || !status.configured || !!token.trim()"
          :loading="busy"
          @click="act('sync')"
          >立即同步</n-button
        >
        <n-tag :bordered="false" :type="status.configured ? 'success' : 'default'">
          {{ status.configured ? '自动同步已开启' : '未配置' }}
        </n-tag>
      </n-space>
      <n-alert type="info" :bordered="false">
        将当前森空岛缓存中的游戏 UID、昵称、区服和全部已拥有干员的等级、精英化、潜能、技能及模组练度
        在本地校验后上传至一图流，更新对应账号的干员数据；与上次成功上传的内容相同则跳过。
        不会上传仓库、养成计划、森空岛账号密码或登录凭据。
        旧缓存缺少游戏账号信息时，请先重新同步一次森空岛。
      </n-alert>
      <n-text v-if="status.last_synced_at" depth="3">
        最近同步：{{ new Date(status.last_synced_at * 1000).toLocaleString() }} ·
        {{ status.last_synced_count }} 名干员
      </n-text>
      <n-text v-if="status.last_sync_error" type="warning">
        最近一次同步未完成：{{ status.last_sync_error }}
      </n-text>
      <n-text v-if="feedback" :type="failed ? 'error' : 'success'" aria-live="polite">
        {{ feedback }}
      </n-text>
    </n-space>
  </n-card>
</template>
