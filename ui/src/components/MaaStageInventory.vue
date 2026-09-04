<script setup>
import axios from 'axios'
import { storeToRefs } from 'pinia'
import { useMessage } from 'naive-ui'
import { computed, onMounted, ref } from 'vue'
import { useConfigStore } from '@/stores/config'
import {
  createInventoryItemOption,
  createLimitRule,
  createRatioMember,
  evaluateLimitRule,
  inventoryCount,
  previewInventorySelection,
  selectRatioMember
} from '@/utils/maa_stage_inventory'
import { WEEKDAYS } from '@/utils/maa_weekly_plan'

const message = useMessage()
const store = useConfigStore()
const {
  maa_stage_inventory_enable,
  maa_stage_limit_rules,
  maa_stage_ratio_rules,
  maa_weekly_plan
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

const currentWeekdayIndex = computed(() => {
  const day = new Date().getDay()
  return day === 0 ? 6 : day - 1
})

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
  stageOptions.value.filter((option) => selectedStageValues.value.has(option.value))
)

const limitStageOptions = computed(() => {
  const bound = new Set(maa_stage_limit_rules.value.map((rule) => rule.stage))
  return selectedStageOptions.value.map((option) => ({
    ...option,
    disabled: bound.has(option.value)
  }))
})

const previewResult = computed(() =>
  previewInventorySelection(
    currentPlanStages.value,
    maa_stage_limit_rules.value,
    maa_stage_ratio_rules.value,
    inventory.value
  )
)

function stageLabel(stage) {
  return stageOptionMap.value.get(stage)?.label || stage || '未选择关卡'
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
  return withCurrentOption(itemOptions.value, value, item?.item_name || value)
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
  return evaluateLimitRule(rule, inventory.value)
}

function memberScore(member) {
  const ratio = Number(member?.ratio) || 0
  if (ratio <= 0 || !member?.item_id) {
    return null
  }
  return inventoryCount(member, inventory.value) / ratio
}

function selectedRatioMember(rule) {
  const excludedStages = new Set(
    (rule.members || [])
      .map((member) => member.stage)
      .filter((stage) => stage && !selectedStageValues.value.has(stage))
  )
  return selectRatioMember(rule, inventory.value, excludedStages)?.member || null
}

async function loadInventoryRuleData() {
  loading.value = true
  loadError.value = ''
  try {
    const response = await axios.get(`${import.meta.env.VITE_HTTP_URL}/stage/inventory-rules`)
    stageOptions.value = Array.isArray(response.data.stages) ? response.data.stages : []
    itemOptions.value = Array.isArray(response.data.items) ? response.data.items : []
    inventory.value = response.data.inventory || {}
    inventoryUpdatedAt.value = response.data.inventory_updated_at || ''
    activityRatioSuggestion.value = response.data.activity_ratio_suggestion || null
  } catch (error) {
    loadError.value = error?.response?.data?.message || error.message || '读取库存选关数据失败'
  } finally {
    loading.value = false
  }
}

