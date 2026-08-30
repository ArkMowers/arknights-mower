<template>
  <div class="home-container">
    <div class="page-header">
      <h1 class="page-title">专精推荐</h1>
      <n-space align="center" :size="8">
        <n-button size="small" @click="openPlanModal">
          <template #icon><n-icon :component="ListIcon" /></template>
          专精计划
          <n-badge
            v-if="planEntries.length"
            :value="planEntries.length"
            :max="99"
            style="margin-left: 4px"
          />
        </n-button>
        <n-button size="small" @click="openSettings">
          <template #icon><n-icon :component="SettingsIcon" /></template>
          专精路线
        </n-button>
        <n-button size="small" @click="showWorkshopSettings = true">
          <template #icon><n-icon :component="SettingsIcon" /></template>
          加工站干员设置
        </n-button>
        <n-button size="small" type="warning" @click="autoWorkshop" :loading="workshopLoading">
          <template #icon><n-icon :component="HammerIcon" /></template>
          自动合成配置
        </n-button>
        <n-button size="small" @click="savePreset">保存合成配置</n-button>
        <n-button size="small" @click="restorePreset">还原合成配置</n-button>
        <n-button type="primary" size="small" @click="fetchCultivate" :loading="store.loading">
          <template #icon><n-icon :component="RefreshIcon" /></template>
          刷新
        </n-button>
        <n-text v-if="store.cultivateMsg" depth="3" style="font-size: 11px"
          >更新: {{ store.cultivateMsg }}</n-text
        >
      </n-space>
    </div>

    <div
      class="mastery-global-switch"
      style="display: flex; align-items: center; gap: 8px; margin-top: 8px"
    >
      <n-switch v-model:value="configStore.enable_mastery" size="small" />
      <n-text strong>全自动专精</n-text>
      <n-text depth="3" style="font-size: 12px"
        >关闭后暂停专精自动化（训练室动作/通知/守卫），保留仓库材料扫描</n-text
      >
    </div>

    <n-space style="margin-top: 8px" :size="8" align="center" wrap>
      <n-input
        v-model:value="searchQuery"
        placeholder="搜索干员名称"
        clearable
        style="width: 200px"
        size="small"
      />
      <n-select
        v-model:value="filterRarity"
        :options="rarityOptions"
        multiple
        placeholder="稀有度"
        style="min-width: 140px"
        size="small"
        clearable
      />
      <n-select
        v-model:value="filterProfession"
        :options="professionOptions"
        multiple
        placeholder="职业"
        style="min-width: 140px"
        size="small"
        clearable
      />
    </n-space>
    <n-space style="margin-top: 4px" :size="8" align="center" wrap>
      <n-select
        v-model:value="idleFilter"
        :options="idleFilterOptions"
        size="small"
        style="min-width: 100px"
      />
      <n-checkbox v-model:checked="showOnlyPlanned">只看计划</n-checkbox>
      <n-checkbox v-model:checked="filterAchievable">材料充足</n-checkbox>
      <n-checkbox v-model:checked="decomposeT3">缺料拆解为T3</n-checkbox>
    </n-space>

    <n-divider />

    <n-text
      v-if="store.cultivateMsg"
      :type="store.cultivateOk ? 'success' : 'error'"
      depth="2"
      style="font-size: 12px"
    >
      森空岛同步：{{ store.cultivateMsg }}
    </n-text>

    <n-spin v-if="store.loading" size="large" description="正在分析干员数据..." />
    <n-alert v-else-if="store.error" type="warning" :closable="false">
      <template #header><n-text strong>暂无干员数据</n-text></template>
      <div>{{ store.error }}</div>
      <n-button
        type="primary"
        size="small"
        style="margin-top: 12px"
        @click="fetchCultivate"
        :loading="store.loading"
        >从森空岛拉取数据</n-button
      >
    </n-alert>
    <n-empty v-else-if="displayList.length === 0" :description="emptyText" />

    <div v-else class="mastery-list">
      <!-- 计划内 T3 缺料汇总 -->
      <n-card
        v-if="plannedT3Summary.length"
        size="small"
        title="计划缺料汇总（T3）"
        style="margin-bottom: 8px"
      >
        <n-space :size="4" wrap>
          <n-tag v-for="m in plannedT3Summary" :key="m.id" type="warning" size="small">
            {{ m.name }} x{{ m.count }}
          </n-tag>
        </n-space>
      </n-card>

      <n-collapse accordion>
        <n-collapse-item v-for="op in displayList" :key="op.char_id">
          <template #header>
            <n-space align="center" :size="8">
              <n-avatar
                :src="'/avatar/' + op.name + '.webp'"
                :size="28"
                round
                fallback-src="/avatar/阿米娅.webp"
              />
              <n-text strong>{{ op.name }}</n-text>
              <n-text depth="3">({{ op.rarity }}★)</n-text>
            </n-space>
          </template>
          <template #header-extra>
            <n-space :size="4">
              <n-tag :bordered="false" size="small">{{ professionName(op.profession) }}</n-tag>
              <n-tag :bordered="false" size="small">E{{ op.elite }} Lv{{ op.level }}</n-tag>
              <n-tag v-if="hasPlannedSkill(op)" type="success" :bordered="false" size="small"
                >计划中</n-tag
              >
              <n-button
                size="tiny"
                quaternary
                type="warning"
                @click.stop="addAllToPlan(op)"
                v-if="!allPlanned(op)"
                >全加计划</n-button
              >
            </n-space>
          </template>

          <div v-for="rec in visibleRecs(op)" :key="rec.skill_index" class="rec-item">
            <n-card size="small">
              <template #header>
                <n-space align="center" justify="space-between" style="width: 100%">
                  <n-space align="center" :size="8">
                    <n-text strong>{{ rec.skill_name }} → M3</n-text>
                    <n-text depth="3" style="font-size: 12px"
                      >Lv{{ rec.current_level + 7 }}→10</n-text
                    >
                  </n-space>
                  <n-space :size="4">
                    <n-tag :type="rec.full_chain_achievable ? 'success' : 'warning'" size="small">
                      {{ rec.full_chain_achievable ? '材料充足' : '材料不足' }}
                    </n-tag>
                    <n-button
                      size="tiny"
                      :type="isSkillPlanned(op.char_id, rec.skill_index) ? 'success' : 'default'"
                      @click.stop="toggleSkillPlan(op, rec)"
                    >
                      {{ isSkillPlanned(op.char_id, rec.skill_index) ? '已计划' : '加计划' }}
                    </n-button>
                    <n-button type="primary" size="tiny" @click.stop="confirmSkill(op, rec)"
                      >一键专精</n-button
                    >
                  </n-space>
                </n-space>
              </template>
              <n-space vertical :size="4">
                <n-text depth="2"
                  >总训练时间: {{ formatTime(rec.total_time) }} |
                  {{ rec.remaining_levels }}级专精</n-text
                >
                <n-text depth="3" class="section-label">所需材料:</n-text>
                <n-grid :x-gap="8" :y-gap="4" cols="3 m:4 l:5 xl:6" responsive="screen">
                  <n-gi v-for="mat in rec.chain_needed_materials" :key="mat.id">
                    <n-thing>
                      <template #avatar>
                        <n-avatar
                          :src="'/depot/' + mat.name + '.webp'"
                          :size="24"
                          fallback-src="/depot/源岩.webp"
                        />
                      </template>
                      <template #header>
                        <n-text :depth="chainHas(rec, mat.id) ? 1 : 3" style="font-size: 11px">{{
                          mat.name
                        }}</n-text>
                      </template>
                      <template #description>
                        <n-text
                          :type="chainHas(rec, mat.id) ? 'success' : 'error'"
                          style="font-size: 11px"
                          >x{{ mat.count }}</n-text
                        >
                      </template>
                    </n-thing>
                  </n-gi>
                </n-grid>
                <div v-if="currentMissing(rec).length" class="missing-section">
                  <n-text depth="3" type="error" style="font-size: 11px"
                    >缺少{{ decomposeT3 ? '(T3拆解)' : '' }}:</n-text
                  >
                  <n-space :size="2">
                    <n-tag v-for="m in currentMissing(rec)" :key="m.id" type="error" size="small">
                      {{ m.name }}x{{ decomposeT3 ? m.count : m.count }}
                      <n-text
                        v-if="decomposeT3 && m.total"
                        depth="3"
                        style="font-size: 10px; margin-left: 2px"
                        >(需{{ m.total }}有{{ m.owned }})</n-text
                      >
                    </n-tag>
                  </n-space>
                </div>
              </n-space>
            </n-card>
          </div>
        </n-collapse-item>
      </n-collapse>
    </div>

    <!-- 确认专精 -->
    <n-modal
      v-model:show="showConfirm"
      preset="card"
      title="确认专精任务"
      style="width: min(560px, 95vw)"
      :mask-closable="false"
    >
      <n-space vertical>
        <n-text
          >干员: <n-text strong>{{ cd.op?.name }}</n-text> |
          <n-tag size="small">{{ professionName(cd.op?.profession) }}</n-tag></n-text
        >
        <n-text
          >技能: <n-text strong>{{ cd.rec?.skill_name }}</n-text> → M3 |
          {{ formatTime(cd.rec?.total_time || 0) }}</n-text
        >
        <n-divider />
        <n-text depth="2">训练室换班:</n-text>
        <n-space :size="4" style="margin-top: 4px">
          <n-tag size="small" :bordered="false">train</n-tag>
          <n-tag size="small" type="info">一号位: {{ cd.firstSupport || '当前' }}</n-tag>
          <n-tag size="small" type="warning">二号位: {{ cd.op?.name }}</n-tag>
        </n-space>
        <n-divider />
        <n-text depth="2">专精工具人:</n-text>
        <div v-if="cd.supports?.length" style="margin-top: 4px">
          <div v-for="(sup, si) in cd.supports" :key="si" class="confirm-support-row">
            <n-tag size="small" :bordered="false" type="info">专{{ sup.skill_level }}</n-tag>
            <n-text>{{ sup.name }}</n-text>
            <n-text depth="3" v-if="sup.swap_name !== sup.name">→ {{ sup.swap_name }}</n-text>
            <n-text depth="3">{{ sup.efficiency }}%</n-text>
          </div>
        </div>
        <n-text v-else depth="3">(未配置)</n-text>
        <n-divider />
        <n-text :type="cd.rec?.full_chain_achievable ? 'success' : 'warning'"
          >材料: {{ cd.rec?.full_chain_achievable ? '充足 ✓' : '不足 ✗' }}</n-text
        >
        <n-text v-if="currentMissing(cd.rec).length" style="margin-top: 4px">
          缺少:
          <n-tag
            v-for="m in currentMissing(cd.rec)"
            :key="m.id"
            type="error"
            size="small"
            style="margin-left: 4px"
            >{{ m.name }}x{{ m.count }}</n-tag
          >
        </n-text>
      </n-space>
      <template #footer>
        <n-space justify="end">
          <n-button @click="showConfirm = false">取消</n-button>
          <n-button type="primary" @click="doAddTask">确认添加任务</n-button>
        </n-space>
      </template>
    </n-modal>

    <!-- 专精路线设置 -->
    <n-modal
      v-model:show="showSettings"
      preset="card"
      title="专精路线设置"
      style="width: min(720px, 95vw)"
      :mask-closable="false"
    >
      <n-tabs type="segment" v-model:value="settingsTab">
        <n-tab-pane v-for="prof in profKeys" :key="prof" :name="prof" :tab="prof">
          <n-scrollbar style="max-height: 60vh">
            <n-dynamic-input
              v-model:value="routeSettings[prof].supports"
              :on-create="() => newSupport(prof)"
              :max="3"
            >
              <template #create-button-default>添加专精工具人</template>
              <template #default="{ value }">
                <div class="support-outer">
                  <n-select
                    v-model:value="value.skill_level"
                    :options="level_list"
                    style="width: 80px"
                  />
                  <div class="support-inner">
                    <div class="task-col">
                      <label style="font-size: 13px">协助位</label>
                      <n-select
                        v-model:value="value.name"
                        filterable
                        :options="operatorOptions"
                        :filter="(p, o) => pinyin_match(o.label, p)"
                        :render-label="render_op_label"
                        style="width: 178px"
                      />
                      <label class="ml" style="font-size: 13px">训练速度</label>
                      <n-input-number
                        v-model:value="value.efficiency"
                        :min="30"
                        :max="100"
                        style="width: 80px"
                        :show-button="false"
                        ><template #suffix>%</template></n-input-number
                      >
                    </div>
                    <div class="task-col">
                      <n-checkbox v-model:checked="value.swap">中途换人</n-checkbox>
                      <n-select
                        :disabled="!value.swap"
                        v-model:value="value.swap_name"
                        :options="swap_list"
                        :render-label="render_op_label"
                        style="width: 140px"
                      />
                      <n-select
                        :disabled="!value.swap"
                        v-model:value="value.match"
                        :options="swap_30"
                        style="width: 160px"
                      />
                    </div>
                  </div>
                </div>
              </template>
            </n-dynamic-input>
          </n-scrollbar>
          <div style="display: flex; gap: 12px; margin-top: 16px; align-items: center">
            <n-checkbox v-model:checked="routeSettings[prof].optimal">最优协助干员</n-checkbox>
            <n-checkbox v-model:checked="routeSettings[prof].half_off">有减半加成</n-checkbox>
          </div>
        </n-tab-pane>
      </n-tabs>
      <n-divider />
      <n-text depth="2">中枢干员加成</n-text>
      <div style="display: flex; align-items: center; gap: 8px; margin-top: 4px">
        <n-switch
          v-model:value="masterySettings.central_bonus"
          :checked-value="5"
          :unchecked-value="0"
        >
          <template #checked>+5%</template>
          <template #unchecked>无</template>
        </n-switch>
        <n-text depth="3" style="font-size: 11px">
          阿斯卡纶 / 烛煌 / 斩业星熊 入驻控制中枢时训练速度 +5%
        </n-text>
      </div>
      <n-text depth="2" style="margin-top: 10px">减半换人缓冲时间（分钟）</n-text>
      <n-input-number
        v-model:value="masterySettings.mastery_swap_buffer"
        :min="0"
        :max="60"
        size="small"
        style="width: 120px; margin-top: 4px"
      />
      <n-text depth="3" style="font-size: 11px; margin-top: 2px">
        减半对象需在位时间 = 5小时 + 缓冲时间，缓冲越大越保守
      </n-text>
      <template #footer>
        <n-space justify="end">
          <n-button @click="resetRoute" :disabled="routeSaving">恢复默认</n-button>
          <n-button type="primary" @click="saveRouteAndClose" :loading="routeSaving">
            保存并关闭
          </n-button>
        </n-space>
      </template>
    </n-modal>

    <!-- 专精计划 -->
    <n-modal
      v-model:show="showPlan"
      preset="card"
      title="专精计划"
      style="width: min(600px, 95vw)"
      :mask-closable="false"
      @update:show="onPlanModalShow"
    >
      <n-space vertical>
        <n-input v-model:value="planSearch" placeholder="搜索干员" clearable size="small" />
        <draggable
          v-model="sortablePlanEntries"
          item-key="key"
          handle=".drag-handle"
          @end="onPlanReorder"
        >
          <template #item="{ element: e }">
            <n-tag
              closable
              size="small"
              :type="getStatusType(e.status)"
              @close="removePlanEntry(e)"
              style="margin: 2px 4px; cursor: move"
              class="drag-handle"
            >
              {{ e.name }} {{ e.skill_name }}
              <template v-if="e.status && e.status !== 'idle'">
                ({{ getStatusLabel(e.status) }}{{ e.failed_reason ? '：' + e.failed_reason : '' }})
              </template>
            </n-tag>
          </template>
        </draggable>
        <n-text v-if="!planEntries.length" depth="3">未添加计划</n-text>
        <n-divider />
        <n-scrollbar style="max-height: 50vh">
          <div v-for="op in filteredPlanOperators" :key="op.char_id" class="plan-op-row">
            <n-space align="center" :size="4">
              <n-avatar
                :src="'/avatar/' + op.name + '.webp'"
                :size="22"
                round
                fallback-src="/avatar/阿米娅.webp"
              />
              <n-text strong style="font-size: 13px">{{ op.name }}</n-text>
              <n-text depth="3" style="font-size: 11px">{{ op.rarity }}★</n-text>
              <n-button size="tiny" quaternary @click="addAllToPlan(op, true)">全加</n-button>
            </n-space>
            <n-space :size="4" style="margin-left: 8px">
              <n-button
                v-for="rec in op.recommendations"
                :key="rec.skill_index"
                size="tiny"
                :type="isSkillPlanned(op.char_id, rec.skill_index) ? 'success' : 'default'"
                @click="toggleSkillPlan(op, rec, true)"
              >
                {{ rec.skill_name }}
              </n-button>
            </n-space>
          </div>
        </n-scrollbar>
      </n-space>
      <template #footer>
        <n-space justify="space-between">
          <n-button @click="clearPlan" size="small">清空</n-button>
          <n-button type="primary" @click="savePlanFn" size="small">保存</n-button>
        </n-space>
      </template>
    </n-modal>

    <!-- 加工站干员设置 -->
    <n-modal
      v-model:show="showWorkshopSettings"
      preset="card"
      title="加工站干员设置"
      style="width: min(500px, 95vw)"
      :mask-closable="false"
    >
      <n-space vertical>
        <div>
          <n-text depth="3">非 T5 材料加工干员</n-text>
          <help-text>
            选择 九色鹿 时会自动添加 碳素，碳素组，家具零件_碳素组 作为垫刀材料
          </help-text>
        </div>
        <slick-operator-select
          v-model="fodderOps"
          :disabled="false"
          select_placeholder="选择干员（九色鹿带垫刀材料）"
        />
        <n-text depth="3">T5 加工干员</n-text>
        <slick-operator-select v-model="t5Ops" :disabled="false" select_placeholder="选择干员" />
        <n-text depth="3">技巧概要加工干员</n-text>
        <slick-operator-select v-model="bookOps" :disabled="false" select_placeholder="选择干员" />
      </n-space>
      <template #footer>
        <n-space justify="end">
          <n-button size="small" @click="resetWorkshopDefaults">恢复默认</n-button>
          <n-button type="primary" size="small" @click="showWorkshopSettings = false"
            >保存</n-button
          >
        </n-space>
      </template>
    </n-modal>
  </div>
