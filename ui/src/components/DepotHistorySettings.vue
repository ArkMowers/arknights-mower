<script setup>
import { i18n } from '@/i18n'
import { useConfigStore } from '@/stores/config'
import { storeToRefs } from 'pinia'

const { depot_history_limit, depot_history_keep } = storeToRefs(useConfigStore())
</script>

<template>
  <n-card :title="i18n.global.t('settings.history.depotHistory')">
    <n-form class="settings-row-form" label-placement="left" :show-feedback="false">
      <n-form-item>
        <template #label>
          <span class="settings-row-copy">
            <span>{{ i18n.global.t('settings.history.historyEntriesToRead') }}</span>
            <span id="depot-history-limit-description" class="settings-row-description">
              {{ i18n.global.t('settings.history.theMaximumScanRecordsReadForDepot') }}
            </span>
          </span>
        </template>
        <mower-input-number
          v-model:value="depot_history_limit"
          :min="1"
          :max="20000"
          :input-props="{
            'aria-label': i18n.global.t('settings.history.historyEntriesToRead'),
            'aria-describedby': 'depot-history-limit-description'
          }"
        />
      </n-form-item>
      <n-form-item>
        <template #label>
          <span class="settings-row-copy">
            <span>{{ i18n.global.t('settings.history.historyEntriesToKeep') }}</span>
            <span id="depot-history-keep-description" class="settings-row-description">
              {{ i18n.global.t('settings.history.theMaximumScanRecordsKeptLocallyDelete') }}
            </span>
          </span>
        </template>
        <mower-input-number
          v-model:value="depot_history_keep"
          :min="0"
          :input-props="{
            'aria-label': i18n.global.t('settings.history.historyEntriesToKeep'),
            'aria-describedby': 'depot-history-keep-description'
          }"
        />
      </n-form-item>
    </n-form>
    <p class="depot-history-note">
      {{ i18n.global.t('settings.history.readUpTo3000RecordsBy') }}
    </p>
  </n-card>
</template>

<style scoped>
.depot-history-note {
  margin: 16px 0 0;
  padding-top: 14px;
  border-top: 1px solid var(--settings-card-border);
  color: var(--mower-text-muted);
  font-size: 12px;
  line-height: 1.65;
  text-wrap: pretty;
}
</style>
