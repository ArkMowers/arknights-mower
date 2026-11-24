<script setup>
import { publicAsset } from '@/utils/publicAsset'
import { computed, ref, shallowRef, watch } from 'vue'
import { dormRecoveryFor } from '@/utils/baseDormRecovery'
import OperatorSkillTooltip from '@/components/OperatorSkillTooltip.vue'
import { builtinGroups, allGroupOptions, singleRecommendations } from '@/data/baseGroups'
import {
  filterGroups,
  groupFacilities,
  groupMembers,
  groupSingleRecommendations
} from '@/utils/baseGroups'
import {
  applyEstimateConditions,
  defaultEstimateOptions,
  defaultEstimateSelection,
  estimateFields,
  estimateGroup
} from '@/utils/baseGroupEstimates'

const props = defineProps({
  items: { type: Array, required: true },
  baseConditions: { type: Object, default: () => ({}) },
  conditionSource: { type: String, default: '' }
})
const groups = builtinGroups
const allOptions = [...allGroupOptions, ...singleRecommendations]
const view = ref('groups')
const activeVariants = ref({})
const displayedGroups = computed(() =>
  view.value === 'singles'
    ? singleRecommendations
    : groups.map(
        (group) =>
          allGroupOptions.find((option) => option.id === activeVariants.value[group.id]) || group
      )
)
function groupDisplayTitle(group) {
  return groups.find((parent) => parent.id === group.parentId)?.title || group.title
}
function variantOptions(group) {
  const parent = groups.find((parent) => parent.id === (group.parentId || group.id))
  if (!parent?.variants.length) return []
  return [parent, ...parent.variants]
    .map((variant, index) => {
      const recommended = variant.recommended || variant.core
      const ownership = recommended.map(
        (name) => props.items.find((item) => item.avatar === name)?.ownership
      )
      const availability = ownership.every((value) => value === 'owned')
        ? 0
        : ownership.some((value) => value === 'unowned')
          ? 2
          : 1
      const estimate = estimateGroup(variant, recommended, optionsForGroup(variant), props.items)
      const efficiency = estimate.valid
        ? estimate.metrics.find((metric) => metric.label === '贸易订单效率')?.value
        : undefined
      return { ...variant, availability, efficiency, index }
    })
    .sort((a, b) => {
      if (a.id === 'builtin-jaye-parts' || b.id === 'builtin-jaye-parts')
        return a.id === b.id ? 0 : a.id === 'builtin-jaye-parts' ? 1 : -1
      if (parent.id !== 'builtin-karlan')
        return a.availability - b.availability || a.index - b.index
      return (
        a.availability - b.availability ||
        (b.efficiency || 0) - (a.efficiency || 0) ||
        a.index - b.index
      )
    })
}
function chooseVariant(group, id) {
  activeVariants.value[group.parentId || group.id] = id
}
function applyRecommended(group) {
  selections.value[group.id] = [...group.recommended]
  if (group.core.includes('孑')) conditions.value[group.parentId || group.id].jayeStage = '未精英化'
}
function facilityLabel(value) {
  return (
    {
      金属: '制造 · 赤金',
      经验: '制造 · 经验',
      源石: '制造 · 碎片',
      通用: view.value === 'singles' ? '制造 · 通用' : '通用 / 跨设施'
    }[value] || value
  )
}
const search = ref('')
const facility = ref(null)
const ownership = ref(null)
const selections = ref(
  Object.fromEntries(
    allOptions.map((group) => [
      group.id,
      group.kind === 'single' ? [...group.recommended] : defaultEstimateSelection(group)
    ])
  )
)
const conditions = ref(
  Object.fromEntries(
    allOptions.map((group) => [
      group.id,
      {
        ...defaultEstimateOptions(group),
        ...(group.kind === 'single' && group.core.includes('孑') ? { jayeStage: '未精英化' } : {})
      }
    ])
  )
)
watch(
  () => props.baseConditions,
  (source, previous) => {
    for (const group of allOptions) {
      const current = conditions.value[group.id]
      const next = applyEstimateConditions(group, current, source)
      const previousDefaults =
        previous && applyEstimateConditions(group, defaultEstimateOptions(group), previous)
      for (const key of Object.keys(next)) {
        if (!previousDefaults || current[key] === previousDefaults[key]) current[key] = next[key]
      }
    }
  },
  { immediate: true }
)
function optionsForGroup(group) {
  const own = conditions.value[group.id]
  if (group.kind === 'single' && group.core.includes('孑')) return { ...own, jayeStage: '未精英化' }
  if (group.parentId !== 'builtin-karlan') return own
  const parent = conditions.value[group.parentId]
  return { ...own, jayeStage: parent.jayeStage, orderCap: parent.orderCap }
}
function conditionTarget(group, field) {
  return conditions.value[
    group.parentId === 'builtin-karlan' && ['jayeStage', 'orderCap'].includes(field.key)
      ? group.parentId
      : group.id
  ]
}
const estimates = computed(() =>
  Object.fromEntries(
    allOptions.map((group) => [
      group.id,
      estimateGroup(group, selections.value[group.id], optionsForGroup(group), props.items, {
        maximum: group.kind === 'single'
      })
    ])
  )
)
function displayOnlyMember(group, member) {
  return group.id === 'builtin-run-order' || (group.kind === 'single' && member.role === 'core')
}
function toggleMember(group, name) {
  if (group.id === 'builtin-run-order') return
  const selected = selections.value[group.id]
  selections.value[group.id] = selected.includes(name)
    ? selected.filter((member) => member !== name)
    : [...selected, name]
}
function formatMetric(metric) {
  const value = Number(metric.value.toFixed(2))
  return `${value > 0 ? '+' : ''}${value}${metric.unit}`
}
const dormRecovery = computed(() => {
  return Object.fromEntries(
    singleRecommendations
      .filter((group) => group.kind === 'single')
      .map((group) => [group.id, dormRecoveryFor(group.core[0])])
  )
})
const visibleGroups = computed(() =>
  filterGroups(displayedGroups.value, props.items, {
    search: search.value,
    facility: facility.value,
    ownership: ownership.value,
    recovery: dormRecovery.value
  })
)
const heldSections = shallowRef(null)
const expandedDetails = ref({})
const recommendationSections = computed(
  () =>
    heldSections.value ||
    (view.value === 'singles'
      ? groupSingleRecommendations(visibleGroups.value, estimates.value, dormRecovery.value)
      : [{ id: 'combinations', groups: visibleGroups.value }])
)
function holdSectionOrder(event) {
  if (event.target.closest('.estimate-fields') && !heldSections.value)
    heldSections.value = recommendationSections.value
}
function releaseSectionOrder(event) {
  if (!event.relatedTarget?.closest('.estimate-fields')) heldSections.value = null
}
function visibleMetrics(group, section) {
  const metrics = estimates.value[group.id].metrics
  return group.kind === 'single' && section.metric
    ? metrics.filter((metric) => metric !== section.metric && metric.label !== section.metric.label)
    : metrics
}
function visibleEstimateFields(group) {
  return estimateFields(group).filter(
    (field) =>
      !(group.kind === 'single' && field.key === 'jayeStage') &&
      (group.facility !== '中枢' ||
        !['factories', 'trade', 'power', 'eligibleGoldLines'].includes(field.key))
  )
}
function memberSections(group) {
  const members = groupMembers(group, props.items)
  return [
    { key: 'core', title: group.coreTitle || '核心干员' },
    { key: 'support', title: group.supportTitle || '备选干员' },
    { key: 'accessory', title: '挂件' }
  ]
    .map((section) => ({
      ...section,
      members: members.filter((member) => member.role === section.key)
    }))
    .filter((section) => section.members.length)
}
const facilityOptions = computed(() =>
  groupFacilities.map((value) => ({ value, label: facilityLabel(value) }))
)
const ownershipOptions = [
  { value: 'core-owned', label: '核心均已拥有' },
  { value: 'missing', label: '含未拥有成员' },
  { value: 'unknown', label: '持有状态未知' }
]
function ownershipSummary(group) {
  const list = groupMembers(group, props.items)
  const owned = list.filter((member) => member.ownership === 'owned').length
  const unknown = list.filter((member) => member.ownership === 'unknown').length
  return unknown === list.length
    ? '持有状态未知'
    : `已拥有 ${owned} / ${list.length}${unknown ? ` · ${unknown} 人未知` : ''}`
}
</script>