</template>

<script setup>
import { computed, nextTick, onMounted, reactive, ref, watch } from 'vue'
import {
  NAlert,
  NAvatar,
  NBadge,
  NButton,
  NCard,
  NCheckbox,
  NCollapse,
  NCollapseItem,
  NDivider,
  NEmpty,
  NGi,
  NGrid,
  NIcon,
  NInput,
  NInputNumber,
  NModal,
  NScrollbar,
  NSelect,
  NSpace,
  NSpin,
  NTabs,
  NTabPane,
  NTag,
  NText,
  NThing,
  NDynamicInput,
  useMessage
} from 'naive-ui'
import { Settings, List } from '@vicons/carbon'
import { Build, Refresh } from '@vicons/ionicons5'
import axios from 'axios'
import draggable from 'vuedraggable'
import { useMasteryStore } from '@/stores/mastery'
import { usePlanStore } from '@/stores/plan'
import { useConfigStore } from '@/stores/config'
import { storeToRefs } from 'pinia'
import { pinyin_match } from '@/utils/common'
import {
  buildMasteryRoutePayload,
  normalizeMasteryRouteDefaults,
  parseMasteryRoute
} from '@/utils/masteryRoute'
import { render_op_label } from '@/utils/op_select'

const ListIcon = List
const SettingsIcon = Settings
const HammerIcon = Build
const RefreshIcon = Refresh
const message = useMessage()
const store = useMasteryStore()
const planStore = usePlanStore()
const configStore = useConfigStore()
const { operators: operatorOptions } = storeToRefs(planStore)

