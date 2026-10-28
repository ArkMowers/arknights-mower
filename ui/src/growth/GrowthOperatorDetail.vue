<script setup>
import { operatorDisplayName, skillDisplayName } from '@/i18n/gameNames'
import { moduleDisplayName } from '@/i18n/moduleNames'
import { i18n } from '@/i18n'
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { NButton, NCheckbox, NIcon, NTag, NTooltip } from 'naive-ui'
import CloseOutline from '@vicons/ionicons5/es/CloseOutline'
import FlashOutline from '@vicons/ionicons5/es/FlashOutline'
import PeopleOutline from '@vicons/ionicons5/es/PeopleOutline'
import GrowthAvatar from './GrowthAvatar.vue'
import GrowthLevelPlan from '@/components/GrowthLevelPlan.vue'
import MasteryMaterials from '@/components/MasteryMaterials.vue'
import {
  eliteLabel,
  formatRate,
  masteryLabel,
  professionName,
  planStatusLabel
} from './growthFormatters'
import { operatorSkillRows } from './growthRecommendation'
import { skillRowDisplayName } from './growthDisplay'

const props = defineProps({
  operator: { type: Object, required: true },
  loading: Boolean,
  error: { type: String, default: '' },
  skillRows: { type: Array, default: () => [] },
  moduleRows: { type: Array, default: () => [] },
  basic: { type: Object, default: () => ({}) },
  levelSelected: { type: String, default: null },
  levelRequired: { type: String, default: null },
  levelSaving: Boolean,
  goalSaving: Boolean,
  targetSaving: Boolean,
  startingMastery: Boolean,
  batchAdding: Boolean,
  survey: { type: Object, default: null },
  completedSkills: { type: Array, default: () => [] },
  plannedCount: { type: Number, default: 0 }
})
const emit = defineEmits([
  'close',
  'retry',
  'apply-level',
  'toggle-skill',
  'change-target',
  'insert-task',
  'open-supports',
  'toggle-module',
  'change-module-target',
  'toggle-basic',
  'add-all'
])

// 聚合值和具体目标绑定：专三率写明来自哪个技能，模组解锁率写明来自哪个模组。
const surveyStats = computed(() => {
  if (!props.survey) return []
  const skills = (props.survey.skills || []).filter(
    (skill) => skill.rate !== null && skill.rate !== undefined
  )
  const modules = (props.survey.modules || []).filter(
    (module) => module.rate !== null && module.rate !== undefined
  )
  const bestSkill = skills.length
    ? skills.reduce((left, right) => (right.rate > left.rate ? right : left))
    : null
  const bestModule = modules.length
    ? modules.reduce((left, right) => (right.rate > left.rate ? right : left))
    : null
  const moduleRow = (props.operator.modules || []).find((module) => module.id === bestModule?.id)
  return [
    {
      key: 'mastery',
      label: i18n.global.t('growthUpdates.highestMasteryRate'),
      detail: bestSkill
        ? skillRowDisplayName(operatorSkillRows(props.operator)[bestSkill.index])
        : '',
      rate: bestSkill?.rate ?? null
    },
    {
      key: 'module',
      label: i18n.global.t('growthUpdates.highestModuleUnlockRate'),
      detail: moduleRow
        ? moduleRow.type || moduleDisplayName(moduleRow.id, moduleRow.name || '')
        : '',
      rate: bestModule?.rate ?? null
    },
    {
      key: 'elite2',
      label: i18n.global.t('growth.detail.elite2Rate'),
      detail: '',
      rate: props.survey.elite2 ?? null
    }
  ]
})

const subtitle = computed(() => {
  const op = props.operator
  const label = i18n.global.t('growth.format.operatorSubtitle', {
    profession: professionName(op.profession),
    elite: eliteLabel(op.elite),
    level: op.level ?? 1
  })
  return (
    (op.rarity ? op.rarity + '★ · ' : '') +
    label +
    (op.potential ? ' · ' + i18n.global.t('growth.format.potential', { level: op.potential }) : '')
  )
})

const addable = computed(() =>
  props.skillRows.filter((row) => !row.planned && row.rec?.current_level < 3)
)
const availableMastery = computed(
  () => (props.operator.max_phase ?? (props.operator.rarity >= 4 ? 2 : 0)) >= 2
)
const availableModules = computed(() => props.moduleRows.length > 0)

