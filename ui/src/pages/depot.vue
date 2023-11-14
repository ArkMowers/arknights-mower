<template>
  <div>
    <n-card>
      <template #header>
        <Depotswitch />
      </template>

      <div class="card-container">
        <n-grid x-gap="10px" y-gap="10px" cols="1" responsive="screen">
          <n-gi><n-button @click="copyToClipboard"> 明日方舟工具箱代码</n-button></n-gi>
          <n-gi>这次扫描在{{ time }},下次扫描在{{ maa_gap }}小时之后。</n-gi>
          <n-gi>注：目前仅限MAA仓库扫描</n-gi>
          <n-gi><n-button @click="showModal = true"> 仓库变化 </n-button></n-gi>
        </n-grid>
      </div>
      <div class="card-container">
        <n-grid x-gap="10px" y-gap="10px" cols="1" responsive="screen">
          <n-gi v-for="(data, title) in cangkuwupin">
            <h2>{{ title }}</h2>
            <n-grid x-gap="10px" y-gap="10px" cols="2 m:6 l:6 " responsive="screen">
              <n-gi v-for="(key, item) in data" content-indented="true">
                <n-thing>
                  <template #avatar>
                    <n-avatar color="000" size="large" :src="'/depot/' + item + '.png'" />
                  </template>
                  <template #header>{{ item }}</template>
                  <template #description>拥有：{{ key }}</template>
                </n-thing>
              </n-gi>
            </n-grid>
          </n-gi>
        </n-grid>
      </div>

      <n-modal v-model:show="showModal">
        <n-card
          style="width: 600px"
          title="仓库变化："
          :bordered="false"
          size="huge"
          role="dialog"
          aria-modal="true"
        >
          {{ reportData[2] }}
        </n-card>
      </n-modal>
    </n-card>
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
import { ref, onMounted } from 'vue'
import { useConfigStore } from '@/stores/config'
const store = useConfigStore()

import { storeToRefs } from 'pinia'
const { maa_gap } = storeToRefs(store)

//模态框
const showModal = ref(false)

//进入网页就拿参数
document.addEventListener('DOMContentLoaded', async function () {
  await axios.get(`${import.meta.env.VITE_HTTP_URL}/depot/readdepot`)
})

//拿参数 实时同步参数
import { usedepotStore, tireCategories } from '@/stores/depot'

const depotStore = usedepotStore()
const { getDepotinfo } = depotStore

const reportData = ref([])
const time = ref('')
const tireData = [ref({}), ref({}), ref({}), ref({}), ref({}), ref({}), ref({}), ref({})]
const cangkuwupin = {
  稀有度5: tireData[0].value,
  稀有度4: tireData[1].value,
  稀有度3: tireData[2].value,
  稀有度2: tireData[3].value,
  稀有度1: tireData[4].value,
  模组: tireData[5].value,
  技能书: tireData[6].value,
  芯片: tireData[7].value
}

const sort = (tireList, targetData) => {
  for (const item of tireList) {
    if (reportData.value[1].hasOwnProperty(item)) targetData.value[item] = reportData.value[1][item]
    else targetData.value[item] = 0
  }
}

onMounted(async () => {
  reportData.value = await getDepotinfo()
  time.value = reportData.value[4].slice(0, -7)

  tireCategories.forEach((category, index) => {
    sort(category, tireData[index])
  })
})

//复制到剪贴板
const copyToClipboard = async () => {
  try {
    await navigator.clipboard.writeText(reportData.value[3])
    console.log('Text copied:', reportData.value[3])
  } catch (err) {
    console.error('Failed to copy text:', err)
  }
}
</script>
