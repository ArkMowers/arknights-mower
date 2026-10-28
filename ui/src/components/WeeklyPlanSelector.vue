<script setup>
import { i18n } from '@/i18n'
const { t } = i18n.global

import Close from '@vicons/ionicons5/es/Close'
import { storeToRefs } from 'pinia'
import { computed, ref, watch } from 'vue'
import { useConfigStore } from '@/stores/config'
import { useResourceVersionStore } from '@/stores/resourceVersion'

defineProps({
  compact: {
    type: Boolean,
    default: false
  }
})

const store = useConfigStore()
const resourceVersion = useResourceVersionStore()
const {
  maa_weekly_plan,
  maa_weekly_plan_active,
  maa_weekly_plan_options,
  maa_weekly_plan_activity_fallbacks,
  maa_weekly_plan_activity_switch_times,
  maa_weekly_plan_activity_end_times
} = storeToRefs(store)
const { update_weekly_plan_active, delete_weekly_plan, update_weekly_plan_activity_fallback } =
  store

watch(
  () => resourceVersion.info.current_version,
  async () => {
    try {
      await store.refresh_weekly_plan_metadata()
    } catch {
      error.value = t('tasks.eventEndReadFailed')
    }
  }
)

const loading = ref(false)
const error = ref('')
const localValue = ref('')
const localFallbackValue = ref(null)
const localFallbackTime = ref(null)

watch(
  maa_weekly_plan_active,
  (value) => {
    localValue.value = value || ''
  },
  { immediate: true }
)

watch(
  [
    maa_weekly_plan_active,
    maa_weekly_plan_activity_fallbacks,
    maa_weekly_plan_activity_switch_times,
    maa_weekly_plan_activity_end_times
  ],
  ([active, fallbacks, switchTimes, endTimes]) => {
    localFallbackValue.value = fallbacks?.[active] || null
    const timestamp = switchTimes?.[active] || endTimes?.[active]
    localFallbackTime.value = timestamp ? timestamp * 1000 : null
  },
  { immediate: true, deep: true }
)

const options = computed(() =>
  maa_weekly_plan_options.value.map((item) => ({
    label: item,
    value: item
  }))
)

const canDelete = computed(
  () => maa_weekly_plan_options.value.length > 1 && Boolean(maa_weekly_plan_active.value)
)
const fallbackOptions = computed(() =>
  options.value.filter((option) => option.value !== maa_weekly_plan_active.value)
)
const hasFallbackTarget = computed(() => Boolean(localFallbackValue.value))
const fallbackTimeIsCustom = computed(() =>
  Boolean(maa_weekly_plan_activity_switch_times.value?.[maa_weekly_plan_active.value])
)

function handleInputKeydown(event) {
  if (event.key === 'Enter') {
    event.preventDefault()
    handleEnter()
  }
}

async function applyPlan(value, isNew = false) {
  const key = typeof value === 'string' ? value.trim() : ''
  if (!key) {
    error.value = t('tasks.weeklyPlanNameRequired')
    localValue.value = maa_weekly_plan_active.value || ''
    return
  }

  loading.value = true
  error.value = ''
  try {
    await update_weekly_plan_active(key, isNew ? maa_weekly_plan.value : undefined)
    localValue.value = key
  } catch (e) {
    error.value = e?.response?.data?.error || e?.message || String(e)
    localValue.value = maa_weekly_plan_active.value || ''
  } finally {
    loading.value = false
  }
}

async function handleSelect(value) {
  if (!value || value === maa_weekly_plan_active.value) {
    localValue.value = value || maa_weekly_plan_active.value || ''
    return
  }
  await applyPlan(value, false)
}

async function handleEnter() {
  const key = localValue.value.trim()
  if (!key || key === maa_weekly_plan_active.value) {
    return
  }
  const isExisting = maa_weekly_plan_options.value.includes(key)
  await applyPlan(key, !isExisting)
}

async function handleDelete() {
  if (!canDelete.value) {
    return
  }
  loading.value = true
  error.value = ''
  try {
    await delete_weekly_plan(maa_weekly_plan_active.value)
  } catch (e) {
    error.value = e?.response?.data?.error || e?.message || String(e)
  } finally {
    loading.value = false
  }
}

