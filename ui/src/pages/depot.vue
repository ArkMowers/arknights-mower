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
      <n-gi> 扫描时间：{{ reportData[2] }} <n-divider /></n-gi>
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
import { usedepotStore } from '@/stores/depot'
const depotStore = usedepotStore()
const { getDepotinfo } = depotStore

const reportData = ref([])
let sortedReportData = ref([])
async function fetchData() {
  reportData.value = await getDepotinfo()
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
