<script setup>
import { i18n } from '@/i18n'
import { itemDisplayName } from '@/i18n/gameNames'
import { operatorSyncMessage } from '@/i18n/operatorSync'
const { t } = i18n.global

import axios from 'axios'
import { storeToRefs } from 'pinia'
import { useMessage } from 'naive-ui'
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import { useConfigStore } from '@/stores/config'
import { useResourceVersionStore } from '@/stores/resourceVersion'
import {
  applyChipLimitPreset,
  createInventoryItemOption,
  createLimitRule,
  createRatioMember,
  evaluateLimitRule,
  inventoryCount,
  previewInventorySelection,
  selectRatioMember
} from '@/utils/maa_stage_inventory'
import {
  WEEKDAYS,
  formatWeekday,
  formatStageLabel,
  getGameWeekdayIndex,
  localizeActivityStageLabel
} from '@/utils/maa_weekly_plan'

const message = useMessage()
const emit = defineEmits(['chip-limits-applied'])
const store = useConfigStore()
const resourceVersion = useResourceVersionStore()
const {
  maa_stage_inventory_enable,
  maa_stage_limit_rules,
  maa_stage_ratio_rules,
  maa_weekly_plan,
  maa_weekly_plan_active
} = storeToRefs(store)

const loading = ref(false)
const refreshing = ref(false)
const loadError = ref('')
const stageOptions = ref([])
const itemOptions = ref([])
const inventory = ref({})
const inventoryUpdatedAt = ref('')
const activityRatioSuggestion = ref(null)
const limitStageToAdd = ref(null)
const activePlanLabel = computed(() => maa_weekly_plan_active.value || t('tasks.currentPlan'))

const currentWeekdayIndex = computed(() => getGameWeekdayIndex())

const currentWeekday = computed(() => WEEKDAYS[currentWeekdayIndex.value])
const currentPlanStages = computed(() => {
  const plan = maa_weekly_plan.value.find((item) => item.weekday === currentWeekday.value)
  return Array.isArray(plan?.stage) ? plan.stage : []
})

const stageOptionMap = computed(
  () => new Map(stageOptions.value.map((option) => [option.value, option]))
)
const itemOptionMap = computed(
  () => new Map(itemOptions.value.map((option) => [option.value, option]))
)
const itemAliasMap = computed(() => {
  const aliases = new Map()
  for (const option of itemOptions.value) {
    const itemId = String(option?.id || option?.value || '').trim()
    if (!itemId) {
      continue
    }
    for (const alias of [option.value, option.id, option.name, option.label]) {
      const normalized = String(alias || '').trim()
      if (normalized) {
        aliases.set(normalized, itemId)
      }
    }
  }
  return aliases
})

const selectedStageValues = computed(() => {
  const selected = new Set()
  for (const plan of maa_weekly_plan.value) {
    for (const stage of Array.isArray(plan?.stage) ? plan.stage : []) {
      if (stage && stage !== 'Annihilation') {
        selected.add(stage)
      }
    }
  }
  return selected
})

const selectedStageOptions = computed(() =>
  stageOptions.value
    .filter((option) => selectedStageValues.value.has(option.value))
    .map((option) => ({
      ...option,
      label: localizeActivityStageLabel(option.label || formatStageLabel(option.value))
    }))
)

const limitStageOptions = computed(() => {
  const bound = new Set(maa_stage_limit_rules.value.map((rule) => rule.stage))
  return selectedStageOptions.value.map((option) => ({
    ...option,
    disabled: bound.has(option.value)
  }))
})

const previewResult = computed(() => {
  if (!maa_stage_inventory_enable.value) {
    return { stages: [...currentPlanStages.value], limitSkipped: [], ratioDecisions: [] }
  }
  return previewInventorySelection(
    currentPlanStages.value,
    maa_stage_limit_rules.value,
    maa_stage_ratio_rules.value,
    inventory.value,
    itemAliasMap.value
  )
})

