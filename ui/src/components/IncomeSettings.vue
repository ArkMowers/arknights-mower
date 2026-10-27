<script setup>
import { i18n } from '@/i18n'
const { t } = i18n.global

import { inject, onMounted, reactive, ref } from 'vue'
import { incomeAlgorithms, incomeSettingsUrl, loadIncomeSettings } from '@/utils/incomeSettings'
const axios = inject('axios')
const valuation = ref(null)
const ratios = reactive({ experience: 0.9568, gold: 0.76544, order: 0.23456, efficiency: 1 })
const settingsLoading = ref(false)
const settingsBusy = ref(false)
const settingsError = ref('')
const settingsMessage = ref('')
const importInput = ref(null)
const settingsUrl = incomeSettingsUrl
const algorithm = ref(2)
function selectAlgorithm(value) {
  const preset = incomeAlgorithms.find((row) => row.value === value)
  if (preset?.ratios) Object.assign(ratios, preset.ratios)
}
function applySettings(value) {
  valuation.value = value
  Object.assign(ratios, value.ratios)
  algorithm.value = value.base_algorithm
}
async function loadSettings() {
  settingsLoading.value = true
  settingsError.value = ''
  try {
    applySettings(await loadIncomeSettings(axios))
  } catch {
    settingsError.value = t('tasks.incomeReadFailed')
  } finally {
    settingsLoading.value = false
  }
}
async function updateSettings(action, file = null) {
  if (settingsBusy.value || settingsLoading.value || !valuation.value) return
  settingsBusy.value = true
  settingsError.value = ''
  settingsMessage.value = ''
  const submitted = { ...ratios }
  try {
    let response
    if (action === 'import') {
      const body = new FormData()
      body.append('file', file)
      response = await axios.post(`${settingsUrl}/import`, body)
    } else if (action === 'reset') {
      response = await axios.delete(settingsUrl)
    } else {
      response = await axios.put(settingsUrl, {
        ratios: submitted,
        base_algorithm: algorithm.value
      })
    }
    applySettings(response.data)
    settingsMessage.value =
      action === 'import'
        ? t('tasks.valuationImportSummary', {
            updated: response.data.last_import.updated,
            added: response.data.last_import.added,
            retained: response.data.last_import.retained,
            skipped: response.data.last_import.unpriced?.length || 0
          })
        : t('tasks.incomeSaved')
  } catch (error) {
    settingsError.value = error.response?.data?.error || t('tasks.incomeSaveFailed')
  } finally {
    settingsBusy.value = false
  }
}
async function importValues(event) {
  const file = event.target.files?.[0]
  try {
    if (!file) return
    if (!file.name.toLowerCase().endsWith('.xlsx') || file.size > 2 * 1024 * 1024) {
      settingsError.value = t('tasks.incomeFileHelp')
      return
    }
    await updateSettings('import', file)
  } finally {
    event.target.value = ''
  }
}

