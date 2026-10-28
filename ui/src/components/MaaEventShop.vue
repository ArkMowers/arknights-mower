<script setup>
import { computed, inject, onMounted, ref } from 'vue'
import { storeToRefs } from 'pinia'
import { useMessage } from 'naive-ui'
import { useConfigStore } from '@/stores/config'
import { i18n } from '@/i18n'

const { t } = i18n.global

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
    message.error(error.response?.data?.message || t('maaActivities.loadFailed'))
  }
}
onMounted(refresh)
</script>

<template>
  <n-card :title="t('maaActivities.eventShopTitle')">
    <template #header-extra
      ><n-switch v-model:value="settings.enable" :aria-label="t('maaActivities.enableEventShop')"
    /></template>
    <n-flex vertical :size="16">
      <n-alert :show-icon="false">
        {{ t('maaActivities.eventShopHelp') }}
      </n-alert>
      <n-form label-placement="top" :show-feedback="false">
        <n-form-item :label="t('maaActivities.activity')">
          <n-select
            v-model:value="settings.activity"
            :options="activityOptions"
            :consistent-menu-width="false"
            :placeholder="t('maaActivities.selectActivity')"
            @update:show="(show) => show && refresh()"
          />
        </n-form-item>
        <n-form-item :label="t('maaActivities.shopEntry')">
          <n-checkbox v-model:checked="settings.custom_entry">{{
            t('maaActivities.overrideEntry')
          }}</n-checkbox>
        </n-form-item>
        <template v-if="settings.custom_entry">
          <n-form-item :label="t('maaActivities.entryCoordinates')">
            <n-flex :wrap="false">
              <n-input-number
                v-model:value="settings.x"
                :min="0"
                :max="1919"
                :precision="0"
                :aria-label="t('maaActivities.entryX')"
              />
              <n-input-number
                v-model:value="settings.y"
                :min="0"
                :max="1079"
                :precision="0"
                :aria-label="t('maaActivities.entryY')"
              />
            </n-flex>
          </n-form-item>
          <n-form-item :label="t('maaActivities.confirmationText')">
            <n-input
              v-model:value="settings.confirm_text"
              :maxlength="128"
              :placeholder="t('maaActivities.confirmationPlaceholder')"
            />
          </n-form-item>
        </template>
        <n-alert v-else :show-icon="false" :type="selected?.x != null ? 'info' : 'warning'">
          <template v-if="selected?.x != null">{{
            t('maaActivities.resourceEntry', {
              x: selected.x,
              y: selected.y,
              text: selected.confirm_text
            })
          }}</template>
          <template v-else>{{ t('maaActivities.missingEntry') }}</template>
        </n-alert>
        <n-form-item :label="t('maaActivities.blacklist')">
          <n-dynamic-tags v-model:value="settings.blacklist" :max="64" />
        </n-form-item>
        <n-form-item :label="t('maaActivities.sourcePlan')">
          <n-select
            v-model:value="source"
            :options="sourceOptions"
            :consistent-menu-width="false"
            clearable
            :placeholder="t('maaActivities.noPlanSwitch')"
            @update:show="(show) => show && refresh()"
          />
        </n-form-item>
      </n-form>
      <n-alert v-if="settings.switch_source" :show-icon="false" :type="target ? 'info' : 'warning'">
        <template v-if="target">{{ t('maaActivities.targetPlanHelp', { plan: target }) }}</template>
        <template v-else>{{
          t('maaActivities.selectFallbackHelp', { plan: settings.switch_source })
        }}</template>
        {{ t('maaActivities.switchBoundary') }}
      </n-alert>
      <n-text depth="3">{{ t('maaActivities.entryHelp') }}</n-text>
      <n-button @click="refresh">{{ t('maaActivities.refresh') }}</n-button>
    </n-flex>
  </n-card>
</template>