function stageLabel(stage) {
  return (
    localizeActivityStageLabel(stageOptionMap.value.get(stage)?.label) ||
    formatStageLabel(stage) ||
    t('tasks.noStageSelected')
  )
}

function withCurrentOption(options, value, label = value) {
  if (!value || options.some((option) => option.value === value)) {
    return options
  }
  return [{ value, label }, ...options]
}

function stageOptionsFor(value) {
  return withCurrentOption(selectedStageOptions.value, value)
}

function itemOptionsFor(item) {
  const value = String(item?.item_id || '')
  return withCurrentOption(itemOptions.value, value, item?.item_name || value).map((option) => ({
    ...option,
    label: itemDisplayName(option.id || option.value, option.name || option.label)
  }))
}

function ratioStageOptions(rule, memberIndex) {
  const used = new Set(
    (rule.members || [])
      .filter((_, index) => index !== memberIndex)
      .map((member) => member.stage)
      .filter(Boolean)
  )
  return stageOptionsFor(rule.members?.[memberIndex]?.stage).map((option) => ({
    ...option,
    disabled: used.has(option.value)
  }))
}

function limitEvaluation(rule) {
  return evaluateLimitRule(rule, inventory.value, itemAliasMap.value)
}

function displayInventoryCount(item) {
  return inventoryCount(item, inventory.value, itemAliasMap.value)
}

function memberScore(member) {
  const ratio = Number(member?.ratio) || 0
  if (ratio <= 0 || !(member?.item_id || member?.item_name)) {
    return null
  }
  return displayInventoryCount(member) / ratio
}

function selectedRatioMember(rule) {
  const excludedStages = new Set(
    (rule.members || [])
      .map((member) => member.stage)
      .filter((stage) => stage && !selectedStageValues.value.has(stage))
  )
  return (
    selectRatioMember(
      rule,
      inventory.value,
      excludedStages,
      currentPlanStages.value,
      itemAliasMap.value
    )?.member || null
  )
}

let inventoryRequest = 0
onBeforeUnmount(() => {
  inventoryRequest += 1
})

async function loadInventoryRuleData() {
  const request = ++inventoryRequest
  loading.value = true
  loadError.value = ''
  try {
    const response = await axios.get(`${import.meta.env.VITE_HTTP_URL}/stage/inventory-rules`)
    if (request !== inventoryRequest) return
    stageOptions.value = Array.isArray(response.data.stages) ? response.data.stages : []
    itemOptions.value = Array.isArray(response.data.items) ? response.data.items : []
    inventory.value = response.data.inventory || {}
    inventoryUpdatedAt.value = response.data.inventory_updated_at || ''
    activityRatioSuggestion.value = response.data.activity_ratio_suggestion || null
  } catch (error) {
    if (request !== inventoryRequest) return
    loadError.value =
      error?.response?.data?.message || error.message || t('tasks.inventoryStageDataFailed')
  } finally {
    if (request === inventoryRequest) loading.value = false
  }
}

async function refreshInventory() {
  refreshing.value = true
  try {
    const response = await axios.get(`${import.meta.env.VITE_HTTP_URL}/cultivate-fetch`)
    if (!response.data?.success) {
      throw new Error(response.data?.message || t('tasks.inventoryRefreshFailed'))
    }
    await loadInventoryRuleData()
    message.success(t('tasks.inventoryRefreshed'))
  } catch (error) {
    message.error(
      operatorSyncMessage(
        error?.response?.data?.message || error.message || t('tasks.inventoryRefreshFailed')
      )
    )
  } finally {
    refreshing.value = false
  }
}

function addLimitRule() {
  const stageOption = stageOptionMap.value.get(limitStageToAdd.value)
  if (!stageOption) {
    return
  }
  maa_stage_limit_rules.value.push(createLimitRule(stageOption))
  limitStageToAdd.value = null
}

function applyChipLimits() {
  maa_stage_limit_rules.value = applyChipLimitPreset(
    maa_stage_limit_rules.value,
    stageOptions.value
  )
  maa_stage_inventory_enable.value = true
  emit('chip-limits-applied')
  message.success(t('tasks.chipPresetApplied'))
}

