<template>
  <n-card v-if="choices.length" size="small" class="level-card" title="等级与精英化">
    <n-space justify="space-between" align="center" :size="10">
      <n-text depth="3">当前：{{ eliteLabel(operator.elite) }} {{ operator.level }} 级</n-text>
      <n-text strong>目标：{{ displayedChoice?.label || '未规划' }}</n-text>
    </n-space>
    <div class="level-slider">
      <n-slider
        :value="draftIndex"
        @update:value="updateDraft"
        @dragstart="dragging = true"
        @dragend="finishDrag"
        :min="0"
        :max="choices.length"
        :step="1"
        :marks="marks"
        :disabled="saving || committing"
        :format-tooltip="formatTarget"
        aria-label="等级与精英化目标"
      />
    </div>
    <n-text depth="3" class="overview-note">
      松开后自动保存，已选养成项目的最低前置会自动保留。
    </n-text>
    <n-text v-if="requiredKey" depth="3" class="overview-note">
      最低前置：{{ allChoices.find((choice) => choice.key === requiredKey)?.label }}
    </n-text>
    <MasteryMaterials
      v-if="displayedChoice?.summary"
      :summary="displayedChoice.summary"
      title="等级与精英化材料"
    />
  </n-card>
</template>

<script setup>
import { computed, nextTick, ref, watch } from 'vue'
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
const dragging = ref(false)
const committing = ref(false)
const eliteLabel = (elite) => ['精零', '精一', '精二'][elite] || `精${elite}`
const draftIndex = ref(0)
watch(() => [props.operator.char_id, props.selectedKey], resetDraft, { immediate: true })
const draftChoice = computed(() => choices.value[draftIndex.value - 1])
const displayedChoice = computed(
  () => draftChoice.value || allChoices.value.find((choice) => choice.key === props.requiredKey)
)
const draftKey = computed(() => draftChoice.value?.key || null)
const marks = computed(() =>
  Object.fromEntries([
    [0, '未规划'],
    ...choices.value.map((choice, index) => [
      index + 1,
      `${eliteLabel(choice.elite)} ${choice.level}`
    ])
  ])
)
function formatTarget(index) {
  return choices.value[index - 1]?.label || '未规划'
}
function resetDraft() {
  draftIndex.value = choices.value.findIndex((choice) => choice.key === props.selectedKey) + 1
}
function updateDraft(value) {
  if (props.saving || committing.value) return
  draftIndex.value = value
  if (!dragging.value) return commitDraft()
}
function finishDrag() {
  dragging.value = false
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
.level-slider {
  padding: 16px 20px 32px;
}
.level-card {
  margin-top: 12px;
}
.overview-note {
  display: block;
  margin: 8px 0;
  font-size: 12px;
}
</style>