function formatTime(at) {
  return new Date(at * 1000).toLocaleString(i18n.global.locale.value, { hour12: false })
}
onMounted(loadSettings)
</script>
<template>
  <n-card id="income-settings" :title="t('tasks.incomeSettingsTitle')">
    <n-spin :show="settingsLoading || settingsBusy">
      <p class="settings-description">{{ t('tasks.incomeSettingsHelp') }}</p>
      <div v-if="valuation" class="valuation-source">
        <span>{{ valuation.source }}</span>
        <span>{{ Object.keys(valuation.prices).length }}{{ t('tasks.valuesCountSuffix') }}</span>
        <span>{{
          valuation.imported_at ? formatTime(valuation.imported_at) : t('tasks.builtInSnapshot')
        }}</span>
      </div>
      <div class="valuation-actions">
        <input ref="importInput" type="file" accept=".xlsx" hidden @change="importValues" />
        <n-button
          secondary
          :disabled="!valuation || settingsBusy || settingsLoading"
          @click="importInput.click()"
          >{{ t('tasks.importYituliuValues') }}</n-button
        >
        <n-button quaternary :disabled="settingsBusy || settingsLoading" @click="loadSettings">{{
          t('tasks.reload')
        }}</n-button>
        <n-button
          quaternary
          :disabled="!valuation || settingsBusy || settingsLoading"
          @click="updateSettings('reset')"
          >{{ t('tasks.restoreAllDefaults') }}</n-button
        >
      </div>
      <n-text depth="3" style="font-size: 12px">
        <n-a
          href="https://ark.yituliu.cn/material/value"
          target="_blank"
          rel="noopener noreferrer"
          >{{ t('tasks.yituliuValueTable') }}</n-a
        >
        ·
        <n-a
          href="https://creativecommons.org/licenses/by-nc/4.0/deed.zh"
          target="_blank"
          rel="noopener noreferrer"
          >CC BY-NC 4.0</n-a
        >
      </n-text>
      <n-collapse style="margin-top: 14px">
        <n-collapse-item :title="t('tasks.defaultValuation')" name="default-method">
          <n-text depth="3" style="font-size: 13px; line-height: 1.8">{{
            t('tasks.defaultValuationHelp')
          }}</n-text>
        </n-collapse-item>
      </n-collapse>
      <n-divider />
      <label class="algorithm-field"
        ><span>{{ t('tasks.baseIncomeAlgorithm') }}</span
        ><n-select
          v-model:value="algorithm"
          :options="incomeAlgorithms"
          :disabled="!valuation || settingsBusy || settingsLoading"
          @update:value="selectAlgorithm"
      /></label>
      <p class="settings-description">{{ t('tasks.incomeRatiosHelp') }}</p>
      <div class="ratio-fields">
        <label
          v-for="field in [
            { key: 'experience', label: t('tasks.experienceValueRatio') },
            { key: 'gold', label: t('tasks.goldValueRatio') },
            { key: 'order', label: t('tasks.orderValueRatio') },
            { key: 'efficiency', label: t('tasks.recyclingEfficiency') }
          ]"
          :key="field.key"
        >
          <span>{{ field.label }}</span>
          <n-input-number
            v-model:value="ratios[field.key]"
            :min="field.key === 'experience' ? 0.000001 : 0"
            :max="1000"
            :disabled="
              !valuation ||
              settingsBusy ||
              settingsLoading ||
              (algorithm !== -1 && field.key !== 'efficiency')
            "
            :show-button="false"
          />
        </label>
      </div>
      <n-button
        type="primary"
        :loading="settingsBusy"
        :disabled="!valuation || settingsLoading"
        @click="updateSettings('ratios')"
        >{{ t('tasks.saveIncomeSettings') }}</n-button
      >
      <n-alert v-if="settingsError" type="error" class="settings-feedback">{{
        settingsError
      }}</n-alert>
      <p v-if="settingsMessage" class="settings-feedback">{{ settingsMessage }}</p>
    </n-spin>
  </n-card>
</template>
<style scoped>
.settings-description,
.valuation-source {
  font-size: 13px;
  line-height: 1.8;
  opacity: 0.75;
}
.settings-description {
  margin: 0 0 14px;
}
.algorithm-field {
  display: grid;
  min-width: 0;
  grid-template-columns: minmax(0, 1fr);
  gap: 8px;
  margin-bottom: 12px;
}
.valuation-source,
.valuation-actions {
  display: flex;
  flex-wrap: wrap;
  gap: 12px;
  margin: 12px 0;
}
.ratio-fields {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 16px;
  margin: 18px 0;
}
.ratio-fields label {
  display: grid;
  gap: 8px;
  font-size: 13px;
  min-width: 0;
}
.settings-feedback {
  margin-top: 12px;
}
@media (max-width: 480px) {
  .ratio-fields {
    grid-template-columns: 1fr;
  }
}
</style>
