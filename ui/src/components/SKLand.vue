<script setup>
import { inject, ref } from 'vue'
const axios = inject('axios')

import { useConfigStore } from '@/stores/config'
const store = useConfigStore()

import { storeToRefs } from 'pinia'
const { skland_enable, skland_info } = storeToRefs(store)

function add_account() {
  return {
    isCheck: true,
    account: '',
    password: '',
    sign_in_official: true,
    sign_in_bilibili: true,
    cultivate_select: true
  }
}

const maa_msg = ref('')

async function test_maa() {
  maa_msg.value = '正在测试……'
  const response = await axios.get(`${import.meta.env.VITE_HTTP_URL}/check-skland`)
  maa_msg.value = response.data
}
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
      <n-button @click="test_maa">测试设置</n-button>
      <div>{{ maa_msg }}</div>
    </div>
  </n-card>
</template>

<style>
.card-title {
  font-weight: 500;
  font-size: 18px;
}

.misc-container {
  margin-top: 12px;
  display: flex;
  align-items: center;
  gap: 12px;
}
</style>