const profKeys = ['先锋', '近卫', '重装', '狙击', '术师', '医疗', '辅助', '特种']
const profMap = {
  WARRIOR: '近卫',
  SNIPER: '狙击',
  TANK: '重装',
  MEDIC: '医疗',
  SUPPORT: '辅助',
  CASTER: '术师',
  SPECIAL: '特种',
  PIONEER: '先锋'
}
const professionName = (p) => profMap[p] || p

const rarityOptions = [
  { label: '6★', value: 6 },
  { label: '5★', value: 5 },
  { label: '4★', value: 4 }
]
const professionOptions = profKeys.map((p) => ({ label: p, value: p }))

const searchQuery = ref('')
const filterRarity = ref([])
const filterProfession = ref([])
const filterAchievable = ref(false)
const showOnlyPlanned = ref(false)
const decomposeT3 = ref(false)
// 空闲状态三态：all=全部 idle=空闲 busy=非空闲
const idleFilter = ref('all')
const idleFilterOptions = [
  { label: '全部', value: 'all' },
  { label: '空闲', value: 'idle' },
  { label: '非空闲', value: 'busy' }
]
const {
  fodder_operators: fodderOps,
  t5_operators: t5Ops,
  book_operators: bookOps
} = storeToRefs(configStore)
const workshopLoading = ref(false)
const showWorkshopSettings = ref(false)

