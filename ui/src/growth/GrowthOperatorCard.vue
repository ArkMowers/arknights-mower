<script setup>
import { computed, ref, watch } from 'vue'
import GrowthAvatar from './GrowthAvatar.vue'
import GrowthGameIcon from './GrowthGameIcon.vue'
import { moduleBadge } from './growthGameIcons'
import { eliteLabel, formatRate, masteryLabel, professionName } from './growthFormatters'
import {
  operatorSkillRows,
  recommendedTarget,
  remainingLevelTarget,
  remainingModuleTargets,
  surveyModuleRate,
  surveySkillRate
} from './growthRecommendation'

const props = defineProps({
  operator: { type: Object, required: true },
  survey: { type: Object, default: null },
  planned: Boolean,
  plannedCount: { type: Number, default: 0 },
  rank: { type: [Number, String], default: null },
  layout: { type: String, default: 'grid' },
  recommendationSort: { type: String, default: 'mastery' }
})
const emit = defineEmits(['open'])

function skillTone(level) {
  if (level >= 3) return 'done'
  if (level > 0) return 'warn'
  return 'low'
}
const skillRows = computed(() =>
  operatorSkillRows(props.operator).map((row) => ({
    ...row,
    rate: surveySkillRate(props.survey, row.index),
    tone: skillTone(row.current),
    highlighted: (props.survey?.skillHighlights || []).includes(row.index)
  }))
)
const skills = computed(() => skillRows.value.map((row) => row.current))
const supportsMastery = computed(() => {
  const maxPhase =
    props.operator.max_phase ??
    (props.operator.rarity >= 4 ? 2 : props.operator.rarity === 3 ? 1 : 0)
  return maxPhase >= 2 && skills.value.length > 0
})
const moduleTargets = computed(() => remainingModuleTargets(props.operator, props.survey))
const moduleRows = computed(() =>
  (props.operator.modules || []).map((module) => ({
    ...module,
    current: Number(module.current_level) || 0,
    target: Number(module.max_level) || 3,
    label: module.type || module.name || '模组',
    badge: moduleBadge(module.type, module.id),
    rate: surveyModuleRate(props.survey, module.id),
    highlighted: (props.survey?.moduleHighlights || []).includes(module.id)
  }))
)
const recommended = computed(() =>
  recommendedTarget(props.operator, props.survey, props.recommendationSort)
)
const activeSkillIndex = ref(0)
const activeLevel = ref(false)
const levelTarget = computed(() => remainingLevelTarget(props.operator))
const activeModule = ref(false)
const activeModuleId = ref(null)
// 用户点过技能段后不再自动改选中；公开样本异步到达时默认选中推荐目标。
const pickedByUser = ref(false)
const defaultTarget = computed(() => {
  if (recommended.value) return recommended.value
  if (props.recommendationSort === 'module') {
    return moduleTargets.value[0] || { kind: 'module', id: null }
  }
  const first = (props.operator.recommendations || []).find((rec) => Number(rec.current_level) < 3)
  if (first) return { kind: 'skill', index: Number(first.skill_index) }
  if (moduleTargets.value.length) return moduleTargets.value[0]
  return { kind: 'skill', index: 0 }
})
watch(
  [defaultTarget, () => props.recommendationSort],
  ([target, sort], [, previousSort] = []) => {
    if (!target || (pickedByUser.value && sort === previousSort)) return
    pickedByUser.value = false
    activeLevel.value = target.kind === 'level'
    if (target.kind === 'module') {
      activeModule.value = true
      activeModuleId.value = target.id
    } else {
      activeModule.value = false
      activeSkillIndex.value = target.index
    }
  },
  { immediate: true }
)
const moduleTarget = computed(() => {
  if (!activeModuleId.value) return null
  return moduleRows.value.find((row) => row.id === activeModuleId.value) || null
})
// 卡片分别显示选中的等级目标、技能或模组状态。
const statusLine = computed(() => {
  if (activeLevel.value && levelTarget.value) {
    const target = levelTarget.value
    return {
      tone: 'low',
      text:
        eliteLabel(target.currentElite) +
        ' ' +
        target.currentLevel +
        ' → ' +
        eliteLabel(target.elite) +
        ' ' +
        target.level
    }
  }
  if (activeModule.value) {
    const target = moduleTarget.value
    if (!target) return { tone: 'low', text: '暂无待养成模组' }
    return {
      tone: skillTone(target.current >= target.target ? 3 : target.current),
      text: target.label + ' · ' + (target.current ? target.current + ' 级' : '未解锁')
    }
  }
  if (!supportsMastery.value) {
    return {
      tone: 'low',
      text: (props.operator.modules || []).length ? '等级与模组养成' : '等级养成'
    }
  }
  const row = skillRows.value[activeSkillIndex.value] || skillRows.value[0]
  return { tone: row.tone, text: row.name + ' · ' + masteryLabel(row.current) }
})
const activeRate = computed(() => {
  if (activeLevel.value) return null
  if (activeModule.value) return moduleTarget.value?.rate ?? null
  if (!supportsMastery.value) return null
  const row = skillRows.value[activeSkillIndex.value] || skillRows.value[0]
  return row?.rate ?? null
})
const activeRateLabel = computed(() => (activeModule.value ? '解锁率' : '专三率'))
const activeRateTitle = computed(() => {
  if (activeRate.value === null || activeRate.value === undefined) return '暂无公开样本'
  if (activeModule.value && moduleTarget.value) {
    return moduleTarget.value.label + ' · 一图流公开模组解锁率 ' + formatRate(activeRate.value)
  }
  const row = skillRows.value[activeSkillIndex.value] || skillRows.value[0]
  return (row?.name || '') + ' · 一图流公开专三率 ' + formatRate(activeRate.value)
})
function selectSkill(index) {
  pickedByUser.value = true
  activeLevel.value = false
  activeModule.value = false
  activeSkillIndex.value = index
}
function selectModule(id = moduleTargets.value[0]?.id || moduleRows.value[0]?.id) {
  if (!moduleRows.value.some((row) => row.id === id)) return
  pickedByUser.value = true
  activeLevel.value = false
  activeModule.value = true
  activeModuleId.value = id
}
const surveyMatches = computed(
  () =>
    Boolean(props.survey?.eliteHighlight) ||
    Boolean(props.survey?.skillHighlights?.length) ||
    Boolean(props.survey?.moduleHighlights?.length)
)
const surveyMatchLabel = computed(() => {
  const labels = []
  if (props.survey?.eliteHighlight) labels.push('精英化目标')
  for (const row of skillRows.value) if (row.highlighted) labels.push(row.name)
  for (const module of props.operator.modules || []) {
    if ((props.survey?.moduleHighlights || []).includes(module.id))
      labels.push(module.name || module.type || module.id)
  }
  return labels.length ? '达到筛选门槛：' + labels.join('、') : ''
})
const levelLabel = computed(
  () => eliteLabel(props.operator.elite) + ' ' + (props.operator.level ?? 1) + ' 级'
)
const levelProgress = computed(() => {
  const target = levelTarget.value
  if (!target) return ''
  if (target.currentElite === target.elite)
    return '距满级 ' + (target.level - target.currentLevel) + ' 级'
  return '目标 ' + eliteLabel(target.elite) + ' ' + target.level + ' 级'
})

