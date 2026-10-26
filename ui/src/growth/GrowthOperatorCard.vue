<script setup>
import { computed, ref } from 'vue'
import GrowthAvatar from './GrowthAvatar.vue'
import { eliteLabel, formatRate, masteryLabel, professionName } from './growthFormatters'

const props = defineProps({
  operator: { type: Object, required: true },
  survey: { type: Object, default: null },
  planned: Boolean,
  plannedCount: { type: Number, default: 0 },
  rank: { type: [Number, String], default: null },
  layout: { type: String, default: 'grid' }
})
const emit = defineEmits(['open'])

const skills = computed(() => {
  const levels = props.operator.skill_levels || []
  const recommendations = props.operator.recommendations || []
  const count = Math.max(levels.length, ...recommendations.map((row) => row.skill_index + 1))
  return Array.from({ length: count }, (_, index) =>
    Number(
      levels[index] ?? recommendations.find((row) => row.skill_index === index)?.current_level ?? 0
    )
  )
})
const supportsMastery = computed(() => {
  const maxPhase =
    props.operator.max_phase ??
    (props.operator.rarity >= 4 ? 2 : props.operator.rarity === 3 ? 1 : 0)
  return maxPhase >= 2 && skills.value.length > 0
})
const ordinal = ['一', '二', '三']
const masteredCount = computed(() => skills.value.filter((level) => level >= 3).length)
const activeSkill = ref(0)
function skillTone(level) {
  if (level >= 3) return 'done'
  if (level > 0) return 'warn'
  return 'low'
}
const skillRows = computed(() => {
  const recs = props.operator.recommendations || []
  return skills.value.map((level, index) => {
    const rec = recs.find((item) => Number(item.skill_index) === index)
    return {
      index,
      level,
      name: rec?.skill_name || ordinal[index] + '技能',
      tone: skillTone(level),
      highlighted: (props.survey?.skillHighlights || []).includes(index)
    }
  })
})
// 卡片只陈述选中技能的当前状态；三个技能段各读各的，不给出猜测性的下一步文案。
const statusLine = computed(() => {
  if (!supportsMastery.value) {
    return {
      tone: 'low',
      text: (props.operator.modules || []).length ? '等级与模组养成' : '等级养成'
    }
  }
  const row = skillRows.value[activeSkill.value] || skillRows.value[0]
  return { tone: row.tone, text: row.name + ' · ' + masteryLabel(row.level) }
})
function selectSkill(index) {
  activeSkill.value = index
}
const surveyProbe = computed(() => {
  const rates = props.survey?.skills || []
  const known = rates.filter((skill) => skill.rate !== null && skill.rate !== undefined)
  if (!known.length) return ''
  const best = known.reduce((left, right) => (right.rate > left.rate ? right : left))
  return '专三 ' + formatRate(best.rate)
})
const moduleCount = computed(
  () => (props.operator.modules || []).filter((module) => module.current_level > 0).length
)
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
const subtitle = computed(
  () =>
    professionName(props.operator.profession) +
    ' · ' +
    eliteLabel(props.operator.elite) +
    ' ' +
    (props.operator.level ?? 1) +
    ' 级'
)

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
      { 'is-planned': planned, 'is-survey-match': surveyMatches }
    ]"
    role="button"
    tabindex="0"
    :aria-label="operator.name + ' 的养成档案' + (surveyMatchLabel ? '，' + surveyMatchLabel : '')"
    :title="surveyMatchLabel || undefined"
    @click="open"
    @keydown="keydown"
  >
    <span v-if="rank" class="growth-opcard__rank gp-num" aria-hidden="true">{{ rank }}</span>

    <div class="growth-opcard__head">
      <GrowthAvatar
        :name="operator.name"
        :rarity="operator.rarity"
        :size="layout === 'compact' ? 46 : 58"
      />
      <div class="growth-opcard__id">
        <h3 class="growth-opcard__name">{{ operator.name }}</h3>
        <p class="growth-opcard__meta">
          <span class="gp-mono growth-opcard__rarity">{{ operator.rarity }}★</span>
          {{ subtitle }}
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

    <div
      v-if="supportsMastery"
      class="growth-opcard__progress"
      role="group"
      aria-label="技能专精进度"
    >
      <button
        v-for="row in skillRows"
        :key="row.index"
        type="button"
        class="growth-opcard__seg"
        :class="{
          'is-active': activeSkill === row.index,
          'is-highlighted': row.highlighted,
          'is-done': row.level >= 3,
          'is-partial': row.level > 0 && row.level < 3
        }"
        :aria-pressed="activeSkill === row.index"
        :aria-label="
          row.name + ' ' + masteryLabel(row.level) + (row.highlighted ? '，达到筛选门槛' : '')
        "
        @click.stop="selectSkill(row.index)"
        @keydown="stopKeydownPropagation"
      >
        <span class="growth-opcard__seg-bar" aria-hidden="true" />
      </button>
      <span class="growth-opcard__progress-label gp-mono">
        专三 {{ masteredCount }}/{{ skills.length }}
        <template v-if="moduleCount"> · 模组 {{ moduleCount }}</template>
      </span>
    </div>
    <div v-else class="growth-opcard__progress growth-opcard__progress--low">
      <span>等级 {{ eliteLabel(operator.elite) }} {{ operator.level }}</span>
      <template v-if="moduleCount"
        ><span> · 模组 {{ moduleCount }}</span></template
      >
    </div>

    <footer class="growth-opcard__foot">
      <span v-if="planned" class="gp-stamp gp-stamp--flat growth-opcard__stamp"
        >计划中{{ plannedCount > 1 ? ' ' + plannedCount : '' }}</span
      >
      <span v-else-if="surveyProbe" class="growth-opcard__probe gp-mono">{{ surveyProbe }}</span>
      <span v-else class="growth-opcard__probe gp-mono">无公开样本</span>
      <span class="growth-opcard__enter" aria-hidden="true">档案 →</span>
    </footer>
  </article>
