<template>
  <section v-if="choices.length" class="growth-level">
    <div class="growth-level__head">
      <div>
        <h4 class="growth-level__title">等级与精英化</h4>
        <p class="growth-level__current">
          <span class="growth-level__current-chip">当前</span>
          {{ eliteLabel(operator.elite) }} {{ operator.level }} 级
        </p>
      </div>
      <div class="growth-level__target">
        <span class="growth-level__target-label">目标</span>
        <span class="growth-level__target-row">
          <b :class="{ 'is-empty': !selectedKey }">{{ displayedChoice?.label || '未规划' }}</b>
          <button
            v-if="selectedKey"
            type="button"
            class="growth-level__clear"
            @click="updateDraft(0)"
          >
            清除
          </button>
        </span>
      </div>
    </div>

    <div
      class="growth-level__track"
      :class="{ 'is-idle': idle }"
      :style="{ '--node-count': choices.length }"
      role="group"
      aria-label="等级与精英化目标"
    >
      <span
        v-if="choices.length > 1"
        class="growth-level__rail"
        :style="{ left: railInset, right: railInset }"
        aria-hidden="true"
      >
        <span class="growth-level__rail-fill" :style="{ width: railFill }" />
        <span
          v-if="goalSegment"
          class="growth-level__rail-goal"
          :style="{ left: goalSegment.left, width: goalSegment.width }"
        />
      </span>
      <span
        v-if="!progress.done && !currentOnNode"
        class="growth-level__now"
        :style="{ left: nowLeft }"
        aria-hidden="true"
      />
      <button
        v-for="node in nodeList"
        :key="node.key"
        type="button"
        class="growth-level__node"
        :class="{
          'is-done': node.done,
          'is-target': node.target,
          'is-current': node.current,
          'is-selectable': node.selectable
        }"
        :disabled="node.done || saving || committing"
        :aria-label="
          node.done
            ? node.label + '（已达到）'
            : node.target
              ? node.label + '（当前目标）'
              : node.label
        "
        :aria-pressed="node.done ? undefined : node.target"
        @click="selectNode(node)"
      >
        <span class="growth-level__node-dot" aria-hidden="true">
          <span
            v-if="node.done || node.target"
            class="growth-level__node-glyph growth-level__node-glyph--check"
          >
            <n-icon :component="CheckmarkOutline" :size="14" />
          </span>
          <span v-if="node.target" class="growth-level__node-glyph growth-level__node-glyph--close">
            <n-icon :component="CloseOutline" :size="14" />
          </span>
          <span
            v-if="node.selectable"
            class="growth-level__node-glyph growth-level__node-glyph--plus"
          >
            <n-icon :component="AddOutline" :size="14" />
          </span>
        </span>
        <span class="growth-level__node-label">{{ node.short }}</span>
      </button>
    </div>

    <div class="growth-level__meta">
      <span v-if="requiredKey" class="growth-level__required">
        最低前置：{{ allChoices.find((choice) => choice.key === requiredKey)?.label }}
      </span>
      <span v-else class="growth-level__hint">{{
        idle ? '选一个里程碑作为目标，材料会自动算好' : '点击节点设置目标；再次点击当前目标可清除'
      }}</span>
    </div>

    <MasteryMaterials
      v-if="displayedChoice?.summary"
      :summary="displayedChoice.summary"
      title="等级与精英化材料"
    />
  </section>
</template>

<script setup>
import { computed, nextTick, ref, watch } from 'vue'
import AddOutline from '@vicons/ionicons5/es/AddOutline'
import CheckmarkOutline from '@vicons/ionicons5/es/CheckmarkOutline'
import CloseOutline from '@vicons/ionicons5/es/CloseOutline'
import { operatorLevelGoals } from '@/utils/growthPlanning'
import MasteryMaterials from '@/components/MasteryMaterials.vue'

