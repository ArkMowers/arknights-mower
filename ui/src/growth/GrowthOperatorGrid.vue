<script setup>
import { computed, onScopeDispose, ref, watch } from 'vue'
import { NButton, NIcon, NInput, NPopover, NTooltip } from 'naive-ui'
import SearchOutline from '@vicons/ionicons5/es/SearchOutline'
import RefreshOutline from '@vicons/ionicons5/es/RefreshOutline'
import FunnelOutline from '@vicons/ionicons5/es/FunnelOutline'
import ChevronBackOutline from '@vicons/ionicons5/es/ChevronBackOutline'
import ChevronForwardOutline from '@vicons/ionicons5/es/ChevronForwardOutline'
import GrowthOperatorCard from './GrowthOperatorCard.vue'
import GrowthSurveyFilters from '@/components/GrowthSurveyFilters.vue'

const props = defineProps({
  cards: { type: Array, default: () => [] },
  loading: Boolean,
  error: { type: String, default: '' },
  emptyText: { type: String, default: '没有匹配当前筛选条件的干员' },
  hasData: { type: Boolean, default: true },
  search: { type: String, default: '' },
  rarities: { type: Array, default: () => [] },
  professions: { type: Array, default: () => [] },
  idleFilter: { type: String, default: 'all' },
  idleOptions: { type: Array, default: () => [] },
  rarityOptions: { type: Array, default: () => [] },
  professionOptions: { type: Array, default: () => [] },
  surveyFilters: { type: Object, required: true },
  survey: { type: Object, default: () => ({ operators: [] }) },
  surveyLoading: Boolean,
  batchAdding: Boolean,
  batchProgress: { type: String, default: '' },
  filteredCount: { type: Number, default: 0 },
  addableCount: { type: Number, default: 0 },
  total: { type: Number, default: 0 },
  page: { type: Number, default: 1 },
  pageSize: { type: Number, default: 30 }
})
const emit = defineEmits([
  'update:search',
  'update:rarities',
  'update:professions',
  'update:idleFilter',
  'update:surveyFilters',
  'update:page',
  'refresh-survey',
  'reset',
  'add-filtered',
  'open',
  'refresh',
  'sync'
])

const showFilters = ref(false)
// 浮层宽度跟随视口收缩，1280 窗口下也不会横向溢出 trigger 右侧。
const popoverWidth = 'min(740px, calc(100vw - 32px))'
const popoverRef = ref(null)
let popoverScrollHost = null

function handlePopoverKeydown(event) {
  if (event.key === 'Escape') showFilters.value = false
}

// 页面内容区滚动时 naive-ui 不会自动重算浮层位置，手动让浮层重新锚定 trigger。
function syncPopoverPosition() {
  const instance = popoverRef.value
  if (instance && typeof instance.syncPosition === 'function') instance.syncPosition()
}

function clearPopoverListeners() {
  if (typeof window !== 'undefined') window.removeEventListener('keydown', handlePopoverKeydown)
  if (popoverScrollHost) {
    popoverScrollHost.removeEventListener('scroll', syncPopoverPosition)
    popoverScrollHost = null
  }
}

function bindPopoverListeners() {
  if (typeof window === 'undefined' || typeof document === 'undefined') return
  window.addEventListener('keydown', handlePopoverKeydown)
  popoverScrollHost = document.querySelector(
    '.layout-content-container > .n-layout-scroll-container'
  )
  popoverScrollHost?.addEventListener('scroll', syncPopoverPosition, { passive: true })
}

watch(showFilters, (open) => {
  clearPopoverListeners()
  if (open) bindPopoverListeners()
})
onScopeDispose(clearPopoverListeners)
const activeThresholds = computed(() => {
  const labels = { mastery: '专三率', module: '模组解锁率', elite1: '精一率', elite2: '精二率' }
  return Object.entries(labels)
    .filter(([key]) => props.surveyFilters[key] !== null && props.surveyFilters[key] !== undefined)
    .map(([key, label]) => ({
      key,
      label,
      rate: props.surveyFilters[key],
      text: label + ' ≥ ' + props.surveyFilters[key] + '%'
    }))
})
const surveyActive = computed(
  () => activeThresholds.value.length > 0 || props.surveyFilters.hideCompleted === false
)
const surveyFiltersProxy = computed({
  get: () => props.surveyFilters,
  set: (value) => emit('update:surveyFilters', value)
})

