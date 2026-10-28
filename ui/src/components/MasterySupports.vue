<template>
  <n-modal
    :show="show"
    @update:show="$emit('update:show', $event)"
    preset="card"
    :title="i18n.global.t('growth.supports.masteryAssistantPlan')"
    style="width: min(660px, 95vw)"
    content-style="overflow-y: auto; min-height: 0"
    :mask-closable="!saving"
    :closable="!saving"
    :close-on-esc="!saving"
  >
    <n-space vertical :size="16">
      <n-text strong>{{ operatorDisplayName(name) }}</n-text>
      <n-alert v-if="error" type="error">{{ error }}</n-alert>
      <n-alert v-if="!editable" type="info">{{
        i18n.global.t('growth.supports.noStagesCanBeEditedNowDuring')
      }}</n-alert>
      <n-text depth="3">
        {{ i18n.global.t('growth.supports.controlCenterBonus')
        }}{{ plan?.support_plan?.central_bonus || 0
        }}{{ i18n.global.t('growth.supports.automaticPlansExcludeOperatorsAssignedOutsideThe') }}
      </n-text>
      <n-spin :show="loading">
        <n-space vertical :size="12">
          <n-card
            v-for="stage in stages"
            :key="stage.level"
            size="small"
            :title="i18n.global.t('growth.supports.m', { value0: stage.level })"
          >
            <n-space vertical>
              <n-text v-if="stage.level <= editableAfter" depth="3">{{
                i18n.global.t('growth.supports.thisStageHasStartedOrFinishedIts')
              }}</n-text>
              <n-text depth="3">{{
                stage.manual
                  ? i18n.global.t('growth.supports.customAssistants')
                  : i18n.global.t('growth.supports.automaticRecommendation')
              }}</n-text>
              <n-text
                v-if="
                  plan.support_runtime?.level === stage.level &&
                  plan.support_runtime.working_operator
                "
                depth="3"
              >
                {{ i18n.global.t('growth.supports.actualAssistants')
                }}{{ operatorDisplayName(plan.support_runtime.working_operator) }}
              </n-text>
              <label :for="`support-${stage.level}`">{{
                i18n.global.t('growth.supports.startingAssistant')
              }}</label>
              <n-select
                :id="`support-${stage.level}`"
                v-model:value="stage.operator"
                :options="options"
                filterable
                :disabled="stage.level <= editableAfter || saving"
              />
              <template v-if="stage.level < plan.target_level">
                <label :for="`reducer-${stage.level}`">{{
                  i18n.global.t('growth.supports.laterReplacementOptional')
                }}</label>
                <n-select
                  :id="`reducer-${stage.level}`"
                  v-model:value="stage.swap_target"
                  :options="options"
                  filterable
                  clearable
                  :disabled="stage.level <= editableAfter || saving"
                  :placeholder="i18n.global.t('growth.supports.noReplacement')"
                />
              </template>
              <n-text v-if="stage.activate_with" depth="3"
                >{{ i18n.global.t('growth.supports.beforeThisStageStartsKeep') }}
                {{ operatorDisplayName(stage.activate_with)
                }}{{ i18n.global.t('growth.supports.inPlaceThenSwapAfterTheHalving') }}</n-text
              >
            </n-space>
          </n-card>
          <n-empty
            v-if="!stages.length"
            :description="i18n.global.t('growth.supports.thisOlderPlanHasNoAutomaticAssistant')"
          />
        </n-space>
      </n-spin>
      <n-text depth="3">{{
        i18n.global.t('growth.supports.customAssistantsDoNotNeedATraining')
      }}</n-text>
    </n-space>
    <template #footer>
      <n-space justify="end">
        <n-button @click="$emit('update:show', false)" :disabled="saving">{{
          i18n.global.t('growth.supports.close')
        }}</n-button>
        <n-button
          type="primary"
          :loading="saving"
          :disabled="!editable || !stages.length || loading"
          @click="save"
          >{{ i18n.global.t('growth.supports.saveAssistants') }}</n-button
        >
      </n-space>
    </template>
  </n-modal>
</template>

<script setup>
import { operatorDisplayName } from '@/i18n/gameNames'
import { i18n } from '@/i18n'
import { computed, ref, watch } from 'vue'
import axios from 'axios'
import { supportEditableAfter } from '@/utils/masterySupport'
import { NAlert, NButton, NCard, NEmpty, NModal, NSelect, NSpace, NSpin, NText } from 'naive-ui'

const props = defineProps({ show: Boolean, plan: Object, name: String })
const emit = defineEmits(['update:show', 'saved'])
const stages = ref([])
const operators = ref([])
const loading = ref(false)
const saving = ref(false)
const error = ref('')
const editableAfter = computed(() => supportEditableAfter(props.plan))
const editable = computed(() => stages.value.some((s) => s.level > editableAfter.value))
const options = computed(() =>
  operators.value
    .filter((o) => o.name !== props.name)
    .map((o) => ({
      value: o.name,
      label: o.blocked.length
        ? i18n.global.t('growth.supports.assignedOutsideTheTrainingRoom', {
            value0: operatorDisplayName(o.name)
          })
        : operatorDisplayName(o.name),
      disabled: o.blocked.length > 0
    }))
)

watch(
  () => props.show,
  async (show) => {
    if (!show) return
    const planId = props.plan?.id
    stages.value = (props.plan?.support_plan?.stages || []).map((s) => ({ ...s }))
    operators.value = []
    loading.value = true
    error.value = ''
    try {
      const { data } = await axios.get(`${import.meta.env.VITE_HTTP_URL}/mastery-plan/supports`)
      if (props.show && props.plan?.id === planId) operators.value = data.operators
    } catch (e) {
      error.value = e.response?.data?.error || e.message
    } finally {
      loading.value = false
    }
  },
  { immediate: true }
)

async function save() {
  saving.value = true
  error.value = ''
  try {
    await axios.patch(`${import.meta.env.VITE_HTTP_URL}/mastery-plan/supports`, {
      id: props.plan.id,
      stages: stages.value.map(({ level, operator, swap_target }) => ({
        level,
        operator,
        swap_target
      }))
    })
    emit('saved')
    emit('update:show', false)
  } catch (e) {
    error.value = e.response?.data?.error || e.message
  } finally {
    saving.value = false
  }
}
</script>
