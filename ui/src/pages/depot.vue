<template>
  <div class="card-container">
    <n-button
      @click="copyToClipboard"
      tag="a"
      href="https://arkntools.app/#/material"
      target="_blank"
    >
      明日方舟工具箱代码 点击复制
    </n-button>
    <n-divider />

    <n-grid cols="1" responsive="screen">
      <n-gi>
        <n-space align="center" justify="space-between">
          <n-text>
            扫描时间：{{ reportData[2] }} <br />
            注：万以下的数字并不会计入，如"龙门币 245万" "资质凭证 2万"
          </n-text>
          <n-text v-if="cultivateMsg" :type="cultivateOk ? 'success' : 'error'" depth="2" style="font-size: 12px">
            森空岛同步：{{ cultivateMsg }}
          </n-text>
        </n-space>
        <n-divider />
      </n-gi>
      <n-gi v-for="(categoryItems, categoryName) in sortedReportData" :key="categoryName">
        <n-h2>{{ categoryName.slice(1) }}</n-h2>
        <n-grid x-gap="10px" y-gap="10px" cols="2 m:6 l:6 " responsive="screen">
          <n-gi v-for="itemData in categoryItems" :key="itemData">
            <n-thing>
              <template #avatar>
                <n-avatar color="000" size="large" :src="'/depot/' + itemData['icon'] + '.webp'" />
              </template>
              <template #header>{{ itemData['key'] }}</template>
              <template #description>拥有：{{ itemData['number'] }}</template>
            </n-thing>
          </n-gi>
        </n-grid>
        <n-divider />
      </n-gi>
    </n-grid>
  </div>
</template>
<style>
.card-container {
  display: flex;
  margin: 10px, 0px, 0px, 50px;
  flex-wrap: wrap;
}
</style>
<script setup>
import { ref, onMounted, computed } from 'vue'
import { useMessage } from 'naive-ui'
import { usedepotStore } from '@/stores/depot'
const depotStore = usedepotStore()
const { getDepotinfo } = depotStore
const message = useMessage()

const reportData = ref([])
const sortedReportData = ref([])
const cultivateOk = ref(false)
const cultivateMsg = ref('')

async function fetchData() {
  const resp = await getDepotinfo()
  if (resp.depot) {
    reportData.value = resp.depot
    cultivateOk.value = resp.cultivate_ok
    cultivateMsg.value = resp.cultivate_msg
    if (resp.cultivate_ok) {
      message.success(`森空岛数据同步成功 ${resp.cultivate_msg}`)
    } else if (resp.cultivate_msg) {
      message.warning(`森空岛同步失败: ${resp.cultivate_msg}`)
    }
  } else {
    reportData.value = resp
  }
  sortReportData()
}

function sortReportData() {
  sortedReportData.value = { ...reportData.value[0] }
  for (const key in sortedReportData.value) {
    if (sortedReportData.value.hasOwnProperty(key)) {
      const innerData = sortedReportData.value[key]
      const sortedInnerData = Object.entries(innerData)
        .map(([k, v]) => ({ key: k, ...v }))
        .sort((a, b) => a.sort - b.sort)
      sortedReportData.value[key] = sortedInnerData
    }
  }
}
onMounted(fetchData)
const copyToClipboard = async () => {
  try {
    await navigator.clipboard.writeText(reportData.value[1])
    console.log('Text copied:', reportData.value[1])
  } catch (err) {
    console.error('Failed to copy text:', err)
  }
}
</script>
