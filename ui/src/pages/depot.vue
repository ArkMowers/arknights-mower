<template>
  <div>
    <n-card>
      <template #header>
        <n-checkbox v-model:checked="maa_depot_enable">
          <div class="card-title">MAA仓库扫描 {{ maa_depot_enable ? '开启' : '关闭' }}</div>
        </n-checkbox>
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
const { maa_gap, maa_depot_enable } = storeToRefs(store)

//模态框
const showModal = ref(false)

//进入网页就拿参数
document.addEventListener('DOMContentLoaded', async function () {
  await axios.get(`${import.meta.env.VITE_HTTP_URL}/depot/readdepot`)
})

//拿参数 实时同步参数
import { usedepotStore } from '@/stores/depot'

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

const tireCategories = [
  ['烧结核凝晶', '晶体电子单元', 'D32钢', '双极纳米片', '聚合剂'],
  [
    '提纯源岩',
    '改量装置',
    '聚酸酯块',
    '糖聚块',
    '异铁块',
    '酮阵列',
    '转质盐聚块',
    '切削原液',
    '精炼溶剂',
    '晶体电路',
    '炽合金块',
    '聚合凝胶',
    '白马醇',
    '三水锰矿',
    '五水研磨石',
    'RMA70-24'
  ],
  [
    '固源岩组',
    '全新装置',
    '聚酸酯组',
    '糖组',
    '异铁组',
    '酮凝集组',
    '转质盐组',
    '化合切削液',
    '半自然溶剂',
    '晶体元件',
    '炽合金',
    '凝胶',
    '扭转醇',
    '轻锰矿',
    '研磨石',
    'RMA70-12'
  ],
  ['固源岩', '装置', '聚酸酯', '糖', '异铁', '酮凝集'],
  ['源岩', '破损装置', '酯原料', '代糖', '异铁碎片', '双酮'],
  ['模组数据块', '数据增补仪', '数据增补条'],
  ['技巧概要·卷3', '技巧概要·卷2', '技巧概要·卷1'],
  [
    '重装双芯片',
    '重装芯片组',
    '重装芯片',
    '狙击双芯片',
    '狙击芯片组',
    '狙击芯片',
    '医疗双芯片',
    '医疗芯片组',
    '医疗芯片',
    '术师双芯片',
    '术师芯片组',
    '术师芯片',
    '先锋双芯片',
    '先锋芯片组',
    '先锋芯片',
    '近卫双芯片',
    '近卫芯片组',
    '近卫芯片',
    '辅助双芯片',
    '辅助芯片组',
    '辅助芯片',
    '特种双芯片',
    '特种芯片组',
    '特种芯片',
    '采购凭证',
    '芯片助剂'
  ]
]

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
