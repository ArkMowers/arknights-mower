<template>
  <PageLayout>
    <template #header>
      <PageHeader>{{ t('baseSkills.title') }}</PageHeader>
    </template>
    <div class="base-skills-page">
      <div class="snapshot-actions">
        <n-button :loading="syncing" :disabled="loading" @click="syncCultivate">
          {{ t('baseSkills.sync') }}
        </n-button>
        <n-text depth="3" class="snapshot-message">{{ dataMessage }}</n-text>
      </div>
      <n-alert v-if="error" type="error" closable @close="error = ''">{{ error }}</n-alert>
      <n-tabs v-model:value="activePane" type="line" size="medium" class="base-tabs">
        <n-tab-pane name="skills" :tab="t('baseSkills.title')">
          <section class="skill-filter-panel" :aria-label="t('baseSkills.filters')">
            <div class="search-fields">
              <label
                ><span>{{ t('baseSkills.operator') }}</span
                ><n-input
                  v-model:value="name_select"
                  clearable
                  :placeholder="t('baseSkills.operatorSearch')"
                  :aria-label="t('baseSkills.operatorSearchLabel')"
              /></label>
              <label
                ><span>{{ t('baseSkills.skill') }}</span
                ><n-input
                  v-model:value="des_select"
                  clearable
                  :placeholder="t('baseSkills.skillSearch')"
                  :aria-label="t('baseSkills.skillSearchLabel')"
              /></label>
            </div>
            <button
              type="button"
              class="mobile-filter-toggle"
              :aria-expanded="showFilters"
              @click="showFilters = !showFilters"
            >
              {{ t(showFilters ? 'baseSkills.collapseFilters' : 'baseSkills.expandFilters') }}
              <span v-if="facility_select || ownership_select || status_select">
                {{ t('baseSkills.filtered') }}</span
              >
            </button>
            <div class="filter-extras" :class="{ 'is-open': showFilters }">
              <n-select
                v-model:value="facility_select"
                clearable
                :options="facilityOptions"
                :placeholder="t('baseSkills.allFacilities')"
                :aria-label="t('baseSkills.facilityFilter')"
                class="facility-select"
              />
              <div class="status-filters">
                <n-select
                  v-model:value="ownership_select"
                  clearable
                  :options="ownershipOptions"
                  :placeholder="t('baseSkills.allOwnership')"
                  :aria-label="t('baseSkills.ownershipFilter')"
                />
                <n-select
                  v-model:value="status_select"
                  clearable
                  :options="statusOptions"
                  :placeholder="t('baseSkills.allUnlock')"
                  :aria-label="t('baseSkills.unlockFilter')"
                />
                <n-button quaternary @click="resetFilters">{{
                  t('baseSkills.resetFilters')
                }}</n-button>
              </div>
            </div>
          </section>
          <div class="results-heading">
            <span>{{
              t('baseSkills.counts', {
                operators: filteredItems.length,
                skills: filteredSkillCount
              })
            }}</span>
            <span class="result-help">{{ t('baseSkills.replacedHelp') }}</span>
          </div>
          <n-empty
            v-if="!filteredItems.length"
            :description="t('baseSkills.empty')"
            class="skill-empty"
            ><template #extra
              ><n-button @click="resetFilters">{{
                t('baseSkills.clearFilters')
              }}</n-button></template
            ></n-empty
          >
          <div v-if="filteredItems.length" class="skill-table-heading" aria-hidden="true">
            <span>{{ t('baseSkills.operator') }}</span
            ><span>{{ t('baseSkills.skillNumber') }}</span
            ><span>{{ t('baseSkills.unlockCondition') }}</span
            ><span>{{ t('baseSkills.status') }}</span> <span>{{ t('baseSkills.skillName') }}</span
            ><span>{{ t('baseSkills.facility') }}</span
            ><span>{{ t('baseSkills.description') }}</span>
          </div>
          <n-virtual-list
            v-if="filteredItems.length"
            :item-size="150"
            :items="filteredItems"
            item-resizable
            class="skill-list"
          >
            <template #default="{ item }">
              <BasementSkillRows :key="item.key" :item="item" />
            </template>
          </n-virtual-list>
        </n-tab-pane>
        <n-tab-pane name="groups" :tab="t('baseSkills.groups')" display-directive="show:lazy">
          <BaseGroups :items="skill_items" :base-conditions="snapshot?.base_conditions" />
        </n-tab-pane>
      </n-tabs>
    </div>
  </PageLayout>
