<script setup>
import { operatorDisplayName, itemDisplayName } from '@/i18n/gameNames'
import { i18n } from '@/i18n'
import { computed, onMounted, onUnmounted, watch } from 'vue'
import axios from 'axios'
import { NButton, NSpace, NText } from 'naive-ui'
import { useMowerStore } from '@/stores/mower'
import { createWorkshopStatus } from '@/utils/workshopStatus'

const props = defineProps({ revision: { type: Number, default: 0 } })
const mower = useMowerStore()
const model = createWorkshopStatus(
  axios,
  `${import.meta.env.VITE_HTTP_URL}/workshop-status`,
  () => mower.running
)
const { data, stale, loading } = model
const label = computed(() => {
  if (stale.value)
    return data.value
      ? i18n.global.t('growth.workshop.craftingStatusNeedsRefresh')
      : i18n.global.t('growth.workshop.couldNotReadCraftingStatus')
  if (!data.value) return i18n.global.t('growth.workshop.loadingCraftingStatus')
  return (
    {
      idle: i18n.global.t('growth.workshop.noCraftingTasks'),
      ready: i18n.global.t('growth.workshop.readyToCraft'),
      queued: i18n.global.t('growth.workshop.queued'),
      running: i18n.global.t('growth.workshop.crafting'),
      waiting: i18n.global.t('growth.workshop.waitingForCraftingConditions'),
      stopped: i18n.global.t('growth.workshop.schedulerStopped'),
      unavailable: i18n.global.t('growth.workshop.craftingStatusUnavailable')
    }[data.value.execution] || i18n.global.t('growth.workshop.craftingStatusUnavailable')
  )
})
watch([() => props.revision, () => mower.running], model.refresh)
onMounted(model.start)
onUnmounted(model.stop)
</script>

<template>
  <n-space size="small" align="center" style="margin-top: 12px" aria-live="polite">
    <n-text
      >{{ label
      }}{{ stale ? i18n.global.t('growth.workshop.previousResultRefreshFailed') : '' }}</n-text
    >
    <n-text v-if="data?.recipe" depth="3"
      >{{ data.project_name ? `${operatorDisplayName(data.project_name)} · ` : ''
      }}{{ itemDisplayName(data.recipe) }}</n-text
    >
    <n-text v-for="(block, index) in data?.blockers || []" :key="index" depth="3">
      {{ block.operator ? `${operatorDisplayName(block.operator)}: ` : '' }}{{ block.message }}
    </n-text>
    <n-button size="tiny" text :loading="loading" @click="model.refresh">{{
      i18n.global.t('growth.workshop.refreshCraftingStatus')
    }}</n-button>
  </n-space>
</template>