function resetWorkshopDefaults() {
  fodderOps.value = ['九色鹿']
  t5Ops.value = ['年']
  bookOps.value = ['司霆惊蛰']
}
const workshopT3Summary = ref([])

const emptyText = computed(() => {
  if (searchQuery.value || filterRarity.value.length || filterProfession.value.length)
    return '没有匹配的干员'
  if (idleFilter.value === 'idle') return '没有空闲干员'
  if (idleFilter.value === 'busy') return '没有非空闲干员'
  if (showOnlyPlanned.value) return '没有计划中的专精项'
  return '没有推荐项'
})

// ─── 计划（技能级别）───
// 格式: { "charId_skillIndex": true, ... }
const plan = ref({})
const planStatus = ref({}) // { "charId_skillIndex": {id, status, target_level, priority, expires_at} }
const showPlan = ref(false)
const planSearch = ref('')
// 草稿式编辑：弹层内移除的 planStatus key，保存时才删后端；re-add 会移出该集合
const draftRemoved = ref(new Set())
// 保存后主动关闭弹层，不触发「关闭不保存即丢弃」的重载
let planJustSaved = false

function planKey(cid, si) {
  return `${cid}_${si}`
}
function isSkillPlanned(cid, si) {
  return !!plan.value[planKey(cid, si)]
}
function hasPlannedSkill(op) {
  return op.recommendations.some((r) => isSkillPlanned(op.char_id, r.skill_index))
}
function allPlanned(op) {
  return op.recommendations.every((r) => isSkillPlanned(op.char_id, r.skill_index))
}

function getStatusLabel(status) {
  const map = {
    idle: '待执行',
    arranging: '正在安排',
    training: '训练中',
    waiting_collect: '待收取',
    completed: '已完成',
    failed: '失败'
  }
  return map[status] || status
}

function getStatusType(status) {
  const map = {
    idle: 'default',
    arranging: 'info',
    training: 'success',
    waiting_collect: 'warning',
    completed: 'success',
    failed: 'error'
  }
  return map[status] || 'default'
}

async function toggleSkillPlan(op, rec, draft = false) {
  const k = planKey(op.char_id, rec.skill_index)
  if (plan.value[k]) {
    // 删除计划
    const info = planStatus.value[k]
    if (!draft && info && info.id) {
      try {
        await axios.delete(`${import.meta.env.VITE_HTTP_URL}/mastery-plan`, {
          data: { id: info.id }
        })
      } catch (e) {
        message.error(`删除失败: ${e.message}`)
        return
      }
    }
    delete plan.value[k]
    if (draft) {
      draftRemoved.value.add(k) // 草稿：保留 id，保存时删后端
    } else {
      delete planStatus.value[k] // 主列表 quick-add：已删后端，同步本地
    }
  } else if (draft) {
    // 弹层内草稿：只动本地，保存时 POST
    plan.value[k] = true
    draftRemoved.value.delete(k)
  } else {
    // 主列表 quick-add：立即写后端
    try {
      const body = { items: [{ name: op.name, skill_index: rec.skill_index }] }
      const r = await axios.post(`${import.meta.env.VITE_HTTP_URL}/mastery-plan`, body)
      const results = r.data?.results || []
      if (results[0]?.status === 'added') {
        plan.value[k] = true
        // #65：target_level 由服务端默认专三（与推荐一致）
        planStatus.value[k] = { id: results[0].id, status: 'idle', target_level: 3, priority: 0 }
      } else {
        message.warning(results[0]?.reason || '添加失败')
      }
    } catch (e) {
      message.error(`保存失败: ${e.message}`)
    }
  }
}