const props = defineProps({
  operator: { type: Object, required: true },
  selectedKey: { type: String, default: null },
  requiredKey: { type: String, default: null },
  saving: Boolean,
  applyTarget: { type: Function, required: true }
})
const allChoices = computed(() => operatorLevelGoals(props.operator))
const choices = computed(() =>
  props.operator.rarity <= 3 ? allChoices.value.slice(-1) : allChoices.value
)
const committing = ref(false)
const eliteLabel = (elite) => ['精零', '精一', '精二'][elite] || '精' + elite
const draftIndex = ref(0)
watch(() => [props.operator.char_id, props.selectedKey], resetDraft, { immediate: true })
const draftChoice = computed(() => choices.value[draftIndex.value - 1])
const displayedChoice = computed(
  () =>
    draftChoice.value ||
    allChoices.value.find((choice) => choice.key === props.selectedKey) ||
    allChoices.value.find((choice) => choice.key === props.requiredKey)
)
const draftKey = computed(() => draftChoice.value?.key || null)

const currentNode = computed(() => ({
  elite: props.operator.elite ?? 0,
  level: props.operator.level ?? 1
}))

function isReached(choice) {
  const current = currentNode.value
  if (current.elite > choice.elite) return true
  if (current.elite < choice.elite) return false
  return current.level >= choice.level
}

const nodeList = computed(() => {
  const reached = choices.value.filter(isReached)
  const currentKey = reached.length ? reached[reached.length - 1].key : null
  return choices.value.map((choice, index) => {
    const done = isReached(choice)
    const target = !done && props.selectedKey === choice.key
    return {
      key: choice.key,
      index: index + 1,
      label: choice.label,
      short: eliteLabel(choice.elite) + ' ' + choice.level,
      done,
      target,
      // 只有未达成且未选中的节点可以「设为目标」；已完成节点保持惰性展示。
      selectable: !done && !target,
      current: choice.key === currentKey
    }
  })
})

// 轨道显示当前进度：已达成的部分连成绿线，当前等级在两节点之间按等级插值。
const railInset = computed(() => (choices.value.length > 1 ? 50 / choices.value.length + '%' : '0'))
const progress = computed(() => {
  const options = choices.value
  const count = options.length
  const current = currentNode.value
  const reachedCount = options.filter(isReached).length
  if (count <= 1) return { ratio: reachedCount ? 1 : 0, done: reachedCount >= count }
  if (reachedCount === 0) return { ratio: 0, done: false }
  if (reachedCount >= count) return { ratio: 1, done: true }
  const from = options[reachedCount - 1]
  const to = options[reachedCount]
  let fraction = 0.5
  if (from.elite === to.elite) {
    const span = to.level - from.level
    fraction = span > 0 ? (current.level - from.level) / span : 0
  }
  fraction = Math.max(0, Math.min(1, fraction))
  return { ratio: (reachedCount - 1 + fraction) / (count - 1), done: false }
})
const railFill = computed(() => progress.value.ratio * 100 + '%')
const idle = computed(() => !props.selectedKey && !nodeList.value.some((node) => node.done))
const nowLeft = computed(() => {
  const count = choices.value.length
  if (count <= 1) return '50%'
  const inset = 50 / count
  return inset + progress.value.ratio * (100 - inset * 2) + '%'
})

// 当前练度正好落在里程碑节点上时，不再叠一个小圆点，避免遮住节点勾选状态。
const currentOnNode = computed(() => {
  const count = choices.value.length
  if (count <= 1) return progress.value.ratio >= 1
  const step = 1 / (count - 1)
  const nearest = Math.round(progress.value.ratio / step) * step
  return Math.abs(progress.value.ratio - nearest) < 0.02
})

// 当前练度到已选目标之间的差额，用红色虚线画在轨道上。
const goalSegment = computed(() => {
  const index = choices.value.findIndex((choice) => choice.key === props.selectedKey)
  const count = choices.value.length
  if (index < 0 || count <= 1) return null
  const targetRatio = index / (count - 1)
  const start = progress.value.ratio
  if (targetRatio <= start + 0.002) return null
  return { left: start * 100 + '%', width: (targetRatio - start) * 100 + '%' }
})

function selectNode(node) {
  if (node.done) return
  if (props.saving || committing.value) return
  if (node.target) return updateDraft(0)
  return updateDraft(node.index)
}