// 窄屏下档案改为底部抽屉。抽屉与遮罩 teleport 到 body，避免被窗口壳内容区
// （position: relative; z-index: 1; overflow: hidden）裁剪或压在底部导航下面。
const sheetMode = ref(false)
let sheetQuery = null
function syncSheetMode(event) {
  sheetMode.value = event.matches
}
onMounted(() => {
  if (typeof window === 'undefined' || typeof window.matchMedia !== 'function') return
  sheetQuery = window.matchMedia('(max-width: 1120px)')
  sheetMode.value = sheetQuery.matches
  sheetQuery.addEventListener?.('change', syncSheetMode)
})
onBeforeUnmount(() => {
  sheetQuery?.removeEventListener?.('change', syncSheetMode)
})

function targetLabel(value) {
  return masteryLabel(value)
}

function skillStatusType(status) {
  if (status === 'training' || status === 'arranging') return 'warning'
  if (status === 'failed') return 'error'
  if (status === 'waiting_collect' || status === 'waiting') return 'info'
  return 'default'
}
</script>

<template>
  <Teleport to="body" :disabled="!sheetMode">
    <div
      v-if="sheetMode"
      class="growth-dossier__backdrop"
      aria-hidden="true"
      @click="emit('close')"
    />
    <aside
      class="growth-dossier"
      :class="{ 'growth-dossier--sheet': sheetMode }"
      :aria-label="i18n.global.t('growth.detail.operatorGrowthDossier')"
    >
      <header class="growth-dossier__head">
        <div class="growth-dossier__head-main">
          <GrowthAvatar :name="operator.name" :rarity="operator.rarity" :size="72" />
          <div class="growth-dossier__identity">
            <span class="gp-kicker">{{ i18n.global.t('growth.format.operatorDossier') }}</span>
            <h2 class="growth-dossier__name">{{ operatorDisplayName(operator.name) }}</h2>
            <p
              class="growth-dossier__subtitle"
              :class="{ 'is-highlighted': survey?.eliteHighlight }"
            >
              {{ subtitle }}
            </p>
          </div>
          <button
            type="button"
            class="growth-dossier__close"
            :aria-label="i18n.global.t('growth.detail.closeOperatorDossier')"
            @click="emit('close')"
          >
            <n-icon :component="CloseOutline" :size="18" />
          </button>
        </div>

        <div v-if="surveyStats.length" class="growth-dossier__survey">
          <div v-for="stat in surveyStats" :key="stat.key" class="growth-dossier__survey-item">
            <span class="growth-dossier__survey-label">{{ stat.label }}</span>
            <span v-if="stat.detail" class="growth-dossier__survey-detail">{{ stat.detail }}</span>
            <span class="growth-dossier__survey-value gp-mono">{{ formatRate(stat.rate) }}</span>
            <span class="gp-meter growth-dossier__survey-meter" aria-hidden="true">
              <span :style="{ width: (stat.rate || 0) + '%' }" />
            </span>
          </div>
        </div>
        <div v-else class="growth-dossier__survey growth-dossier__survey--empty">
          {{ i18n.global.t('growth.detail.noPublicStatisticsAvailable') }}
        </div>
      </header>

      <div v-if="loading" class="growth-dossier__body">
        <div v-for="index in 4" :key="index" class="gp-skeleton growth-dossier__skeleton" />
      </div>

      <div v-else-if="error" class="gp-empty growth-dossier__error">
        <p class="gp-empty__title">
          {{ i18n.global.t('growth.detail.couldNotLoadMaterialLevelDetails') }}
        </p>
        <p class="gp-muted">{{ error }}</p>
        <div class="gp-empty__actions">
          <n-button size="small" @click="emit('retry')">{{
            i18n.global.t('growth.detail.retry')
          }}</n-button>
        </div>
      </div>

      <div v-else class="growth-dossier__body">
        <p v-if="operator.material_error" class="growth-dossier__warning">
          {{ operator.material_error }}
        </p>
        <section class="growth-dossier__block">
          <GrowthLevelPlan
            :operator="operator"
            :selected-key="levelSelected"
            :required-key="levelRequired"
            :saving="levelSaving || goalSaving"
            :apply-target="(key) => emit('apply-level', key)"
          />
        </section>

        <section v-if="basic?.supported" class="growth-dossier__block">
          <header class="growth-dossier__block-head">
            <h3>{{ i18n.global.t('growth.detail.basicSkills') }}</h3>
            <n-tag size="small" :bordered="false" :type="basic.planned ? 'success' : 'default'">
              {{
                basic.achieved
                  ? i18n.global.t('growth.detail.rank7Reached')
                  : basic.planned
                    ? i18n.global.t('growth.detail.planned')
                    : i18n.global.t('growth.detail.notPlanned')
              }}
            </n-tag>
          </header>
          <n-checkbox
            :checked="basic.checked"
            :disabled="basic.disabled"
            @update:checked="emit('toggle-basic', $event)"
          >
            {{
              basic.achieved
                ? i18n.global.t('growth.detail.basicSkillsAreAlreadyRank7')
                : i18n.global.t('growth.detail.planBasicSkillsToRank7')
            }}
          </n-checkbox>
          <p class="growth-dossier__note">
            {{ basic.note }}
          </p>
          <MasteryMaterials
            v-if="basic.materials"
            :summary="basic.materials"
            :title="i18n.global.t('growth.detail.basicSkillUpgradeMaterials')"
          />
        </section>

        <section v-if="availableMastery" class="growth-dossier__block">
          <header class="growth-dossier__block-head">
            <h3>{{ i18n.global.t('growth.detail.skillMastery') }}</h3>
            <span class="growth-dossier__block-meta gp-mono"
              >{{ skillRows.length }} {{ i18n.global.t('growth.detail.items') }}</span
            >
          </header>
          <p v-if="operator.mastery_error" class="growth-dossier__warning">
            {{ operator.mastery_error }}
          </p>
          <div v-for="row in skillRows" :key="row.rec.skill_index" class="growth-dossier__skill">
            <div class="growth-dossier__skill-head">
              <div class="growth-dossier__skill-title">
                <b>{{ skillDisplayName(row.rec.skill_name) }}</b>
                <n-tag
                  size="small"
                  :bordered="false"
                  :type="
                    survey?.skillHighlights?.includes(row.rec.skill_index) ? 'warning' : 'default'
                  "
                >
                  {{ i18n.global.t('growth.detail.m3') }}
                  {{
                    formatRate(
                      survey?.skills?.find((skill) => skill.index === row.rec.skill_index)?.rate
                    )
                  }}
                </n-tag>
                <span class="gp-mono growth-dossier__skill-level">
                  {{ masteryLabel(row.rec.current_level) }} {{ i18n.global.t('growth.detail.m')
                  }}{{
                    [
                      '',
                      i18n.global.t('growth.detail.1'),
                      i18n.global.t('growth.detail.2'),
                      i18n.global.t('growth.detail.3')
                    ][row.target]
                  }}
                </span>
                <n-tag
                  v-if="row.status"
                  size="small"
                  :bordered="false"
                  :type="skillStatusType(row.status.status)"
                >
                  {{ planStatusLabel(row.status.status) }}
                </n-tag>
                <span v-else-if="row.planned" class="gp-stamp gp-stamp--flat">{{
                  i18n.global.t('growth.detail.planned')
                }}</span>
              </div>
              <div class="growth-dossier__skill-time gp-mono">
                <template v-if="row.rec.total_time"
                  >{{ Math.round(row.rec.total_time / 3600) }}h</template
                >
              </div>
            </div>

            <div class="growth-dossier__skill-controls">
              <div
                class="growth-dossier__targets"
                role="group"
                :aria-label="i18n.global.t('growth.detail.targetMasteryLevel')"
              >
                <button
                  v-for="option in row.targetOptions"
                  :key="option.value"
                  type="button"
                  class="growth-dossier__target"
                  :class="{ 'is-active': option.value === row.target }"
                  :aria-pressed="option.value === row.target"
                  :disabled="row.locked || targetSaving"
                  @click="emit('change-target', { rec: row.rec, value: option.value })"
                >
                  {{ targetLabel(option.value) }}
                </button>
              </div>
              <n-button
                size="small"
                :type="row.planned ? 'default' : 'primary'"
                :secondary="!row.planned"
                :disabled="row.disabled"
                @click="emit('toggle-skill', row.rec)"
              >
                {{
                  row.planned
                    ? i18n.global.t('growth.detail.removeFromPlan')
                    : i18n.global.t('growth.detail.addToPlan')
                }}
              </n-button>
              <n-tooltip :disabled="!operator.mastery_error">
                <template #trigger>
                  <n-button
                    size="small"
                    quaternary
                    :disabled="!!operator.mastery_error || startingMastery"
                    @click="emit('insert-task', row.rec)"
                  >
                    <template #icon><n-icon :component="FlashOutline" /></template>
                    {{ i18n.global.t('growth.detail.trainNow') }}
                  </n-button>
                </template>
                {{ operator.mastery_error }}
              </n-tooltip>
              <n-button
                v-if="row.hasSupport"
                size="small"
                quaternary
                @click="emit('open-supports', row.rec)"
              >
                <template #icon><n-icon :component="PeopleOutline" /></template>
                {{ i18n.global.t('growth.detail.assistantPlan') }}
              </n-button>
            </div>

            <MasteryMaterials
              v-if="row.rec.skill_material_summary"
              :summary="row.rec.skill_material_summary"
              :title="
                skillDisplayName(row.rec.skill_name) +
                i18n.global.t('growth.detail.masteryMaterials')
              "
            />
            <p v-else class="growth-dossier__note">
              {{ i18n.global.t('growth.detail.loadSkillTargetsToViewMaterialsFor') }}
            </p>
          </div>
          <div v-if="completedSkills.length" class="growth-dossier__completed">
            <span class="growth-dossier__completed-title">{{
              i18n.global.t('growthUpdates.completedMastery')
            }}</span>
            <span
              v-for="row in completedSkills"
              :key="row.index"
              class="growth-dossier__completed-item"
            >
              <b>{{ skillRowDisplayName(row) }}</b>
              <span class="gp-mono"
                >{{ i18n.global.t('growth.detail.m3Rate') }} {{ formatRate(row.rate) }}</span
              >
            </span>
          </div>
          <p v-if="!skillRows.length" class="growth-dossier__note">
            {{ i18n.global.t('growth.detail.allOfThisOperatorSSkillsAre') }}
          </p>
        </section>

        <section v-if="availableModules" class="growth-dossier__block">
          <header class="growth-dossier__block-head">
            <h3>{{ i18n.global.t('growth.detail.moduleGoals') }}</h3>
            <span class="growth-dossier__block-meta gp-mono"
              >{{ moduleRows.length }} {{ i18n.global.t('growth.detail.modules') }}</span
            >
          </header>
          <p class="growth-dossier__note">
            {{ i18n.global.t('growth.detail.modulesDefaultToTheHighestCurrentlyAvailable') }}
          </p>
          <div v-for="row in moduleRows" :key="row.module.id" class="growth-dossier__module">
            <div class="growth-dossier__module-head">
              <n-checkbox
                :checked="row.planned"
                :disabled="row.disabled"
                @update:checked="emit('toggle-module', { module: row.module, value: $event })"
              >
                <b
                  >{{ row.module.type }} ·
                  {{ moduleDisplayName(row.module.id, row.module.name) }}</b
                >
              </n-checkbox>
              <n-tag
                size="small"
                :bordered="false"
                :type="row.module.current_level ? 'success' : 'default'"
              >
                {{
                  row.module.current_level
                    ? i18n.global.t('growth.detail.unlocked') +
                      row.module.current_level +
                      i18n.global.t('growth.detail.levels')
                    : i18n.global.t('growth.detail.elite') +
                      row.module.elite +
                      ' ' +
                      row.module.level +
                      i18n.global.t('growth.detail.levelsToUnlock')
                }}
              </n-tag>
              <n-tag
                size="small"
                :bordered="false"
                :type="survey?.moduleHighlights?.includes(row.module.id) ? 'warning' : 'default'"
              >
                {{ i18n.global.t('growth.detail.unlock') }}
                {{
                  formatRate(survey?.modules?.find((module) => module.id === row.module.id)?.rate)
                }}
              </n-tag>
            </div>
            <div
              v-if="row.module.current_level < row.module.max_level"
              class="growth-dossier__module-controls"
            >
              <div
                class="growth-dossier__targets"
                role="group"
                :aria-label="i18n.global.t('growth.detail.targetModuleLevel')"
              >
                <button
                  v-for="option in row.targetOptions"
                  :key="option.value"
                  type="button"
                  class="growth-dossier__target"
                  :class="{ 'is-active': option.value === row.target }"
                  :aria-pressed="option.value === row.target"
                  :disabled="goalSaving"
                  @click="emit('change-module-target', { module: row.module, value: option.value })"
                >
                  {{ i18n.global.t('growth.detail.target') }} {{ option.value }}
                  {{ i18n.global.t('growth.detail.levels') }}
                </button>
              </div>
            </div>
            <p v-if="row.module.material_error" class="growth-dossier__warning">
              {{ row.module.material_error }}
            </p>
            <MasteryMaterials
              v-else-if="row.summary"
              :summary="row.summary"
              :title="i18n.global.t('growth.detail.moduleUpgradeMaterials')"
            />
          </div>
        </section>
      </div>

      <footer v-if="!loading && !error" class="growth-dossier__foot">
        <div class="growth-dossier__foot-text">
          <b>{{ plannedCount }}</b> {{ i18n.global.t('growth.detail.goalsForThisOperator') }}
        </div>
        <n-button
          v-if="availableMastery"
          size="small"
          type="primary"
          :disabled="!addable.length || goalSaving || batchAdding"
          @click="emit('add-all')"
        >
          {{ i18n.global.t('growth.detail.addAllSkillsToPlan') }}
        </n-button>
      </footer>
    </aside>
  </Teleport>