async function handleFallback(value) {
  loading.value = true
  error.value = ''
  try {
    await update_weekly_plan_activity_fallback(value || '')
    localFallbackValue.value = value || null
  } catch (e) {
    error.value = e?.response?.data?.error || e?.message || String(e)
    localFallbackValue.value =
      maa_weekly_plan_activity_fallbacks.value?.[maa_weekly_plan_active.value] || null
  } finally {
    loading.value = false
  }
}

async function handleFallbackTime(value) {
  if (!localFallbackValue.value) {
    return
  }
  loading.value = true
  error.value = ''
  try {
    await update_weekly_plan_activity_fallback(
      localFallbackValue.value,
      value == null ? null : Math.floor(value / 1000)
    )
  } catch (e) {
    error.value = e?.response?.data?.error || e?.message || String(e)
    const timestamp =
      maa_weekly_plan_activity_switch_times.value?.[maa_weekly_plan_active.value] ||
      maa_weekly_plan_activity_end_times.value?.[maa_weekly_plan_active.value]
    localFallbackTime.value = timestamp ? timestamp * 1000 : null
  } finally {
    loading.value = false
  }
}
</script>

<template>
  <div class="weekly-plan-row" :class="{ compact }">
    <div class="weekly-plan-label">{{ compact ? t('tasks.plan') : t('tasks.weeklyPlanName') }}</div>
    <n-auto-complete
      v-model:value="localValue"
      class="weekly-plan-input"
      :options="options"
      menu-trigger="focus"
      :input-props="{
        placeholder: t('tasks.selectOrCreatePlan'),
        onKeydown: handleInputKeydown
      }"
      :loading="loading"
      clearable
      @select="handleSelect"
    />
    <n-button
      quaternary
      circle
      class="delete-plan-button"
      :disabled="!canDelete || loading"
      @click="handleDelete"
    >
      <template #icon>
        <n-icon :component="Close" />
      </template>
    </n-button>
    <div class="weekly-plan-label fallback-label">{{ t('tasks.switchPlan') }}</div>
    <n-select
      :value="localFallbackValue"
      class="weekly-plan-input"
      :options="fallbackOptions"
      :loading="loading"
      :disabled="!fallbackOptions.length"
      clearable
      :placeholder="
        fallbackOptions.length ? t('tasks.switchToPlan') : t('tasks.createAnotherPlanFirst')
      "
      @update:value="handleFallback"
    />
    <span class="fallback-note" :title="t('tasks.eventPlanSwitchHelp')">{{
      t('tasks.automatic')
    }}</span>
    <div class="weekly-plan-label fallback-label">{{ t('tasks.switchTime') }}</div>
    <n-date-picker
      :value="localFallbackTime"
      class="weekly-plan-input fallback-time"
      type="datetime"
      clearable
      :disabled="!hasFallbackTarget || loading"
      :placeholder="t('tasks.eventEndNotDetected')"
      @update:value="handleFallbackTime"
    />
    <span class="fallback-note" :title="t('tasks.switchTimeHelp')">
      {{ fallbackTimeIsCustom ? t('tasks.custom') : t('tasks.default') }}
    </span>
    <div v-if="error" class="selector-error">{{ error }}</div>
  </div>
</template>

<style scoped lang="scss">
.weekly-plan-row {
  display: grid;
  grid-template-columns: 88px minmax(0, 1fr) 32px;
  align-items: center;
  gap: 8px;
  width: 100%;
}

.weekly-plan-row.compact {
  grid-template-columns: 48px minmax(0, 1fr) 32px;
}

.weekly-plan-label {
  white-space: nowrap;
}

.weekly-plan-input {
  min-width: 0;
}

.delete-plan-button {
  justify-self: end;
}

.fallback-label,
.fallback-note {
  font-size: 12px;
  opacity: 0.65;
}

.fallback-note {
  text-align: center;
}

.fallback-time {
  width: 100%;
}

.selector-error {
  grid-column: 2 / 4;
  color: #d03050;
  font-size: 12px;
}
</style>
