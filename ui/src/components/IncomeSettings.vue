<script setup>
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
    settingsError.value = '收益设置读取失败，请重试'
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
        ? `已更新 ${response.data.last_import.updated} 项价值，新增 ${response.data.last_import.added} 项，其余 ${response.data.last_import.retained} 项保留原值；跳过 ${response.data.last_import.unpriced?.length || 0} 项无有效价格的项目`
        : '收益设置已保存'
  } catch (error) {
    settingsError.value = error.response?.data?.error || '收益设置保存失败，请重新读取设置确认'
  } finally {
    settingsBusy.value = false
  }
}
async function importValues(event) {
  const file = event.target.files?.[0]
  try {
    if (!file) return
    if (!file.name.toLowerCase().endsWith('.xlsx') || file.size > 2 * 1024 * 1024) {
      settingsError.value = '请选择不超过 2 MiB 的一图流 .xlsx 物品价值表'
      return
    }
    await updateSettings('import', file)
  } finally {
    event.target.value = ''
  }
}

function formatTime(at) {
  return new Date(at * 1000).toLocaleString('zh-CN', { hour12: false })
}
onMounted(loadSettings)
</script>
<template>
  <n-card id="income-settings" title="材料价值与基报算法">
    <n-spin :show="settingsLoading || settingsBusy">
      <p class="settings-description">
        默认采用所提供计算表的材料价值、CE6 / 0.23456 算法与 SS
        活动计价（含代币折币）。导入“物品价值表”Excel
        可更新价值或添加新材料，未提供的项目保留原值。回收站与养成统计共用此设置。
      </p>
      <div v-if="valuation" class="valuation-source">
        <span>{{ valuation.source }}</span>
        <span>{{ Object.keys(valuation.prices).length }} 项价值</span>
        <span>{{ valuation.imported_at ? formatTime(valuation.imported_at) : '内置快照' }}</span>
      </div>
      <div class="valuation-actions">
        <input ref="importInput" type="file" accept=".xlsx" hidden @change="importValues" />
        <n-button
          secondary
          :disabled="!valuation || settingsBusy || settingsLoading"
          @click="importInput.click()"
          >导入一图流材料价值</n-button
        >
        <n-button quaternary :disabled="settingsBusy || settingsLoading" @click="loadSettings"
          >重新读取</n-button
        >
        <n-button
          quaternary
          :disabled="!valuation || settingsBusy || settingsLoading"
          @click="updateSettings('reset')"
          >恢复全部默认值</n-button
        >
      </div>
      <n-text depth="3" style="font-size: 12px">
        <n-a href="https://ark.yituliu.cn/material/value" target="_blank" rel="noopener noreferrer"
          >一图流物品价值表</n-a
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
        <n-collapse-item title="默认估值口径" name="default-method">
          <n-text depth="3" style="font-size: 13px; line-height: 1.8">
            龙门币按 CE6、钱书按 0.23456 算法；蓝材料按 SS 活动计价，包含代币和龙门币价值。
            扭转醇、轻锰矿、研磨石、RMA70-12 按代币等价龙门币计价。
            绿→蓝按九色鹿因果价值联立计算，蓝→紫用蚀清（18%固定异铁组副产物），紫→金用年／芳汀（20%副产物）。
            紫糖、紫酯保留加工价值。电极单元按 SS 掉率 0.7 预估，白材料等其他价值沿用所提供计算表。
          </n-text>
        </n-collapse-item>
      </n-collapse>
      <n-divider />
      <label class="algorithm-field"
        ><span>基报收益算法</span
        ><n-select
          v-model:value="algorithm"
          :options="incomeAlgorithms"
          :disabled="!valuation || settingsBusy || settingsLoading"
          @update:value="selectAlgorithm"
      /></label>
      <p class="settings-description">
        基建报表与回收站等效制造站效率使用同一组产物系数。回收站效率仅用于理论日产量换算，100% 填
        1。
      </p>
      <div class="ratio-fields">
        <label
          v-for="field in [
            { key: 'experience', label: '经验书价值比例' },
            { key: 'gold', label: '赤金价值比例' },
            { key: 'order', label: '订单价值比例' },
            { key: 'efficiency', label: '回收站效率（1 = 100%）' }
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
        >保存收益设置</n-button
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
