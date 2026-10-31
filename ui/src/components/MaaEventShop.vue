<script setup>
import { computed, inject, onMounted, ref } from 'vue'
import { storeToRefs } from 'pinia'
import { useMessage } from 'naive-ui'
import { useConfigStore } from '@/stores/config'

const store = useConfigStore()
const { maa_event_shop: settings, shop_list, item_list } = storeToRefs(store)
const axios = inject('axios')
const message = useMessage()
const base = import.meta.env.VITE_HTTP_URL || ''
const shops = ref([])
const selected = computed(() =>
  shops.value.find((item) => item.activity === settings.value.activity)
)
const activityOptions = computed(() =>
  shops.value.map((item) => ({ label: item.activity, value: item.activity }))
)
const blacklistOptions = computed(() => {
  const names = new Set(['数据增补条', '数据增补仪', '家具零件'])
  for (const option of [...(shop_list.value || []), ...(item_list.value || [])]) {
    names.add(option.value)
  }
  return [...names].map((name) => ({ label: name, value: name }))
})
async function refresh() {
  try {
    const [navigation] = await Promise.all([axios.get(`${base}/maa-event-shop`), store.load_item()])
    shops.value = navigation.data.shops
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
        MAA
        日常结束后，仅当当前理智周计划包含所选活动的关卡时，才进入对应商店兑换。按商品顺序兑换，遇到无限商品即停止。商品黑名单中的物品不会兑换。
      </n-alert>
      <n-form label-placement="top" :show-feedback="false">
        <n-form-item label="活动">
          <n-select
            v-model:value="settings.activity"
            :options="activityOptions"
            placeholder="选择当前活动"
            @update:show="(show) => show && refresh()"
          />
        </n-form-item>
        <n-form-item label="商店入口">
          <n-checkbox v-model:checked="settings.custom_entry"
            >覆盖资源包中的入口坐标与确认文字</n-checkbox
          >
        </n-form-item>
        <template v-if="settings.custom_entry">
          <n-form-item label="入口坐标（1920 × 1080）">
            <n-flex :wrap="false">
              <n-input-number
                v-model:value="settings.x"
                :min="0"
                :max="1919"
                :precision="0"
                aria-label="商店入口 X"
              />
              <n-input-number
                v-model:value="settings.y"
                :min="0"
                :max="1079"
                :precision="0"
                aria-label="商店入口 Y"
              />
            </n-flex>
          </n-form-item>
          <n-form-item label="商店页面确认文字">
            <n-input
              v-model:value="settings.confirm_text"
              :maxlength="128"
              placeholder="填写进入商店后可见的专有标题"
            />
          </n-form-item>
        </template>
        <n-alert v-else :show-icon="false" :type="selected?.x != null ? 'info' : 'warning'">
          <template v-if="selected?.x != null"
            >资源入口：({{ selected.x }}, {{ selected.y }})；确认文字：{{
              selected.confirm_text
            }}</template
          >
          <template v-else
            >当前活动尚无商店入口资源，请覆盖入口坐标与确认文字。缺少适配或未确认页面时跳过兑换。</template
          >
        </n-alert>
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
        >入口坐标取自活动首页。确认文字应为商店内的专有标题；活动关闭后不会点击入口。尚无资源适配的活动仅在关卡开放期可选，商店延长开放期需资源包提供时间。</n-text
      >
      <n-button @click="refresh">刷新活动</n-button>
    </n-flex>
  </n-card>
</template>