</template>

<script setup>
import { i18n } from '@/i18n'
import { baseSkillText } from '@/i18n/baseSkills'
import { localizedBaseSkill } from '@/i18n/baseSkillDetails'
import { operatorSyncMessage } from '@/i18n/operatorSync'
const { t } = i18n.global

import axios from 'axios'
import BasementSkillRows from '@/components/buffer.vue'
import BaseGroups from '@/components/BaseGroups.vue'
import PageLayout from '@/components/PageLayout.vue'
import PageHeader from '@/components/PageHeader.vue'
import { ref, computed, onMounted } from 'vue'
import { useBasementSkill } from '@/stores/basementSkill'
import {
  annotateBasementSkills,
  filterBasementSkills,
  ownershipLabels,
  skillStatusLabels
} from '@/utils/basementSkills'

const { skill, load, snapshot, loadOwnedOperators: readOwnedOperators } = useBasementSkill()
const activePane = ref('skills')
const showFilters = ref(false)
const loading = ref(false)
const syncing = ref(false)
const errorState = ref({ message: '' })
const error = computed({
  get: () =>
    errorState.value.key
      ? t(errorState.value.key, errorState.value.params)
      : operatorSyncMessage(errorState.value.message),
  set: (message) => {
    errorState.value = { message }
  }
})
const name_select = ref('')
const des_select = ref('')
const facility_select = ref(null)
const ownership_select = ref(null)
const status_select = ref(null)

const skill_items = computed(() => annotateBasementSkills(skill.value, snapshot.value))
const facilityOptions = computed(() =>
  [...new Set(skill.value.flatMap((operator) => operator.child_skill.map((s) => s.roomType)))].map(
    (value) => ({ value, label: baseSkillText(value) })
  )
)
const ownershipOptions = computed(() =>
  Object.entries(ownershipLabels).map(([value, label]) => ({ value, label: baseSkillText(label) }))
)
const statusOptions = computed(() =>
  Object.entries(skillStatusLabels)
    .filter(([value]) => value !== 'unowned')
    .map(([value, label]) => ({ value, label: baseSkillText(label) }))
)
const filteredItems = computed(() => {
  const filters = {
    name: name_select.value,
    facility: facility_select.value,
    ownership: ownership_select.value,
    status: status_select.value
  }
  const candidates = filterBasementSkills(skill_items.value, filters)
  const query = des_select.value.trim()
  if (!query) return candidates
  const originalMatches = new Set(
    filterBasementSkills(candidates, { description: query }).flatMap((item) => item.childSkill)
  )
  const displayQuery = query.toLocaleLowerCase()
  return candidates.flatMap((item) => {
    const childSkill = item.childSkill.filter((skill) => {
      if (originalMatches.has(skill)) return true
      const display = localizedBaseSkill(item.avatar, skill)
      return `${display.skillname} ${display.des.replace(/<[^>]*>/g, '')}`
        .toLocaleLowerCase()
        .includes(displayQuery)
    })
    return childSkill.length ? [{ ...item, childSkill, span: childSkill.length }] : []
  })
})
const filteredSkillCount = computed(() =>
  filteredItems.value.reduce((count, item) => count + item.childSkill.length, 0)
)
const dataMessage = computed(() => {
  if (loading.value) return t('baseSkills.loading')
  if (snapshot.value?.has_data)
    return t('baseSkills.snapshotLoaded', { count: snapshot.value.operators?.length || 0 })
  return operatorSyncMessage(snapshot.value?.message) || t('baseSkills.syncHelp')
})