function toggleRarity(value) {
  const list = [...props.rarities]
  const index = list.indexOf(value)
  if (index >= 0) list.splice(index, 1)
  else list.push(value)
  emit('update:rarities', list)
}

function toggleProfession(value) {
  const list = [...(props.professions || [])]
  const index = list.indexOf(value)
  if (index >= 0) list.splice(index, 1)
  else list.push(value)
  emit('update:professions', list)
}

function clearThreshold(key) {
  emit('update:surveyFilters', { ...props.surveyFilters, [key]: null })
}

function resetAll() {
  emit('reset')
}

const emptyDescription = computed(() =>
  props.hasData
    ? props.emptyText || '试着放宽稀有度、职业或大数据门槛，或清空搜索词。'
    : '从森空岛同步一次干员数据后即可开始规划。'
)

// 分页只按当前筛选结果计算；用总干员数会让筛选后的页码与“共 N 位”都对不上。
const listTotal = computed(() => Math.max(0, props.filteredCount || 0))
const totalPages = computed(() => Math.max(1, Math.ceil(listTotal.value / props.pageSize)))
const pageWindow = computed(() => {
  const pages = []
  const last = totalPages.value
  const start = Math.max(1, Math.min(props.page - 1, last - 2))
  const end = Math.min(last, start + 2)
  for (let page = start; page <= end; page += 1) pages.push(page)
  return pages
})
const rangeText = computed(() => {
  if (!listTotal.value) return '0 位'
  const start = (props.page - 1) * props.pageSize + 1
  const end = Math.min(listTotal.value, props.page * props.pageSize)
  return start + '–' + end + ' / ' + listTotal.value
})
</script>