<template>
  <div class="groups-page">
    <div class="groups-heading">
      <h2>
        基建干员推荐 <span>{{ visibleGroups.length }}</span>
      </h2>
    </div>
    <div class="recommendation-toolbar">
      <div class="recommendation-views" aria-label="推荐类型">
        <button type="button" :aria-pressed="view === 'groups'" @click="view = 'groups'">
          组合推荐 <span>{{ groups.length }}</span>
        </button>
        <button type="button" :aria-pressed="view === 'singles'" @click="view = 'singles'">
          散件推荐 <span>{{ singleRecommendations.length }}</span>
        </button>
      </div>
      <span class="recommendation-help">{{
        view === 'groups'
          ? '核心与备选按推荐优先级排列，支援位置单独注明'
          : '按满练效率推荐（孑固定精0），同效率干员放在同一组，可分别使用；悬停技能查看说明'
      }}</span>
    </div>
    <p v-if="conditionSource" class="condition-source">{{ conditionSource }}</p>
    <div class="group-filters">
      <n-input
        v-model:value="search"
        clearable
        placeholder="搜索推荐 / 干员 / 拼音"
        aria-label="搜索组合"
      />
      <n-select
        v-model:value="facility"
        clearable
        :options="facilityOptions"
        placeholder="全部分类"
        aria-label="组合分类"
      />
      <n-select
        v-model:value="ownership"
        clearable
        :options="ownershipOptions"
        placeholder="全部持有状态"
        aria-label="组合持有状态"
      />
    </div>
    <div
      class="group-list"
      :class="{ 'single-list': view === 'singles' }"
      aria-label="基建干员推荐列表"
      @focusin="holdSectionOrder"
      @focusout="releaseSectionOrder"
    >
      <n-empty
        v-if="!visibleGroups.length"
        description="没有符合条件的组合，请调整筛选条件"
        class="group-empty"
      />
      <section
        v-for="section in recommendationSections"
        :key="section.id"
        :class="view === 'singles' ? 'single-section' : 'combination-section'"
      >
        <header v-if="view === 'singles'" class="single-section-heading">
          <h3>
            {{ section.roster ? '跑单干员' : section.title || facilityLabel(section.facility) }}
            <strong v-if="!section.roster && !section.control">{{
              section.metric ? formatMetric(section.metric) : '条件未满足'
            }}</strong>
          </h3>
          <span
            >{{ section.roster ? section.groups[0].core.length : section.groups.length }} 名干员 ·
            可分别使用{{
              section.roster
                ? ''
                : section.groups.some((group) => group.core.includes('孑'))
                  ? ' · 孑按精0，其余满练'
                  : ' · 满练效率'
            }}</span
          >
          <p v-if="section.control">逐人列出作用设施与全部效果，联动搭配见组合推荐</p>
          <p v-else-if="section.metric">
            {{ section.metric.label }}{{ section.average ? ' · 用尽平均' : '' }}
          </p>
        </header>
        <div
          :class="
            view === 'singles'
              ? section.roster
                ? 'roster-section-members'
                : section.control
                  ? 'single-section-members control-section-members'
                  : 'single-section-members'
              : 'combination-members'
          "
        >
          <article
            v-for="group in section.groups"
            :key="group.id"
            class="group-detail"
            :class="{
              'single-detail': group.kind === 'single',
              'roster-detail': group.kind === 'roster'
            }"
            :aria-label="group.title"
          >
            <header v-if="!['single', 'roster'].includes(group.kind)" class="detail-heading">
              <h3>
                {{ groupDisplayTitle(group) }}
                <span class="facility-badge">{{ facilityLabel(group.facility) }}</span>
              </h3>
              <span v-if="estimates[group.id].assumptions.length" class="assumption-badge"
                >满练度假设</span
              >
              <span class="ownership-summary">{{ ownershipSummary(group) }}</span>
              <button
                v-if="group.recommended"
                class="apply-recommendation"
                type="button"
                @click="applyRecommended(group)"
              >
                {{ group.core.includes('孑') ? '套用精零搭配' : '套用推荐' }}
              </button>
            </header>
            <p v-if="group.core.includes('孑')" class="jaye-recommendation">
              <strong>推荐精0孑（未精英化），仅限3级贸易站</strong>
              <span>精英化会改变订单上限机制，精零限定搭配将不再适用。</span>
            </p>
            <div
              v-if="variantOptions(group).length"
              class="variant-options"
              :aria-label="`${groupDisplayTitle(group)}搭配`"
            >
              <button
                v-for="(variant, index) in variantOptions(group)"
                :key="variant.id"
                type="button"
                :aria-pressed="variant.id === group.id"
                @click="chooseVariant(group, variant.id)"
              >
                <span class="variant-rank">{{ index + 1 }}</span>{{ variant.variantTitle
                }}<small v-if="variant.efficiency !== undefined" class="variant-efficiency"
                  >{{ Number(variant.efficiency.toFixed(2)) }}%</small
                >
              </button>
            </div>
            <section
              v-for="section in memberSections(group)"
              :key="section.key"
              class="member-section"
              :aria-label="`${group.title} · ${section.title}`"
            >
              <h4>{{ section.title }}</h4>
              <div class="member-grid">
                <div
                  v-for="member in section.members"
                  :key="member.name"
                  class="member-card"
                  :class="{
                    selected:
                      !displayOnlyMember(group, member) &&
                      selections[group.id].includes(member.name)
                  }"
                >
                  <component
                    :is="displayOnlyMember(group, member) ? 'div' : 'button'"
                    :type="displayOnlyMember(group, member) ? undefined : 'button'"
                    class="member-toggle"
                    :class="{ 'display-only': displayOnlyMember(group, member) }"
                    :aria-pressed="
                      displayOnlyMember(group, member)
                        ? undefined
                        : selections[group.id].includes(member.name)
                    "
                    :aria-label="
                      displayOnlyMember(group, member)
                        ? member.name
                        : `${group.title} · ${member.name} · ${selections[group.id].includes(member.name) ? '已选中' : '未选中'}`
                    "
                    @click="!displayOnlyMember(group, member) && toggleMember(group, member.name)"
                  >
                    <span
                      v-if="!displayOnlyMember(group, member)"
                      class="selection-mark"
                      aria-hidden="true"
                      >{{ selections[group.id].includes(member.name) ? '✓' : '' }}</span
                    >
                    <n-avatar
                      :src="publicAsset(`/avatar/${encodeURIComponent(member.name)}.webp`)"
                      :size="32"
                      round
                      :img-props="{ alt: member.name }"
                      :class="{ 'avatar-missing': member.ownership === 'unowned' }"
                    >
                      <template #fallback>{{ member.name.slice(0, 1) }}</template>
                    </n-avatar>
                    <span class="member-text">
                      <strong>{{ member.name }}</strong>
                      <span v-if="group.placements[member.name]" class="member-placement">{{
                        group.placements[member.name]
                      }}</span>
                      <span v-if="member.note" class="member-note">{{ member.note }}</span>
                      <span
                        v-if="member.ownership !== 'unknown'"
                        class="member-status"
                        :class="{ owned: member.ownership === 'owned' }"
                        >{{
                          member.ownership === 'owned'
                            ? view === 'singles'
                              ? '已拥有'
                              : member.progression || '已拥有'
                            : '未拥有'
                        }}</span
                      >
                    </span>
                  </component>
                  <OperatorSkillTooltip
                    :name="member.name"
                    :maximum="group.kind === 'single' || group.kind === 'roster'"
                    :unpromoted="group.kind === 'single' && member.name === '孑'"
                  >
                    <span class="skill-label" :aria-label="`${member.name}的基建技能`">技能</span>
                  </OperatorSkillTooltip>
                </div>
              </div>
            </section>
            <p v-if="group.note" class="group-note">{{ group.note }}</p>
            <p
              v-if="dormRecovery[group.id]"
              class="dorm-recovery"
              :class="{ locked: !dormRecovery[group.id].available }"
            >
              <span class="recovery-label">宿舍额外恢复 · 点/小时</span>
              <span>{{ dormRecovery[group.id].description }}</span>
              <span v-if="!dormRecovery[group.id].available"
                >{{ dormRecovery[group.id].unlock }}技能，{{
                  dormRecovery[group.id].inactive
                }}</span
              >
            </p>
            <div
              v-if="
                group.id !== 'builtin-run-order' &&
                (group.kind !== 'single' ||
                  visibleMetrics(group, section).length ||
                  estimates[group.id].warnings.length ||
                  !estimates[group.id].metrics.length)
              "
              class="estimate-result"
              aria-live="polite"
              :aria-label="`${group.title}效率估算`"
            >
              <span class="estimate-label">效率估算</span>
              <span v-if="!estimates[group.id].hasSelection" class="estimate-empty"
                >勾选核心或备选干员计算</span
              >
              <span
                v-else-if="
                  !estimates[group.id].metrics.length && !estimates[group.id].warnings.length
                "
                class="estimate-empty"
                >该选择无直接效率加成，详见明细</span
              >
              <span
                v-for="metric in visibleMetrics(group, section)"
                :key="metric.label"
                class="estimate-metric"
              >
                {{ metric.label }} <strong>{{ formatMetric(metric) }}</strong>
              </span>
              <span
                v-for="warning in estimates[group.id].warnings"
                :key="warning"
                class="estimate-warning"
                >{{ warning }}</span
              >
            </div>
            <details
              v-if="group.id !== 'builtin-run-order'"
              class="estimate-details"
              :open="expandedDetails[group.id]"
            >
              <summary @click.prevent="expandedDetails[group.id] = !expandedDetails[group.id]">
                计算条件与明细
              </summary>
              <div v-if="visibleEstimateFields(group).length" class="estimate-fields">
                <label v-for="field in visibleEstimateFields(group)" :key="field.key">
                  <input
                    v-if="field.type === 'checkbox'"
                    v-model="conditionTarget(group, field)[field.key]"
                    type="checkbox"
                  />
                  <span>{{ field.label }}</span>
                  <select v-if="field.options" v-model="conditionTarget(group, field)[field.key]">
                    <option
                      v-for="option in field.options"
                      :key="option.value"
                      :value="option.value"
                    >
                      {{ option.label }}
                    </option>
                  </select>
                  <input
                    v-else-if="field.type !== 'checkbox'"
                    v-model.number="conditionTarget(group, field)[field.key]"
                    type="number"
                    :min="field.min"
                    :max="field.max"
                    step="1"
                  />
                </label>
              </div>
              <p v-for="line in estimates[group.id].details" :key="line">{{ line }}</p>
              <p>仅计所选干员技能，不含设施基础效率；不同设施分别显示，中枢同类加成取最高</p>
            </details>
          </article>
        </div>
      </section>
    </div>
  </div>