</template>

<style scoped>
.growth-opcard {
  position: relative;
  display: flex;
  flex-direction: column;
  gap: 10px;
  min-width: 0;
  padding: 14px 15px 12px;
  border-radius: 16px;
  background: var(--gp-surface);
  box-shadow: inset 0 0 0 1px var(--gp-hair-soft);
  text-align: left;
  cursor: pointer;
  transition:
    transform 220ms var(--gp-ease),
    box-shadow 220ms var(--gp-ease),
    background 220ms var(--gp-ease);
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

.growth-opcard__head {
  display: flex;
  align-items: center;
  gap: 11px;
  min-width: 0;
}

.growth-opcard__id {
  min-width: 0;
}

.growth-opcard__name {
  margin: 0;
  overflow: hidden;
  color: var(--gp-ink);
  font-size: 15.5px;
  font-weight: 700;
  letter-spacing: -0.01em;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.growth-opcard__meta {
  margin: 3px 0 0;
  overflow: hidden;
  color: var(--gp-muted);
  font-size: 11.5px;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.growth-opcard__rarity {
  color: var(--gp-ink-2);
  font-weight: 700;
}

.growth-opcard__skill {
  display: flex;
  align-items: center;
  gap: 4px;
  margin: 0;
  overflow: hidden;
  color: var(--gp-ink-2);
  font-size: 12px;
  line-height: 1.45;
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
  align-items: center;
  gap: 3px;
  min-width: 0;
}

/* 每个技能段都是独立命中区：24x18 的按钮里放 22x4 的横条，hover 不改变任何盒尺寸。 */
.growth-opcard__seg {
  /* 光晕取色：未专精中性、专一/二琥珀、专三绿色，与等级节点共用同一套发光语言。 */
  /* 未专精用 --gp-hair：浅色主题即 rgba(24,25,28,0.15)，深色主题自动转为浅色光。 */
  --seg-glow: var(--gp-hair);
  --seg-inset: 0 0 transparent;
  display: inline-grid;
  flex: none;
  place-items: center;
  width: 24px;
  height: 18px;
  padding: 0;
  border: 0;
  border-radius: 6px;
  background: transparent;
  cursor: pointer;
}

.growth-opcard__seg.is-partial {
  --seg-glow: var(--gp-warn-block);
  --seg-inset: inset 0 0 0 1px var(--gp-warn);
}

.growth-opcard__seg.is-done {
  --seg-glow: var(--gp-accent-block);
}

.growth-opcard__seg:focus-visible {
  outline: 2px solid var(--gp-accent);
  outline-offset: 1px;
}

.growth-opcard__seg-bar {
  width: 22px;
  height: 4px;
  border-radius: 999px;
  background: var(--gp-surface-3);
  box-shadow: var(--seg-inset);
  opacity: 0.92;
  transition:
    background-color 160ms var(--gp-ease),
    box-shadow 160ms var(--gp-ease),
    opacity 160ms var(--gp-ease);
}

/* 光晕只用模糊层，没有硬边扩散：hover 单层，选中两层，hover 选中段略强。 */
.growth-opcard__seg:hover .growth-opcard__seg-bar,
.growth-opcard__seg:focus-visible .growth-opcard__seg-bar {
  box-shadow:
    var(--seg-inset),
    0 0 5px 2px var(--seg-glow);
  opacity: 1;
}

.growth-opcard__seg.is-active .growth-opcard__seg-bar {
  box-shadow:
    var(--seg-inset),
    0 0 6px 2px var(--seg-glow),
    0 0 12px 4px var(--seg-glow);
}

.growth-opcard__seg.is-active:hover .growth-opcard__seg-bar,
.growth-opcard__seg.is-active:focus-visible .growth-opcard__seg-bar {
  box-shadow:
    var(--seg-inset),
    0 0 8px 3px var(--seg-glow),
    0 0 14px 5px var(--seg-glow);
}

.growth-opcard__seg.is-partial .growth-opcard__seg-bar {
  background: var(--gp-warn-block);
}

.growth-opcard__seg.is-done .growth-opcard__seg-bar {
  background: var(--gp-accent);
}

.growth-opcard__progress--low {
  min-height: 18px;
  color: var(--gp-muted);
  font-size: 10.5px;
}

.growth-opcard__progress-label {
  min-width: 0;
  margin-left: 6px;
  overflow: hidden;
  color: var(--gp-muted);
  font-size: 10px;
  text-overflow: ellipsis;
  white-space: nowrap;
}

/* 固定页脚高度：计划中印章与专三率/无公开样本互换时不改变卡片高度。 */
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
  top: 10px;
  right: 12px;
  color: var(--gp-surface-3);
  font-size: 30px;
  line-height: 1;
}

.growth-opcard.is-planned {
  background: var(--gp-surface-2);
}

.growth-opcard.is-survey-match {
  box-shadow: inset 0 0 0 1px var(--gp-accent);
}

.growth-opcard__seg.is-highlighted .growth-opcard__seg-bar {
  outline: 1px solid var(--gp-accent);
  outline-offset: 2px;
}

.growth-opcard--compact {
  padding: 12px 13px 10px;
}

.growth-opcard--compact .growth-opcard__skill {
  font-size: 11.5px;
}

@media (prefers-reduced-motion: reduce) {
  .growth-opcard,
  .growth-opcard__enter,
  .growth-opcard__seg,
  .growth-opcard__seg-bar {
    transition: none;
  }
  .growth-opcard:hover {
    transform: none;
  }
}
</style>