async function addAllToPlan(op, draft = false) {
  const recs = op.recommendations
  if (draft) {
    // 计划弹窗内草稿：只动本地，保存时 POST
    for (const rec of recs) {
      const k = planKey(op.char_id, rec.skill_index)
      plan.value[k] = true
      draftRemoved.value.delete(k)
    }
    message.success(`${op.name} 全部技能已加入计划`)
    return
  }
  // 主列表 quick-add：立即写后端（跳过已计划技能，后端无 (char,skill) 唯一约束，重复 POST 会建重复行）
  const toAdd = recs.filter((rec) => !plan.value[planKey(op.char_id, rec.skill_index)])
  if (!toAdd.length) {
    message.info(`${op.name} 所有推荐技能都已在计划中`)
    return
  }
  try {
    const r = await axios.post(`${import.meta.env.VITE_HTTP_URL}/mastery-plan`, {
      items: toAdd.map((rec) => ({ name: op.name, skill_index: rec.skill_index }))
    })
    const results = r.data?.results || []
    const errs = []
    results.forEach((res, i) => {
      const rec = toAdd[i]
      if (res.status === 'added') {
        const k = planKey(op.char_id, rec.skill_index)
        plan.value[k] = true
        // #65：target_level 由服务端默认专三（与推荐一致）
        planStatus.value[k] = { id: res.id, status: 'idle', target_level: 3, priority: 0 }
      } else {
        errs.push(res.reason || '添加失败')
      }
    })
    if (errs.length) {
      message.warning(`${op.name} 有 ${errs.length} 项未加入: ${errs.join('；')}`)
    } else {
      message.success(`${op.name} 全部技能已加入计划`)
    }
  } catch (e) {
    message.error(`保存失败: ${e.message}`)
  }
}

function removePlanEntry(e) {
  // 弹层内草稿式删除：只动本地，保存时删后端（planStatus 保留 id）
  delete plan.value[e.key]
  draftRemoved.value.add(e.key)
}
function clearPlan() {
  // 草稿式清空：只清本地视图，保存时才删后端计划（已挪到左侧，远离保存）
  for (const k in planStatus.value) draftRemoved.value.add(k)
  plan.value = {}
}
async function savePlanFn() {
  const toAdd = []
  for (const k in plan.value) {
    if (planStatus.value[k]?.id) continue // 已是后端计划
    const [cid, si] = parsePlanKey(k)
    const op = store.recommendations.find((o) => o.char_id === cid)
    if (op && si !== undefined) {
      // #65：不传 target_level，服务端默认专三
      toAdd.push({ name: op.name, skill_index: parseInt(si) })
    }
  }
  // 草稿中被移除且未重新加回的计划（清空/单删/技能反选）
  const toDel = [...draftRemoved.value].filter((k) => !plan.value[k] && planStatus.value[k]?.id)
  const orderUpdates = sortablePlanEntries.value
    .map((e, idx) => ({ id: planStatus.value[e.key]?.id, priority: idx }))
    .filter((u) => u.id)
  if (!toAdd.length && !toDel.length && !orderUpdates.length) {
    message.info('没有变更需要保存')
    showPlan.value = false
    return
  }
  if (toAdd.length) {
    const r = await axios.post(`${import.meta.env.VITE_HTTP_URL}/mastery-plan`, { items: toAdd })
    const results = r.data?.results || []
    const err = results.filter((x) => x.status === 'error')
    if (err.length) {
      message.warning(`保存完成，${err.length} 项失败: ${err.map((x) => x.reason).join('；')}`)
    }
  }
  for (const k of toDel) {
    try {
      await axios.delete(`${import.meta.env.VITE_HTTP_URL}/mastery-plan`, {
        data: { id: planStatus.value[k].id }
      })
    } catch (e) {
      message.error(`删除失败: ${e.message}`)
    }
  }
  if (orderUpdates.length) {
    try {
      await axios.patch(`${import.meta.env.VITE_HTTP_URL}/mastery-plan/order`, orderUpdates)
    } catch (e) {
      message.error(`排序失败: ${e.message}`)
    }
  }
  planJustSaved = true
  await refreshPlanFromServer()
  showPlan.value = false
  message.success(`计划已保存${toAdd.length ? `（新增 ${toAdd.length} 项）` : ''}`)
}

async function refreshPlanFromServer() {
  try {
    const r = await axios.get(`${import.meta.env.VITE_HTTP_URL}/mastery-plan`)
    const data = r.data || {}
    const p = {}
    const ps = {}
    for (const item of data.plans || []) {
      const k = planKey(item.char_id, item.skill_index)
      // failed 计划也要显示（带失败原因），不能从列表凭空消失（#69）
      if (item.status !== 'completed') {
        p[k] = true
      }
      ps[k] = {
        id: item.id,
        status: item.status,
        target_level: item.target_level,
        priority: item.priority,
        expires_at: item.expires_at,
        failed_reason: item.failed_reason
      }
    }
    plan.value = p
    planStatus.value = ps
    draftRemoved.value.clear() // 以服务端为准，丢弃未落库的删除意图
  } catch (e) {
    console.error('refreshPlanFromServer failed', e)
  }
}

async function openPlanModal() {
  // 打开即重载：丢弃上次未保存的草稿（与路线编辑「关闭不保存即丢弃」一致）
  await refreshPlanFromServer()
  showPlan.value = true
}

function onPlanModalShow(show) {
  if (!show && !planJustSaved) {
    refreshPlanFromServer() // 未保存关闭 → 还原草稿
  }
  planJustSaved = false
}

function parsePlanKey(k) {
  const i = k.lastIndexOf('_')
  return [k.slice(0, i), parseInt(k.slice(i + 1))]
}

const planEntries = computed(() => {
  const entries = []
  for (const k in plan.value) {
    const [cid, si] = parsePlanKey(k)
    const op = store.recommendations.find((o) => o.char_id === cid)
    if (op) {
      const rec = op.recommendations.find((r) => r.skill_index === si)
      const info = planStatus.value[k] || {}
      if (rec)
        entries.push({
          key: k,
          id: info.id,
          char_id: cid,
          skill_index: si,
          name: op.name,
          skill_name: rec.skill_name,
          status: info.status || 'idle',
          priority: info.priority || 0,
          failed_reason: info.failed_reason
        })
    }
  }
  entries.sort((a, b) => {
    // failed 计划排到列表底部（待重试，不参与正常优先级排序）
    if (a.status === 'failed' && b.status !== 'failed') return 1
    if (b.status === 'failed' && a.status !== 'failed') return -1
    return a.priority - b.priority
  })
  return entries
})

const sortablePlanEntries = ref([])
watch(
  planEntries,
  (val) => {
    sortablePlanEntries.value = [...val]
  },
  { immediate: true }
)

function onPlanReorder() {
  // 草稿式排序：只更新本地优先级，保存时才写后端
  sortablePlanEntries.value.forEach((e, idx) => {
    if (planStatus.value[e.key]) planStatus.value[e.key].priority = idx
  })
}

const filteredPlanOperators = computed(() => {
  let list = allOperatorList.value.filter((o) => hasPlannedSkill(o))
  const q = planSearch.value.trim().toLowerCase()
  if (q) list = list.filter((o) => o.name.toLowerCase().includes(q))
  return list
})

