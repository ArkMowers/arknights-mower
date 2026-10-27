<script setup>
import { i18n } from '@/i18n'
import { operatorDisplayName } from '@/i18n/gameNames'
import { reportErrorMessage } from '@/i18n/reports'
const { t } = i18n.global
import { computed, ref, watch } from 'vue'
import { MAX_MOOD_VIEW_OPERATORS } from '@/utils/mood_observation'

const props = defineProps({
  show: { type: Boolean, default: false },
  view: { type: Object, default: null },
  catalog: { type: Array, default: () => [] }
})
const emit = defineEmits(['update:show', 'save', 'remove'])
const name = ref('')
const selected = ref([])
const error = ref('')
const options = computed(() =>
  props.catalog.map((item) => ({
    label:
      operatorDisplayName(item.name) +
      (item.sampleCount === 0
        ? t('reports.noSamplesSuffix')
        : item.sampleCount != null
          ? t('reports.sampleCountSuffix', { count: item.sampleCount })
          : ''),
    value: item.name
  }))
)
watch(
  () => [props.show, props.view],
  () => {
    if (!props.show) return
    name.value = props.view?.name ?? ''
    selected.value = [...(props.view?.operators ?? [])]
    error.value = ''
  },
  { immediate: true }
)

function submit() {
  const title = name.value.trim()
  if (!title || title.length > 30) {
    error.value = t('reports.invalidObservationName')
    return
  }
  if (selected.value.length < 1 || selected.value.length > MAX_MOOD_VIEW_OPERATORS) {
    error.value = t('reports.invalidObservationOperators')
    return
  }
  emit('save', { id: props.view?.id, name: title, operators: [...selected.value] })
}

function close() {
  emit('update:show', false)
}
</script>

<template>
  <n-modal
    :show="show"
    preset="card"
    :title="view ? t('reports.editObservation') : t('reports.createObservation')"
    style="width: min(94vw, 550px)"
    @update:show="emit('update:show', $event)"
  >
    <div class="observation-fields">
      <label>
        <span>{{ t('reports.observationName') }}</span>
        <n-input
          v-model:value="name"
          maxlength="30"
          :placeholder="t('reports.observationExample')"
        />
      </label>
      <div class="observation-field">
        <span>{{ t('reports.chooseObservationOperators') }}</span>
        <n-select
          v-model:value="selected"
          :options="options"
          multiple
          filterable
          tag
          clearable
          :max-tag-count="3"
          :max="MAX_MOOD_VIEW_OPERATORS"
          :placeholder="t('reports.observationOperatorsPlaceholder')"
        />
      </div>
      <p class="observation-help">{{ t('reports.observationHelp') }}</p>
      <p v-if="error" role="alert" class="observation-error">{{ reportErrorMessage(error) }}</p>
      <div class="observation-actions">
        <n-button v-if="view" type="error" secondary @click="emit('remove', view.id)">{{
          t('reports.deleteObservation')
        }}</n-button>
        <n-button @click="close">{{ t('reports.cancel') }}</n-button>
        <n-button type="primary" @click="submit">{{ t('reports.saveObservation') }}</n-button>
      </div>
    </div>
  </n-modal>
</template>

<style scoped>
.observation-fields {
  display: flex;
  flex-direction: column;
  gap: 15px;
}
.observation-fields label,
.observation-field {
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.observation-help {
  margin: 0;
  font-size: 12px;
  opacity: 0.75;
}
.observation-error {
  color: #d14545;
  font-size: 12px;
  margin: 0;
}
.observation-actions {
  display: flex;
  align-items: center;
  justify-content: flex-end;
  gap: 8px;
  flex-wrap: wrap;
}
.observation-actions :first-child:nth-last-child(3) {
  margin-right: auto;
}
</style>