async function refreshInventory() {
  refreshing.value = true
  try {
    const response = await axios.get(`${import.meta.env.VITE_HTTP_URL}/cultivate-fetch`)
    if (!response.data?.success) {
      throw new Error(response.data?.message || '库存刷新失败')
    }
    await loadInventoryRuleData()
    message.success('库存已刷新')
  } catch (error) {
    message.error(error?.response?.data?.message || error.message || '库存刷新失败')
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
  let name = suggestion.name || '当前活动绑定'
  let suffix = 2
  while (existingNames.has(name)) {
    name = `${suggestion.name || '当前活动绑定'} ${suffix}`
    suffix += 1
  }
  suggestion.name = name
  maa_stage_ratio_rules.value.push(suggestion)
  message.success('已添加当前活动关卡与掉落物绑定')
}

onMounted(loadInventoryRuleData)
</script>

<template>
  <section class="inventory-panel">
    <n-alert v-if="loadError" type="error" :closable="false">
      {{ loadError }}
      <n-button text type="primary" @click="loadInventoryRuleData">重新读取</n-button>
    </n-alert>

    <n-spin :show="loading">
      <n-card class="overview-card" size="small">
        <n-flex justify="space-between" align="center" :wrap="true">
          <div>
            <div class="overview-title">启用库存选关</div>
            <n-text depth="3">
              只有先在列表计划或表格计划中选中的关卡才会刷取；库存规则不会自动加入关卡。
            </n-text>
          </div>
          <n-space align="center">
            <n-text v-if="inventoryUpdatedAt" depth="3" class="update-time">
              库存更新于 {{ inventoryUpdatedAt }}
            </n-text>
            <n-button :loading="refreshing" @click="refreshInventory">刷新库存</n-button>
            <n-switch v-model:value="maa_stage_inventory_enable" size="large" />
          </n-space>
        </n-flex>
        <n-divider />
        <n-space vertical :size="4">
          <n-text depth="3">• 刷理智前刷新库存；物品上限优先于比例。</n-text>
          <n-text depth="3">• 上限填 0 表示该物品不限上限。</n-text>
          <n-text depth="3">• 比例填 0 表示该关卡不参与比例关系计算。</n-text>
          <n-text depth="3">
            • 当天全部关卡都被上限规则跳过时，本次恢复原计划；当前剿灭和上次作战不参与绑定。
          </n-text>
        </n-space>
      </n-card>

      <n-alert v-if="selectedStageValues.size === 0" type="info" :closable="false" class="top-gap">
        请先在“列表计划”或“表格计划”中选择关卡，再配置库存上限或比例。
      </n-alert>

      <n-tabs type="segment" animated class="top-gap">
        <n-tab-pane name="limit" tab="物品上限">
          <n-card size="small">
            <n-flex align="center" class="add-toolbar">
              <n-select
                v-model:value="limitStageToAdd"
                class="stage-picker"
                filterable
                clearable
                :placeholder="
                  selectedStageValues.size ? '选择要绑定的关卡' : '请先在周计划中选择关卡'
                "
                :options="limitStageOptions"
              />
              <n-button type="primary" :disabled="!limitStageToAdd" @click="addLimitRule">
                添加关卡上限
              </n-button>
              <n-text depth="3">
                这里只列出周计划已经选择的关卡；绑定后自动载入常规掉落，也可添加自定义物品。
              </n-text>
            </n-flex>
          </n-card>

          <n-empty
            v-if="maa_stage_limit_rules.length === 0"
            description="尚未设置物品上限"
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
                <n-tag v-if="!selectedStageValues.has(rule.stage)" type="warning" :bordered="false">
                  周计划未选择，不会刷取
                </n-tag>
                <n-tag
                  v-else-if="limitEvaluation(rule).active"
                  :type="limitEvaluation(rule).reached ? 'error' : 'success'"
                  :bordered="false"
                >
                  {{ limitEvaluation(rule).reached ? '已达上限，将跳过' : '未达上限' }}
                </n-tag>
                <n-tag v-else :bordered="false">未设置有效上限</n-tag>
              </n-flex>
            </template>
            <template #header-extra>
              <n-button quaternary type="error" @click="removeLimitRule(ruleIndex)">
                删除
              </n-button>
            </template>

            <n-flex align="center" class="operator-row">
              <n-text>多物品规则</n-text>
              <n-radio-group v-model:value="rule.operator" size="small">
                <n-radio-button value="and">且：全部达到才跳过</n-radio-button>
                <n-radio-button value="or">或：任一达到就跳过</n-radio-button>
              </n-radio-group>
            </n-flex>

            <div class="limit-grid grid-header">
              <span>物品</span>
              <span>当前库存</span>
              <span>数量上限</span>
              <span>操作</span>
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
                placeholder="选择或输入物品"
                :options="itemOptionsFor(item)"
                :on-create="createInventoryItemOption"
                @update:value="(value) => updateItem(item, value)"
              />
              <span class="inventory-number">{{ inventoryCount(item, inventory) }}</span>
              <n-input-number v-model:value="item.limit" :min="0" :precision="0" placeholder="0" />
              <n-button
                quaternary
                type="error"
                aria-label="删除物品"
                @click="rule.items.splice(itemIndex, 1)"
              >
                删除
              </n-button>
            </div>
            <n-button dashed block class="row-add-button" @click="addLimitItem(rule)">
              添加自定义物品
            </n-button>
          </n-card>
        </n-tab-pane>

        <n-tab-pane name="ratio" tab="关卡比例">
          <n-card size="small">
            <n-flex align="center" class="add-toolbar">
              <n-button type="primary" @click="addRatioRule">新建比例规则</n-button>
              <n-button
                type="info"
                secondary
                :disabled="!activityRatioSuggestion"
                @click="applyActivityRatioSuggestion"
              >
                一键绑定活动关卡
              </n-button>
              <n-text depth="3">
                一键绑定只创建当前活动的关卡与掉落物关系，比例保持
                0；关卡仍需在周计划中选中才会刷取。
              </n-text>
            </n-flex>
          </n-card>

          <n-empty
            v-if="maa_stage_ratio_rules.length === 0"
            description="尚未设置关卡比例"
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
                <n-input v-model:value="rule.name" class="ratio-name" placeholder="比例规则名称" />
                <n-tag v-if="selectedRatioMember(rule)" type="info" :bordered="false">
                  当前优先 {{ selectedRatioMember(rule).stage }}
                </n-tag>
                <n-tag
                  v-if="
                    (rule.members || []).some(
                      (member) => member.stage && !selectedStageValues.has(member.stage)
                    )
                  "
                  type="warning"
                  :bordered="false"
                >
                  含周计划未选择的关卡
                </n-tag>
              </n-flex>
            </template>
            <template #header-extra>
              <n-button quaternary type="error" @click="removeRatioRule(ruleIndex)">
                删除
              </n-button>
            </template>

            <div class="ratio-grid grid-header">
              <span>关卡</span>
              <span>对应物品</span>
              <span>当前库存</span>
              <span>比例</span>
              <span>库存 ÷ 比例</span>
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
                placeholder="选择关卡"
                :options="ratioStageOptions(rule, memberIndex)"
                @update:value="(value) => changeRatioStage(member, value)"
              />
              <n-select
                :value="member.item_id"
                filterable
                tag
                clearable
                placeholder="选择或输入物品"
                :options="itemOptionsFor(member)"
                :on-create="createInventoryItemOption"
                @update:value="(value) => updateItem(member, value)"
              />
              <span class="inventory-number">{{ inventoryCount(member, inventory) }}</span>
              <n-input-number v-model:value="member.ratio" :min="0" placeholder="0" />
              <n-tag v-if="memberScore(member) === null" size="small" :bordered="false">
                不参与
              </n-tag>
              <span v-else class="score-number">{{ memberScore(member).toFixed(2) }}</span>
              <n-button
                quaternary
                type="error"
                aria-label="删除比例成员"
                @click="rule.members.splice(memberIndex, 1)"
              >
                删除
              </n-button>
            </div>
            <n-button dashed block class="row-add-button" @click="addRatioMember(rule)">
              添加关卡
            </n-button>
          </n-card>
        </n-tab-pane>
      </n-tabs>

      <n-card title="今日执行预览" size="small" class="top-gap preview-card">
        <template #header-extra>
          <n-tag :type="maa_stage_inventory_enable ? 'success' : 'default'" :bordered="false">
            {{ maa_stage_inventory_enable ? '库存选关已启用' : '库存选关未启用' }}
          </n-tag>
        </template>
        <n-empty
          v-if="currentPlanStages.length === 0"
          :description="`${currentWeekday}未设置刷理智关卡`"
        />
        <n-space v-else vertical :size="10">
          <div class="preview-line">
            <n-text depth="3">原计划</n-text>
            <n-space :size="6" wrap>
              <n-tag v-for="(stage, index) in currentPlanStages" :key="`${stage}-${index}`">
                {{ stageLabel(stage) }}
              </n-tag>
            </n-space>
          </div>
          <n-alert v-if="previewResult.limitFallback" type="warning" :closable="false">
            全部关卡均达到上限，本次跳过设置失效并恢复原计划。
          </n-alert>
          <div v-else-if="previewResult.limitSkipped.length" class="preview-line">
            <n-text depth="3">达到上限</n-text>
            <n-space :size="6" wrap>
              <n-tag v-for="stage in previewResult.limitSkipped" :key="stage" type="error">
                {{ stageLabel(stage) }}
              </n-tag>
            </n-space>
          </div>
          <div v-if="previewResult.ratioDecisions.length" class="preview-line">
            <n-text depth="3">比例选择</n-text>
            <n-space :size="6" wrap>
              <n-tag
                v-for="(decision, index) in previewResult.ratioDecisions"
                :key="`${decision.name}-${index}`"
                type="info"
              >
                {{ decision.name || `规则 ${index + 1}` }} → {{ decision.selected }}
              </n-tag>
            </n-space>
          </div>
          <div class="preview-line">
            <n-text depth="3">实际执行</n-text>
            <n-space :size="6" wrap>
              <n-tag
                v-for="(stage, index) in maa_stage_inventory_enable
                  ? previewResult.stages
                  : currentPlanStages"
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
  margin-bottom: 4px;
  font-size: 18px;
  font-weight: 650;
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
