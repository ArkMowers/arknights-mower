<script setup>
import { computed, ref, watch } from 'vue'
import OperatorSkillTooltip from '@/components/OperatorSkillTooltip.vue'
import { builtinGroups } from '@/data/baseGroups'
import { filterGroups, groupFacilities, groupMembers } from '@/utils/baseGroups'
import {
  applyEstimateConditions,
  defaultEstimateOptions,
  defaultEstimateSelection,
  estimateFields,
  estimateGroup
} from '@/utils/baseGroupEstimates'

const props = defineProps({
  items: { type: Array, required: true },
  baseConditions: { type: Object, default: () => ({}) }
})
const resourceBase = import.meta.env.BASE_URL
const groups = builtinGroups
const search = ref('')
const facility = ref(null)
const ownership = ref(null)
const maxLevel = ref(false)
const selections = ref(
  Object.fromEntries(groups.map((group) => [group.id, defaultEstimateSelection(group)]))
)
const conditions = ref(
  Object.fromEntries(groups.map((group) => [group.id, defaultEstimateOptions(group)]))
)
watch(
  () => props.baseConditions,
  (source) => {
    for (const group of groups) {
      conditions.value[group.id] = applyEstimateConditions(
        group,
        conditions.value[group.id],
        source
      )
    }
  },
  { immediate: true }
)
const estimates = computed(() =>
  Object.fromEntries(
    groups.map((group) => [
      group.id,
      estimateGroup(
        group,
        selections.value[group.id],
        conditions.value[group.id],
        props.items,
        maxLevel.value
      )
    ])
  )
)
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
const visibleGroups = computed(() =>
  filterGroups(groups, props.items, {
    search: search.value,
    facility: facility.value,
    ownership: ownership.value
  })
)
function memberSections(group) {
  const members = groupMembers(group, props.items)
  return [
    { key: 'core', title: group.coreTitle || '核心干员' },
    { key: 'support', title: '备选干员' },
    { key: 'accessory', title: '挂件' }
  ]
    .map((section) => ({
      ...section,
      members: members.filter((member) => member.role === section.key)
    }))
    .filter((section) => section.members.length)
}
const facilityOptions = groupFacilities.map((value) => ({ value, label: value }))
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
        基建组合 <span>{{ visibleGroups.length }}</span>
      </h2>
      <label class="estimate-mode"><input v-model="maxLevel" type="checkbox" />按满练度计算</label>
    </div>
    <div class="group-filters">
      <n-input
        v-model:value="search"
        clearable
        placeholder="搜索组合 / 干员 / 拼音"
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
    <div class="group-list" aria-label="基建组合列表">
      <n-empty
        v-if="!visibleGroups.length"
        description="没有符合条件的组合，请调整筛选条件"
        class="group-empty"
      />
      <article
        v-for="group in visibleGroups"
        :key="group.id"
        class="group-detail"
        :aria-label="group.title"
      >
        <header class="detail-heading">
          <h3>
            {{ group.title }} <span class="facility-badge">{{ group.facility }}</span>
          </h3>
          <span class="ownership-summary">{{ ownershipSummary(group) }}</span>
        </header>
        <p v-if="group.note" class="group-note">{{ group.note }}</p>
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
                  group.id !== 'builtin-run-order' && selections[group.id].includes(member.name)
              }"
            >
              <component
                :is="group.id === 'builtin-run-order' ? 'div' : 'button'"
                :type="group.id === 'builtin-run-order' ? undefined : 'button'"
                class="member-toggle"
                :class="{ 'display-only': group.id === 'builtin-run-order' }"
                :aria-pressed="
                  group.id === 'builtin-run-order'
                    ? undefined
                    : selections[group.id].includes(member.name)
                "
                :aria-label="
                  group.id === 'builtin-run-order'
                    ? member.name
                    : `${group.title} · ${member.name} · ${selections[group.id].includes(member.name) ? '已选中' : '未选中'}`
                "
                @click="group.id !== 'builtin-run-order' && toggleMember(group, member.name)"
              >
                <span
                  v-if="group.id !== 'builtin-run-order'"
                  class="selection-mark"
                  aria-hidden="true"
                  >{{ selections[group.id].includes(member.name) ? '✓' : '' }}</span
                >
                <n-avatar
                  :src="`${resourceBase}avatar/${encodeURIComponent(member.name)}.webp`"
                  :size="32"
                  round
                  :img-props="{ alt: member.name }"
                  :class="{ 'avatar-missing': member.ownership === 'unowned' }"
                >
                  <template #fallback>{{ member.name.slice(0, 1) }}</template>
                </n-avatar>
                <span class="member-text">
                  <strong>{{ member.name }}</strong>
                  <span v-if="member.note" class="member-note">{{ member.note }}</span>
                  <span
                    v-if="member.ownership !== 'unknown'"
                    class="member-status"
                    :class="{ owned: member.ownership === 'owned' }"
                    >{{
                      member.ownership === 'owned' ? member.progression || '已拥有' : '未拥有'
                    }}</span
                  >
                </span>
              </component>
              <OperatorSkillTooltip :name="member.name">
                <span class="skill-label" :aria-label="`${member.name}的基建技能`">技能</span>
              </OperatorSkillTooltip>
            </div>
          </div>
        </section>
        <div
          v-if="group.id !== 'builtin-run-order'"
          class="estimate-result"
          aria-live="polite"
          :aria-label="`${group.title}效率估算`"
        >
          <span class="estimate-label">效率估算</span>
          <span v-if="!estimates[group.id].hasSelection" class="estimate-empty"
            >勾选核心或备选干员计算</span
          >
          <span
            v-else-if="!estimates[group.id].metrics.length && !estimates[group.id].warnings.length"
            class="estimate-empty"
            >该选择无直接效率加成，详见明细</span
          >
          <span
            v-for="metric in estimates[group.id].metrics"
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
        <details v-if="group.id !== 'builtin-run-order'" class="estimate-details">
          <summary>计算条件与明细</summary>
          <div v-if="estimateFields(group).length" class="estimate-fields">
            <label v-for="field in estimateFields(group)" :key="field.key">
              <input
                v-if="field.type === 'checkbox'"
                v-model="conditions[group.id][field.key]"
                type="checkbox"
              />
              <span>{{ field.label }}</span>
              <select v-if="field.options" v-model="conditions[group.id][field.key]">
                <option v-for="option in field.options" :key="option.value" :value="option.value">
                  {{ option.label }}
                </option>
              </select>
              <input
                v-else-if="field.type !== 'checkbox'"
                v-model.number="conditions[group.id][field.key]"
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
  </div>
</template>

<style scoped>
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
.estimate-mode {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 12px;
  cursor: pointer;
}
.estimate-mode input {
  accent-color: var(--mower-primary);
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
  border-radius: 4px;
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
  border-radius: 8px;
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
  border-radius: 6px;
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
  border-radius: 6px;
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