async function savePreset() {
  try {
    await axios.post(`${import.meta.env.VITE_HTTP_URL}/workshop-preset`, {
      settings: configStore.workshop_settings,
      fodder_operators: fodderOps.value,
      t5_operators: t5Ops.value,
      book_operators: bookOps.value
    })
    message.success('当前合成配置已保存为默认')
  } catch (e) {
    message.error('保存失败: ' + e.message)
  }
}
async function restorePreset() {
  try {
    const r = await axios.get(`${import.meta.env.VITE_HTTP_URL}/workshop-preset`)
    const data = r.data
    if (data && (data.settings?.length || data.length)) {
      configStore.workshop_settings = data.settings || data
      if (data.fodder_operators) fodderOps.value = data.fodder_operators
      if (data.t5_operators) t5Ops.value = data.t5_operators
      if (data.book_operators) bookOps.value = data.book_operators
      await new Promise((res) => setTimeout(res, 100))
      await axios.post(`${import.meta.env.VITE_HTTP_URL}/conf`, configStore.build_config())
      message.success('合成配置已还原')
    } else {
      message.warning('暂无已保存的合成配置')
    }
  } catch (e) {
    message.error('还原失败: ' + e.message)
  }
}

async function autoWorkshop() {
  workshopLoading.value = true
  try {
    const keys = Object.keys(plan.value).filter((k) => plan.value[k])
    const resp = await axios.post(`${import.meta.env.VITE_HTTP_URL}/workshop-auto-config`, {
      planned_skills: keys,
      fodder_operators: fodderOps.value,
      t5_operators: t5Ops.value,
      book_operators: bookOps.value
    })
    const ws = resp.data?.workshop_settings
    if (!ws) {
      message.warning('生成失败')
      return
    }
    if (keys.length === 0) {
      message.success('当前没有专精计划，已自动生成全量合成方案')
    }
    configStore.workshop_settings = ws

    await new Promise((r) => setTimeout(r, 100))
    await axios.post(`${import.meta.env.VITE_HTTP_URL}/conf`, configStore.build_config())
    workshopT3Summary.value = resp.data?.t3_summary || []

    const tasksResp = await axios.get(`${import.meta.env.VITE_HTTP_URL}/task`)
    const tasks = tasksResp.data || []
    const hasTask = (opName) =>
      tasks.some((t) => {
        const tType =
          typeof t.type === 'string' ? t.type : t.type?.display_value || t.type?.value || ''
        return tType === '加工材料' && (t.meta_data === '' || t.meta_data === opName)
      })

    let added = []
    let skipped = []
    for (const entry of ws) {
      if (!entry.operator || !entry.items?.length) continue
      const op = entry.operator
      if (hasTask(op)) {
        skipped.push(op)
        continue
      }
      const r = await axios.post(`${import.meta.env.VITE_HTTP_URL}/task`, {
        task: {
          time: new Date(Date.now() + 120000 + added.length * 600000).toISOString(),
          plan: {},
          task_type: '加工材料',
          meta_data: op
        }
      })
      if (r.data === '添加任务成功！') {
        added.push(op)
      } else {
        message.warning(`${op} 任务添加失败: ${r.data}`)
      }
    }

    const parts = []
    if (added.length) parts.push(`已添加任务: ${added.join(', ')}`)
    if (skipped.length) parts.push(`已有任务: ${skipped.join(', ')}`)
    message.success(`合成配置已生成${parts.length ? '，' + parts.join('；') : ''}`)
  } catch (e) {
    message.error(`生成失败: ${e.message}`)
  } finally {
    workshopLoading.value = false
  }
}

// ─── 专精路线设置 ───
const showSettings = ref(false)
const settingsTab = ref('近卫')
const swap_list = [
  { value: '艾丽妮', label: '艾丽妮' },
  { value: '逻各斯', label: '逻各斯' }
]
const swap_30 = [
  { value: 'yes', label: '有30%速度加成' },
  { value: 'no', label: '无训练速度加成' }
]
const level_list = [
  { value: 1, label: '专一' },
  { value: 2, label: '专二' },
  { value: 3, label: '专三' }
]
// 全局路线设置（#91 修订）：中枢加成（0/5）+ 换人缓冲时间，存路线配置设置行，不走 conf。
const masterySettings = reactive({ central_bonus: 0, mastery_swap_buffer: 10 })

const defaultsCache = ref(null)

const routeSettings = reactive(
  Object.fromEntries(profKeys.map((p) => [p, { supports: [], half_off: true }]))
)
let _autoSaveReady = false
let _routeSaveChain = Promise.resolve()
const _dirtyRouteProfessions = new Set()
let _dirtyMasterySettings = false
const routeSaving = ref(false)

function persistRouteSettings() {
  const professions = [..._dirtyRouteProfessions]
  if (!professions.length) return _routeSaveChain
  _dirtyRouteProfessions.clear()
  const payloads = professions.map((profession) =>
    buildMasteryRoutePayload(profession, routeSettings[profession])
  )
  routeSaving.value = true
  const savePromise = _routeSaveChain
    .catch(() => {})
    .then(() =>
      Promise.all(
        payloads.map((payload) =>
          axios.post(`${import.meta.env.VITE_HTTP_URL}/mastery-route`, payload)
        )
      )
    )
  _routeSaveChain = savePromise
  savePromise.then(
    () => {
      if (_routeSaveChain === savePromise) routeSaving.value = false
    },
    () => {
      professions.forEach((profession) => _dirtyRouteProfessions.add(profession))
      if (_routeSaveChain === savePromise) routeSaving.value = false
    }
  )
  return savePromise
}

// 编辑只改内存，持久化仅在「保存并关闭」触发（改错可关掉弹窗还原，不被自动保存覆盖）
function markRouteDirty(profession) {
  if (!_autoSaveReady) return
  _dirtyRouteProfessions.add(profession)
}

function flushRouteSettings() {
  return persistRouteSettings()
}

for (const profession of profKeys) {
  watch(
    () => routeSettings[profession],
    () => markRouteDirty(profession),
    { deep: true }
  )
}

// #115：modal 级中枢加成/缓冲与逐职业路线同源走草稿语义——改了不保存关掉要还原
watch(
  () => [masterySettings.central_bonus, masterySettings.mastery_swap_buffer],
  () => {
    if (_autoSaveReady) _dirtyMasterySettings = true
  }
)