function removeLimitRule(index) {
  maa_stage_limit_rules.value.splice(index, 1)
}

function changeLimitRuleStage(rule, stage) {
  const stageOption = stageOptionMap.value.get(stage)
  rule.stage = stage
  rule.items = (stageOption?.materials || []).map((item) => ({
    item_id: item.id,
    item_name: item.name,
    limit: 0
  }))
}

function addLimitItem(rule) {
  rule.items.push({ item_id: '', item_name: '', limit: 0 })
}

function updateItem(item, value) {
  const normalized = String(value || '').trim()
  const option = itemOptionMap.value.get(normalized)
  item.item_id = normalized
  item.item_name = option?.label || normalized
}

function addRatioRule() {
  maa_stage_ratio_rules.value.push({
    name: `比例规则 ${maa_stage_ratio_rules.value.length + 1}`,
    enabled: true,
    members: [createRatioMember(), createRatioMember()]
  })
}

function removeRatioRule(index) {
  maa_stage_ratio_rules.value.splice(index, 1)
}

function addRatioMember(rule) {
  rule.members.push(createRatioMember())
}

function changeRatioStage(member, stage) {
  const stageOption = stageOptionMap.value.get(stage)
  const defaultItem = stageOption?.materials?.[0]
  member.stage = stage
  member.item_id = defaultItem?.id || ''
  member.item_name = defaultItem?.name || ''
  member.ratio = 0
}

function applyActivityRatioSuggestion() {
  if (!activityRatioSuggestion.value) {
    return
  }
  const suggestion = {
    name: activityRatioSuggestion.value.name,
    enabled: activityRatioSuggestion.value.enabled !== false,
    members: (activityRatioSuggestion.value.members || []).map((member) => ({ ...member }))
  }
  const existingNames = new Set(maa_stage_ratio_rules.value.map((rule) => rule.name))
  let name = suggestion.name || t('tasks.currentEventBinding')
  let suffix = 2
  while (existingNames.has(name)) {
    name = `${suggestion.name || t('tasks.currentEventBinding')} ${suffix}`
    suffix += 1
  }
  suggestion.name = name
  maa_stage_ratio_rules.value.push(suggestion)
  message.success(t('tasks.eventBindingAdded'))
}

watch([maa_weekly_plan_active, () => resourceVersion.info.current_version], loadInventoryRuleData, {
  immediate: true
})
</script>