<template>
  <div class="growth-grid-view">
    <div class="growth-filters">
      <div class="growth-filters__main">
        <n-input
          :value="search"
          class="growth-filters__search"
          placeholder="搜索干员或拼音"
          clearable
          aria-label="搜索干员"
          @update:value="emit('update:search', $event)"
        >
          <template #prefix><n-icon :component="SearchOutline" /></template>
        </n-input>
        <n-popover
          ref="popoverRef"
          v-model:show="showFilters"
          trigger="click"
          placement="bottom-start"
          :width="popoverWidth"
          :show-arrow="false"
          raw
        >
          <template #trigger>
            <button
              type="button"
              class="growth-filters__survey"
              :class="{ 'is-active': surveyActive }"
              :aria-expanded="showFilters"
            >
              <n-icon :component="FunnelOutline" :size="15" />
              大数据筛选
              <span v-if="activeThresholds.length" class="gp-mono growth-filters__survey-count">{{
                activeThresholds.length
              }}</span>
            </button>
          </template>
          <div class="growth-filters__popover">
            <GrowthSurveyFilters
              v-model="surveyFiltersProxy"
              :survey="survey"
              :loading="surveyLoading"
              @refresh="emit('refresh-survey')"
            >
              <p class="growth-filters__popover-hint">
                筛选只影响列表展示，不改动任何已保存的养成计划。
              </p>
            </GrowthSurveyFilters>
          </div>
        </n-popover>
        <button type="button" class="growth-filters__reset" @click="resetAll">重置</button>
        <span class="growth-filters__count gp-mono">{{ filteredCount }} / {{ total }} 位</span>
        <div class="growth-filters__spacer" />
        <n-tooltip>
          <template #trigger>
            <n-button
              class="growth-filters__batch"
              size="small"
              type="primary"
              secondary
              :loading="batchAdding"
              :disabled="loading || !addableCount"
              @click="emit('add-filtered')"
            >
              按筛选加入计划 · {{ addableCount }}
            </n-button>
          </template>
          添加当前筛选结果中达到所选比例门槛的技能、模组与精英化目标，跳过已在计划或已完成的项目。未设置门槛时不添加。
        </n-tooltip>
        <span v-if="batchProgress" class="growth-filters__batch-progress">{{ batchProgress }}</span>
      </div>

      <div v-if="activeThresholds.length" class="growth-filters__thresholds">
        <button
          v-for="threshold in activeThresholds"
          :key="threshold.key"
          type="button"
          class="gp-chip gp-chip--accent growth-filters__threshold"
          :aria-label="'清除筛选 ' + threshold.text"
          @click="clearThreshold(threshold.key)"
        >
          {{ threshold.text }}
          <span aria-hidden="true">×</span>
        </button>
        <span class="growth-filters__hint">达到比例的目标会在干员卡与档案中标出</span>
      </div>

      <div class="growth-filters__chips" role="group" aria-label="稀有度筛选">
        <span class="growth-filters__chips-label">稀有度</span>
        <button
          v-for="option in rarityOptions"
          :key="option.value"
          type="button"
          class="growth-filters__chip"
          :class="{ 'is-active': rarities.includes(option.value) }"
          :aria-pressed="rarities.includes(option.value)"
          @click="toggleRarity(option.value)"
        >
          {{ option.label }}
        </button>
        <span class="growth-filters__chips-sep" aria-hidden="true" />
        <span class="growth-filters__chips-label">职业</span>
        <button
          v-for="option in professionOptions"
          :key="option.value"
          type="button"
          class="growth-filters__chip"
          :class="{ 'is-active': professions.includes(option.value) }"
          :aria-pressed="professions.includes(option.value)"
          @click="toggleProfession(option.value)"
        >
          {{ option.label }}
        </button>
        <span class="growth-filters__chips-sep" aria-hidden="true" />
        <span class="growth-filters__chips-label">状态</span>
        <button
          v-for="option in idleOptions"
          :key="option.value"
          type="button"
          class="growth-filters__chip"
          :class="{ 'is-active': idleFilter === option.value }"
          :aria-pressed="idleFilter === option.value"
          @click="emit('update:idleFilter', option.value)"
        >
          {{ option.label }}
        </button>
      </div>
    </div>

    <div v-if="error" class="gp-empty">
      <p class="gp-empty__title">干员数据读取失败</p>
      <p class="gp-muted">{{ error }}</p>
      <div class="gp-empty__actions">
        <n-button size="small" @click="emit('refresh')">重新读取</n-button>
      </div>
    </div>

    <div v-else-if="loading && !cards.length" class="growth-grid" aria-busy="true">
      <div v-for="index in 8" :key="index" class="growth-grid__skeleton gp-skeleton" />
    </div>

    <div v-else-if="!cards.length" class="gp-empty">
      <p class="gp-empty__title">{{ hasData ? '没有符合筛选的干员' : '还没有干员数据' }}</p>
      <p class="gp-muted">{{ emptyDescription }}</p>
      <div class="gp-empty__actions">
        <n-button v-if="hasData" size="small" @click="resetAll">清空筛选</n-button>
        <n-button v-else size="small" @click="emit('sync')">
          <template #icon><n-icon :component="RefreshOutline" /></template>
          同步干员数据
        </n-button>
      </div>
    </div>

    <div v-else class="growth-grid">
      <GrowthOperatorCard
        v-for="(card, index) in cards"
        :key="card.operator.char_id"
        class="gp-rise"
        :style="{ '--gp-delay': Math.min(index, 7) }"
        :operator="card.operator"
        :survey="card.survey"
        :planned="card.planned"
        :planned-count="card.plannedCount"
        @open="(op) => emit('open', op)"
      />
    </div>

    <nav v-if="listTotal > pageSize" class="growth-pager" aria-label="干员分页">
      <button
        type="button"
        class="growth-pager__step"
        :disabled="page <= 1"
        aria-label="上一页"
        @click="emit('update:page', page - 1)"
      >
        <n-icon :component="ChevronBackOutline" />
      </button>
      <button
        v-for="item in pageWindow"
        :key="item"
        type="button"
        class="growth-pager__page gp-mono"
        :class="{ 'is-active': item === page }"
        :aria-current="item === page ? 'page' : undefined"
        @click="emit('update:page', item)"
      >
        {{ String(item).padStart(2, '0') }}
      </button>
      <button
        type="button"
        class="growth-pager__step"
        :disabled="page >= totalPages"
        aria-label="下一页"
        @click="emit('update:page', page + 1)"
      >
        <n-icon :component="ChevronForwardOutline" />
      </button>
      <span class="growth-pager__range gp-mono">{{ rangeText }}</span>
    </nav>
    <div v-else-if="listTotal" class="growth-grid__count gp-mono">共 {{ listTotal }} 位干员</div>
  </div>
