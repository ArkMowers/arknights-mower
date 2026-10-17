<script setup>
import { inject, ref, computed } from 'vue'
import { copyMowerTestText } from '../utils/copyMowerTestText'
const axios = inject('axios')

import { useConfigStore } from '@/stores/config'
const store = useConfigStore()

import { storeToRefs } from 'pinia'
const { skland_enable, skland_info } = storeToRefs(store)

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
  maa_msg.value = '正在测试……'
  try {
    const response = await axios.get(`${import.meta.env.VITE_HTTP_URL}/check-skland`)
    maa_msg.value = Array.isArray(response.data)
      ? response.data.join('\n')
      : String(response.data ?? '')
  } catch (error) {
    maa_msg.value = `测试失败：${error.response?.data?.message || error.message || String(error)}`
  } finally {
    testing.value = false
  }
}

async function copy_result() {
  if (!maa_msg.value) return
  copying.value = true
  try {
    copy_status.value = (await copyMowerTestText(maa_msg.value))
      ? '已复制'
      : '复制失败，请手动选择文字'
  } catch {
    copy_status.value = '复制失败，请手动选择文字'
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
      <div class="card-title">森空岛账号</div>
      <help-text>
        <div>连接失败时，请尝试：</div>
        <ol style="margin: 0">
          <li>同步系统时间后再试；</li>
          <li>检查账号密码是否正确；</li>
          <li>关闭代理软件或设置分流规则；</li>
          <li>登录森空岛App，查看是否需要人机验证。</li>
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
            placeholder="账号"
          />
          <n-input
            v-model:value="value.password"
            type="password"
            show-password-on="click"
            placeholder="密码"
          />
        </div>
      </template>
    </n-dynamic-input>
    <div class="misc-container">
      <n-button :disabled="!enable_test || testing" :loading="testing" @click="test_maa"
        >测试设置</n-button
      >
      <n-button :disabled="!maa_msg || testing || copying" @click="copy_result">复制结果</n-button>
      <span aria-live="polite">{{ copy_status }}</span>
      <n-card
        content-scrollable
        style="max-height: 230px; min-width: 320px; max-width: 100%; flex: 1"
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
.misc-container {
  margin-top: 12px;
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 12px;
}
</style>