<template>
  <section class="inventory-panel">
    <n-alert v-if="loadError" type="error" :closable="false">
      {{ loadError }}
      <n-button text type="primary" @click="loadInventoryRuleData">{{
        t('tasks.reload')
      }}</n-button>
    </n-alert>

    <n-spin :show="loading">
      <n-card class="overview-card" size="small">
        <n-flex justify="space-between" align="center" :wrap="true">
          <div class="overview-copy">
            <n-flex align="center" :size="8" :wrap="true">
              <div class="overview-title">{{ t('tasks.enableInventoryStages') }}</div>
              <n-tag
                type="info"
                size="small"
                :bordered="false"
                class="plan-scope-tag"
                :title="activePlanLabel"
                >{{ t('tasks.planPrefix') }}{{ activePlanLabel }}
              </n-tag>
            </n-flex>
            <n-text depth="3">{{ t('tasks.currentPlanRulesHelp') }}</n-text>
          </div>
          <n-space align="center">
            <n-text v-if="inventoryUpdatedAt" depth="3" class="update-time"
              >{{ t('tasks.inventoryUpdatedAt') }} {{ inventoryUpdatedAt }}
            </n-text>
            <n-button :loading="refreshing" @click="refreshInventory">{{
              t('tasks.refreshInventory')
            }}</n-button>
            <n-switch
              v-model:value="maa_stage_inventory_enable"
              size="large"
              :aria-label="t('tasks.enableInventoryStages')"
            />
          </n-space>
        </n-flex>
        <n-divider />
        <n-space vertical :size="4">
          <n-text depth="3">{{ t('tasks.inventoryRule1') }}</n-text>
          <n-text depth="3">{{ t('tasks.inventoryRule2') }}</n-text>
          <n-text depth="3">{{ t('tasks.inventoryRule3') }}</n-text>
          <n-text depth="3">{{ t('tasks.inventoryRule4') }}</n-text>
          <n-text depth="3">{{ t('tasks.inventoryRule5') }}</n-text>
          <n-text depth="3">{{ t('tasks.inventoryRule6') }}</n-text>
          <n-text depth="3">{{ t('tasks.inventoryRule7') }}</n-text>
        </n-space>
      </n-card>

      <n-alert v-if="!maa_stage_inventory_enable" type="info" :closable="false" class="top-gap">{{
        t('tasks.inventoryDisabledHelp')
      }}</n-alert>

      <n-alert v-if="selectedStageValues.size === 0" type="info" :closable="false" class="top-gap"
        >{{ t('tasks.selectStagesFirstBefore') }}{{ activePlanLabel
        }}{{ t('tasks.selectStagesFirstAfter') }}</n-alert
      >

      <n-tabs type="segment" class="top-gap">
        <n-tab-pane name="limit" :tab="t('tasks.itemLimits')">
          <n-card size="small">
            <n-flex align="center" class="add-toolbar">
              <n-select
                v-model:value="limitStageToAdd"
                class="stage-picker"
                filterable
                clearable
                :placeholder="
                  selectedStageValues.size
                    ? t('tasks.selectBoundStage')
                    : t('tasks.selectWeeklyStagesFirst')
                "
                :options="limitStageOptions"
              />
              <n-button type="primary" :disabled="!limitStageToAdd" @click="addLimitRule">{{
                t('tasks.addStageLimit')
              }}</n-button>
              <n-space align="center" :size="6" :wrap="false">
                <n-button
                  :disabled="loading || !!loadError || stageOptions.length === 0"
                  @click="applyChipLimits"
                  >{{ t('tasks.chipLimitsPreset') }}</n-button
                >
                <help-text :label="t('tasks.chipLimitsHelpTitle')">{{
                  t('tasks.chipLimitsHelp')
                }}</help-text>
              </n-space>
              <n-text depth="3">{{ t('tasks.selectedStagesOnlyHelp') }}</n-text>
            </n-flex>
          </n-card>

          <n-empty
            v-if="maa_stage_limit_rules.length === 0"
            :description="t('tasks.noPlanItemLimits', { plan: activePlanLabel })"
            class="empty-block"
          />

          <n-card
            v-for="(rule, ruleIndex) in maa_stage_limit_rules"
            :key="`${rule.stage}-${ruleIndex}`"
            size="small"
            class="rule-card"
          >
            <template #header>
              <n-flex align="center" :wrap="true">
                <n-switch v-model:value="rule.enabled" size="small" />
                <n-select
                  :value="rule.stage"
                  class="rule-stage-select"
                  filterable
                  :options="stageOptionsFor(rule.stage)"
                  @update:value="(value) => changeLimitRuleStage(rule, value)"
                />
                <n-tag
                  v-if="!selectedStageValues.has(rule.stage)"
                  type="warning"
                  :bordered="false"
                  >{{ t('tasks.stageNotSelected') }}</n-tag
                >
                <n-tag v-else-if="rule.enabled === false" :bordered="false">{{
                  t('tasks.ruleDisabled')
                }}</n-tag>
                <n-tag v-else-if="!maa_stage_inventory_enable" :bordered="false">{{
                  t('tasks.inventoryRuleInactive')
                }}</n-tag>
                <n-tag
                  v-else-if="limitEvaluation(rule).active"
                  :type="limitEvaluation(rule).reached ? 'error' : 'success'"
                  :bordered="false"
                >
                  {{
                    limitEvaluation(rule).reached
                      ? t('tasks.reachedWillSkip')
                      : t('tasks.belowLimit')
                  }}
                </n-tag>
                <n-tag v-else :bordered="false">{{ t('tasks.noEffectiveLimit') }}</n-tag>
              </n-flex>
            </template>
            <template #header-extra>
              <n-button quaternary type="error" @click="removeLimitRule(ruleIndex)">{{
                t('tasks.delete')
              }}</n-button>
            </template>

            <n-flex align="center" class="operator-row">
              <n-text>{{ t('tasks.multiItemRule') }}</n-text>
              <n-radio-group v-model:value="rule.operator" size="small">
                <n-radio-button value="and">{{ t('tasks.allLimitsReached') }}</n-radio-button>
                <n-radio-button value="or">{{ t('tasks.anyLimitReached') }}</n-radio-button>
              </n-radio-group>
            </n-flex>

            <div class="limit-grid grid-header">
              <span>{{ t('tasks.item') }}</span>
              <span>{{ t('tasks.currentInventory') }}</span>
              <span>{{ t('tasks.quantityLimit') }}</span>
              <span>{{ t('tasks.actions') }}</span>
            </div>
            <div
              v-for="(item, itemIndex) in rule.items"
              :key="`${ruleIndex}-${itemIndex}`"
              class="limit-grid item-row"
            >
              <n-select
                :value="item.item_id"
                filterable
                tag
                clearable
                :clear-created-options-on-clear="false"
                :placeholder="t('tasks.selectOrEnterItem')"
                :options="itemOptionsFor(item)"
                :on-create="createInventoryItemOption"
                @update:value="(value) => updateItem(item, value)"
              />
              <span class="inventory-number">{{ displayInventoryCount(item) }}</span>
              <mower-input-number
                v-model:value="item.limit"
                :min="0"
                :precision="0"
                placeholder="0"
              />
              <n-button
                quaternary
                type="error"
                :aria-label="t('tasks.deleteItem')"
                @click="rule.items.splice(itemIndex, 1)"
                >{{ t('tasks.delete') }}</n-button
              >
            </div>
            <n-button dashed block class="row-add-button" @click="addLimitItem(rule)">{{
              t('tasks.addCustomItem')
            }}</n-button>
          </n-card>
        </n-tab-pane>

        <n-tab-pane name="ratio" :tab="t('tasks.stageRatios')">
          <n-card size="small">
            <n-flex align="center" class="add-toolbar">
              <n-button type="primary" @click="addRatioRule">{{
                t('tasks.newRatioRule')
              }}</n-button>
              <n-button
                type="info"
                secondary
                :disabled="!activityRatioSuggestion"
                @click="applyActivityRatioSuggestion"
                >{{ t('tasks.bindEventStages') }}</n-button
              >
              <n-text depth="3">{{ t('tasks.bindEventStagesHelp') }}</n-text>
            </n-flex>
          </n-card>

          <n-empty
            v-if="maa_stage_ratio_rules.length === 0"
            :description="t('tasks.noPlanStageRatios', { plan: activePlanLabel })"
            class="empty-block"
          />

          <n-card
            v-for="(rule, ruleIndex) in maa_stage_ratio_rules"
            :key="`ratio-${ruleIndex}`"
            size="small"
            class="rule-card"
          >
            <template #header>
              <n-flex align="center">
                <n-switch v-model:value="rule.enabled" size="small" />
                <n-input
                  v-model:value="rule.name"
                  class="ratio-name"
                  :placeholder="t('tasks.ratioRuleName')"
                />
                <n-tag v-if="rule.enabled === false" :bordered="false">{{
                  t('tasks.ruleDisabled')
                }}</n-tag>
                <n-tag v-else-if="!maa_stage_inventory_enable" :bordered="false">{{
                  t('tasks.inventoryRuleInactive')
                }}</n-tag>
                <n-tag v-else-if="selectedRatioMember(rule)" type="info" :bordered="false"
                  >{{ t('tasks.currentPriority') }} {{ selectedRatioMember(rule).stage }}
                </n-tag>
                <n-tag
                  v-if="
                    (rule.members || []).some(
                      (member) => member.stage && !selectedStageValues.has(member.stage)
                    )
                  "
                  type="warning"
                  :bordered="false"
                  >{{ t('tasks.includesUnselectedStages') }}</n-tag
                >
              </n-flex>
            </template>
            <template #header-extra>
              <n-button quaternary type="error" @click="removeRatioRule(ruleIndex)">{{
                t('tasks.delete')
              }}</n-button>
            </template>

            <div class="ratio-grid grid-header">
              <span>{{ t('tasks.stage') }}</span>
              <span>{{ t('tasks.correspondingItem') }}</span>
              <span>{{ t('tasks.currentInventory') }}</span>
              <span>{{ t('tasks.ratio') }}</span>
              <span>{{ t('tasks.inventoryDividedRatio') }}</span>
              <span></span>
            </div>
            <div
              v-for="(member, memberIndex) in rule.members"
              :key="`${ruleIndex}-${memberIndex}`"
              class="ratio-grid item-row"
            >
              <n-select
                :value="member.stage"
                filterable
                clearable
                :placeholder="t('tasks.selectStage')"
                :options="ratioStageOptions(rule, memberIndex)"
                @update:value="(value) => changeRatioStage(member, value)"
              />
              <n-select
                :value="member.item_id"
                filterable
                tag
                clearable
                :clear-created-options-on-clear="false"
                :placeholder="t('tasks.selectOrEnterItem')"
                :options="itemOptionsFor(member)"
                :on-create="createInventoryItemOption"
                @update:value="(value) => updateItem(member, value)"
              />
              <span class="inventory-number">{{ displayInventoryCount(member) }}</span>
              <mower-input-number v-model:value="member.ratio" :min="0" placeholder="0" />
              <n-tag v-if="memberScore(member) === null" size="small" :bordered="false">{{
                t('tasks.excluded')
              }}</n-tag>
              <span v-else class="score-number">{{ memberScore(member).toFixed(2) }}</span>
              <n-button
                quaternary
                type="error"
                :aria-label="t('tasks.deleteRatioMember')"
                @click="rule.members.splice(memberIndex, 1)"
                >{{ t('tasks.delete') }}</n-button
              >
            </div>
            <n-button dashed block class="row-add-button" @click="addRatioMember(rule)">{{
              t('tasks.addStage')
            }}</n-button>
          </n-card>
        </n-tab-pane>
      </n-tabs>

      <n-card :title="t('tasks.todayPreview')" size="small" class="top-gap preview-card">
        <template #header-extra>
          <n-tag :type="maa_stage_inventory_enable ? 'success' : 'default'" :bordered="false">
            {{
              maa_stage_inventory_enable
                ? t('tasks.inventoryStagesEnabled')
                : t('tasks.inventoryStagesDisabled')
            }}
          </n-tag>
        </template>
        <n-empty
          v-if="currentPlanStages.length === 0"
          :description="t('tasks.noWeekdayStages', { weekday: formatWeekday(currentWeekday) })"
        />
        <n-space v-else vertical :size="10">
          <div class="preview-line">
            <n-text depth="3">{{ t('tasks.originalPlan') }}</n-text>
            <n-space :size="6" wrap>
              <n-tag v-for="(stage, index) in currentPlanStages" :key="`${stage}-${index}`">
                {{ stageLabel(stage) }}
              </n-tag>
            </n-space>
          </div>
          <n-alert
            v-if="!previewResult.stages.length && previewResult.limitSkipped.length"
            type="info"
            :closable="false"
            >{{ t('tasks.allLimitsReachedHelp') }}</n-alert
          >
          <div v-else-if="previewResult.limitSkipped.length" class="preview-line">
            <n-text depth="3">{{ t('tasks.limitReached') }}</n-text>
            <n-space :size="6" wrap>
              <n-tag v-for="stage in previewResult.limitSkipped" :key="stage" type="error">
                {{ stageLabel(stage) }}
              </n-tag>
            </n-space>
          </div>
          <div v-if="previewResult.ratioDecisions.length" class="preview-line">
            <n-text depth="3">{{ t('tasks.ratioSelection') }}</n-text>
            <n-space :size="6" wrap>
              <n-tag
                v-for="(decision, index) in previewResult.ratioDecisions"
                :key="`${decision.name}-${index}`"
                type="info"
              >
                {{ decision.name || t('tasks.unnamedRule', { index: index + 1 }) }} →
                {{ decision.selected }}
              </n-tag>
            </n-space>
          </div>
          <div class="preview-line">
            <n-text depth="3">{{ t('tasks.actualExecution') }}</n-text>
            <n-space :size="6" wrap>
              <n-tag
                v-for="(stage, index) in previewResult.stages"
                :key="`selected-${stage}-${index}`"
                type="success"
              >
                {{ stageLabel(stage) }}
              </n-tag>
            </n-space>
          </div>
        </n-space>
      </n-card>
    </n-spin>
  </section>
