<script setup>
import { inject, ref } from 'vue'
const axios = inject('axios')
const busy = ref(false)
const status = ref('由安卓版自动管理，无需填写地址或安装路径。')
async function check() {
  busy.value = true
  try { const { data } = await axios.get(`${import.meta.env.VITE_HTTP_URL}/check-maa`); status.value = data.message }
  catch { status.value = '连接失败，请在手机上启动服务并完成 Shizuku 授权。' }
  finally { busy.value = false }
}
</script>
<template>
  <n-alert type="success" :show-icon="false" style="margin-bottom: 18px">
    <n-flex align="center" justify="space-between">
      <strong>安卓后台连接</strong><n-tag type="success" size="small" :bordered="false">已接管</n-tag>
    </n-flex>
    <div style="margin: 8px 0 12px; line-height: 1.7">后台明日方舟 · 自动截图与触控 · 官方 Android ARM64 MAA</div>
    <n-flex align="center"><router-link to="/android-settings"><n-button>后台与系统设置</n-button></router-link><n-button size="small" :loading="busy" @click="check">测试连接</n-button><span>{{ status }}</span></n-flex>
  </n-alert>
</template>
