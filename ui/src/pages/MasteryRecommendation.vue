<template>
  <div class="home-container">
    <div class="page-header">
      <h1 class="page-title">专精推荐</h1>
      <n-space align="center" :size="8">
        <n-button size="small" @click="showPlan = true">
          <template #icon><n-icon :component="ListIcon" /></template>
          专精计划
          <n-badge
            v-if="planEntries.length"
            :value="planEntries.length"
            :max="99"
            style="margin-left: 4px"
          />
        </n-button>
        <n-button size="small" @click="showSettings = true">
          <template #icon><n-icon :component="SettingsIcon" /></template>
          专精路线
        </n-button>
        <n-button size="small" type="warning" @click="autoWorkshop" :loading="workshopLoading">
          <template #icon><n-icon :component="HammerIcon" /></template>
          自动合成配置
        </n-button>
        <n-select v-model:value="t5Operator" :options="operatorOptions" filterable placeholder="T5合成干员" style="width: 120px" size="small" />
        <n-select v-model:value="bookOperator" :options="operatorOptions" filterable placeholder="技巧概要干员" style="width: 120px" size="small" />
        <n-button type="primary" size="small" @click="fetchCultivate" :loading="store.loading">
          <template #icon><n-icon :component="RefreshIcon" /></template>
          刷新
        </n-button>
        <n-text v-if="store.cultivateMsg" depth="3" style="font-size: 11px"
          >更新: {{ store.cultivateMsg }}</n-text
        >
      </n-space>
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
      <template #footer>
        <n-space justify="end">
          <n-button @click="resetRoute">恢复默认</n-button>
          <n-button type="primary" @click="saveRoute">保存</n-button>
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
    >
      <n-space vertical>
        <n-input v-model:value="planSearch" placeholder="搜索干员" clearable size="small" />
        <n-space :size="4" wrap>
          <n-tag
            v-for="e in planEntries"
            :key="e.key"
            closable
            size="small"
            type="success"
            @close="removePlanEntry(e)"
          >
            {{ e.name }} {{ e.skill_name }}
          </n-tag>
          <n-text v-if="!planEntries.length" depth="3">未添加计划</n-text>
        </n-space>
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
              <n-button size="tiny" quaternary @click="addAllToPlan(op)">全加</n-button>
            </n-space>
            <n-space :size="4" style="margin-left: 8px">
              <n-button
                v-for="rec in op.recommendations"
                :key="rec.skill_index"
                size="tiny"
                :type="isSkillPlanned(op.char_id, rec.skill_index) ? 'success' : 'default'"
                @click="toggleSkillPlan(op, rec)"
              >
                {{ rec.skill_name }}
              </n-button>
            </n-space>
          </div>
        </n-scrollbar>
      </n-space>
      <template #footer>
        <n-space justify="end">
          <n-button @click="clearPlan" size="small">清空</n-button>
          <n-button type="primary" @click="savePlanFn" size="small">保存</n-button>
        </n-space>
      </template>
    </n-modal>
  </div>
</template>

<script setup>
import { computed, onMounted, reactive, ref, watch } from 'vue'
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
import { useMasteryStore } from '@/stores/mastery'
import { usePlanStore } from '@/stores/plan'
import { useConfigStore } from '@/stores/config'
import { storeToRefs } from 'pinia'
import { pinyin_match } from '@/utils/common'
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

const ROUTE_KEY = 'mower_mastery_route'

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
  { label: '4★', value: 4 },
  { label: '3★', value: 3 }
]
const professionOptions = profKeys.map((p) => ({ label: p, value: p }))

const searchQuery = ref('')
const filterRarity = ref([])
const filterProfession = ref([])
const filterAchievable = ref(false)
const showOnlyPlanned = ref(false)
const decomposeT3 = ref(false)
const workshopLoading = ref(false)
const t5Operator = ref('年')
const bookOperator = ref('司霆惊蛰')
const workshopT3Summary = ref([])

const emptyText = computed(() => {
  if (searchQuery.value || filterRarity.value.length || filterProfession.value.length) return '没有匹配的干员'
  if (showOnlyPlanned.value) return '没有计划中的专精项'
  return '没有推荐项'
})

