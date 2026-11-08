<script setup>
import { computed, onMounted } from 'vue'
import { storeToRefs } from 'pinia'
import { useMessage } from 'naive-ui'
import { useConfigStore } from '@/stores/config'

const store = useConfigStore()
const { maa_event_shop: settings, shop_list, item_list } = storeToRefs(store)
const message = useMessage()
const blacklistOptions = computed(() => {
  const names = new Set(['数据增补条', '数据增补仪', '家具零件'])
  for (const option of [...(shop_list.value || []), ...(item_list.value || [])]) {
    names.add(option.value)
  }
  return [...names].map((name) => ({ label: name, value: name }))
})
async function refresh() {
  try {
    await store.load_item()
  } catch (error) {
    message.error(error.response?.data?.message || '读取活动商店设置失败')
  }
}
onMounted(refresh)
</script>

<template>
  <n-card title="活动商店兑换">
    <template #header-extra
      ><n-switch v-model:value="settings.enable" aria-label="启用活动商店兑换"
    /></template>
    <n-flex vertical :size="16">
      <n-alert :show-icon="false">
        MAA 日常结束后，自动识别当前开放的 SS
        活动；当前理智周计划包含该活动的关卡时，才进入活动商店兑换。没有当期 SS
        活动时不执行。按商品顺序兑换，遇到无限商品即停止。商品黑名单中的物品不会兑换。
      </n-alert>
      <n-form label-placement="top" :show-feedback="false">
        <n-form-item label="商品黑名单（名称关键词）">
          <n-select
            v-model:value="settings.blacklist"
            multiple
            filterable
            tag
            :options="blacklistOptions"
            placeholder="选择商品或输入名称关键词"
            aria-label="活动商店商品黑名单"
          />
        </n-form-item>
      </n-form>
      <n-text depth="3"
        >自动识别活动代币图标，定位活动和商店入口，无需填写坐标或确认文字。未识别到入口或未确认兑换页面时跳过兑换。</n-text
      >
      <n-button @click="refresh">刷新商品列表</n-button>
    </n-flex>
  </n-card>
</template>