function resetDraft() {
  draftIndex.value = choices.value.findIndex((choice) => choice.key === props.selectedKey) + 1
}
function updateDraft(value) {
  if (props.saving || committing.value) return
  draftIndex.value = value
  return commitDraft()
}
async function commitDraft() {
  if (props.saving || committing.value) return
  if (draftKey.value === props.selectedKey) return
  committing.value = true
  try {
    await props.applyTarget(draftKey.value)
  } finally {
    await nextTick()
    committing.value = false
    resetDraft()
  }
}
</script>

<style scoped>
.growth-level {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.growth-level__head {
  display: flex;
  align-items: flex-end;
  justify-content: space-between;
  gap: 12px;
}

.growth-level__title {
  margin: 0;
  color: var(--gp-ink);
  font-size: 13.5px;
  font-weight: 700;
}

.growth-level__current {
  display: flex;
  align-items: center;
  gap: 6px;
  margin: 3px 0 0;
  color: var(--gp-ink);
  font-size: 11.5px;
  font-weight: 650;
}

.growth-level__current-chip {
  padding: 0 6px;
  border-radius: 999px;
  background: var(--gp-accent-block);
  color: var(--gp-accent-ink);
  font-size: 9px;
  font-weight: 700;
  letter-spacing: 0.08em;
  line-height: 1.7;
}

.growth-level__target {
  display: flex;
  flex-direction: column;
  align-items: flex-end;
  gap: 2px;
  text-align: right;
}

.growth-level__target-label {
  color: var(--gp-faint);
  font-size: 10.5px;
  letter-spacing: 0.04em;
}

.growth-level__target-row {
  display: flex;
  align-items: baseline;
  gap: 8px;
}

.growth-level__target b {
  color: var(--gp-ink);
  font-size: 13.5px;
  font-weight: 700;
}

.growth-level__target b.is-empty {
  color: var(--gp-muted);
  font-weight: 600;
}

.growth-level__clear {
  padding: 0;
  border: 0;
  background: transparent;
  color: var(--gp-faint);
  font: inherit;
  font-size: 10.5px;
  text-decoration: underline;
  text-underline-offset: 2px;
  cursor: pointer;
}

.growth-level__clear:hover {
  color: var(--gp-ink);
}

.growth-level__track {
  position: relative;
  display: grid;
  grid-template-columns: repeat(var(--node-count), minmax(0, 1fr));
  align-items: start;
  gap: 4px;
  padding: 8px 2px 0;
}

.growth-level__rail {
  position: absolute;
  top: 19px;
  height: 2px;
  border-radius: 2px;
  background: var(--gp-surface-3);
}

/* 实际练度位置：轨道上的一个小圆点，配合已达成部分的绿线。 */
.growth-level__now {
  position: absolute;
  top: 14px;
  z-index: 2;
  width: 12px;
  height: 12px;
  border: 2px solid var(--gp-accent);
  border-radius: 999px;
  background: var(--gp-surface);
  box-shadow: 0 0 0 3px var(--gp-accent-block);
  transform: translateX(-50%);
  pointer-events: none;
}

.growth-level__rail-fill {
  display: block;
  height: 100%;
  border-radius: inherit;
  background: var(--gp-accent);
  transition: width 0.25s var(--gp-ease);
}

.growth-level__rail-goal {
  position: absolute;
  top: 0;
  height: 100%;
  border-radius: inherit;
  background: repeating-linear-gradient(
    90deg,
    var(--gp-signal) 0 5px,
    rgba(196, 71, 46, 0.28) 5px 9px
  );
}

.growth-level__node {
  position: relative;
  z-index: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 7px;
  padding: 0;
  border: 0;
  border-radius: 12px;
  background: transparent;
  color: var(--gp-muted);
  font: inherit;
  cursor: pointer;
}

/* 已完成节点只做展示：不可点击、不可聚焦、不响应 hover。 */
.growth-level__node.is-done,
.growth-level__node:disabled {
  cursor: default;
}

/* 保存过程中其余节点暂时不可点，弱化但不参与 hover 位移。 */
.growth-level__node:disabled:not(.is-done) {
  opacity: 0.55;
}

.growth-level__node:focus-visible {
  outline: none;
}

.growth-level__node:focus-visible .growth-level__node-dot {
  outline: 2px solid var(--gp-accent);
  outline-offset: 3px;
}

.growth-level__node-dot {
  position: relative;
  display: grid;
  place-items: center;
  width: 24px;
  height: 24px;
  border-radius: 999px;
  background: var(--gp-surface);
  box-shadow: inset 0 0 0 1px var(--gp-hair);
  color: var(--gp-signal);
  transition:
    background-color 0.18s var(--gp-ease),
    box-shadow 0.18s var(--gp-ease),
    color 0.18s var(--gp-ease);
}

/* 同一个圆点里叠放图标，hover 只切换透明度，不改变尺寸与占位。 */
.growth-level__node-glyph {
  grid-area: 1 / 1;
  display: grid;
  place-items: center;
  transition:
    color 0.18s var(--gp-ease),
    opacity 0.18s var(--gp-ease);
}

.growth-level__node.is-done .growth-level__node-dot {
  background: var(--gp-accent);
  box-shadow:
    inset 0 0 0 1px var(--gp-accent),
    0 0 0 3px var(--gp-accent-block),
    0 3px 12px -3px rgba(24, 160, 88, 0.5);
  color: #ffffff;
}

/* 可设目标的节点 = 空心圆 + 一圈柔和发光，圆点内常驻细笔画「+」图标（不参与占位）。 */
.growth-level__node-glyph--plus {
  color: var(--gp-muted);
}

.growth-level__node.is-selectable .growth-level__node-dot {
  box-shadow:
    inset 0 0 0 1px color-mix(in srgb, var(--gp-accent) 48%, transparent),
    0 0 0 3px var(--gp-accent-block);
}

/* hover 只让圆环与发光增强：内环转实色、外圈扩到 6px 并叠一层更淡的光。 */
.growth-level__node.is-selectable:hover:not(:disabled) .growth-level__node-dot {
  box-shadow:
    inset 0 0 0 1.5px var(--gp-accent),
    0 0 0 3px var(--gp-accent-block),
    0 0 0 6px color-mix(in srgb, var(--gp-accent-block) 55%, transparent);
}

.growth-level__node.is-selectable:hover:not(:disabled) .growth-level__node-glyph--plus {
  color: var(--gp-accent-ink);
}

.growth-level__node.is-selectable:hover:not(:disabled) .growth-level__node-label {
  color: var(--gp-ink-2);
}

/* 已选目标：保留 signal 圆环与外圈，hover 只在外层再加一圈柔光，并把勾原位换成 ×。 */
.growth-level__node.is-target .growth-level__node-dot {
  box-shadow:
    inset 0 0 0 1.5px var(--gp-signal),
    0 0 0 3px var(--gp-signal-block);
  color: var(--gp-signal);
}

.growth-level__node.is-target:hover:not(:disabled) .growth-level__node-dot {
  box-shadow:
    inset 0 0 0 1.5px var(--gp-signal),
    0 0 0 3px var(--gp-signal-block),
    0 0 0 6px var(--gp-signal-block);
}

.growth-level__node.is-target .growth-level__node-glyph--close {
  opacity: 0;
}

.growth-level__node.is-target:hover:not(:disabled) .growth-level__node-glyph--check {
  opacity: 0;
}

.growth-level__node.is-target:hover:not(:disabled) .growth-level__node-glyph--close {
  opacity: 1;
}

.growth-level__node.is-target .growth-level__node-label {
  color: var(--gp-signal);
  font-weight: 650;
}

.growth-level__node-label {
  max-width: 100%;
  overflow: hidden;
  color: var(--gp-faint);
  font-size: 10px;
  line-height: 1.35;
  text-overflow: ellipsis;
  white-space: nowrap;
  transition: color 0.18s var(--gp-ease);
}

.growth-level__node.is-done .growth-level__node-label {
  color: var(--gp-accent-ink);
}

.growth-level__meta {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  flex-wrap: wrap;
  font-size: 10.5px;
}

.growth-level__required {
  color: var(--gp-warn);
}

.growth-level__hint {
  color: var(--gp-faint);
}

@media (prefers-reduced-motion: reduce) {
  .growth-level__node-dot,
  .growth-level__node-glyph,
  .growth-level__node-label,
  .growth-level__rail-fill {
    transition: none;
  }
}
</style>