</template>

<style scoped>
.growth-grid-view {
  display: flex;
  flex-direction: column;
  gap: 14px;
  min-width: 0;
}

.growth-filters {
  display: flex;
  flex-direction: column;
  gap: 10px;
  padding: 14px 16px;
  border-radius: 18px;
  background: var(--gp-surface);
  box-shadow: inset 0 0 0 1px var(--gp-hair-soft);
}

.growth-filters__main {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
}

.growth-filters__search {
  width: 240px;
  flex: 0 1 240px;
  --n-height: 36px;
}

.growth-filters__survey {
  display: inline-flex;
  align-items: center;
  gap: 7px;
  height: 36px;
  padding: 0 13px;
  border: 1px solid var(--gp-hair-soft);
  border-radius: 10px;
  background: var(--gp-surface-2);
  color: var(--gp-ink-2);
  font: inherit;
  font-size: 12.5px;
  font-weight: 650;
  cursor: pointer;
  transition:
    border-color 160ms var(--gp-ease),
    background 160ms var(--gp-ease),
    color 160ms var(--gp-ease);
}

.growth-filters__survey:hover {
  border-color: var(--gp-hair);
}

.growth-filters__survey.is-active {
  border-color: var(--gp-accent);
  background: var(--gp-accent-block);
  color: var(--gp-accent-ink);
}

.growth-filters__survey:focus-visible {
  outline: 2px solid var(--gp-accent);
  outline-offset: 2px;
}

.growth-filters__survey-count {
  display: inline-grid;
  place-items: center;
  min-width: 17px;
  height: 17px;
  padding: 0 4px;
  border-radius: 999px;
  background: currentColor;
  color: var(--gp-surface);
  font-size: 10px;
  font-weight: 700;
}

.growth-filters__reset {
  height: 36px;
  padding: 0 8px;
  border: 0;
  background: none;
  color: var(--gp-muted);
  font: inherit;
  font-size: 12.5px;
  cursor: pointer;
  text-decoration: underline;
  text-underline-offset: 4px;
  text-decoration-color: var(--gp-hair);
}

.growth-filters__reset:hover {
  color: var(--gp-ink);
}

.growth-filters__count {
  color: var(--gp-muted);
  font-size: 11px;
}

.growth-filters__spacer {
  flex: 1 1 auto;
}

.growth-filters__batch {
  --n-height: 34px;
  white-space: nowrap;
}

.growth-filters__batch-progress {
  color: var(--gp-muted);
  font-size: 11.5px;
}

.growth-filters__thresholds {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}

.growth-filters__threshold {
  border: 0;
  cursor: pointer;
  font: inherit;
  font-size: 12px;
}

.growth-filters__threshold span {
  opacity: 0.7;
}

.growth-filters__hint {
  color: var(--gp-faint);
  font-size: 11.5px;
}

.growth-filters__chips {
  display: flex;
  align-items: center;
  gap: 5px;
  flex-wrap: wrap;
}

.growth-filters__chips-label {
  margin-right: 2px;
  color: var(--gp-faint);
  font-size: 11px;
  font-weight: 600;
  letter-spacing: 0.04em;
}

.growth-filters__chain {
  width: 1px;
  height: 14px;
  background: var(--gp-hair-soft);
}

.growth-filters__chips-sep {
  width: 1px;
  height: 14px;
  margin: 0 4px;
  background: var(--gp-hair-soft);
}

