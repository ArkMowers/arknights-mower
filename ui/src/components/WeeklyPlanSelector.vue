<script setup>
import Close from '@vicons/ionicons5/Close'
import { storeToRefs } from 'pinia'
import { computed, ref, watch } from 'vue'
import { useConfigStore } from '@/stores/config'

defineProps({
  compact: {
    type: Boolean,
    default: false
  }
})

const store = useConfigStore()
const {
  maa_weekly_plan,
  maa_weekly_plan_active,
  maa_weekly_plan_options,
  maa_weekly_plan_activity_fallbacks
} = storeToRefs(store)
const { update_weekly_plan_active, delete_weekly_plan, update_weekly_plan_activity_fallback } =
  store

const loading = ref(false)
const error = ref('')
const localValue = ref('')
const localFallbackValue = ref(null)

watch(
  maa_weekly_plan_active,
  (value) => {
    localValue.value = value || ''
  },
  { immediate: true }
)

watch(
  [maa_weekly_plan_active, maa_weekly_plan_activity_fallbacks],
  ([active, fallbacks]) => {
    localFallbackValue.value = fallbacks?.[active] || null
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

function handleInputKeydown(event) {
  if (event.key === 'Enter') {
    event.preventDefault()
    handleEnter()
  }
}

async function applyPlan(value, isNew = false) {
  const key = typeof value === 'string' ? value.trim() : ''
  if (!key) {
    error.value = '周计划方案不能为空'
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
</script>

<template>
  <div class="weekly-plan-row" :class="{ compact }">
    <div class="weekly-plan-label">{{ compact ? '方案' : '周计划方案' }}</div>
    <n-auto-complete
      v-model:value="localValue"
      class="weekly-plan-input"
      :options="options"
      menu-trigger="focus"
      :input-props="{
        placeholder: '选择方案，或输入新方案名后回车',
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
    <div v-if="fallbackOptions.length" class="weekly-plan-label fallback-label">
      {{ compact ? '结束后' : '活动结束后' }}
    </div>
    <n-select
      v-if="fallbackOptions.length"
      :value="localFallbackValue"
      class="weekly-plan-input"
      :options="fallbackOptions"
      :loading="loading"
      clearable
      placeholder="自动切换到方案"
      @update:value="handleFallback"
    />
    <span
      v-if="fallbackOptions.length"
      class="fallback-note"
      title="当前方案包含的资源活动关卡全部结束后，在实际刷理智前自动切换"
    >
      自动
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

.selector-error {
  grid-column: 2 / 4;
  color: #d03050;
  font-size: 12px;
}
</style>