</template>

<style scoped>
.growth-dossier {
  position: sticky;
  top: 58px;
  display: flex;
  flex-direction: column;
  max-height: calc(100dvh - 92px);
  min-width: 0;
  border-radius: 22px;
  background: var(--gp-surface);
  box-shadow: inset 0 0 0 1px var(--gp-hair-soft);
  overflow: hidden;
}

.growth-dossier__backdrop {
  display: none;
}

.growth-dossier__head {
  flex: none;
  display: flex;
  flex-direction: column;
  gap: 12px;
  padding: 18px 18px 14px;
  border-bottom: 1px solid var(--gp-hair-soft);
  background: var(--gp-surface-2);
}

.growth-dossier__head-main {
  display: flex;
  align-items: flex-start;
  gap: 13px;
}

.growth-dossier__identity {
  min-width: 0;
  flex: 1;
}

.growth-dossier__identity .gp-kicker {
  font-size: 9.5px;
  letter-spacing: 0.12em;
}

.growth-dossier__name {
  margin: 4px 0 2px;
  font-size: 23px;
  font-weight: 700;
  letter-spacing: -0.02em;
  line-height: 1.1;
}

.growth-dossier__subtitle {
  margin: 0;
  color: var(--gp-muted);
  font-size: 11.5px;
}

