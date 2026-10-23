<template>
  <div class="base-skills-page">
    <div class="snapshot-actions">
      <n-button :loading="syncing" :disabled="loading" @click="syncCultivate">
        同步森空岛练度
      </n-button>
      <n-text depth="3" class="snapshot-message">{{ dataMessage }}</n-text>
    </div>
    <n-alert v-if="error" type="error" closable @close="error = ''">{{ error }}</n-alert>
    <n-tabs v-model:value="activePane" type="line" size="medium" class="base-tabs">
      <n-tab-pane name="skills" tab="基建技能">
        <section class="skill-filter-panel" aria-label="技能筛选">
          <div class="search-fields">
            <label
              ><span>干员</span
              ><n-input
                v-model:value="name_select"
                clearable
                placeholder="干员名称 / 拼音"
                aria-label="搜索干员"
            /></label>
            <label
              ><span>技能</span
              ><n-input
                v-model:value="des_select"
                clearable
                placeholder="技能名称或描述 / 拼音"
                aria-label="搜索技能"
            /></label>
          </div>
          <button
            type="button"
            class="mobile-filter-toggle"
            :aria-expanded="showFilters"
            @click="showFilters = !showFilters"
          >
            {{ showFilters ? '收起设施与状态筛选' : '展开设施与状态筛选' }}
            <span v-if="facility_select || ownership_select || status_select"> · 已筛选</span>
          </button>
          <div class="filter-extras" :class="{ 'is-open': showFilters }">
            <n-select
              v-model:value="facility_select"
              clearable
              :options="facilityOptions"
              placeholder="全部设施"
              aria-label="设施筛选"
              class="facility-select"
            />
            <div class="status-filters">
              <n-select
                v-model:value="ownership_select"
                clearable
                :options="ownershipOptions"
                placeholder="全部持有状态"
                aria-label="持有状态筛选"
              />
              <n-select
                v-model:value="status_select"
                clearable
                :options="statusOptions"
                placeholder="全部解锁状态"
                aria-label="技能解锁筛选"
              />
              <n-button quaternary @click="resetFilters">重置筛选</n-button>
            </div>
          </div>
        </section>
        <div class="results-heading">
          <span
            ><strong>{{ filteredItems.length }}</strong> 名干员
            <span class="count-separator">/</span>
            <strong>{{ filteredSkillCount }}</strong> 个技能版本</span
          >
          <span class="result-help">“已替换”表示该技能的升级版本已解锁</span>
        </div>
        <n-empty
          v-if="!filteredItems.length"
          description="没有符合筛选条件的基建技能"
          class="skill-empty"
          ><template #extra><n-button @click="resetFilters">清除筛选</n-button></template></n-empty
        >
        <div v-if="filteredItems.length" class="skill-table-heading" aria-hidden="true">
          <span>干员</span><span>技能序号</span><span>解锁条件</span><span>当前状态</span>
          <span>技能名称</span><span>进驻场所</span><span>描述</span>
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
      <n-tab-pane name="groups" tab="基建组合" display-directive="show:lazy">
        <BaseGroups :items="skill_items" :base-conditions="snapshot?.base_conditions" />
      </n-tab-pane>
    </n-tabs>
  </div>
</template>

<script setup>
import axios from 'axios'
import BasementSkillRows from '@/components/buffer.vue'
import BaseGroups from '@/components/BaseGroups.vue'
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
const error = ref('')
const name_select = ref('')
const des_select = ref('')
const facility_select = ref(null)
const ownership_select = ref(null)
const status_select = ref(null)

const skill_items = computed(() => annotateBasementSkills(skill.value, snapshot.value))
const facilityOptions = computed(() =>
  [...new Set(skill.value.flatMap((operator) => operator.child_skill.map((s) => s.roomType)))].map(
    (value) => ({ value, label: value })
  )
)
const ownershipOptions = Object.entries(ownershipLabels).map(([value, label]) => ({ value, label }))
const statusOptions = Object.entries(skillStatusLabels)
  .filter(([value]) => value !== 'unowned')
  .map(([value, label]) => ({ value, label }))
const filteredItems = computed(() =>
  filterBasementSkills(skill_items.value, {
    name: name_select.value,
    description: des_select.value,
    facility: facility_select.value,
    ownership: ownership_select.value,
    status: status_select.value
  })
)
const filteredSkillCount = computed(() =>
  filteredItems.value.reduce((count, item) => count + item.childSkill.length, 0)
)
const dataMessage = computed(() => {
  if (loading.value) return '正在读取本地森空岛练度…'
  return snapshot.value?.message || '同步森空岛练度后可显示持有和技能解锁状态。'
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
    error.value = `读取森空岛练度失败：${e.message || e}`
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
      error.value = response.data.message || '同步森空岛练度失败'
      return
    }
    await loadOwnedOperators()
  } catch (e) {
    error.value = `同步森空岛练度失败：${e.message || e}`
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