function newSupport(p) {
  const n = routeSettings[p].supports.length
  if (n >= 3) return null
  const i = n + 1
  const def = defaultsCache.value
  if (def && !routeSettings[p].optimal) {
    if (i >= 3) {
      const ref = def[p]?.supports?.find((s) => s.skill_level >= 3)
      if (ref) return { ...ref, swap: true }
    }
    const backups = def._backups || {}
    const name = backups[p] || ''
    if (name) {
      return { name, skill_level: i, efficiency: 60, swap: true, swap_name: name, match: 'no' }
    }
  }
  if (def && routeSettings[p].optimal) {
    const ref = def[p]?.supports?.find((s) => s.skill_level === i)
    if (ref) return { ...ref, swap: true }
  }
  return { name: '', skill_level: i, efficiency: 60, swap: false, swap_name: '', match: 'no' }
}

function applyRoute(d) {
  for (const p of profKeys) {
    if (d[p]) {
      routeSettings[p].supports = (d[p].supports || routeSettings[p].supports).filter(Boolean)
      routeSettings[p].optimal = !!d[p].optimal
      routeSettings[p].half_off = d[p].half_off !== undefined ? d[p].half_off : true
    }
  }
}

async function loadRoute() {
  const r = await axios.get(`${import.meta.env.VITE_HTTP_URL}/mastery-route`)
  const routes = r.data?.routes || []
  const backups = r.data?.backups || {}
  const routeDefaults = r.data?.defaults || {}
  const settings = r.data?.settings || {}
  masterySettings.central_bonus = settings.central_bonus ?? 0
  masterySettings.mastery_swap_buffer = settings.mastery_swap_buffer ?? 10
  const merged = { _backups: backups }
  for (const rt of routes) {
    const parsed = parseMasteryRoute(rt)
    if (!parsed.profession) continue
    merged[parsed.profession] = parsed
  }
  merged._jsonDefaults = normalizeMasteryRouteDefaults(routeDefaults)
  // DB 未保存过此职业路线时，用默认配置兜底显示（不自动写库，编辑后由保存流程落库）
  for (const p of profKeys) {
    if (!merged[p] && merged._jsonDefaults[p]?.length) {
      merged[p] = {
        profession: p,
        supports: merged._jsonDefaults[p],
        optimal: false,
        half_off: true
      }
    }
  }
  defaultsCache.value = merged
  applyRoute(merged)
  await nextTick()
  _autoSaveReady = true
}
async function openSettings() {
  if (!defaultsCache.value) {
    try {
      await loadRoute()
    } catch (e) {
      console.error('openSettings: loadRoute failed', e)
    }
    if (!defaultsCache.value) {
      defaultsCache.value = {}
    }
  }
  showSettings.value = true
}
async function discardRouteChanges() {
  // 关闭弹窗未保存：丢弃内存修改，从 DB 重载还原。
  // _autoSaveReady 先置 false，避免还原过程（applyRoute 触发 watcher）被误标记 dirty。
  _autoSaveReady = false
  _dirtyRouteProfessions.clear()
  _dirtyMasterySettings = false
  try {
    await loadRoute()
  } catch (e) {
    _autoSaveReady = true
    throw e
  }
}
watch(showSettings, (val) => {
  if (!val && (_dirtyRouteProfessions.size || _dirtyMasterySettings)) {
    discardRouteChanges()
      .then(() => message.warning('专精路线修改未保存，已还原'))
      .catch((e) => console.error('discard route changes failed', e))
  }
})

async function saveRouteAndClose() {
  try {
    await Promise.all([
      flushRouteSettings(),
      axios.post(`${import.meta.env.VITE_HTTP_URL}/mastery-route/settings`, {
        central_bonus: masterySettings.central_bonus,
        mastery_swap_buffer: masterySettings.mastery_swap_buffer
      })
    ])
    _dirtyMasterySettings = false // 已落库，关弹窗不再触发「未保存还原」
    showSettings.value = false
    message.success('专精路线设置已保存')
  } catch (e) {
    console.error('saveRouteAndClose: failed', e)
    message.error('保存失败')
  }
}

function resetRoute() {
  const p = settingsTab.value
  if (!p) return
  const def = defaultsCache.value
  if (!def) {
    message.warning('请先关闭再打开专精路线设置')
    return
  }
  const jsonSupports = def._jsonDefaults?.[p]
  if (!jsonSupports?.length) {
    message.info('没有默认路线可恢复')
    return
  }
  routeSettings[p].supports = jsonSupports.map((s) => ({ ...s }))
  routeSettings[p].half_off = true
  routeSettings[p].optimal = false
  _dirtyRouteProfessions.add(p)
  message.success(`已恢复 ${p} 默认路线（保存并关闭后生效）`)
}

// ─── 显示列表 ───
const allOperatorList = ref([])

// ─── 空闲干员筛选 ───
// 空闲 = 不在排班表（主/副表槽位 + 候补 replacement）& 不在专精路线配置（协助位 name/换人 swap_name）
// & 不在加工站工具人 & 不在宿舍黑名单。
// 与「是否有专精计划」正交：空闲/非空闲只看基地占用，计划状态由「只看计划」管——
// 否则空闲却有计划（可正常训练）的干员会和真正非空闲却有计划（错计划）的混在一起。
// 排班由 App 启动时全局 load（router-view 以 loaded 门控，进入本页必然已加载）。
const scheduledOperatorSet = computed(() => {
  const busy = new Set()
  const plans = [planStore.plan, ...(planStore.backup_plans || []).map((b) => b.plan)]
  for (const p of plans) {
    for (const facility in p || {}) {
      for (const slot of p[facility]?.plans || []) {
        for (const agent of [slot.agent, ...(slot.replacement || [])]) {
          if (agent && agent !== 'Free' && agent !== 'Current') busy.add(agent)
        }
      }
    }
  }
  return busy
})
const routeOperatorSet = computed(() => {
  const busy = new Set()
  for (const p of profKeys) {
    for (const sup of routeSettings[p]?.supports || []) {
      if (sup.name) busy.add(sup.name)
      if (sup.swap_name) busy.add(sup.swap_name)
    }
  }
  return busy
})
const workshopOperators = computed(() => [
  ...(fodderOps.value || []),
  ...(t5Ops.value || []),
  ...(bookOps.value || [])
])
function isIdleOperator(op) {
  if (scheduledOperatorSet.value.has(op.name)) return false
  if (routeOperatorSet.value.has(op.name)) return false
  if (workshopOperators.value.includes(op.name)) return false
  if ((configStore.free_blacklist || []).includes(op.name)) return false
  return true
}

