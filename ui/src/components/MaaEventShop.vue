<script setup>
import { computed, inject, onMounted, ref } from 'vue'
import { storeToRefs } from 'pinia'
import { useMessage } from 'naive-ui'
import { useConfigStore } from '@/stores/config'

const { maa_event_shop: settings } = storeToRefs(useConfigStore())
const axios = inject('axios')
const message = useMessage()
const base = import.meta.env.VITE_HTTP_URL || ''
const shops = ref([])
const fallbacks = ref({})
const plans = ref([])
const selected = computed(() =>
  shops.value.find((item) => item.activity === settings.value.activity)
)
const activityOptions = computed(() =>
  shops.value.map((item) => ({ label: item.activity, value: item.activity }))
)
const sourceOptions = computed(() => plans.value.map((name) => ({ label: name, value: name })))
const source = computed({
  get: () => settings.value.switch_source,
  set: (value) => (settings.value.switch_source = value || '')
})
const target = computed(() => fallbacks.value[settings.value.switch_source] || '')
async function refresh() {
  try {
    const [navigation, weekly] = await Promise.all([
      axios.get(`${base}/maa-event-shop`),
      axios.get(`${base}/weekly-plans`)
    ])
    shops.value = navigation.data.shops
    fallbacks.value = weekly.data.activity_fallbacks || {}
    plans.value = weekly.data.plans || []
  } catch (error) {
    message.error(error.response?.data?.message || '读取活动商店与方案失败')
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
        日常结束后进入所选活动的商店，按商品顺序兑换，遇到无限商品即停止。商品黑名单中的物品不会兑换。
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
          <n-dynamic-tags v-model:value="settings.blacklist" :max="64" />
        </n-form-item>
        <n-form-item label="有限商品兑换完毕后切换的源方案">
          <n-select
            v-model:value="source"
            :options="sourceOptions"
            clearable
            placeholder="不切换方案"
            @update:show="(show) => show && refresh()"
          />
        </n-form-item>
      </n-form>
      <n-alert v-if="settings.switch_source" :show-icon="false" :type="target ? 'info' : 'warning'">
        <template v-if="target"
          >结束后方案：{{
            target
          }}。与刷理智中的定时切换共用此目标，任一条件先满足即切换。</template
        >
        <template v-else
          >请先在刷理智中为“{{ settings.switch_source }}”选择结束后方案，否则不会切换。</template
        >
        仅在当前仍使用源方案时生效；任务中断、货币不足或期间已切换方案均不会再次切换。
      </n-alert>
      <n-text depth="3"
        >入口坐标取自活动首页。确认文字应为商店内的专有标题；活动关闭后不会点击入口。尚无资源适配的活动仅在关卡开放期可选，商店延长开放期需资源包提供时间。</n-text
      >
      <n-button @click="refresh">刷新活动与方案</n-button>
    </n-flex>
  </n-card>
</template>