.growth-dossier__subtitle.is-highlighted {
  color: var(--gp-warn);
}

.growth-dossier__close {
  display: grid;
  place-items: center;
  width: 30px;
  height: 30px;
  flex: none;
  border: 1px solid transparent;
  border-radius: 8px;
  background: transparent;
  color: var(--gp-muted);
  cursor: pointer;
}

.growth-dossier__close:hover {
  border-color: var(--gp-hair-soft);
  color: var(--gp-ink);
}

.growth-dossier__close:focus-visible {
  outline: 2px solid var(--gp-accent);
  outline-offset: 1px;
}

.growth-dossier__survey {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 10px;
}

.growth-dossier__survey--empty {
  display: block;
  color: var(--gp-faint);
  font-size: 11px;
}

.growth-dossier__survey-item {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.growth-dossier__survey-label {
  color: var(--gp-faint);
  font-size: 10px;
  letter-spacing: 0.03em;
}

.growth-dossier__survey-detail {
  overflow: hidden;
  color: var(--gp-muted);
  font-size: 10px;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.growth-dossier__survey-value {
  font-size: 13px;
  font-weight: 700;
  color: var(--gp-ink);
}

.growth-dossier__survey-meter {
  height: 3px;
}

.growth-dossier__body {
  display: flex;
  flex-direction: column;
  gap: 18px;
  padding: 16px 18px 20px;
  overflow-y: auto;
  overscroll-behavior: contain;
  min-height: 0;
  scrollbar-gutter: stable;
  scrollbar-width: thin;
  scrollbar-color: var(--gp-hair) transparent;
}

.growth-dossier__body::-webkit-scrollbar {
  width: 8px;
  height: 8px;
}

.growth-dossier__body::-webkit-scrollbar-track {
  background: transparent;
}

.growth-dossier__body::-webkit-scrollbar-thumb {
  min-height: 36px;
  background: var(--gp-hair);
  background-clip: content-box;
  border: 2px solid transparent;
  border-radius: 999px;
}

.growth-dossier__body::-webkit-scrollbar-thumb:hover {
  background-color: var(--gp-muted);
}

.growth-dossier__skeleton {
  height: 84px;
}

.growth-dossier__block {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.growth-dossier__block-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  padding-bottom: 8px;
  border-bottom: 1px solid var(--gp-hair-soft);
}

.growth-dossier__block-head h3 {
  margin: 0;
  font-size: 14.5px;
  font-weight: 700;
  letter-spacing: 0.01em;
}

.growth-dossier__block-meta {
  color: var(--gp-faint);
  font-size: 10.5px;
}

.growth-dossier__note {
  margin: 0;
  color: var(--gp-muted);
  font-size: 11.5px;
  line-height: 1.6;
}

.growth-dossier__completed {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 6px 14px;
  margin-top: 12px;
  padding-top: 10px;
  border-top: 1px dashed var(--gp-hair-soft);
}

.growth-dossier__completed-title {
  color: var(--gp-faint);
  font-size: 10px;
  letter-spacing: 0.03em;
}

.growth-dossier__completed-item {
  display: inline-flex;
  align-items: baseline;
  gap: 6px;
}

.growth-dossier__completed-item b {
  color: var(--gp-ink-2);
  font-size: 11px;
  font-weight: 600;
}

.growth-dossier__completed-item .gp-mono {
  color: var(--gp-muted);
  font-size: 10px;
}

.growth-dossier__warning {
  margin: 0;
  padding: 8px 10px;
  border-radius: 8px;
  background: var(--gp-warn-block);
  color: var(--gp-warn);
  font-size: 11.5px;
  line-height: 1.55;
}

.growth-dossier__skill,
.growth-dossier__module {
  display: flex;
  flex-direction: column;
  gap: 9px;
  padding: 12px;
  border-radius: 12px;
  background: var(--gp-surface-2);
}

.growth-dossier__skill-head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 8px;
}

.growth-dossier__skill-title {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
  min-width: 0;
}

.growth-dossier__skill-title b {
  font-size: 13px;
}

.growth-dossier__skill-level {
  color: var(--gp-muted);
  font-size: 10.5px;
}

.growth-dossier__skill-time {
  flex: none;
  color: var(--gp-faint);
  font-size: 10.5px;
}

.growth-dossier__skill-controls {
  display: flex;
  align-items: center;
  gap: 6px;
  flex-wrap: wrap;
}

.growth-dossier__targets {
  display: inline-flex;
  padding: 2px;
  gap: 2px;
  border-radius: 8px;
  background: var(--gp-surface);
  box-shadow: inset 0 0 0 1px var(--gp-hair-soft);
}

.growth-dossier__target {
  height: 25px;
  padding: 0 8px;
  border: 0;
  border-radius: 6px;
  background: transparent;
  color: var(--gp-muted);
  font: inherit;
  font-size: 11px;
  font-weight: 650;
  cursor: pointer;
}

.growth-dossier__target:hover:not(:disabled):not(.is-active) {
  color: var(--gp-ink);
  background: var(--gp-surface-2);
}

.growth-dossier__target.is-active {
  background: var(--gp-ink);
  color: var(--gp-page);
}

/* 悬停时保留选中态的主题对比色。 */
.growth-dossier__target.is-active:hover:not(:disabled) {
  background: var(--gp-ink-2);
  color: var(--gp-page);
}

.growth-dossier__target:disabled {
  opacity: 0.45;
  cursor: default;
}

.growth-dossier__target:focus-visible {
  outline: 2px solid var(--gp-accent);
  outline-offset: 1px;
}

.growth-dossier__module-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  flex-wrap: wrap;
}