const displayList = computed(() => {
  let list = store.recommendations
  if (showOnlyPlanned.value) list = list.filter((op) => hasPlannedSkill(op))
  if (idleFilter.value === 'idle') list = list.filter((op) => isIdleOperator(op))
  if (idleFilter.value === 'busy') list = list.filter((op) => !isIdleOperator(op))
  if (searchQuery.value.trim()) {
    const q = searchQuery.value.trim().toLowerCase()
    list = list.filter((op) => op.name.toLowerCase().includes(q))
  }
  if (filterRarity.value.length) list = list.filter((op) => filterRarity.value.includes(op.rarity))
  if (filterProfession.value.length)
    list = list.filter((op) => filterProfession.value.includes(profMap[op.profession]))
  if (filterAchievable.value)
    list = list
      .map((op) => ({
        ...op,
        recommendations: op.recommendations.filter((r) => r.full_chain_achievable)
      }))
      .filter((op) => op.recommendations.length > 0)
  return list
})

function visibleRecs(op) {
  if (showOnlyPlanned.value)
    return op.recommendations.filter((r) => isSkillPlanned(op.char_id, r.skill_index))
  return op.recommendations
}

const plannedT3Summary = ref([])

async function refreshT3Summary() {
  const keys = Object.keys(plan.value).filter((k) => plan.value[k])
  if (!keys.length) {
    plannedT3Summary.value = []
    return
  }
  try {
    const r = await axios.post(`${import.meta.env.VITE_HTTP_URL}/mastery-t3-summary`, {
      planned_skills: keys
    })
    plannedT3Summary.value = r.data?.t3_summary || []
  } catch {
    plannedT3Summary.value = []
  }
}

watch(
  plan,
  () => {
    if (store.recommendations.length) refreshT3Summary()
  },
  { deep: true }
)

// ─── 工具函数 ───
function chainHas(rec, matId) {
  return !rec.chain_missing_materials?.some((m) => m.id === matId)
}
function currentMissing(rec) {
  return decomposeT3.value ? rec.chain_missing_t3 || [] : rec.chain_missing_materials || []
}
function formatTime(s) {
  const h = Math.floor(s / 3600),
    m = Math.floor((s % 3600) / 60)
  if (h > 0 && m > 0) return `${h}小时${m}分钟`
  if (h > 0) return `${h}小时`
  if (m > 0) return `${m}分钟`
  return `${s}秒`
}
async function fetchCultivate() {
  await store.fetchCultivate()
  if (store.cultivateOk) {
    message.success(`森空岛数据同步成功 ${store.cultivateMsg}`)
  } else if (store.cultivateMsg) {
    message.error(`森空岛同步失败: ${store.cultivateMsg}`)
  }
}

// ─── 确认 & 提交 ───
const showConfirm = ref(false)
const cd = reactive({ op: null, rec: null, supports: null, firstSupport: null })

function buildSupports(op) {
  const p = profMap[op.profession] || '近卫'
  const s = routeSettings[p]
  if (!s?.supports?.length) return []
  const bonus = masterySettings.central_bonus || 0
  return s.supports.map((sup) => ({
    name: sup.name,
    swap_name: sup.swap ? sup.swap_name || sup.name : sup.name,
    skill_level: sup.skill_level,
    efficiency: Math.min(100, (sup.efficiency || 45) + bonus),
    match: sup.swap ? !!sup.match : false,
    half_off: s.half_off
  }))
}

function confirmSkill(op, rec) {
  const p = profMap[op.profession] || '近卫'
  cd.op = op
  cd.rec = rec
  cd.supports = buildSupports(op)
  cd.firstSupport = routeSettings[p]?.supports?.[0]?.name || ''
  showConfirm.value = true
}

async function doAddTask() {
  showConfirm.value = false
  const { op, rec } = cd
  try {
    // #71：一键专精走 DB 计划创建 API（POST /mastery-plan），不再发原始 /task「技能专精」
    // （死流：server 只认 DB 计划）。target_level 由服务端默认专三，与确认弹窗「→ M3」一致。
    const r = await axios.post(`${import.meta.env.VITE_HTTP_URL}/mastery-plan`, {
      items: [{ name: op.name, skill_index: rec.skill_index }]
    })
    const results = r.data?.results || []
    if (results[0]?.status === 'added') {
      message.success(`${op.name} ${rec.skill_name} 专精任务已添加！`)
      await refreshPlanFromServer()
    } else {
      message.warning(results[0]?.reason || '添加失败')
    }
  } catch (e) {
    message.error(`添加失败: ${e.message}`)
  }
}

// ─── 初始化 ───
onMounted(async () => {
  await refreshPlanFromServer()
  await Promise.all([loadOperators(), store.fetchRecommendations()])
  // 空闲干员筛选需要路线配置：提前加载（defaultsCache 去重，openSettings 不再重复拉取）
  if (!defaultsCache.value) {
    try {
      await loadRoute()
    } catch (e) {
      console.error('mount: loadRoute failed', e)
    }
  }
  allOperatorList.value = store.recommendations.map((op) => ({
    char_id: op.char_id,
    name: op.name,
    rarity: op.rarity,
    profession: op.profession,
    recommendations: op.recommendations
  }))
  await refreshT3Summary()
})

async function loadOperators() {
  try {
    const r = await axios.get(`${import.meta.env.VITE_HTTP_URL}/operator`)
    operatorOptions.value = (r.data || []).map((n) => ({ label: n, value: n }))
  } catch (e) {
    console.error('loadOperators: failed', e)
  }
}
</script>

<style scoped>
.page-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  flex-wrap: wrap;
  gap: 8px;
}
.page-title {
  margin: 0;
  font-size: 20px;
}
.mastery-list {
  width: 100%;
  max-width: 960px;
}
.rec-item .n-card {
  margin-bottom: 0;
}
.section-label {
  display: block;
  margin-bottom: 2px;
}
.missing-section {
  margin-top: 4px;
}
.support-outer {
  margin-bottom: 8px;
}
.support-inner {
  margin-top: 4px;
}
.task-col {
  display: flex;
  align-items: center;
  gap: 8px;
  margin: 4px 0;
}
.ml {
  margin-left: 12px;
}
.confirm-support-row {
  display: flex;
  align-items: center;
  gap: 8px;
  margin: 2px 0;
}
.plan-op-row {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 4px 0;
}
</style>