// ─── 计划（技能级别）───
// 格式: { "charId_0": true, "charId_1": true, ... }
const plan = ref({})
const showPlan = ref(false)
const planSearch = ref('')

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

function toggleSkillPlan(op, rec) {
  const k = planKey(op.char_id, rec.skill_index)
  if (plan.value[k]) {
    delete plan.value[k]
  } else {
    plan.value[k] = true
  }
}

function addAllToPlan(op) {
  for (const rec of op.recommendations) {
    plan.value[planKey(op.char_id, rec.skill_index)] = true
  }
  message.success(`${op.name} 全部技能已加入计划`)
}

function removePlanEntry(e) {
  delete plan.value[e.key]
}
function clearPlan() {
  plan.value = {}
}
function savePlanFn() {
  axios.post(`${import.meta.env.VITE_HTTP_URL}/mastery-plan`, plan.value)
  message.success('计划已保存')
  showPlan.value = false
}

const planEntries = computed(() => {
  const entries = []
  for (const k in plan.value) {
    const [cid, si] = k.split('_')
    const op = store.recommendations.find((o) => o.char_id === cid)
    if (op) {
      const rec = op.recommendations.find((r) => r.skill_index === parseInt(si))
      if (rec)
        entries.push({
          key: k,
          char_id: cid,
          skill_index: parseInt(si),
          name: op.name,
          skill_name: rec.skill_name
        })
    }
  }
  return entries
})

const filteredPlanOperators = computed(() => {
  let list = allOperatorList.value
  const q = planSearch.value.trim().toLowerCase()
  if (q) list = list.filter((o) => o.name.toLowerCase().includes(q))
  return list
})