.growth-dossier__module-controls {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}

.growth-dossier__foot {
  flex: none;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  padding: 12px 18px;
  border-top: 1px solid var(--gp-hair-soft);
  background: var(--gp-surface-2);
}

.growth-dossier__foot-text {
  color: var(--gp-muted);
  font-size: 11.5px;
}

.growth-dossier__foot-text b {
  color: var(--gp-ink);
  font-family: var(--gp-display);
  font-size: 16px;
}

.growth-dossier__error {
  margin: 16px;
}

@media (max-width: 1120px) {
  .growth-dossier {
    position: fixed;
    top: auto;
    left: 0;
    right: 0;
    bottom: 0;
    z-index: 901;
    max-height: 86dvh;
    border-radius: 22px 22px 0 0;
    box-shadow: 0 -20px 60px -24px rgba(0, 0, 0, 0.45);
  }

  .growth-dossier__backdrop {
    display: block;
    position: fixed;
    inset: 0;
    z-index: 900;
    background: rgba(12, 12, 14, 0.46);
  }

  .growth-dossier__body {
    padding-bottom: calc(24px + env(safe-area-inset-bottom, 0px));
  }

  .growth-dossier__foot {
    padding-bottom: calc(12px + env(safe-area-inset-bottom, 0px));
  }
}
</style>
