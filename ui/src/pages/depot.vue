<template>
  <div>
    <n-button @click="copyToClipboard">明日方舟工具箱代码 {{ reportData[4] }}</n-button>
  </div>
  <h2>注：仅限MAA仓库扫描</h2>
  <div>仓库变化{{ reportData[2] }}</div>
  <div class="card-container">
    <n-grid x-gap="10px" y-gap="10px" cols="2 s:4 m:5 l:6 xl:8 2xl:10" responsive="screen">
      <n-gi v-for="(key, item, index) in reportData[1]" content-indented="true">
        <n-thing>
          <template #avatar>
            <n-avatar color="000" size="large" :src="'/depot/' + item + '.png'" />
          </template>
          <template #header> {{ item }} </template>
          <template #description>拥有：{{ key }} </template>
        </n-thing>
      </n-gi>
    </n-grid>
  </div>
</template>

<style>
.card-container {
  display: flex;
  flex-wrap: wrap;
}
</style>

<script setup>
const copyToClipboard = async () => {
  try {
    await navigator.clipboard.writeText(reportData.value[3])
    console.log('Text copied:', reportData.value[3])
  } catch (err) {
    console.error('Failed to copy text:', err)
  }
}
import { ref, onMounted } from 'vue'

import { usedepotStore } from '@/stores/depot'

const depotStore = usedepotStore()
const { getDepotinfo } = depotStore

// Mock report data
const reportData = ref([])
const depotinfo = reportData[0]
onMounted(async () => {
  reportData.value = await getDepotinfo()
})

document.addEventListener('DOMContentLoaded', async function () {
  await axios.get(`${import.meta.env.VITE_HTTP_URL}/depot/readdepot`)
})
</script>

<style scoped></style>