function open() {
  emit('open', props.operator)
}

function keydown(event) {
  if (event.key === 'Enter' || event.key === ' ') {
    event.preventDefault()
    open()
  }
}

// 技能段是卡片里的独立按钮：拦下 keyboard 冒泡，避免回车/空格连带打开整卡档案。
function stopKeydownPropagation(event) {
  event.stopPropagation()
}
</script>

<template>
  <article
    class="growth-opcard"
    :class="[
      'growth-opcard--' + layout,
      'growth-opcard--rarity-' + (operator.rarity ?? 0),
      {
        'is-planned': planned,
        'is-survey-match': surveyMatches,
        'growth-opcard--three-modules': moduleRows.length >= 3
      }
    ]"
    role="button"
    tabindex="0"
    :aria-label="operator.name + ' 的养成档案' + (surveyMatchLabel ? '，' + surveyMatchLabel : '')"
    :title="surveyMatchLabel || undefined"
    @click="open"
    @keydown="keydown"
  >
    <GrowthGameIcon
      kind="profession"
      :value="operator.profession"
      class="growth-opcard__profession"
    />
    <span v-if="rank" class="growth-opcard__rank gp-num" aria-hidden="true">{{ rank }}</span>

    <div class="growth-opcard__head">
      <GrowthAvatar
        :name="operator.name"
        :rarity="operator.rarity"
        :size="layout === 'compact' ? 42 : 'var(--opcard-avatar-size, 58px)'"
      />
      <div class="growth-opcard__id">
        <div class="growth-opcard__identity">
          <h3 class="growth-opcard__name" :title="operator.name">{{ operator.name }}</h3>
          <span class="growth-opcard__level gp-mono" :title="levelLabel" :aria-label="levelLabel">
            <GrowthGameIcon kind="elite" :value="operator.elite ?? 0" />
            <span class="growth-opcard__level-text">
              <span class="growth-opcard__level-prefix">Lv</span>
              <span>{{ operator.level ?? 1 }}</span>
            </span>
          </span>
        </div>
        <p class="growth-opcard__meta">
          <span class="gp-mono growth-opcard__rarity">{{ operator.rarity }}★</span>
          <span class="growth-opcard__profession-label">{{
            professionName(operator.profession)
          }}</span>
        </p>
      </div>
    </div>

    <p
      class="growth-opcard__skill"
      :class="'growth-opcard__skill--' + statusLine.tone"
      aria-live="polite"
    >
      <span class="growth-opcard__skill-text">{{ statusLine.text }}</span>
    </p>

    <div class="growth-opcard__progress">
      <div
        v-if="supportsMastery"
        class="growth-opcard__skills"
        role="group"
        aria-label="技能专精进度"
      >
        <button
          v-for="row in skillRows"
          :key="row.index"
          type="button"
          class="growth-opcard__seg"
          :class="{
            'is-active': !activeLevel && !activeModule && activeSkillIndex === row.index,
            'is-highlighted': row.highlighted,
            'is-done': row.current >= 3,
            'is-partial': row.current > 0 && row.current < 3,
            'is-locked': row.current === 0
          }"
          :aria-pressed="!activeLevel && !activeModule && activeSkillIndex === row.index"
          :aria-label="
            row.name + ' ' + masteryLabel(row.current) + (row.highlighted ? '，达到筛选门槛' : '')
          "
          :title="row.name + ' · ' + masteryLabel(row.current)"
          @click.stop="selectSkill(row.index)"
          @keydown="stopKeydownPropagation"
        >
          <GrowthGameIcon kind="mastery" :value="row.current" />
        </button>
      </div>
      <div
        v-if="moduleRows.length"
        class="growth-opcard__modules"
        role="group"
        aria-label="全部模组进度"
      >
        <button
          v-for="module in moduleRows"
          :key="module.id"
          type="button"
          class="growth-opcard__seg growth-opcard__seg--module"
          :style="{ color: module.badge.color }"
          :class="{
            'is-active': activeModule && activeModuleId === module.id,
            'is-highlighted': module.highlighted,
            'is-done': module.current >= module.target,
            'is-partial': module.current > 0 && module.current < module.target,
            'is-locked': module.current === 0
          }"
          :aria-pressed="activeModule && activeModuleId === module.id"
          :aria-label="
            '模组 ' +
            module.label +
            ' ' +
            (module.current ? module.current + ' 级' : '未解锁') +
            (module.highlighted ? '，达到筛选门槛' : '')
          "
          :title="
            [module.type, module.name, module.current ? module.current + ' 级' : '未解锁']
              .filter(Boolean)
              .join(' · ')
          "
          @click.stop="selectModule(module.id)"
          @keydown="stopKeydownPropagation"
        >
          <GrowthGameIcon kind="module" :value="module.type" :module-id="module.id" />
          <sub v-if="module.current" class="growth-opcard__module-level" aria-hidden="true">{{
            module.current
          }}</sub>
        </button>
      </div>
      <span v-if="!supportsMastery && !moduleRows.length" class="growth-opcard__progress-note"
        >暂不支持专精与模组</span
      >
    </div>

    <footer class="growth-opcard__foot">
      <span v-if="planned" class="gp-stamp gp-stamp--flat growth-opcard__stamp"
        >计划中{{ plannedCount > 1 ? ' ' + plannedCount : '' }}</span
      >
      <span v-else-if="activeLevel && levelTarget" class="growth-opcard__probe gp-mono">{{
        levelProgress
      }}</span>
      <span
        v-else-if="activeRate !== null"
        class="growth-opcard__probe gp-mono"
        :title="activeRateTitle"
        >{{ activeRateLabel }} {{ formatRate(activeRate) }}</span
      >
      <span v-else class="growth-opcard__probe gp-mono">暂无样本</span>
      <span class="growth-opcard__enter" aria-hidden="true">档案 →</span>
    </footer>
  </article>