async function autoWorkshop() {
  workshopLoading.value = true
  try {
    const keys = Object.keys(plan.value).filter(k => plan.value[k])
    const resp = await axios.post(`${import.meta.env.VITE_HTTP_URL}/workshop-auto-config`, {
      planned_skills: keys,
      t5_operator: t5Operator.value,
      book_operator: bookOperator.value
    })
    const ws = resp.data?.workshop_settings
    if (!ws) { message.warning('生成失败'); return }
    configStore.workshop_settings = ws

    await new Promise(r => setTimeout(r, 100))
    await axios.post(`${import.meta.env.VITE_HTTP_URL}/conf`, configStore.build_config())
    workshopT3Summary.value = resp.data?.t3_summary || []

    const tasksResp = await axios.get(`${import.meta.env.VITE_HTTP_URL}/task`)
    const tasks = tasksResp.data || []
    const hasTask = (opName) => tasks.some(t => {
      const tType = typeof t.type === 'string' ? t.type : (t.type?.display_value || t.type?.value || '')
      return tType === '加工材料' && (t.meta_data === '' || t.meta_data === opName)
    })

    let added = []
    let skipped = []
    for (const entry of ws) {
      if (!entry.operator || !entry.items?.length) continue
      const op = entry.operator
      if (hasTask(op)) { skipped.push(op); continue }
      const r = await axios.post(`${import.meta.env.VITE_HTTP_URL}/task`, {
        task: { time: new Date(Date.now() + 120000 + added.length * 600000).toISOString(), plan: {}, task_type: '加工材料', meta_data: op }
      })
      if (r.data === '添加任务成功！') { added.push(op) }
      else { message.warning(`${op} 任务添加失败: ${r.data}`) }
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

function getCharName(cid) {
  const op = store.recommendations.find((o) => o.char_id === cid)
  return op ? op.name : cid
}

// ─── 专精路线设置 ───
const showSettings = ref(false)
const settingsTab = ref('近卫')
const swap_list = [
  { value: '艾丽妮', label: '艾丽妮' },
  { value: '逻各斯', label: '逻各斯' }
]
const swap_30 = [
  { value: true, label: '有30%速度加成' },
  { value: false, label: '无训练速度加成' }
]
const level_list = [
  { value: 1, label: '专一' },
  { value: 2, label: '专二' },
  { value: 3, label: '专三' }
]

const t60 = {
  先锋: { name: '嵯峨', speed: 60 },
  近卫: { name: '史尔特尔', speed: 60 },
  重装: { name: '星熊', speed: 60 },
  狙击: { name: '黑', speed: 60 },
  术师: { name: '卡涅利安', speed: 60 },
  医疗: { name: '阿', speed: 60 },
  辅助: { name: '铃兰', speed: 60 },
  特种: { name: '傀影', speed: 60 }
}
const t1 = {
  先锋: { name: '夜半', speed: 75 },
  近卫: { name: '赤冬', speed: 75 },
  重装: { name: '极光', speed: 75 },
  狙击: { name: '假日威龙陈', speed: 95 },
  术师: { name: '特米米', speed: 75 },
  医疗: { name: '阿', speed: 60 },
  辅助: { name: '铃兰', speed: 60 },
  特种: { name: '罗宾', speed: 75 }
}
const t2 = {
  先锋: { name: '缄默德克萨斯', speed: 80 },
  近卫: { name: '燧石', speed: 75 },
  重装: { name: '暴雨', speed: 75 },
  狙击: { name: '埃拉托', speed: 75 },
  术师: { name: '薄绿', speed: 75 },
  医疗: { name: '濯尘芙蓉', speed: 75 },
  辅助: { name: '铃兰', speed: 60 },
  特种: { name: '缄默德克萨斯', speed: 80 }
}
const t3 = {
  先锋: { name: '嵯峨', speed: 60 },
  近卫: { name: '百炼嘉维尔', speed: 95 },
  重装: { name: '星熊', speed: 60 },
  狙击: { name: 'W', speed: 95 },
  术师: { name: '死芒', speed: 95 },
  医疗: { name: '阿', speed: 60 },
  辅助: { name: '浊心斯卡蒂', speed: 95 },
  特种: { name: '归溟幽灵鲨', speed: 95 }
}

const defaultRoute = (p) => ({
  supports: [
    {
      name: t1[p].name,
      skill_level: 1,
      efficiency: t1[p].speed,
      swap: true,
      swap_name: ['近卫', '狙击'].includes(p) ? '艾丽妮' : '逻各斯',
      match: ['近卫', '狙击', '术师', '辅助'].includes(p)
    },
    {
      name: t2[p].name,
      skill_level: 2,
      efficiency: t2[p].speed,
      swap: true,
      swap_name: ['近卫', '狙击'].includes(p) ? '艾丽妮' : '逻各斯',
      match: ['近卫', '狙击', '术师', '辅助'].includes(p)
    },
    {
      name: t3[p].name,
      skill_level: 3,
      efficiency: t3[p].speed,
      swap: true,
      swap_name: ['近卫', '狙击'].includes(p) ? '艾丽妮' : '逻各斯',
      match: ['近卫', '狙击', '术师', '辅助'].includes(p)
    }
  ],
  optimal: false,
  half_off: true
})
const copyR = (r) => ({
  supports: r.supports.map((s) => ({ ...s })),
  optimal: r.optimal,
  half_off: r.half_off
})
const routeSettings = reactive(Object.fromEntries(profKeys.map((p) => [p, copyR(defaultRoute(p))])))

function newSupport(p) {
  const n = routeSettings[p].supports.length
  if (n >= 3) return null
  const i = n + 1,
    opt = routeSettings[p].optimal
  const s = opt ? (i === 1 ? t1[p] : i === 2 ? t2[p] : t3[p]) : i === 3 ? t3[p] : t60[p]
  return {
    name: s.name,
    skill_level: i,
    efficiency: s.speed,
    swap: true,
    swap_name: ['近卫', '狙击'].includes(p) ? '艾丽妮' : '逻各斯',
    match: ['近卫', '狙击', '术师', '辅助'].includes(p)
  }
}

function loadRoute() {
  try {
    const d = JSON.parse(localStorage.getItem(ROUTE_KEY) || '{}')
    for (const p of profKeys) {
      if (d[p]) {
        routeSettings[p].supports = d[p].supports || routeSettings[p].supports
        routeSettings[p].optimal = !!d[p].optimal
        routeSettings[p].half_off = d[p].half_off !== undefined ? d[p].half_off : true
      }
    }
  } catch {}
}
function saveRoute() {
  localStorage.setItem(ROUTE_KEY, JSON.stringify(routeSettings))
  message.success('已保存')
  showSettings.value = false
}
function resetRoute() {
  for (const p of profKeys) Object.assign(routeSettings[p], copyR(defaultRoute(p)))
  message.info('已恢复默认')
}

// ─── 显示列表 ───
const allOperatorList = ref([])

const displayList = computed(() => {
  let list = store.recommendations
  if (showOnlyPlanned.value) list = list.filter((op) => hasPlannedSkill(op))
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
  if (showOnlyPlanned.value) return op.recommendations.filter(r => isSkillPlanned(op.char_id, r.skill_index))
  return op.recommendations
}

const plannedT3Summary = computed(() => workshopT3Summary.value)

// ─── 工具函数 ───
function chainHas(rec, matId) { return !rec.chain_missing_materials?.some(m => m.id === matId) }
function currentMissing(rec) { return decomposeT3.value ? (rec.chain_missing_t3 || []) : (rec.chain_missing_materials || []) }
function formatTime(s) { const h = Math.floor(s / 3600), m = Math.floor((s % 3600) / 60); if (h > 0 && m > 0) return `${h}小时${m}分钟`; if (h > 0) return `${h}小时`; if (m > 0) return `${m}分钟`; return `${s}秒` }
async function refresh() { await store.fetchRecommendations() }
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
  return s.supports.map((sup) => ({
    name: sup.name,
    swap_name: sup.swap ? sup.swap_name || sup.name : sup.name,
    skill_level: sup.skill_level,
    efficiency: sup.efficiency || 45,
    match: sup.swap ? !!sup.match : false,
    half_off: sup.skill_level === 1 ? s.half_off : false
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
  const { op, rec, supports } = cd
  const p = profMap[op.profession] || '近卫'
  const firstSupport = routeSettings[p]?.supports?.[0]?.name || ''
  const skillNum = rec.skill_index + 1
  try {
    const r1 = await axios.post(`${import.meta.env.VITE_HTTP_URL}/task`, {
      task: {
        time: new Date(Date.now() + 60000).toISOString(),
        plan: { train: [firstSupport, op.name] },
        task_type: '上班',
        meta_data: ''
      }
    })
    if (r1.data !== '添加任务成功！') {
      message.warning(r1.data)
      return
    }
    const r2 = await axios.post(`${import.meta.env.VITE_HTTP_URL}/task`, {
      task: {
        time: new Date(Date.now() + 120000).toISOString(),
        plan: {},
        task_type: '技能专精',
        meta_data: '' + skillNum
      },
      upgrade_support: supports
    })
    r2.data === '添加任务成功！'
      ? message.success(`${op.name} ${rec.skill_name} 专精任务已添加！`)
      : message.warning(r2.data)
  } catch (e) {
    message.error(`添加失败: ${e.message}`)
  }
}

// ─── 初始化 ───
onMounted(async () => {
loadRoute()
    try {
      const r = await axios.get(`${import.meta.env.VITE_HTTP_URL}/mastery-plan`)
      plan.value = r.data || {}
    } catch {}
    await Promise.all([loadOperators(), store.fetchRecommendations()])
  allOperatorList.value = store.recommendations.map((op) => ({
    char_id: op.char_id,
    name: op.name,
    rarity: op.rarity,
    profession: op.profession,
    recommendations: op.recommendations
  }))
})

async function loadOperators() {
  try {
    const r = await axios.get(`${import.meta.env.VITE_HTTP_URL}/operator`)
    operatorOptions.value = (r.data || []).map((n) => ({ label: n, value: n }))
  } catch {}
}

watch(
    plan,
    (v) => {
      axios.post(`${import.meta.env.VITE_HTTP_URL}/mastery-plan`, v).catch(() => {})
    },
    { deep: true }
  )
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