</template>

<style scoped>
.dorm-recovery {
  display: flex;
  flex-wrap: wrap;
  gap: 2px 8px;
  margin: 6px 0 10px;
  font-size: 12px;
  line-height: 1.6;
  color: var(--mower-primary);
  text-wrap: pretty;
}
.dorm-recovery .recovery-label,
.dorm-recovery.locked {
  color: var(--mower-text-muted);
}

.jaye-recommendation {
  display: flex;
  flex-wrap: wrap;
  align-items: baseline;
  gap: 4px 12px;
  margin: 0 0 12px;
  padding: 10px 12px;
  border: 1px solid color-mix(in srgb, var(--mower-warning, #b46d19) 30%, transparent);
  border-radius: calc(6px * var(--mower-corner-scale));
  corner-shape: var(--mower-corner-shape);
  background: color-mix(in srgb, var(--mower-warning, #b46d19) 8%, var(--mower-surface));
  color: var(--mower-warning, #b46d19);
}
.jaye-recommendation strong {
  font-size: 14px;
}
.jaye-recommendation span {
  font-size: 12px;
}

.assumption-badge {
  color: var(--mower-text-muted);
  background: var(--mower-hover);
  padding: 2px 6px;
  border-radius: calc(4px * var(--mower-corner-scale));
  corner-shape: var(--mower-corner-shape);
  font-size: 11px;
}
.recommendation-toolbar {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 12px;
}
.recommendation-views {
  display: flex;
  gap: 4px;
  padding: 4px;
  border-radius: calc(10px * var(--mower-corner-scale));
  corner-shape: var(--mower-corner-shape);
  background: var(--mower-surface-raised, var(--mower-surface));
  box-shadow: 0 0 0 1px var(--mower-border);
}
.recommendation-views button,
.variant-options button,
.apply-recommendation {
  color: var(--mower-text-muted);
  background: transparent;
  font: inherit;
  font-size: 12px;
  cursor: pointer;
  border: 0;
  border-radius: calc(6px * var(--mower-corner-scale));
  corner-shape: var(--mower-corner-shape);
  min-height: 40px;
  padding: 7px 12px;
  transition:
    background-color 150ms,
    color 150ms,
    transform 150ms;
}
.recommendation-views button[aria-pressed='true'],
.variant-options button[aria-pressed='true'] {
  background: var(--mower-primary-light, rgba(75, 130, 100, 0.12));
  color: var(--mower-primary);
  font-weight: 600;
}
.recommendation-views button span {
  margin-left: 6px;
  font-variant-numeric: tabular-nums;
  opacity: 0.7;
}
.recommendation-help {
  color: var(--mower-text-muted);
  font-size: 12px;
  text-wrap: pretty;
}
.variant-options {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  margin: 0 0 12px;
}
.variant-options button {
  border: 1px solid var(--mower-border);
}
.variant-efficiency {
  margin-left: 6px;
  font-variant-numeric: tabular-nums;
  opacity: 0.7;
}
.variant-rank {
  display: inline-block;
  margin-right: 6px;
  font-size: 11px;
  opacity: 0.6;
  font-variant-numeric: tabular-nums;
}
.apply-recommendation {
  margin-left: auto;
  color: var(--mower-primary);
  box-shadow: inset 0 0 0 1px var(--mower-border);
}
.apply-recommendation:hover {
  background: var(--mower-hover);
}
.variant-options button:active,
.apply-recommendation:active {
  transform: scale(0.96);
}
.member-placement {
  font-size: 11px;
  color: var(--mower-text-muted);
}
.combination-section,
.combination-members {
  display: contents;
}
.single-section {
  border: 1px solid var(--mower-border);
  border-radius: calc(8px * var(--mower-corner-scale));
  corner-shape: var(--mower-corner-shape);
  background: var(--mower-surface);
  overflow: hidden;
}
.single-section-heading {
  display: flex;
  flex-wrap: wrap;
  align-items: baseline;
  gap: 4px 16px;
  padding: 14px 16px;
  background: var(--mower-hover);
}
.single-section-heading h3 {
  font-size: 15px;
}
.single-section-heading strong {
  margin-left: 8px;
  color: var(--mower-primary);
}
.single-section-heading span,
.single-section-heading p,
.condition-source {
  font-size: 12px;
  color: var(--mower-text-muted);
}
.single-section-heading p {
  flex-basis: 100%;
}
.single-section-members.control-section-members {
  grid-template-columns: minmax(0, 1fr);
}
.single-section-members {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(min(100%, 230px), 1fr));
  align-items: start;
  gap: 16px;
  padding: 16px;
}
.group-detail.single-detail {
  border: 0;
  padding: 0;
  min-width: 0;
}
.single-detail .member-section {
  display: block;
}
.single-detail .member-section:first-of-type h4 {
  display: none;
}
.single-detail .member-section + .member-section {
  margin-top: 8px;
}
.single-detail .group-note {
  margin: 6px 0;
}
.single-detail .estimate-result {
  border: 0;
  padding: 0;
  margin-top: 6px;
}
.roster-detail {
  border: 0;
}
.roster-detail .member-section {
  display: block;
}
.roster-detail .member-section h4 {
  display: none;
}
.roster-detail .member-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
}
.roster-detail .member-card {
  align-items: stretch;
}
.roster-detail .member-toggle,
.roster-detail .member-text {
  flex: 1;
}
.roster-detail .member-text {
  overflow-wrap: anywhere;
}
.roster-detail .skill-label {
  flex: 0 0 40px;
  min-height: 40px;
  margin-left: 0;
}
@media (max-width: 600px) {
  .roster-detail .member-grid {
    grid-template-columns: minmax(0, 1fr);
  }
}
.single-detail h3 {
  font-size: 14px;
}
.single-detail .detail-heading {
  margin-bottom: 6px;
}
.single-detail .ownership-summary {
  margin-left: auto;
}
.single-detail .estimate-label {
  display: none;
}
@media (max-width: 900px) {
  .single-section-members {
    grid-template-columns: minmax(0, 1fr);
  }
}
@media (prefers-reduced-motion: reduce) {
  .recommendation-views button,
  .variant-options button,
  .apply-recommendation {
    transition: none;
  }
}

.groups-page {
  display: flex;
  flex-direction: column;
  gap: 14px;
}
.groups-heading {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 16px;
}
.member-card.selected {
  border-color: var(--mower-primary);
}
.selection-mark {
  width: 12px;
  height: 12px;
  border: 1px solid var(--mower-border);
  border-radius: 3px;
  flex: none;
  font-size: 11px;
  line-height: 12px;
  text-align: center;
}
.selected .selection-mark {
  color: var(--mower-primary);
  border-color: var(--mower-primary);
}
.skill-label {
  display: grid;
  place-items: center;
  align-self: stretch;
  min-width: 24px;
  min-height: 28px;
  padding: 0 3px;
  border: 0;
  background: transparent;
  font: inherit;
  font-size: 10px;
  cursor: help;
  color: var(--mower-text-muted);
  border-left: 1px solid var(--mower-border);
  margin-left: 2px;
}
.skill-label:hover {
  color: var(--mower-primary);
}
.member-toggle:focus-visible,
.skill-label:focus-visible {
  outline: 2px solid var(--mower-primary);
  outline-offset: 2px;
}
.estimate-result {
  display: flex;
  flex-wrap: wrap;
  align-items: baseline;
  gap: 6px 14px;
  border-top: 1px solid var(--mower-border);
  padding-top: 10px;
  margin-top: 12px;
  font-size: 12px;
  font-variant-numeric: tabular-nums;
}
.estimate-label,
.estimate-empty {
  color: var(--mower-text-muted);
}
.estimate-metric strong {
  color: var(--mower-primary);
  font-weight: 600;
}
.estimate-warning {
  color: var(--mower-warning, #b46d19);
}
.estimate-details {
  margin-top: 8px;
  font-size: 12px;
  color: var(--mower-text-muted);
}
.estimate-details summary {
  cursor: pointer;
  width: fit-content;
  padding: 4px 0;
}
.estimate-details p {
  margin-top: 5px;
  line-height: 1.6;
}
.estimate-fields {
  display: flex;
  flex-wrap: wrap;
  gap: 10px 16px;
  margin: 8px 0;
}
.estimate-fields label {
  display: flex;
  align-items: center;
  gap: 8px;
}
.estimate-fields input,
.estimate-fields select {
  background: var(--mower-surface);
  color: inherit;
  font: inherit;
  border: 1px solid var(--mower-border);
  border-radius: calc(4px * var(--mower-corner-scale));
  corner-shape: var(--mower-corner-shape);
  padding: 5px 6px;
  box-sizing: border-box;
  min-height: 30px;
}
.estimate-fields input[type='number'] {
  width: 64px;
}
.estimate-fields input[type='checkbox'] {
  margin: 0;
  padding: 0;
  min-height: auto;
  accent-color: var(--mower-primary);
  cursor: pointer;
}
h2,
h3,
h4,
p {
  margin: 0;
}
h2 {
  font-size: 18px;
  font-weight: 600;
}
h2 span {
  margin-left: 6px;
  color: var(--mower-text-muted);
  font-size: 13px;
  font-weight: 400;
  font-variant-numeric: tabular-nums;
}
.group-filters {
  display: grid;
  grid-template-columns: minmax(180px, 1fr) 160px 180px;
  gap: 12px;
}
.group-list {
  display: flex;
  flex-direction: column;
  gap: 12px;
}
.group-detail {
  background: var(--mower-surface);
  border: 1px solid var(--mower-border);
  border-radius: calc(8px * var(--mower-corner-scale));
  corner-shape: var(--mower-corner-shape);
  padding: 14px 16px;
}
.detail-heading {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
  margin-bottom: 10px;
}
h3 {
  font-size: 16px;
  font-weight: 600;
}
.facility-badge {
  margin-left: 8px;
  font-size: 12px;
  font-weight: 400;
  color: var(--mower-text-muted);
}
.ownership-summary {
  font-size: 12px;
  color: var(--mower-text-muted);
  font-variant-numeric: tabular-nums;
}
.group-note {
  margin-bottom: 10px;
  color: var(--mower-primary);
  font-size: 12px;
  line-height: 1.7;
  text-wrap: pretty;
}
.member-section {
  display: grid;
  grid-template-columns: 64px minmax(0, 1fr);
  align-items: start;
  gap: 10px;
}
.member-section + .member-section {
  margin-top: 8px;
}
h4 {
  padding-top: 11px;
  font-size: 12px;
  font-weight: 400;
  color: var(--mower-text-muted);
}
.member-grid {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}
.member-card {
  display: flex;
  align-items: center;
  min-height: 40px;
  max-width: 100%;
  padding: 0;
  border: 1px solid var(--mower-border);
  border-radius: calc(6px * var(--mower-corner-scale));
  corner-shape: var(--mower-corner-shape);
  background: transparent;
  color: inherit;
  font: inherit;
  text-align: left;
  transition: border-color 150ms;
}
.member-toggle.display-only {
  cursor: default;
}
.member-toggle {
  display: flex;
  align-items: center;
  gap: 7px;
  border: 0;
  border-radius: calc(6px * var(--mower-corner-scale));
  corner-shape: var(--mower-corner-shape);
  padding: 4px 8px;
  min-height: 40px;
  min-width: 0;
  color: inherit;
  background: transparent;
  font: inherit;
  text-align: left;
  cursor: pointer;
  transition: transform 150ms;
}
.member-card:hover {
  border-color: var(--mower-primary);
}
.member-toggle:not(.display-only):active {
  transform: scale(0.96);
}
.member-card :deep(.n-avatar) {
  flex: none;
  outline: 1px solid rgb(0 0 0 / 10%);
  outline-offset: -1px;
}
:global(.provider--dark) .member-card :deep(.n-avatar) {
  outline-color: rgb(255 255 255 / 10%);
}
.avatar-missing {
  opacity: 0.4;
  filter: grayscale(1);
}
.member-text {
  display: flex;
  flex-direction: column;
  min-width: 0;
  gap: 2px;
}
.member-card strong {
  font-size: 12px;
  font-weight: 500;
  overflow-wrap: anywhere;
}
.member-note {
  font-size: 11px;
  color: var(--mower-primary);
  line-height: 1.4;
  text-wrap: pretty;
}
.member-status {
  font-size: 11px;
  color: var(--mower-text-muted);
  font-variant-numeric: tabular-nums;
}
.member-status.owned {
  color: var(--mower-primary);
}
.group-empty {
  padding: 48px 16px;
}
@media (max-width: 760px) {
  .group-filters {
    grid-template-columns: minmax(0, 1fr) minmax(0, 1fr);
  }
  .group-filters > :first-child {
    grid-column: 1 / -1;
  }
  .group-detail {
    padding: 12px;
  }
  .member-section {
    grid-template-columns: minmax(0, 1fr);
    gap: 6px;
  }
  h4 {
    padding-top: 0;
  }
}
@media (prefers-reduced-motion: reduce) {
  .member-card,
  .member-toggle {
    transition: none;
  }
}
</style>