.growth-filters__chip {
  height: 25px;
  padding: 0 9px;
  border: 1px solid transparent;
  border-radius: 6px;
  background: transparent;
  color: var(--gp-muted);
  font: inherit;
  font-size: 11.5px;
  font-weight: 600;
  cursor: pointer;
  transition:
    background 140ms var(--gp-ease),
    color 140ms var(--gp-ease),
    border-color 140ms var(--gp-ease);
}

.growth-filters__chip:hover {
  background: var(--gp-surface-2);
  color: var(--gp-ink);
}

.growth-filters__chip.is-active {
  border-color: var(--gp-ink);
  background: var(--gp-ink);
  color: var(--gp-page);
}

.growth-filters__chip:focus-visible {
  outline: 2px solid var(--gp-accent);
  outline-offset: 1px;
}

.growth-filters__popover {
  max-height: min(74vh, 660px);
  overflow: auto;
  overflow-x: hidden;
  overscroll-behavior: contain;
  border-radius: var(--gp-r);
  background: var(--gp-surface);
  box-shadow:
    inset 0 0 0 1px var(--gp-hair-soft),
    var(--gp-shadow-float);
  padding: 6px;
  scrollbar-width: thin;
  scrollbar-color: var(--gp-hair) transparent;
}

/* 浮层是唯一的卡片表面：内层筛选区透明、无圆角，
   避免“圆角里再套一个圆角”的接缝（尤其底部两角）。 */
.growth-filters__popover :deep(.survey) {
  padding: 10px 10px 12px;
  border-radius: 0;
  background: transparent;
}

.growth-filters__popover::-webkit-scrollbar {
  width: 8px;
  height: 8px;
}

.growth-filters__popover::-webkit-scrollbar-thumb {
  background: var(--gp-hair);
  background-clip: content-box;
  border: 2px solid transparent;
  border-radius: 999px;
}

.growth-filters__popover-hint {
  margin: 4px 0 0;
  color: var(--gp-muted);
  font-size: 11.5px;
}

.growth-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(212px, 1fr));
  gap: 10px;
}

.growth-grid__skeleton {
  height: 156px;
  border-radius: 16px;
}

.growth-grid__count {
  color: var(--gp-faint);
  font-size: 11px;
  text-align: right;
}

.growth-pager {
  display: flex;
  align-items: center;
  gap: 4px;
  justify-content: flex-end;
  padding-top: 2px;
}

.growth-pager__step,
.growth-pager__page {
  display: inline-grid;
  place-items: center;
  min-width: 30px;
  height: 30px;
  padding: 0 8px;
  border: 0;
  border-radius: 8px;
  background: transparent;
  color: var(--gp-muted);
  font: inherit;
  font-size: 12px;
  cursor: pointer;
}

.growth-pager__page.gp-mono {
  font-size: 11.5px;
}

.growth-pager__step:hover:not(:disabled),
.growth-pager__page:hover {
  background: var(--gp-surface);
  color: var(--gp-ink);
}

.growth-pager__page.is-active {
  background: var(--gp-ink);
  color: var(--gp-page);
}

.growth-pager__step:disabled {
  opacity: 0.35;
  cursor: default;
}

.growth-pager__range {
  margin-left: 8px;
  color: var(--gp-faint);
  font-size: 11px;
}

.growth-pager__step:focus-visible,
.growth-pager__page:focus-visible {
  outline: 2px solid var(--gp-accent);
  outline-offset: 1px;
}

@media (max-width: 720px) {
  .growth-filters {
    padding: 12px;
  }
  .growth-filters__search {
    width: 100%;
    flex: 1 1 100%;
  }
  .growth-filters__count {
    order: 5;
  }
  .growth-filters__spacer {
    display: none;
  }
  .growth-filters__batch {
    margin-left: auto;
  }
  .growth-grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
    gap: 8px;
  }
  .growth-filters__chips {
    flex-wrap: nowrap;
    overflow-x: auto;
    scrollbar-width: none;
    padding-bottom: 2px;
  }
  .growth-filters__chips::-webkit-scrollbar {
    display: none;
  }
  .growth-filters__chips-label,
  .growth-filters__chip {
    flex: none;
  }
}
</style>