function resetFilters() {
  name_select.value = ''
  des_select.value = ''
  facility_select.value = null
  ownership_select.value = null
  status_select.value = null
}

async function loadOwnedOperators() {
  loading.value = true
  error.value = ''
  try {
    await readOwnedOperators()
  } catch (e) {
    errorState.value = { key: 'baseSkills.loadFailed', params: { message: e.message || e } }
  } finally {
    loading.value = false
  }
}

async function syncCultivate() {
  if (syncing.value || loading.value) return
  syncing.value = true
  error.value = ''
  try {
    const response = await axios.get(`${import.meta.env.VITE_HTTP_URL}/cultivate-fetch`)
    if (!response.data.success) {
      if (response.data.message) error.value = response.data.message
      else errorState.value = { key: 'baseSkills.syncFailed' }
      return
    }
    await loadOwnedOperators()
  } catch (e) {
    errorState.value = { key: 'baseSkills.syncError', params: { message: e.message || e } }
  } finally {
    syncing.value = false
  }
}

onMounted(() => Promise.all([load(), loadOwnedOperators()]))
</script>

<style scoped>
.base-skills-page {
  color: var(--mower-text);
  -webkit-font-smoothing: antialiased;
  --skill-columns: 86px 66px 78px 80px 186px 78px minmax(0, 1fr);
}
.snapshot-actions {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 8px 16px;
  margin-bottom: 12px;
}
.snapshot-message {
  font-size: 13px;
}
.base-tabs :deep(.n-tabs-pane-wrapper) {
  padding-top: 4px;
}
.skill-filter-panel,
.search-fields,
.filter-extras,
.status-filters {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 8px;
}
.search-fields label {
  width: 190px;
}
.search-fields label > span {
  position: absolute;
  width: 1px;
  height: 1px;
  overflow: hidden;
  clip-path: inset(50%);
}
.facility-select {
  width: 140px;
}
.status-filters :deep(.n-select) {
  width: 150px;
}
.mobile-filter-toggle {
  display: none;
}
.results-heading {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  flex-wrap: wrap;
  padding: 12px 0;
  font-size: 13px;
  color: var(--mower-text-muted);
  font-variant-numeric: tabular-nums;
}
.results-heading strong {
  color: var(--mower-text);
  font-weight: 500;
}
.count-separator {
  margin: 0 6px;
}
.result-help {
  font-size: 12px;
}
.skill-table-heading {
  display: grid;
  grid-template-columns: var(--skill-columns);
  align-items: center;
  min-height: 36px;
  background: var(--mower-surface);
  border-bottom: 1px solid var(--mower-border);
  color: var(--mower-text-muted);
  font-size: 12px;
  text-align: center;
}
.skill-table-heading span:last-child {
  text-align: left;
  padding-left: 10px;
}
.skill-list {
  height: 65vh;
  min-height: 300px;
}
.skill-empty {
  padding: 48px 16px;
}
@media (max-width: 900px) {
  .skill-table-heading {
    display: none;
  }
}
@media (max-width: 700px) {
  .skill-filter-panel,
  .filter-extras {
    align-items: stretch;
    flex-direction: column;
  }
  .search-fields label {
    width: calc(50% - 4px);
  }
  .filter-extras {
    display: none;
  }
  .filter-extras.is-open {
    display: flex;
  }
  .mobile-filter-toggle {
    display: block;
    align-self: flex-start;
    min-height: 40px;
    border: 0;
    background: transparent;
    color: var(--mower-primary);
    font: inherit;
    padding: 0;
    cursor: pointer;
  }
  .facility-select {
    width: 100%;
  }
  .status-filters :deep(.n-select) {
    width: calc(50% - 4px);
  }
}
</style>