</template>

<style scoped lang="scss">
.inventory-panel {
  width: 100%;
  min-width: 0;
}

.top-gap {
  margin-top: 14px;
}

.update-time {
  font-size: 12px;
  font-variant-numeric: tabular-nums;
}

.overview-card {
  border-left: 4px solid #18a058;
}

.overview-title {
  font-size: 18px;
  font-weight: 650;
  text-wrap: balance;
}

.overview-copy {
  min-width: 0;
}

.plan-scope-tag {
  max-width: min(280px, 60vw);
}

.plan-scope-tag :deep(.n-tag__content) {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.add-toolbar {
  gap: 10px;
}

.stage-picker {
  width: min(360px, 100%);
}

.empty-block {
  margin: 40px 0;
}

.rule-card {
  margin-top: 12px;
}

.rule-stage-select {
  width: min(390px, 55vw);
}

.operator-row {
  gap: 12px;
  margin-bottom: 12px;
}

.grid-header {
  color: var(--n-text-color-3);
  font-size: 12px;
}

.limit-grid,
.ratio-grid {
  display: grid;
  align-items: center;
  gap: 8px;
  min-width: 0;
}

.limit-grid > *,
.ratio-grid > * {
  min-width: 0;
}

.limit-grid {
  grid-template-columns: minmax(180px, 1.8fr) 88px minmax(110px, 1fr) 64px;
}

.ratio-grid {
  grid-template-columns:
    minmax(0, 1fr) minmax(0, 1.25fr) 68px minmax(76px, 0.55fr)
    88px 52px;
}

.item-row {
  min-height: 48px;
  padding: 6px 0;
  border-top: 1px solid rgba(128, 128, 128, 0.14);
}

.inventory-number,
.score-number {
  font-variant-numeric: tabular-nums;
}

.inventory-number {
  font-size: 17px;
  font-weight: 650;
}

.ratio-name {
  width: min(260px, 45vw);
}

.row-add-button {
  margin-top: 8px;
}

.preview-card {
  margin-bottom: 20px;
}

.preview-line {
  display: grid;
  grid-template-columns: 72px minmax(0, 1fr);
  align-items: start;
  gap: 10px;
}

@media (max-width: 780px) {
  .update-time,
  .grid-header {
    display: none;
  }

  .add-toolbar {
    align-items: stretch !important;
    flex-direction: column;
  }

  .stage-picker,
  .rule-stage-select,
  .ratio-name {
    width: 100%;
  }

  .limit-grid,
  .ratio-grid {
    grid-template-columns: 1fr 1fr;
    gap: 8px;
    padding: 12px 0;
  }

  .limit-grid > :first-child,
  .ratio-grid > :first-child,
  .ratio-grid > :nth-child(2) {
    grid-column: 1 / -1;
  }

  .operator-row {
    align-items: flex-start !important;
    flex-direction: column;
  }

  .preview-line {
    grid-template-columns: 1fr;
    gap: 4px;
  }
}
</style>