</template>

<style scoped>
.growth-opcard {
  --opcard-surface: var(--gp-surface);
  position: relative;
  isolation: isolate;
  display: flex;
  flex-direction: column;
  gap: 10px;
  min-width: 0;
  overflow: hidden;
  padding: 14px 15px 12px;
  border-radius: 16px;
  background: var(--opcard-surface);
  box-shadow: inset 0 0 0 1px var(--gp-hair-soft);
  text-align: left;
  cursor: pointer;
  transition:
    transform 220ms var(--gp-ease),
    box-shadow 220ms var(--gp-ease),
    background 220ms var(--gp-ease);
}
.growth-opcard--rarity-6 {
  --opcard-surface: var(--gp-rarity-surface-6);
}
.growth-opcard--rarity-5 {
  --opcard-surface: var(--gp-rarity-surface-5);
}
.growth-opcard--rarity-4 {
  --opcard-surface: var(--gp-rarity-surface-4);
}
.growth-opcard--rarity-3,
.growth-opcard--rarity-2,
.growth-opcard--rarity-1 {
  --opcard-surface: var(--gp-rarity-surface-low);
}
.growth-opcard:hover {
  transform: translateY(-2px);
  box-shadow:
    inset 0 0 0 1px var(--gp-hair),
    0 18px 34px -28px rgba(20, 20, 22, 0.55);
}
.growth-opcard:focus-visible {
  outline: 2px solid var(--gp-accent);
  outline-offset: 2px;
}
.growth-opcard__profession {
  position: absolute;
  z-index: -1;
  top: -10px;
  right: -14px;
  width: 124px;
  height: 124px;
  color: var(--gp-ink);
  opacity: 0.045;
  pointer-events: none;
}
.growth-opcard__head {
  display: flex;
  align-items: center;
  gap: 10px;
  min-width: 0;
}
.growth-opcard__id {
  flex: 1;
  min-width: 0;
}
.growth-opcard__identity {
  display: flex;
  align-items: center;
  gap: 6px;
}
.growth-opcard__name {
  min-width: 0;
  margin: 0;
  overflow: hidden;
  color: var(--gp-ink);
  font-size: 15.5px;
  font-weight: 700;
  letter-spacing: -0.01em;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.growth-opcard__level {
  display: inline-flex;
  flex: none;
  align-items: center;
  gap: 4px;
  color: var(--gp-ink-2);
  font-size: 11px;
  line-height: 1;
}
.growth-opcard__level .growth-game-icon {
  width: 20px;
  height: 20px;
  filter: drop-shadow(0 1px 1.5px rgb(24 25 28 / 35%));
}
.growth-opcard__level-text {
  display: inline-flex;
  align-items: baseline;
  gap: 1px;
}
.growth-opcard__level-prefix {
  font-size: 0.8em;
}
.growth-opcard__meta {
  display: flex;
  align-items: center;
  gap: 5px;
  margin: 4px 0 0;
  color: var(--gp-muted);
  font-size: 11px;
}
.growth-opcard__rarity {
  color: var(--gp-ink-2);
  font-weight: 700;
}
.growth-opcard__profession-label {
  position: absolute;
  width: 1px;
  height: 1px;
  overflow: hidden;
  clip-path: inset(50%);
  white-space: nowrap;
}
.growth-opcard__skill {
  display: flex;
  align-items: center;
  min-height: 18px;
  margin: 0;
  overflow: hidden;
  color: var(--gp-ink-2);
  font-size: 12px;
  line-height: 1.5;
  white-space: nowrap;
}
.growth-opcard__skill-text {
  overflow: hidden;
  text-overflow: ellipsis;
}
.growth-opcard__skill--done {
  color: var(--gp-accent-ink);
  font-weight: 650;
}
.growth-opcard__skill--warn {
  color: var(--gp-warn);
  font-weight: 650;
}
.growth-opcard__skill--low {
  color: var(--gp-muted);
}
.growth-opcard__progress {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 6px;
  min-width: 0;
  min-height: 34px;
}
.growth-opcard__skills,
.growth-opcard__modules {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 3px;
  max-width: 100%;
}
.growth-opcard__modules {
  gap: 1px;
}
.growth-opcard__skills + .growth-opcard__modules {
  padding-left: 7px;
  border-left: 1px solid var(--gp-hair-soft);
}
.growth-opcard__seg {
  position: relative;
  display: inline-flex;
  flex: none;
  align-items: center;
  justify-content: center;
  width: 30px;
  height: 34px;
  padding: 3px 3px 6px;
  border: 0;
  border-radius: 6px;
  color: var(--gp-muted);
  background: transparent;
  cursor: pointer;
  transition:
    color 160ms var(--gp-ease),
    background 160ms var(--gp-ease),
    box-shadow 160ms var(--gp-ease);
}
.growth-opcard__seg > .growth-game-icon {
  width: 24px;
  height: 24px;
}
.growth-opcard__seg--module {
  width: 26px;
}
.growth-opcard__seg--module > .growth-game-icon {
  width: 26px;
  height: 32px;
}
.growth-opcard__module-level {
  position: absolute;
  right: 1px;
  bottom: 7px;
  font-family: var(--gp-mono);
  font-size: 8px;
  font-weight: 600;
  line-height: 1;
}
.growth-opcard__seg.is-partial {
  color: var(--gp-warn);
}
.growth-opcard__seg.is-done {
  color: var(--gp-accent-ink);
}
.growth-opcard__seg--module.is-locked > .growth-game-icon {
  opacity: 0.3;
}
.growth-opcard__seg--module:not(.is-locked) > .growth-game-icon {
  --module-pattern-opacity: 0.55;
}
.growth-opcard__seg--module:not(.is-locked):hover > .growth-game-icon,
.growth-opcard__seg--module:not(.is-locked):focus-visible > .growth-game-icon,
.growth-opcard__seg--module.is-active:not(.is-locked) > .growth-game-icon {
  --module-pattern-opacity: 0.85;
}
.growth-opcard__seg:hover,
.growth-opcard__seg:focus-visible {
  color: var(--gp-ink);
}
.growth-opcard__skills .growth-opcard__seg.is-active > .growth-game-icon {
  filter: drop-shadow(0 0 4px rgb(160 164 171 / 85%));
}
.growth-opcard__seg:focus-visible {
  outline: 2px solid var(--gp-accent);
  outline-offset: 1px;
}
.growth-opcard__seg.is-highlighted {
  box-shadow: inset 0 0 0 1px var(--gp-accent);
}
.growth-opcard__progress-note {
  color: var(--gp-muted);
  font-size: 10.5px;
}
.growth-opcard__foot {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  height: 22px;
  margin-top: auto;
}
.growth-opcard__probe {
  color: var(--gp-muted);
  font-size: 10.5px;
  letter-spacing: 0.02em;
}
.growth-opcard__stamp {
  font-size: 9.5px;
}
.growth-opcard__enter {
  margin-left: auto;
  color: var(--gp-faint);
  font-size: 11px;
  font-weight: 600;
  transition: color 160ms var(--gp-ease);
}
.growth-opcard:hover .growth-opcard__enter {
  color: var(--gp-accent-ink);
}
.growth-opcard__rank {
  position: absolute;
  z-index: -1;
  top: 51px;
  right: 12px;
  color: var(--gp-ink);
  opacity: 0.08;
  font-size: 30px;
  line-height: 1;
  pointer-events: none;
}
.growth-opcard.is-planned {
  background: color-mix(in srgb, var(--opcard-surface) 96%, var(--gp-ink));
}
.growth-opcard.is-survey-match {
  box-shadow: inset 0 0 0 1px var(--gp-accent);
}
.growth-opcard--compact {
  padding: 12px 13px 10px;
}
.growth-opcard--compact .growth-opcard__skill {
  font-size: 11.5px;
}
.growth-opcard--compact .growth-opcard__head {
  gap: 8px;
}
.growth-opcard--compact .growth-opcard__name {
  font-size: 14px;
}
.growth-opcard--compact .growth-opcard__level {
  gap: 3px;
  font-size: 10px;
}
.growth-opcard--compact .growth-opcard__level .growth-game-icon {
  width: 17px;
  height: 17px;
}
@media (max-width: 520px) {
  .growth-opcard {
    --opcard-avatar-size: 42px;
  }
  .growth-opcard__head {
    gap: 8px;
  }
  .growth-opcard__identity {
    gap: 3px;
  }
  .growth-opcard__level {
    gap: 2px;
    font-size: 10px;
  }
  .growth-opcard__level .growth-game-icon {
    width: 17px;
    height: 17px;
  }
  .growth-opcard__progress {
    gap: 4px;
  }
  .growth-opcard__skills,
  .growth-opcard__modules {
    gap: 1px;
  }
  .growth-opcard__skills + .growth-opcard__modules {
    padding-left: 4px;
  }
  .growth-opcard__seg {
    width: 24px;
  }
  .growth-opcard__seg > .growth-game-icon {
    width: 22px;
    height: 22px;
  }
  .growth-opcard__seg--module {
    width: 26px;
  }
  .growth-opcard__seg--module > .growth-game-icon {
    width: 26px;
    height: 26px;
  }
  .growth-opcard--three-modules .growth-opcard__progress {
    gap: 3px;
  }
  .growth-opcard--three-modules .growth-opcard__skills + .growth-opcard__modules {
    padding-left: 3px;
  }
  .growth-opcard--three-modules .growth-opcard__seg {
    width: 21px;
  }
  .growth-opcard--three-modules .growth-opcard__seg--module > .growth-game-icon {
    width: 23px;
  }
}
@media (max-width: 380px) {
  .growth-opcard--three-modules .growth-opcard__progress {
    gap: 2px;
  }
  .growth-opcard--three-modules .growth-opcard__skills + .growth-opcard__modules {
    padding-left: 2px;
  }
  .growth-opcard--three-modules .growth-opcard__seg {
    width: 19px;
  }
  .growth-opcard--three-modules .growth-opcard__seg--module > .growth-game-icon {
    width: 21px;
  }
}
@media (prefers-reduced-motion: reduce) {
  .growth-opcard,
  .growth-opcard__enter,
  .growth-opcard__seg {
    transition: none;
  }
  .growth-opcard:hover {
    transform: none;
  }
}
</style>
