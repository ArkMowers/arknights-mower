<template>
  <div>
    <n-button @click="copyToClipboard"> 明日方舟工具箱代码</n-button>
  </div>
  <div>这次扫描在{{ time }},下次扫描在{{ maa_gap }}小时之后。</div>
  <div>注：目前仅限MAA仓库扫描</div>
  <n-button @click="showModal = true"> 仓库变化 </n-button>

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
import { usedepotStore } from '@/stores/depot'

const depotStore = usedepotStore()
const { getDepotinfo } = depotStore
const reportData = ref([])
const time = ref('')
onMounted(async () => {
  reportData.value = await getDepotinfo()
  time.value = reportData.value[4].slice(0, -7)
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

<style scoped></style>
