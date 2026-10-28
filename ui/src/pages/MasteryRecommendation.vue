<template>
  <div class="growth-workspace">
    <div class="growth-workspace__inner">
      <GrowthHero
        :total-goals="totalGoalCount"
        :plan-count="planEntries.length"
        :training="trainingCard"
        :next-up="nextUpItem"
        :operators="store.recommendations"
        :auto-mastery="configStore.enable_mastery"
        :loading="store.loading"
        :syncing="cultivateSyncing"
        :sync-hint="syncHint"
        :missing-kinds="planMaterialStats.missing"
        :ready-goals="planMaterialStats.ready"
        :compact="activeView !== 'overview'"
        @update:auto-mastery="configStore.enable_mastery = $event"
        @add-target="openOperatorPicker"
        @open-plan="openCraftingOrder"
        @refresh="refreshGrowthPlanOnly"
        @sync="fetchCultivate"
      />

      <div v-if="crossFormWarning" class="growth-notice" role="status">
        <span class="gp-stamp gp-stamp--warn growth-notice__stamp">{{
          i18n.global.t('growth.page.formChangeReminder')
        }}</span>
        <p>{{ crossFormWarning }}</p>
      </div>

      <GrowthViewNav
        v-model="activeView"
        :operator-count="store.recommendations.length"
        :missing-kinds="planMaterialStats.missing"
        :ready-count="planMaterialStats.ready"
        :goal-count="totalGoalCount"
        @open-route="openSettings"
        @open-workshop="openWorkshopSettings"
      />

      <div v-if="!store.hasData && store.error" class="gp-panel growth-blocked">
        <span class="gp-kicker">{{ i18n.global.t('growth.format.syncRequired') }}</span>
        <h2>{{ i18n.global.t('growth.page.noOperatorDataIsAvailableForPlanning') }}</h2>
        <p>{{ store.error }}</p>
        <div class="growth-blocked__actions">
          <n-button type="primary" :loading="store.loading" @click="fetchCultivate">
            {{ i18n.global.t('growth.page.syncDataFromSkland') }}
          </n-button>
          <n-button quaternary @click="refreshGrowthPlanOnly">{{
            i18n.global.t('growth.page.retryLoading')
          }}</n-button>
        </div>
      </div>

      <div v-else-if="!store.hasData && store.loading" class="growth-loading" aria-busy="true">
        <div class="gp-skeleton" style="height: 220px" />
        <div class="gp-skeleton" style="height: 160px" />
      </div>

      <template v-else>
        <GrowthOverview
          v-if="activeView === 'overview'"
          :goal-count="totalGoalCount"
          :plan-count="planEntries.length"
          :training="trainingCard"
          :next-up="nextUpItem"
          :queue="queueItems"
          :queue-error="queueOrderError"
          :materials="planMaterials"
          :materials-loading="materialsLoading"
          :materials-error="materialsError"
          :material-stats="planMaterialStats"
          :recommended="recommendedCards"
          :pick-sort="pickSort"
          :roster-stats="rosterStats"
          :workshop-status-revision="workshopStatusRevision"
          :workshop-loading="workshopLoading"
          :has-chip-shortage="hasChipShortage"
          :chip-farming-loading="chipFarmingLoading"
          @open-plan="openCraftingOrder"
          @open-materials="activeView = 'materials'"
          @open-insights="activeView = 'insights'"
          @open-operators="activeView = 'operators'"
          @open-operator="openOperator"
          @add-target="openOperatorPicker"
          @generate-crafting="autoWorkshop"
          @configure-chips="configureChipFarming"
          @refresh-materials="refreshT3Summary"
          @update:pick-sort="pickSort = $event"
        />

        <div
          v-else-if="activeView === 'operators'"
          class="growth-operators"
          :class="{ 'has-dossier': !!selectedOperator }"
        >
          <GrowthOperatorGrid
            :cards="operatorCards"
            :loading="store.loading"
            :error="store.error"
            :empty-text="emptyText"
            :has-data="store.hasData"
            :search="searchQuery"
            :rarities="filterRarity"
            :professions="filterProfession"
            :idle-filter="idleFilter"
            :idle-options="idleFilterOptions"
            :rarity-options="rarityOptions"
            :profession-options="professionOptions"
            :survey-filters="surveyFilters"
            :survey="survey"
            :survey-loading="surveyLoading"
            :batch-adding="batchAdding"
            :batch-progress="batchProgress"
            :filtered-count="displayList.length"
            :addable-count="filteredPlanItems.length"
            :total="store.recommendations.length"
            :page="operatorPage"
            :page-size="operatorPageSize"
            @update:search="searchQuery = $event"
            @update:rarities="filterRarity = $event"
            @update:professions="filterProfession = $event"
            @update:idle-filter="idleFilter = $event"
            @update:survey-filters="surveyFilters = $event"
            @update:page="operatorPage = $event"
            @refresh-survey="loadSurvey"
            @reset="resetFilters"
            @add-filtered="addFilteredToPlan"
            @refresh="refreshGrowthPlanOnly"
            @sync="fetchCultivate"
            @open="selectOperator"
          />
          <GrowthOperatorDetail
            v-if="selectedOperator"
            :operator="selectedOperator"
            :loading="detailLoading"
            :error="operatorSyncMessage(detailError)"
            :skill-rows="selectedSkillRows"
            :module-rows="selectedModuleRows"
            :basic="selectedBasicState"
            :level-selected="selectedLevelGoalValue"
            :level-required="selectedRequiredLevel"
            :level-saving="goalSaving"
            :goal-saving="goalSaving"
            :target-saving="targetSaving"
            :starting-mastery="startingMastery"
            :batch-adding="batchAdding"
            :survey="surveyFor(selectedOperatorBase || selectedOperator)"
            :completed-skills="selectedCompletedSkills"
            :planned-count="selectedPlannedCount"
            @close="closeOperator"
            @retry="loadOperatorDetail(expandedOperator[0])"
            @apply-level="applySelectedLevel"
            @toggle-skill="toggleSelectedSkill"
            @change-target="changeSelectedTarget"
            @insert-task="insertSelectedMasteryTask"
            @open-supports="openSelectedSupports"
            @toggle-module="toggleSelectedModule"
            @change-module-target="changeSelectedModuleTarget"
            @toggle-basic="toggleSelectedBasic"
            @add-all="addAllToPlan(selectedOperatorBase)"
          />
        </div>

        <GrowthMaterialsView
          v-else-if="activeView === 'materials'"
          :summary="planMaterials"
          :loading="materialsLoading"
          :error="materialsError"
          :missing-skills="missingPlanSkills"
          :total-goals="totalGoalCount"
          :plan-count="planEntries.length"
          :has-chip-shortage="hasChipShortage"
          :chip-loading="chipFarmingLoading"
          :workshop-loading="workshopLoading"
          @refresh="refreshT3Summary"
          @generate-crafting="autoWorkshop"
          @configure-chips="configureChipFarming"
          @add-target="openOperatorPicker"
          @open-plan="openCraftingOrder"
        />

        <GrowthInsightsView
          v-else
          :statistics="store.personalStatistics"
          :history="store.history"
          :survey="survey"
          :operator-count="store.recommendations.length"
          :survey-loading="surveyLoading"
          @refresh-survey="loadSurvey"
        />
      </template>

      <GrowthCraftingOrder
        ref="craftingOrderRef"
        hide-trigger
        :revision="craftingOrderRevision"
        :recommendations="store.recommendations"
        :count="totalGoalCount"
        @changed="refreshGrowthPlan"
      />

      <MasterySupports
        v-model:show="showSupports"
        :plan="supportSelection.plan"
        :name="supportSelection.name"
        @saved="refreshPlanFromServer"
      />

      <!-- 通用专精路线 -->
      <n-modal
        v-model:show="showSettings"
        preset="card"
        class="growth-modal"
        :style="{ width: 'min(960px, calc(100vw - 24px))' }"
        :mask-closable="false"
        :close-on-esc="!routeCalculating"
        :closable="!routeCalculating"
        @update:show="(value) => (!value ? (showSettings = false) : null)"
      >
        <template #header>
          <div class="growth-modal__head">
            <span class="gp-kicker">{{ i18n.global.t('growth.format.masteryRoutesHeading') }}</span>
            <h2>{{ i18n.global.t('growth.page.defaultMasteryRoutes') }}</h2>
            <p>{{ i18n.global.t('growth.page.prepareTrainingRoomAssistantsByProfessionEach') }}</p>
          </div>
        </template>

        <div class="growth-modal__body route-drawer">
          <nav
            class="route-drawer__rail"
            :aria-label="i18n.global.t('growth.page.professionMasteryRoutes')"
          >
            <button
              v-for="prof in profKeys"
              :key="prof"
              type="button"
              class="route-drawer__prof"
              :class="{ 'is-active': settingsTab === prof }"
              :aria-pressed="settingsTab === prof"
              @click="settingsTab = prof"
            >
              {{ professionName(prof) }}
            </button>
          </nav>

          <div class="route-drawer__body">
            <n-alert
              v-if="defaultsError"
              type="warning"
              :bordered="false"
              class="route-drawer__alert"
            >
              {{ operatorSyncMessage(defaultsError) }}
            </n-alert>

            <section class="route-slots">
              <header class="route-section-head">
                <div>
                  <h3>
                    {{ professionName(settingsTab) }}
                    {{ i18n.global.t('growth.page.assistantSlots') }}
                  </h3>
                  <p>{{ i18n.global.t('growth.page.oneAssistantForEachMasteryStageLeave') }}</p>
                </div>
                <span class="gp-stamp gp-stamp--flat">{{
                  routeSettings[settingsTab].optimal
                    ? i18n.global.t('growth.page.optimal')
                    : i18n.global.t('growth.page.custom')
                }}</span>
              </header>

              <n-dynamic-input
                v-model:value="routeSettings[settingsTab].supports"
                :min="3"
                :max="3"
              >
                <template #action><span hidden /></template>
                <template #default="{ value }">
                  <div class="route-slot">
                    <div class="route-slot__line">
                      <div class="route-slot__stage gp-mono">
                        {{ i18n.global.t('growth.page.m2')
                        }}{{
                          [
                            i18n.global.t('growth.page.1'),
                            i18n.global.t('growth.page.2'),
                            i18n.global.t('growth.page.3')
                          ][value.skill_level - 1]
                        }}
                      </div>
                      <n-select
                        v-model:value="value.name"
                        filterable
                        :options="operatorOptions"
                        :filter="filterOperatorOption"
                        :render-label="render_op_label"
                        :render-option="render_op_option"
                        :placeholder="i18n.global.t('growth.page.selectATrainingAssistant')"
                        :aria-label="i18n.global.t('growth.page.trainingAssistant')"
                      />
                      <label class="route-slot__efficiency">
                        <span>{{ i18n.global.t('growth.page.trainingSpeed') }}</span>
                        <mower-input-number
                          v-model:value="value.efficiency"
                          :min="0"
                          :max="100"
                          :show-button="false"
                          style="width: 88px"
                        >
                          <template #suffix>%</template>
                        </mower-input-number>
                      </label>
                    </div>
                    <div class="route-slot__swap">
                      <n-checkbox v-model:checked="value.swap">{{
                        i18n.global.t('growth.page.assistantSwap')
                      }}</n-checkbox>
                      <n-select
                        :disabled="!value.swap"
                        v-model:value="value.swap_name"
                        :options="swap_list"
                        :render-label="render_op_label"
                        :render-option="render_op_option"
                        :placeholder="i18n.global.t('growth.page.replacement')"
                        :aria-label="i18n.global.t('growth.page.replacementAssistant')"
                      />
                      <n-select
                        :disabled="!value.swap"
                        v-model:value="value.match"
                        :options="swap_30"
                        :aria-label="i18n.global.t('growth.page.swapBonus')"
                      />
                    </div>
                  </div>
                </template>
              </n-dynamic-input>

              <div class="route-flags">
                <n-checkbox v-model:checked="routeSettings[settingsTab].optimal">{{
                  i18n.global.t('growth.page.optimalTrainingAssistants')
                }}</n-checkbox>
                <n-checkbox v-model:checked="routeSettings[settingsTab].half_off">{{
                  i18n.global.t('growth.page.halvingBonusAvailable')
                }}</n-checkbox>
              </div>
            </section>

            <details class="route-reference">
              <summary>
                {{ i18n.global.t('growth.page.bestAssistantsByProfessionReference') }}
              </summary>
              <MasteryProfessionTrainers :trainers="bestTrainers" :professions="profKeys" />
            </details>

            <section class="route-global">
              <header class="route-section-head">
                <div>
                  <h3>{{ i18n.global.t('growth.page.globalParameters') }}</h3>
                  <p>
                    {{
                      i18n.global.t('growth.page.identifyTheControlCenterBonusAutomaticallyFrom')
                    }}
                  </p>
                </div>
              </header>
              <div class="route-central">
                <n-switch
                  :value="autoCentralBonus"
                  disabled
                  :checked-value="5"
                  :unchecked-value="0"
                >
                  <template #checked>+5%</template>
                  <template #unchecked>{{ i18n.global.t('growth.page.none') }}</template>
                </n-switch>
                <span>{{ i18n.global.t('growth.page.controlCenterOperatorBonus') }}</span>
                <HelpText :label="i18n.global.t('growth.page.controlCenterBonusSource')">
                  {{ i18n.global.t('growth.page.detect5FromPrimaryAndReplacementOperators') }}
                </HelpText>
              </div>
              <div class="route-buffers">
                <p class="route-buffers__caption">
                  {{ i18n.global.t('growthUpdates.swapBufferMinutes') }}
                  <HelpText :label="i18n.global.t('growthUpdates.swapBufferHelpLabel')">
                    {{ i18n.global.t('growthUpdates.swapBufferHelp') }}
                  </HelpText>
                </p>
                <label v-for="item in masteryBufferFields" :key="item.key" class="route-buffer">
                  <span>{{ item.label }}</span>
                  <mower-input-number
                    :value="masterySettings.mastery_swap_buffers[item.key]"
                    @update:value="
                      (value) =>
                        (masterySettings.mastery_swap_buffers[item.key] =
                          value ?? DEFAULT_MASTERY_SWAP_BUFFERS[item.key])
                    "
                    :min="0"
                    :max="60"
                    size="small"
                    style="width: 116px; flex: none"
                  />
                </label>
              </div>
            </section>
          </div>
        </div>

        <template #footer>
          <div class="growth-modal__foot">
            <div class="growth-drawer__foot-left">
              <n-button
                @click="calculateOptimalRoutes"
                :disabled="routeSaving || store.loading"
                :loading="routeCalculating"
              >
                {{ i18n.global.t('growth.page.calculateOptimalRoutes') }}
              </n-button>
              <HelpText :label="i18n.global.t('growth.page.aboutOptimalRouteCalculation')">
                {{
                  i18n.global.t('growth.page.synchronizeOperatorDataThenCalculateOptimalDefault')
                }}
              </HelpText>
            </div>
            <div class="growth-drawer__foot-right">
              <n-button :disabled="routeCalculating" @click="showSettings = false">{{
                i18n.global.t('growth.page.cancel')
              }}</n-button>
              <n-button
                type="primary"
                @click="saveRouteAndClose"
                :loading="routeSaving"
                :disabled="routeCalculating"
              >
                {{ i18n.global.t('growth.page.saveClose') }}
              </n-button>
            </div>
          </div>
        </template>
      </n-modal>

      <!-- 加工站干员 -->
      <n-modal
        v-model:show="showWorkshopSettings"
        preset="card"
        class="growth-modal"
        :style="{ width: 'min(720px, calc(100vw - 24px))' }"
        :mask-closable="false"
        :close-on-esc="!workshopDefaultsLoading"
        :closable="!workshopDefaultsLoading"
      >
        <template #header>
          <div class="growth-modal__head">
            <span class="gp-kicker">{{ i18n.global.t('growth.format.workshopLineup') }}</span>
            <h2>{{ i18n.global.t('growth.page.workshopOperators') }}</h2>
            <p>
              {{ i18n.global.t('growth.page.assignCraftingOperatorsByByproductProbabilityAnd') }}
            </p>
          </div>
        </template>

        <div class="growth-modal__body workshop-drawer">
          <n-alert v-if="workshopDefaultsError" type="warning" :bordered="false">
            {{ workshopDefaultsError }}
          </n-alert>

          <section class="workshop-threshold">
            <div class="workshop-threshold__copy">
              <h3>{{ i18n.global.t('growth.page.minimumByproductProbabilityBonus') }}</h3>
              <p>{{ i18n.global.t('growth.page.autoFillOperatorsWithUnlockedSkillsMeeting') }}</p>
            </div>
            <div class="workshop-threshold__controls">
              <mower-input-number
                :value="workshopMinBonus"
                @update:value="workshopMinBonus = $event ?? 80"
                :min="0"
                :max="1000"
                :precision="0"
                :step="5"
                :show-button="false"
                :disabled="workshopDefaultsLoading"
                :input-props="{
                  'aria-label': i18n.global.t('growth.page.minimumByproductProbabilityBonus2')
                }"
                style="width: 104px"
              >
                <template #suffix>%</template>
              </mower-input-number>
              <n-button
                size="small"
                secondary
                type="primary"
                @click="setWorkshopOperators"
                :loading="workshopDefaultsLoading"
              >
                {{ i18n.global.t('growth.page.autoFill') }}
              </n-button>
            </div>
          </section>

          <section class="workshop-policy">
            <n-switch
              :value="workshopProtectT2"
              :disabled="workshopPolicySaving"
              @update:value="setWorkshopMaterialPolicy"
              size="small"
              :aria-label="i18n.global.t('growth.page.doNotCraftWithDevicesOrirockCubes')"
            />
            <span>{{ i18n.global.t('growth.page.doNotCraftWithDevicesOrirockCubes2') }}</span>
            <HelpText>
              {{ i18n.global.t('growth.page.reserveOnlyT2DevicesAndOrirockCubes') }}
            </HelpText>
          </section>

          <section class="workshop-group">
            <header>
              <h3>{{ i18n.global.t('growth.page.nonT5Materials') }}</h3>
              <HelpText>{{
                i18n.global.t('growth.page.shortageCraftingDoesNotUseWhoseSkill')
              }}</HelpText>
            </header>
            <slick-operator-select
              v-model="fodderOps"
              :disabled="workshopDefaultsLoading"
              :select_placeholder="i18n.global.t('growth.page.selectCraftingOperators')"
            />
          </section>

          <section class="workshop-group">
            <header>
              <h3>{{ i18n.global.t('growth.page.t5Materials') }}</h3>
            </header>
            <slick-operator-select
              v-model="t5Ops"
              :disabled="workshopDefaultsLoading"
              :select_placeholder="i18n.global.t('growth.page.selectOperators')"
            />
          </section>

          <section class="workshop-group">
            <header>
              <h3>{{ i18n.global.t('growth.page.skillSummaries') }}</h3>
            </header>
            <slick-operator-select
              v-model="bookOps"
              :disabled="workshopDefaultsLoading"
              :select_placeholder="i18n.global.t('growth.page.selectOperators')"
            />
          </section>

          <details class="workshop-advanced">
            <summary>{{ i18n.global.t('growth.page.fodderMaterialsManualCraftingOnly') }}</summary>
            <workshop-deer-fodder v-model="deerFodder" :disabled="workshopDefaultsLoading" />
          </details>

          <details v-if="workshopRecommendations" class="workshop-advanced">
            <summary>{{ i18n.global.t('growth.page.recommendedOperatorsToRaise') }}</summary>
            <div class="workshop-recommendations">
              <div v-for="category in workshopCategoryLabels" :key="category.key">
                <h4>{{ category.label }}</h4>
                <p v-for="operator in workshopRecommendations[category.key]" :key="operator.name">
                  {{
                    workshopRecommendationText(
                      operator,
                      workshopOwnedOperators !== null && !workshopOwnedOperators.has(operator.name)
                    )
                  }}
                </p>
                <p v-if="!workshopRecommendations[category.key].length" class="gp-muted">
                  {{ i18n.global.t('growth.page.noRecommendedOperators') }}
                </p>
              </div>
            </div>
          </details>
        </div>

        <template #footer>
          <div class="growth-modal__foot">
            <span class="gp-muted growth-drawer__foot-note">{{
              i18n.global.t('growth.page.savedOperatorListsAreKeptWhenDisabled')
            }}</span>
            <n-button
              type="primary"
              size="small"
              @click="showWorkshopSettings = false"
              :disabled="workshopDefaultsLoading"
            >
              {{ i18n.global.t('growth.page.done') }}
            </n-button>
          </div>
        </template>
      </n-modal>
    </div>
  </div>
</template>

<script setup>
import { operatorDisplayName, skillDisplayName } from '@/i18n/gameNames'
import { i18n } from '@/i18n'
import { operatorSyncMessage } from '@/i18n/operatorSync'
import {
  loadWorkshopOperators,
  loadWorkshopReference,
  syncWorkshopOperators,
  selectedWorkshopOperators,
  usesLegacyWorkshopDefaults,
  workshopRecommendationText,
  workshopTraineeWarning
} from '@/utils/workshopOperators'
import {
  masteryFormWarning,
  masteryScheduleContext,
  masteryTraineeWarning
} from '@/utils/masterySupport'
import { computed, nextTick, onMounted, onUnmounted, reactive, ref, shallowRef, watch } from 'vue'
import GrowthCraftingOrder from '@/components/GrowthCraftingOrder.vue'
import { NAlert, NButton, NCheckbox, NDynamicInput, NSelect, NSwitch, useMessage } from 'naive-ui'
import axios from 'axios'
import { useMasteryStore } from '@/stores/mastery'
import MasterySupports from '@/components/MasterySupports.vue'
import MasteryProfessionTrainers from '@/components/MasteryProfessionTrainers.vue'
import GrowthHero from '@/growth/GrowthHero.vue'
import GrowthViewNav from '@/growth/GrowthViewNav.vue'
import GrowthOverview from '@/growth/GrowthOverview.vue'
import GrowthOperatorGrid from '@/growth/GrowthOperatorGrid.vue'
import GrowthOperatorDetail from '@/growth/GrowthOperatorDetail.vue'
import GrowthMaterialsView from '@/growth/GrowthMaterialsView.vue'
import GrowthInsightsView from '@/growth/GrowthInsightsView.vue'
import { goalLabel, professionName } from '@/growth/growthFormatters'
import { sumPersonalStatistics } from '@/utils/operatorStatistics'
import '@/growth/growth.css'
import HelpText from '@/components/HelpText.vue'
import { usePlanStore } from '@/stores/plan'
import { useConfigStore } from '@/stores/config'
import { storeToRefs } from 'pinia'
import { pinyin_match } from '@/utils/common'
import {
  buildMasteryRoutePayload,
  prepareMasteryRoutes,
  completeMasterySupports,
  syncMasteryRouteDefaults,
  DEFAULT_MASTERY_SWAP_BUFFERS,
  normalizeMasterySwapBuffers
} from '@/utils/masteryRoute'
import { render_op_option, render_op_label, filterOperatorOption } from '@/utils/op_select'
import { defaultSurveyFilters, operatorSurvey } from '@/utils/growthSurvey'
import {
  hasRemainingTarget,
  operatorSkillRows,
  recommendedTarget,
  remainingModuleRate,
  remainingSkillRate,
  sortRecommendedCards,
  surveySkillRate
} from '@/growth/growthRecommendation'
import {
  selectedRecommendation,
  goalSelected,
  operatorLevelGoals,
  isGrowthOperatorIdle,
  prerequisiteLevelGoal,
  selectedLevelGoal
} from '@/utils/growthPlanning'

const message = useMessage()
const store = useMasteryStore()
const planStore = usePlanStore()
const configStore = useConfigStore()
const { operators: operatorOptions } = storeToRefs(planStore)

const profKeys = ['先锋', '近卫', '重装', '狙击', '术师', '医疗', '辅助', '特种']
const profMap = {
  WARRIOR: '近卫',
  SNIPER: '狙击',
  TANK: '重装',
  MEDIC: '医疗',
  SUPPORT: '辅助',
  CASTER: '术师',
  SPECIAL: '特种',
  PIONEER: '先锋'
}

const rarityOptions = [
  { label: '6★', value: 6 },
  { label: '5★', value: 5 },
  { label: '4★', value: 4 },
  { label: '3★', value: 3 },
  { label: '2★', value: 2 },
  { label: '1★', value: 1 }
]
const professionOptions = computed(() =>
  profKeys.map((p) => ({ label: professionName(p), value: p }))
)

const expandedOperator = ref([])
const idleFilter = ref('all')
const idleFilterOptions = computed(() => [
  { label: i18n.global.t('growth.page.all'), value: 'all' },
  { label: i18n.global.t('growth.page.idle'), value: 'idle' },
  { label: i18n.global.t('growth.page.busy'), value: 'busy' }
])
const searchQuery = ref('')
const filterRarity = ref([])
const filterProfession = ref([])
const targets = ref({})
const targetSaving = ref(false)
const goalSaving = ref(false)
const batchAdding = ref(false)
const batchProgress = ref('')
let batchController = null
onUnmounted(() => batchController?.abort())
const totalGoalCount = computed(() => planEntries.value.length + store.goals.length)
const isGoalPlanned = (cid, mid) => goalSelected(store.goals, cid, mid)
const levelGoalFor = (op) => selectedLevelGoal(op, hasPlannedSkill(op), store.goals)
const eliteLabel = (elite) =>
  [
    i18n.global.t('growth.page.elite0'),
    i18n.global.t('growth.page.elite1'),
    i18n.global.t('growth.page.elite2')
  ][elite] || i18n.global.t('growth.page.elite', { value0: elite })
function levelChoices(op) {
  return operatorLevelGoals(op)
}
async function applyLevelTarget(op, key) {
  if (goalSaving.value) return
  const choice = levelChoices(op).find((entry) => entry.key === key)
  const choices = levelChoices(op).map((entry) => entry.key)
  const required = prerequisiteLevelGoal(op, hasPlannedSkill(op), store.goals)
  if (choice && choices.indexOf(choice.key) < choices.indexOf(required)) {
    message.info(i18n.global.t('growth.page.thisLevelIsBelowASelectedGoal'))
    return
  }
  // 用实际练度判断是否达成，不能依赖材料摘要：概览/详情返回的摘要可能为空。
  const reached =
    choice &&
    ((op.elite ?? 0) > choice.elite ||
      ((op.elite ?? 0) === choice.elite && (op.level ?? 1) >= choice.level))
  if (reached) {
    message.info(i18n.global.t('growth.page.thisLevelHasAlreadyBeenReachedAnd'))
    return
  }
  if (choice) await toggleGoal(op, choice.key, true)
  else {
    const existing = store.goals.find(
      (goal) => goal.char_id === op.char_id && choices.includes(goal.module_id)
    )
    if (existing) await toggleGoal(op, existing.module_id, false)
  }
}
const hasPlannedGoal = (op) =>
  hasPlannedSkill(op) || store.goals.some((goal) => goal.char_id === op.char_id)
function matchesSearch(name, search) {
  return (
    !search.trim() ||
    name.toLowerCase().includes(search.trim().toLowerCase()) ||
    operatorDisplayName(name).toLowerCase().includes(search.trim().toLowerCase()) ||
    !!pinyin_match(name, search.trim())
  )
}
function resetFilters() {
  searchQuery.value = ''
  filterRarity.value = []
  filterProfession.value = []
  idleFilter.value = 'all'
  surveyFilters.value = defaultSurveyFilters()
}
function targetFor(op, rec) {
  return (
    targets.value[planKey(op.char_id, rec.skill_index)] ||
    planStatus.value[planKey(op.char_id, rec.skill_index)]?.target_level ||
    3
  )
}
function targetOptions(rec) {
  return [1, 2, 3]
    .filter((level) => level > rec.current_level)
    .map((value) => ({ value, label: i18n.global.t('growth.page.targetM', { value0: value }) }))
}
function isTargetLocked(op, rec) {
  const status = planStatus.value[planKey(op.char_id, rec.skill_index)]?.status
  return status && !['idle', 'failed'].includes(status)
}
async function changeTarget(op, rec, value) {
  const key = planKey(op.char_id, rec.skill_index)
  targetSaving.value = true
  try {
    if (planStatus.value[key]?.id) {
      await axios.patch(`${import.meta.env.VITE_HTTP_URL}/mastery-plan/target`, {
        id: planStatus.value[key].id,
        target_level: value
      })
      await refreshPlanFromServer()
    }
    targets.value[key] = value
  } catch (error) {
    message.error(error.response?.data?.error || i18n.global.t('growth.page.failedToSaveTheTarget'))
  } finally {
    targetSaving.value = false
  }
}
const moduleTargets = ref({})
function moduleTarget(op, module) {
  return (
    store.goals.find((goal) => goal.char_id === op.char_id && goal.module_id === module.id)
      ?.target_level ||
    moduleTargets.value[`${op.char_id}:${module.id}`] ||
    module.max_level ||
    1
  )
}
function moduleTargetOptions(module) {
  return Array.from({ length: module.max_level || 1 }, (_, i) => i + 1)
    .filter((level) => level > module.current_level)
    .map((level) => ({
      label: i18n.global.t('growth.page.targetLevel', { value0: level }),
      value: level
    }))
}
async function changeModuleTarget(op, module, value) {
  if (isGoalPlanned(op.char_id, module.id)) {
    await toggleGoal(op, module.id, true, value)
  } else {
    moduleTargets.value[`${op.char_id}:${module.id}`] = value
  }
}
async function toggleGoal(op, moduleId, selected, targetLevel) {
  goalSaving.value = true
  try {
    const response = await axios.post(`${import.meta.env.VITE_HTTP_URL}/growth-plan`, {
      char_id: op.char_id,
      module_id: moduleId,
      selected,
      target_level:
        targetLevel ||
        moduleTarget(op, op.modules?.find((m) => m.id === moduleId) || { id: moduleId })
    })
    store.goals = response.data.goals
  } catch (error) {
    message.error(
      error.response?.data?.error || i18n.global.t('growth.page.failedToSaveTheGrowthGoal')
    )
  } finally {
    goalSaving.value = false
  }
}
const {
  workshop_min_bonus: workshopMinBonus,
  workshop_protect_t2_device_rock: workshopProtectT2,
  workshop_deer_fodder: deerFodder,
  fodder_operators: fodderOps,
  t5_operators: t5Ops,
  book_operators: bookOps
} = storeToRefs(configStore)
const workshopPolicySaving = ref(false)
async function setWorkshopMaterialPolicy(value) {
  workshopProtectT2.value = value
  workshopPolicySaving.value = true
  try {
    await configStore.save_config()
    await store.fetchRecommendations()
    await refreshT3Summary()
  } catch (error) {
    message.error(
      i18n.global.t('growth.page.failedToSaveCraftingSettings', { value0: error.message || error })
    )
  } finally {
    workshopPolicySaving.value = false
  }
}
const workshopStatusRevision = ref(0)
watch(
  [() => configStore.workshop_settings_generation, workshopProtectT2, fodderOps, t5Ops, bookOps],
  () => ++workshopStatusRevision.value,
  { deep: true }
)
const workshopLoading = ref(false)
const showWorkshopSettings = ref(false)
const workshopRecommendations = ref(null)
const workshopOwnedOperators = ref(null)
const workshopDefaultsLoading = ref(false)
const workshopDefaultsError = ref('')
const workshopCategoryLabels = computed(() => [
  { key: 'fodder_operators', label: i18n.global.t('growth.page.nonT5Materials') },
  { key: 't5_operators', label: i18n.global.t('growth.page.t5Materials') },
  { key: 'book_operators', label: i18n.global.t('growth.page.skillSummaries') }
])

async function readWorkshopDefaults(apply = false, sync = false) {
  if (workshopDefaultsLoading.value) return
  workshopDefaultsLoading.value = true
  workshopDefaultsError.value = ''
  try {
    const load = sync ? syncWorkshopOperators : loadWorkshopOperators
    const data = await load(axios, import.meta.env.VITE_HTTP_URL, workshopMinBonus.value)
    workshopRecommendations.value = data.recommendations
    workshopOwnedOperators.value = Array.isArray(data.owned_operators)
      ? new Set(data.owned_operators)
      : null
    if (apply) {
      fodderOps.value = [...data.defaults.fodder_operators]
      t5Ops.value = [...data.defaults.t5_operators]
      bookOps.value = [...data.defaults.book_operators]
    }
  } catch (e) {
    workshopDefaultsError.value =
      e.response?.data?.error ||
      e.message ||
      i18n.global.t('growth.page.failedToReadWorkshopRecommendations')
    workshopOwnedOperators.value = null
    try {
      workshopRecommendations.value = await loadWorkshopReference(
        axios,
        import.meta.env.VITE_HTTP_URL
      )
    } catch {
      workshopRecommendations.value = null
    }
  } finally {
    workshopDefaultsLoading.value = false
  }
}

async function openWorkshopSettings() {
  showWorkshopSettings.value = true
  await readWorkshopDefaults(
    usesLegacyWorkshopDefaults({
      fodder_operators: fodderOps.value,
      t5_operators: t5Ops.value,
      book_operators: bookOps.value
    })
  )
}

async function setWorkshopOperators() {
  await readWorkshopDefaults(true, true)
}
const workshopT3Summary = ref([])

const emptyText = computed(() =>
  idleFilter.value === 'idle'
    ? i18n.global.t('growth.page.noIdleOperatorsMatchTheFilters')
    : idleFilter.value === 'busy'
      ? i18n.global.t('growth.page.noBusyOperatorsMatchTheFilters')
      : i18n.global.t('growth.page.noOperatorsMatchTheCurrentFilters')
)

// ─── 计划（技能级别）───
// 格式: { "charId_skillIndex": true, ... }
const plan = ref({})
const queueOrderKeys = shallowRef([])
const queueOrderError = ref('')
let planReadSequence = 0
let queueOrderController = null
onUnmounted(() => {
  ++planReadSequence
  queueOrderController?.abort()
})
const planStatus = ref({}) // { "charId_skillIndex": {id, status, target_level, priority, expires_at} }
const crossFormWarning = computed(() =>
  masteryFormWarning(
    Object.keys(plan.value)
      .filter((key) => plan.value[key])
      .map((key) => parsePlanKey(key)[0])
  )
)
watch(crossFormWarning, (warning, previous) => {
  if (warning && warning !== previous) message.warning(warning, { duration: 10000 })
})
const craftingOrderRevision = computed(() =>
  JSON.stringify({
    skills: Object.entries(planStatus.value).map(([key, entry]) => [
      key,
      entry.id,
      entry.status,
      entry.target_level,
      entry.priority
    ]),
    goals: store.goals,
    cultivate: store.cultivateMsg
  })
)
function planKey(cid, si) {
  return `${cid}_${si}`
}
function isSkillPlanned(cid, si) {
  return !!plan.value[planKey(cid, si)]
}
function hasPlannedSkill(op) {
  return op.recommendations.some((r) => isSkillPlanned(op.char_id, r.skill_index))
}

async function warnMaterialShortage(additions) {
  const keys = [
    ...new Set([...Object.keys(plan.value).filter((key) => plan.value[key]), ...additions])
  ]
  try {
    const response = await axios.post(
      `${import.meta.env.VITE_HTTP_URL}/mastery-t3-summary`,
      {
        planned_skills: keys,
        goals: store.goals,
        targets: targets.value
      },
      { timeout: 5000 }
    )
    const summary = response.data?.material_summary
    if (!summary) throw new Error(i18n.global.t('growth.page.materialDataUnavailable'))
    if (!summary.available) {
      message.warning(
        summary.craftable
          ? i18n.global.t('growth.page.finishedInventoryCannotCoverTheFullPlan')
          : i18n.global.t('growth.page.theFullPlanLacksMaterialsIncludingSkill')
      )
    }
  } catch {
    message.warning(i18n.global.t('growth.page.theTotalInventoryCouldNotBeChecked'))
  }
}

async function toggleSkillPlan(op, rec) {
  if (batchAdding.value) return
  const k = planKey(op.char_id, rec.skill_index)
  if (!plan.value[k] && op.mastery_error) message.info(op.mastery_error)
  if (!plan.value[k]) await warnMaterialShortage([k])
  if (!plan.value[k] && workshopTrainingWarning(op.name)) {
    message.warning(workshopTrainingWarning(op.name))
  }
  if (!plan.value[k] && trainingWarning(op.name)) {
    message.warning(trainingWarning(op.name))
  }
  if (plan.value[k]) {
    // 删除计划
    const info = planStatus.value[k]
    if (info && info.id) {
      try {
        await axios.delete(`${import.meta.env.VITE_HTTP_URL}/mastery-plan`, {
          data: { id: info.id }
        })
      } catch (e) {
        message.error(i18n.global.t('growth.page.deletionFailed', { value0: e.message }))
        return
      }
    }
    delete plan.value[k]
    delete planStatus.value[k]
  } else {
    // 主列表 quick-add：立即写后端
    try {
      const body = {
        planning: true,
        items: [
          {
            char_id: op.char_id,
            name: op.name,
            skill_index: rec.skill_index,
            target_level: targetFor(op, rec)
          }
        ]
      }
      const r = await axios.post(`${import.meta.env.VITE_HTTP_URL}/mastery-plan`, body)
      const results = r.data?.results || []
      for (const warning of new Set(results.map((result) => result.warning).filter(Boolean))) {
        message.warning(warning)
      }
      if (results[0]?.status === 'added') {
        plan.value[k] = true
        planStatus.value[k] = {
          id: results[0].id,
          status: 'idle',
          target_level: targetFor(op, rec),
          priority: 0
        }
        await refreshPlanFromServer()
      } else if (results[0]?.status === 'existing') {
        // 已有计划：服务端不再新建重复行，直接复用那条去派发。本地状态可能过期，
        // 重新拉一次服务器计划让按钮/状态收敛。
        plan.value[k] = true
        await refreshPlanFromServer()
        message.success(
          results[0]?.reason ||
            i18n.global.t('growth.page.alreadyPlannedScheduledToStartImmediately')
        )
      } else if (results[0]?.status === 'insufficient' || results[0]?.status === 'deferred') {
        await refreshPlanFromServer()
        message.warning(
          results[0]?.reason || i18n.global.t('growth.page.insufficientMaterialsNotStartingYet')
        )
      } else {
        message.warning(results[0]?.reason || i18n.global.t('growth.page.failedToAddThePlan'))
      }
    } catch (e) {
      message.error(i18n.global.t('growth.page.saveFailed', { value0: e.message }))
    }
  }
}

async function addAllToPlan(op) {
  if (batchAdding.value) return
  if (op.mastery_error) message.info(op.mastery_error)
  if (trainingWarning(op.name)) {
    message.warning(trainingWarning(op.name))
  }
  const recs = visibleRecs(op)
  const additions = recs
    .map((rec) => planKey(op.char_id, rec.skill_index))
    .filter((key) => !plan.value[key])
  if (additions.length) await warnMaterialShortage(additions)
  if (
    recs.some((rec) => !plan.value[planKey(op.char_id, rec.skill_index)]) &&
    workshopTrainingWarning(op.name)
  ) {
    message.warning(workshopTrainingWarning(op.name))
  }
  // 主列表 quick-add：立即写后端。已计划技能在本地就跳过；后端按 (干员, 技能) 拦重复，
  // 万一本地状态过期撞上已有计划，服务端会回 existing 而不是再建一行。
  const toAdd = recs.filter((rec) => !plan.value[planKey(op.char_id, rec.skill_index)])
  if (!toAdd.length) {
    message.info(
      i18n.global.t('growth.page.allRecommendedSkillsForAreAlreadyPlanned', {
        value0: operatorDisplayName(op.name)
      })
    )
    return
  }
  try {
    const r = await axios.post(`${import.meta.env.VITE_HTTP_URL}/mastery-plan`, {
      planning: true,
      items: toAdd.map((rec) => ({
        char_id: op.char_id,
        name: op.name,
        skill_index: rec.skill_index,
        target_level: targetFor(op, rec)
      }))
    })
    const results = r.data?.results || []
    for (const warning of new Set(results.map((result) => result.warning).filter(Boolean))) {
      message.warning(warning)
    }
    const errs = []
    const infos = []
    results.forEach((res, i) => {
      const rec = toAdd[i]
      if (res.status === 'added' || res.status === 'existing') {
        const k = planKey(op.char_id, rec.skill_index)
        plan.value[k] = true
        planStatus.value[k] = {
          id: res.id,
          status: 'idle',
          target_level: targetFor(op, rec),
          priority: 0
        }
        if (res.status === 'existing')
          infos.push(res.reason || i18n.global.t('growth.page.alreadyPlanned'))
      } else if (res.status === 'insufficient' || res.status === 'deferred') {
        infos.push(
          i18n.global.t('growth.page.skill', {
            value0: rec.skill_index + 1,
            value1: res.reason || i18n.global.t('growth.page.insufficientMaterialsNotStartingYet')
          })
        )
      } else {
        errs.push(res.reason || i18n.global.t('growth.page.failedToAddThePlan'))
      }
    })
    await refreshPlanFromServer()
    if (errs.length) {
      message.warning(
        i18n.global.t('growth.page.itemsWereNotAdded', {
          value0: operatorDisplayName(op.name),
          value1: errs.length,
          value2: errs.join('；')
        })
      )
    } else if (infos.length) {
      // 材料不足 / 已有计划都明说，别静默当成「全部加入」
      message.info(`${operatorDisplayName(op.name)} ${infos.join('；')}`)
    } else {
      message.success(
        i18n.global.t('growth.page.allSkillsForWereAddedToThe', {
          value0: operatorDisplayName(op.name)
        })
      )
    }
  } catch (e) {
    message.error(i18n.global.t('growth.page.saveFailed', { value0: e.message }))
  }
}

async function refreshPlanFromServer() {
  const sequence = ++planReadSequence
  queueOrderController?.abort()
  const controller = new AbortController()
  queueOrderController = controller
  try {
    const [r, order] = await Promise.all([
      axios.get(`${import.meta.env.VITE_HTTP_URL}/mastery-plan`),
      axios
        .get(`${import.meta.env.VITE_HTTP_URL}/growth-crafting-order`, {
          signal: controller.signal,
          timeout: 30000
        })
        .catch((error) => ({ error }))
    ])
    if (controller.signal.aborted || sequence !== planReadSequence) return
    if (order.error || order.data?.error) {
      queueOrderError.value = i18n.global.t('growth.page.couldNotReadTheGrowthOrderThe')
    } else {
      queueOrderKeys.value = (order.data?.planning_items || order.data?.items || []).map(
        (item) => item.key
      )
      queueOrderError.value = ''
    }
    const data = r.data || {}
    const p = {}
    const ps = {}
    for (const item of data.plans || []) {
      const k = planKey(item.char_id, item.skill_index)
      // failed 计划也要显示（带失败原因），不能从列表凭空消失（#69）
      if (item.status !== 'completed') {
        p[k] = true
      }
      ps[k] = {
        id: item.id,
        status: item.status,
        target_level: item.target_level,
        priority: item.priority,
        expires_at: item.expires_at,
        failed_reason: item.failed_reason,
        support_plan: item.support_plan,
        support_runtime: item.support_runtime
      }
    }
    plan.value = p
    planStatus.value = ps
    ++workshopStatusRevision.value
  } catch (e) {
    console.error('refreshPlanFromServer failed', e)
  }
}

async function refreshGrowthPlan() {
  await Promise.all([refreshPlanFromServer(), store.fetchRecommendations()])
  await refreshT3Summary()
}

function parsePlanKey(k) {
  const i = k.lastIndexOf('_')
  return [k.slice(0, i), parseInt(k.slice(i + 1))]
}

const planEntries = computed(() => {
  const entries = []
  for (const k in plan.value) {
    const [cid, si] = parsePlanKey(k)
    const op = store.recommendations.find((o) => o.char_id === cid)
    if (op) {
      const rec = op.recommendations.find((r) => r.skill_index === si)
      const info = planStatus.value[k] || {}
      if (rec)
        entries.push({
          key: k,
          id: info.id,
          char_id: cid,
          skill_index: si,
          name: op.name,
          skill_name: rec.skill_name,
          profession: op.profession,
          status: info.status || 'idle',
          priority: info.priority || 0,
          failed_reason: info.failed_reason,
          target_level: targetFor(op, rec),
          requirement: op.mastery_error
        })
    }
  }
  entries.sort((a, b) => {
    // failed 计划排到列表底部（待重试，不参与正常优先级排序）
    if (a.status === 'failed' && b.status !== 'failed') return 1
    if (b.status === 'failed' && a.status !== 'failed') return -1
    return a.priority - b.priority
  })
  return entries
})

async function autoWorkshop() {
  workshopLoading.value = true
  try {
    const resp = await axios.post(`${import.meta.env.VITE_HTTP_URL}/workshop-auto-config`, {
      fodder_operators: fodderOps.value,
      t5_operators: t5Ops.value,
      book_operators: bookOps.value
    })
    const ws = resp.data?.workshop_settings
    if (!ws) {
      message.warning(resp.data?.error || i18n.global.t('growth.page.generationFailed'))
      return
    }
    configStore.apply_workshop_response(resp.data)
    if (resp.data.workshop_preset_warning) {
      message.warning(resp.data.workshop_preset_warning)
      return
    }
    workshopT3Summary.value = resp.data?.t3_summary || []

    if (!resp.data.automatic || !ws.length) {
      message.info(
        resp.data.restored
          ? i18n.global.t('growth.page.currentlyCraftableMaterialsAreReadyManualCrafting')
          : resp.data.crafting_status?.blockers?.[0]?.message ||
              i18n.global.t('growth.page.noExecutableRecipesCoverTheCurrentShortage')
      )
      return
    }

    const tasksResp = await axios.get(`${import.meta.env.VITE_HTTP_URL}/task`)
    const tasks = tasksResp.data || []
    const hasTask = (opName) =>
      tasks.some((t) => {
        const tType =
          typeof t.type === 'string' ? t.type : t.type?.display_value || t.type?.value || ''
        return (
          tType === '加工材料' &&
          t.workshop_generation === resp.data.workshop_generation &&
          (t.meta_data === '' || t.meta_data === opName)
        )
      })

    let added = []
    let skipped = []
    for (const entry of ws) {
      if (!entry.operator || !entry.items?.length) continue
      const op = entry.operator
      if (hasTask(op)) {
        skipped.push(op)
        continue
      }
      const r = await axios.post(`${import.meta.env.VITE_HTTP_URL}/task`, {
        task: {
          time: new Date(Date.now() + added.length * 2000).toISOString(),
          plan: {},
          task_type: '加工材料',
          workshop_generation: resp.data.workshop_generation,
          meta_data: op
        }
      })
      if (r.data === i18n.global.t('growth.page.taskAdded')) {
        added.push(op)
      } else {
        message.warning(
          i18n.global.t('growth.page.couldNotAddATaskFor', { value0: op, value1: r.data })
        )
      }
    }

    const parts = []
    if (added.length)
      parts.push(i18n.global.t('growth.page.tasksAdded', { value0: added.join(', ') }))
    if (skipped.length)
      parts.push(i18n.global.t('growth.page.tasksAlreadyPresent', { value0: skipped.join(', ') }))
    if (!added.length && !skipped.length) return
    message.success(
      i18n.global.t('growth.page.generatedCraftingTasksForTheCurrentShortage', {
        value0: parts.length ? '，' + parts.join('；') : ''
      })
    )
  } catch (e) {
    message.error(
      i18n.global.t('growth.page.generationFailed2', {
        value0: e.response?.data?.error || e.message
      })
    )
  } finally {
    workshopLoading.value = false
    ++workshopStatusRevision.value
  }
}

// ─── 通用专精路线预览 ───
const showSettings = ref(false)
const settingsTab = ref('近卫')
const swap_list = [
  { value: '艾丽妮', label: '艾丽妮' },
  { value: '逻各斯', label: '逻各斯' }
]
const swap_30 = computed(() => [
  { value: 'yes', label: i18n.global.t('growth.page.30TrainingSpeedBonus') },
  { value: 'no', label: i18n.global.t('growth.page.noTrainingSpeedBonus') }
])
// 全局路线设置（#91 修订）：中枢加成（0/5）+ 换人缓冲时间，存路线配置设置行，不走 conf。
const masterySettings = reactive({
  central_bonus: 0,
  mastery_swap_buffers: { ...DEFAULT_MASTERY_SWAP_BUFFERS }
})
const masteryBufferFields = computed(() =>
  autoCentralBonus.value
    ? [
        { key: 'central', label: i18n.global.t('growthUpdates.controlCenterBonus') },
        {
          key: 'central_unhalved_m2',
          label: i18n.global.t('growthUpdates.controlCenterBonusUnhalvedM2')
        }
      ]
    : [{ key: 'no_central', label: i18n.global.t('growth.page.noControlCenterBonus') }]
)

const defaultsCache = ref(null)
const bestTrainers = ref({})
const defaultsError = ref('')

const routeSettings = reactive(
  Object.fromEntries(
    profKeys.map((p) => [p, { supports: completeMasterySupports([]), half_off: true }])
  )
)
let _autoSaveReady = false
let _routeSaveChain = Promise.resolve()
const _dirtyRouteProfessions = new Set()
const _suggestedRouteProfessions = new Set()
let _dirtyMasterySettings = false
const routeSaving = ref(false)
const routeCalculating = ref(false)

function persistRouteSettings() {
  const professions = [...new Set([..._dirtyRouteProfessions, ..._suggestedRouteProfessions])]
  if (!professions.length) return _routeSaveChain
  _dirtyRouteProfessions.clear()
  _suggestedRouteProfessions.clear()
  const payloads = professions.map((profession) =>
    buildMasteryRoutePayload(profession, routeSettings[profession])
  )
  routeSaving.value = true
  const savePromise = _routeSaveChain
    .catch(() => {})
    .then(() =>
      Promise.all(
        payloads.map((payload) =>
          axios.post(`${import.meta.env.VITE_HTTP_URL}/mastery-route`, payload)
        )
      )
    )
  _routeSaveChain = savePromise
  savePromise.then(
    () => {
      if (_routeSaveChain === savePromise) routeSaving.value = false
    },
    () => {
      professions.forEach((profession) => _dirtyRouteProfessions.add(profession))
      if (_routeSaveChain === savePromise) routeSaving.value = false
    }
  )
  return savePromise
}

// 编辑只改内存，持久化仅在「保存并关闭」触发（改错可关掉弹窗还原，不被自动保存覆盖）
function markRouteDirty(profession) {
  if (!_autoSaveReady) return
  _dirtyRouteProfessions.add(profession)
}

function flushRouteSettings() {
  return persistRouteSettings()
}

for (const profession of profKeys) {
  watch(
    () => routeSettings[profession],
    () => markRouteDirty(profession),
    { deep: true }
  )
}

// #115：modal 级中枢加成/缓冲与逐职业路线同源走草稿语义——改了不保存关掉要还原
watch(
  () => [masterySettings.central_bonus, ...Object.values(masterySettings.mastery_swap_buffers)],
  () => {
    if (_autoSaveReady) _dirtyMasterySettings = true
  }
)

function applyRoute(d) {
  for (const p of profKeys) {
    if (d[p]) {
      routeSettings[p].supports = completeMasterySupports(d[p].supports, d._jsonDefaults?.[p])
      routeSettings[p].optimal = !!d[p].optimal
      routeSettings[p].half_off = d[p].half_off !== undefined ? d[p].half_off : true
    } else {
      routeSettings[p].supports = completeMasterySupports([], d._jsonDefaults?.[p])
      routeSettings[p].optimal = false
      routeSettings[p].half_off = false
    }
  }
}

async function loadRoute() {
  const r = await axios.get(`${import.meta.env.VITE_HTTP_URL}/mastery-route`)
  const routes = r.data?.routes || []
  const routeDefaults = r.data?.defaults || {}
  const settings = r.data?.settings || {}
  _autoSaveReady = false
  masterySettings.central_bonus = settings.central_bonus ?? 0
  masterySettings.mastery_swap_buffers = normalizeMasterySwapBuffers(settings)
  bestTrainers.value = r.data?.best_trainers || {}
  defaultsError.value = r.data?.defaults_error || ''
  const { routes: merged, suggestedProfessions } = prepareMasteryRoutes(
    routes,
    routeDefaults,
    profKeys
  )
  _suggestedRouteProfessions.clear()
  suggestedProfessions.forEach((p) => _suggestedRouteProfessions.add(p))
  defaultsCache.value = merged
  applyRoute(merged)
  await nextTick()
  _autoSaveReady = true
}
async function openSettings() {
  try {
    await loadRoute()
  } catch (e) {
    defaultsError.value = i18n.global.t('growth.page.couldNotLoadMasteryRoutesPleaseTry')
    console.error('openSettings: loadRoute failed', e)
  }
  showSettings.value = true
}
async function discardRouteChanges() {
  // 关闭弹窗未保存：丢弃内存修改，从 DB 重载还原。
  // _autoSaveReady 先置 false，避免还原过程（applyRoute 触发 watcher）被误标记 dirty。
  _autoSaveReady = false
  _dirtyRouteProfessions.clear()
  _dirtyMasterySettings = false
  try {
    await loadRoute()
  } catch (e) {
    _autoSaveReady = true
    throw e
  }
}
watch(showSettings, (val) => {
  if (!val && (_dirtyRouteProfessions.size || _dirtyMasterySettings)) {
    discardRouteChanges()
      .then(() =>
        message.warning(i18n.global.t('growth.page.unsavedDefaultMasteryRouteChangesWereReverted'))
      )
      .catch((e) => console.error('discard route changes failed', e))
  }
})

async function saveRouteAndClose() {
  try {
    await Promise.all([
      flushRouteSettings(),
      axios.post(`${import.meta.env.VITE_HTTP_URL}/mastery-route/settings`, {
        central_bonus: autoCentralBonus.value,
        mastery_swap_buffers: { ...masterySettings.mastery_swap_buffers }
      })
    ])
    _dirtyMasterySettings = false // 已落库，关弹窗不再触发「未保存还原」
    showSettings.value = false
    message.success(i18n.global.t('growth.page.defaultMasteryRoutesSaved'))
  } catch (e) {
    console.error('saveRouteAndClose: failed', e)
    message.error(i18n.global.t('growth.page.saveFailed2'))
  }
}

async function calculateOptimalRoutes() {
  if (routeCalculating.value || routeSaving.value || store.loading) return
  routeCalculating.value = true
  try {
    const data = await syncMasteryRouteDefaults(axios, import.meta.env.VITE_HTTP_URL)
    const { routes: def } = prepareMasteryRoutes([], data.defaults, profKeys)
    bestTrainers.value = data.best_trainers || {}
    defaultsError.value = ''
    defaultsCache.value = def
    if (!profKeys.some((p) => def._jsonDefaults[p]?.length)) {
      message.info(i18n.global.t('growth.page.noOwnedOperatorsHaveAnUnlockedTraining'))
      return
    }
    for (const p of profKeys) {
      routeSettings[p].supports = (def._jsonDefaults[p] || []).map((s) => ({ ...s }))
      routeSettings[p].half_off = !!def._defaultFlags[p]?.half_off
      routeSettings[p].optimal = false
      _dirtyRouteProfessions.add(p)
    }
    message.success(i18n.global.t('growth.page.operatorDataSynchronizedAndOptimalRoutesCalculated'))
  } catch (e) {
    message.error(
      operatorSyncMessage(
        e.response?.data?.message ||
          e.response?.data?.error ||
          e.message ||
          i18n.global.t('growth.page.calculationFailed')
      )
    )
  } finally {
    routeCalculating.value = false
  }
}

// ─── 显示列表 ───

// 排班上下文用于加入计划时提示训练冲突。
const supportSchedule = computed(() =>
  masteryScheduleContext(planStore.plan, planStore.backup_plans)
)
const autoCentralBonus = computed(() => supportSchedule.value.centralBonus)
function trainingWarning(name) {
  return masteryTraineeWarning(name, supportSchedule.value.blocked)
}

const showSupports = ref(false)
const supportSelection = reactive({ plan: null, name: '' })
async function openSupports(op, rec) {
  await refreshPlanFromServer()
  supportSelection.plan = planStatus.value[planKey(op.char_id, rec.skill_index)]
  supportSelection.name = op.name
  showSupports.value = true
}
const routeOperatorSet = computed(
  () =>
    new Set(
      profKeys.flatMap((profession) =>
        (routeSettings[profession]?.supports || [])
          .flatMap((support) => [support.name, support.swap_name])
          .filter(Boolean)
      )
    )
)
const workshopOperators = computed(() => selectedWorkshopOperators(configStore))
function isIdleOperator(op) {
  return isGrowthOperatorIdle(
    op.name,
    supportSchedule.value.scheduled,
    routeOperatorSet.value,
    workshopOperators.value,
    configStore.free_blacklist || []
  )
}
function workshopTrainingWarning(name) {
  return workshopTraineeWarning(name, workshopOperators.value)
}

const surveyFilters = ref(defaultSurveyFilters())
const survey = ref({ operators: [], error: '', fetched_at: null, stale: false })
const surveyLoading = ref(false)
async function loadSurvey() {
  if (surveyLoading.value) return
  surveyLoading.value = true
  try {
    const response = await axios.get(`${import.meta.env.VITE_HTTP_URL}/growth-survey`, {
      timeout: 30000
    })
    survey.value = response.data
  } catch {
    survey.value = {
      ...survey.value,
      stale: Boolean(survey.value.operators?.length),
      error: i18n.global.t('growth.page.yituliuStatisticsAreTemporarilyUnavailable')
    }
  } finally {
    surveyLoading.value = false
  }
}
const surveyMap = computed(
  () => new Map((survey.value.operators || []).map((row) => [row.charId, row]))
)
const operatorSurveys = computed(
  () =>
    new Map(
      store.recommendations.map((op) => [
        op.char_id,
        operatorSurvey(op, surveyMap.value.get(op.char_id), surveyFilters.value)
      ])
    )
)
const surveyFor = (op) => operatorSurveys.value.get(op.char_id)
function visibleRecs(op) {
  return op.recommendations.map((rec) => selectedRecommendation(rec, targetFor(op, rec)))
}
function visibleModules(op) {
  return op.modules || []
}
const displayList = computed(() => {
  const list = store.recommendations.filter(
    (op) =>
      (idleFilter.value === 'all' || (idleFilter.value === 'idle') === isIdleOperator(op)) &&
      matchesSearch(op.name, searchQuery.value) &&
      (!filterRarity.value.length || filterRarity.value.includes(op.rarity)) &&
      (!filterProfession.value.length || filterProfession.value.includes(profMap[op.profession])) &&
      surveyFor(op).visible
  )
  const byRate = (left, right, rateOf) =>
    (rateOf(right) ?? -1) - (rateOf(left) ?? -1) ||
    right.rarity - left.rarity ||
    left.name.localeCompare(right.name, 'zh-CN')
  if (surveyFilters.value.sort === 'recommendation')
    list.sort((left, right) => byRate(left, right, (op) => remainingSkillRate(op, surveyFor(op))))
  if (surveyFilters.value.sort === 'module')
    list.sort((left, right) => byRate(left, right, (op) => remainingModuleRate(op, surveyFor(op))))
  if (surveyFilters.value.sort === 'level')
    list.sort((a, b) => b.elite - a.elite || b.level - a.level)
  return list
})

const filteredPlanItems = computed(() => {
  const { mastery, module, elite1, elite2 } = surveyFilters.value
  return displayList.value.flatMap((op) => {
    const matches = surveyFor(op)
    const skills =
      mastery !== null
        ? visibleRecs(op)
            .filter(
              (rec) =>
                matches.skillHighlights.includes(rec.skill_index) &&
                rec.current_level < rec.target_level &&
                !isSkillPlanned(op.char_id, rec.skill_index)
            )
            .map((rec) => ({
              kind: 'skill',
              name: op.name,
              char_id: op.char_id,
              skill_index: rec.skill_index,
              target_level: rec.target_level
            }))
        : []
    const modules =
      module !== null
        ? visibleModules(op)
            .filter(
              (entry) =>
                matches.moduleHighlights.includes(entry.id) &&
                entry.current_level < moduleTarget(op, entry) &&
                !isGoalPlanned(op.char_id, entry.id)
            )
            .map((entry) => ({
              kind: 'module',
              char_id: op.char_id,
              module_id: entry.id,
              target_level: moduleTarget(op, entry)
            }))
        : []
    const qualifies = (rate, threshold) => threshold !== null && rate !== null && rate >= threshold
    const choices = operatorLevelGoals(op)
    const phase =
      choices.some((choice) => choice.key === 'elite2') && qualifies(matches.elite2, elite2)
        ? 2
        : qualifies(matches.elite1, elite1)
          ? 1
          : 0
    const selected = choices.find((choice) => choice.key === levelGoalFor(op))
    const goal = choices.find((choice) => choice.elite === phase && choice.level === 1)
    const promotion =
      goal && op.elite < phase && (!selected || selected.elite < phase)
        ? [{ kind: 'promotion', char_id: op.char_id, module_id: goal.key }]
        : []
    return [...skills, ...modules, ...promotion]
  })
})

async function addFilteredToPlan() {
  if (batchAdding.value || store.loading || goalSaving.value || targetSaving.value) return
  const items = filteredPlanItems.value
  if (!items.length) return
  const skills = items.filter((item) => item.kind === 'skill')
  const goals = items.filter((item) => item.kind !== 'skill')
  const controller = new AbortController()
  batchController = controller
  batchAdding.value = true
  goalSaving.value = true
  targetSaving.value = true
  const options = { signal: controller.signal, timeout: 30000 }
  let saved = 0
  let processed = 0
  const failures = []
  const warnings = new Set()
  try {
    if (skills.length) {
      batchProgress.value = i18n.global.t('growth.page.addingSkillPlans', { value0: skills.length })
      await warnMaterialShortage(skills.map((item) => planKey(item.char_id, item.skill_index)))
      if (controller.signal.aborted) return
      const { data } = await axios.post(
        `${import.meta.env.VITE_HTTP_URL}/mastery-plan`,
        {
          planning: true,
          items: skills.map(({ char_id, name, skill_index, target_level }) => ({
            char_id,
            name,
            skill_index,
            target_level
          }))
        },
        options
      )
      if (controller.signal.aborted) return
      skills.forEach((item, index) => {
        const result = data.results?.[index]
        if (result?.warning) warnings.add(result.warning)
        if (
          result?.id &&
          ['added', 'existing', 'deferred', 'insufficient'].includes(result.status)
        ) {
          saved++
          plan.value[planKey(item.char_id, item.skill_index)] = true
        } else
          failures.push(
            result?.reason ||
              i18n.global.t('growth.page.theSkillPlanForWasNotConfirmed', {
                value0: operatorDisplayName(item.name)
              })
          )
      })
      processed += skills.length
    }
    for (const { char_id, module_id, target_level } of goals) {
      if (controller.signal.aborted) return
      const item = { char_id, module_id, ...(target_level ? { target_level } : {}) }
      batchProgress.value = i18n.global.t('growth.page.addingPlan', {
        value0: processed + 1,
        value1: items.length
      })
      const { data } = await axios.post(
        `${import.meta.env.VITE_HTTP_URL}/growth-plan`,
        { ...item, selected: true },
        options
      )
      if (controller.signal.aborted) return
      if (
        !data.goals?.some(
          (goal) => goal.char_id === item.char_id && goal.module_id === item.module_id
        )
      )
        throw new Error(i18n.global.t('growth.page.growthGoalSaveWasNotConfirmed'))
      store.goals = data.goals
      saved++
      processed++
    }
    for (const warning of warnings) message.warning(warning)
    if (failures.length) {
      message.warning(
        i18n.global.t('growth.page.savedPlansWereNotAdded', {
          value0: saved,
          value1: failures.length,
          value2: failures[0]
        })
      )
    } else message.success(i18n.global.t('growth.page.savedFilteredPlans', { value0: saved }))
  } catch (error) {
    if (!controller.signal.aborted) {
      message.error(
        i18n.global.t('growth.page.confirmedSavedOthersAreUnconfirmedRefreshAnd', {
          value0: saved,
          value1: items.length - saved,
          value2:
            error.response?.data?.error || error.message || i18n.global.t('growth.page.saveFailed2')
        })
      )
    }
  } finally {
    if (!controller.signal.aborted) await refreshGrowthPlan()
    batchAdding.value = false
    goalSaving.value = false
    targetSaving.value = false
    batchProgress.value = ''
    batchController = null
  }
}

const operatorPageSize = 30
const operatorPage = ref(1)
const operatorDetail = shallowRef(null)
const detailLoading = ref(false)
const detailError = ref('')
let detailController = null
const pagedOperators = computed(() =>
  displayList.value
    .slice((operatorPage.value - 1) * operatorPageSize, operatorPage.value * operatorPageSize)
    .map((op) => (operatorDetail.value?.char_id === op.char_id ? operatorDetail.value : op))
)
watch(displayList, () => {
  operatorPage.value = 1
  expandedOperator.value = []
})
watch(operatorPage, () => {
  expandedOperator.value = []
})
async function loadOperatorDetail(charId) {
  detailController?.abort()
  operatorDetail.value = null
  detailError.value = ''
  detailLoading.value = Boolean(charId)
  if (!charId) return
  const controller = new AbortController()
  detailController = controller
  try {
    const { data } = await axios.get(`${import.meta.env.VITE_HTTP_URL}/mastery-recommendation`, {
      params: { char_id: charId },
      signal: controller.signal,
      timeout: 30000
    })
    if (controller.signal.aborted) return
    if (data.error) throw new Error(data.error)
    const detail = data.operators?.find((op) => op.char_id === charId)
    if (!detail) throw new Error(i18n.global.t('growth.page.operatorDetailsNotFoundRefreshTheList'))
    operatorDetail.value = detail
  } catch (error) {
    if (!controller.signal.aborted)
      detailError.value = error.message || i18n.global.t('growth.page.failedToReadMaterialDetails')
  } finally {
    if (!controller.signal.aborted) detailLoading.value = false
  }
}
watch(expandedOperator, (names) => loadOperatorDetail(names[0]))
onUnmounted(() => detailController?.abort())

const planMaterials = ref(null)
const chipFarmingLoading = ref(false)
const hasChipShortage = computed(() =>
  planMaterials.value?.missing?.some(
    (row) => (/^32[1-8][12]$/.test(row.id) || row.id === '4006') && row.count > 0
  )
)
async function configureChipFarming() {
  chipFarmingLoading.value = true
  try {
    await configStore.flush_config_saves()
    const response = await axios.post(`${import.meta.env.VITE_HTTP_URL}/growth-chip-farming`)
    await configStore.load_config()
    const stages = response.data.stages || []
    message.success(
      stages.length
        ? i18n.global.t('growth.page.enabledInventoryBasedFarmingForAndAdded', {
            value0: response.data.active,
            value1: stages.join('、')
          })
        : i18n.global.t('growth.page.chipAndPurchaseCertificateStocksAlreadyCover')
    )
  } catch (error) {
    message.error(
      error.response?.data?.error || i18n.global.t('growth.page.failedToConfigureChipFarming')
    )
  } finally {
    chipFarmingLoading.value = false
  }
}
const missingPlanSkills = computed(() => {
  const keys = new Set(planMaterials.value?.missing_skills || [])
  return planEntries.value.filter((entry) => keys.has(entry.key))
})
const materialsLoading = ref(false)
const materialsError = ref('')
let materialRequest = 0
let materialTimer

async function refreshT3Summary() {
  const request = ++materialRequest
  const keys = planEntries.value.map((entry) => entry.key)
  if (!keys.length && !store.goals.length) {
    planMaterials.value = null
    materialsLoading.value = false
    return
  }
  materialsLoading.value = true
  materialsError.value = ''
  try {
    const response = await axios.post(`${import.meta.env.VITE_HTTP_URL}/mastery-t3-summary`, {
      planned_skills: keys,
      goals: store.goals,
      targets: targets.value
    })
    if (request !== materialRequest) return
    if (response.data.error) throw new Error(response.data.error)
    planMaterials.value = response.data.material_summary
  } catch (error) {
    if (request === materialRequest) {
      planMaterials.value = null
      materialsError.value =
        error.response?.data?.error ||
        i18n.global.t('growth.page.materialCalculationFailedRefreshAndTryAgain')
    }
  } finally {
    if (request === materialRequest) materialsLoading.value = false
  }
}

function queueMaterialSummary() {
  if (batchAdding.value) return
  ++materialRequest
  clearTimeout(materialTimer)
  materialsLoading.value = totalGoalCount.value > 0
  materialTimer = setTimeout(refreshT3Summary, 200)
}
watch([plan, planStatus, targets, () => store.goals], queueMaterialSummary, { deep: true })
watch(() => store.recommendations, queueMaterialSummary)
onUnmounted(() => {
  ++materialRequest
  clearTimeout(materialTimer)
})

// ─── 工具函数 ───
const cultivateSyncing = ref(false)
async function fetchCultivate() {
  if (cultivateSyncing.value) return
  cultivateSyncing.value = true
  try {
    await store.fetchCultivate()
    if (store.cultivateOk) {
      message.success(
        i18n.global.t('growth.page.sklandDataSynchronized', { value0: store.cultivateMsg })
      )
    } else if (store.cultivateMsg) {
      message.error(
        i18n.global.t('growth.page.sklandSynchronizationFailed', { value0: store.cultivateMsg })
      )
    }
  } finally {
    cultivateSyncing.value = false
  }
}

// ─── 插入已确认材料的专精任务 ───
const startingMastery = ref(false)

async function insertMasteryTask(op, rec) {
  if (startingMastery.value) return
  if (op.mastery_error) {
    message.warning(op.mastery_error)
    return
  }
  startingMastery.value = true
  try {
    const { data } = await axios.post(`${import.meta.env.VITE_HTTP_URL}/mastery-plan/start`, {
      char_id: op.char_id,
      skill_index: rec.skill_index,
      target_level: rec.target_level
    })
    if (data.warning) message.warning(data.warning)
    if (data.status === 'inserted' || data.status === 'queued') {
      message.success(data.reason)
    } else {
      message.warning(data.reason || i18n.global.t('growth.page.theTaskWasNotInsertedRefreshAnd'))
    }
    await refreshPlanFromServer()
  } catch (error) {
    message.error(
      error.response?.data?.reason ||
        i18n.global.t('growth.page.insertionFailed', { value0: error.message })
    )
  } finally {
    startingMastery.value = false
  }
}

// ─── 工作区视图、队列与派生数据 ───
const VIEW_KEYS = ['overview', 'operators', 'materials', 'insights']

function readQuery() {
  if (typeof window === 'undefined' || !window.location) return new URLSearchParams()
  try {
    return new URLSearchParams(window.location.search)
  } catch {
    return new URLSearchParams()
  }
}

const initialView = readQuery().get('view')
const activeView = ref(VIEW_KEYS.includes(initialView) ? initialView : 'overview')
const craftingOrderRef = ref(null)

function replaceQuery(patch) {
  if (typeof window === 'undefined' || !window.location || !window.history) return
  try {
    const url = new URL(window.location.href)
    for (const [key, value] of Object.entries(patch)) {
      if (value === null || value === undefined || value === '') url.searchParams.delete(key)
      else url.searchParams.set(key, value)
    }
    window.history.replaceState(window.history.state, '', url.toString())
  } catch {
    // 地址栏同步失败不影响页面状态。
  }
}

function scrollToTop() {
  if (typeof document === 'undefined') return
  const host = document.querySelector('.layout-content-container > .n-layout-scroll-container')
  if (host && typeof host.scrollTo === 'function') {
    host.scrollTo({ top: 0, behavior: 'smooth' })
  } else if (typeof window !== 'undefined' && typeof window.scrollTo === 'function') {
    window.scrollTo({ top: 0, behavior: 'smooth' })
  }
}

watch(activeView, (value) => {
  if (value !== 'operators') expandedOperator.value = []
  replaceQuery({ view: value === 'overview' ? null : value, op: expandedOperator.value[0] || null })
  scrollToTop()
})

watch(expandedOperator, (names) => {
  if (activeView.value === 'operators') replaceQuery({ op: names[0] || null })
})

function openOperatorPicker() {
  activeView.value = 'operators'
  nextTick(() => {
    if (typeof document === 'undefined') return
    document.querySelector('.growth-filters__search input')?.focus?.()
  })
}

function openCraftingOrder() {
  craftingOrderRef.value?.open?.()
}

function openOperator(op) {
  if (!op) return
  activeView.value = 'operators'
  expandedOperator.value = [op.char_id]
  replaceQuery({ view: 'operators', op: op.char_id })
}

function selectOperator(op) {
  if (!op) return
  expandedOperator.value = expandedOperator.value.includes(op.char_id) ? [] : [op.char_id]
}

function closeOperator() {
  expandedOperator.value = []
}

function refreshGrowthPlanOnly() {
  void loadSurvey()
  return refreshGrowthPlan()
}

const syncHint = computed(() => {
  const text = store.cultivateMsg
  if (!text) return ''
  if (!store.cultivateOk) return i18n.global.t('growth.page.sklandSynchronizationFailed2')
  return text.length > 12
    ? i18n.global.t('growth.page.sklandSynchronized')
    : i18n.global.t('growth.page.skland') + text
})

function plannedCountFor(op) {
  if (!op) return 0
  const skills = (op.recommendations || []).filter((rec) =>
    isSkillPlanned(op.char_id, rec.skill_index)
  ).length
  const goals = store.goals.filter((goal) => goal.char_id === op.char_id).length
  return skills + goals
}

const queueItems = computed(() => {
  const rows = planEntries.value.map((entry) => ({
    key: 'skill:' + entry.char_id + ':' + entry.skill_index,
    kind: 'skill',
    char_id: entry.char_id,
    name: entry.name,
    label:
      skillDisplayName(entry.skill_name) +
      i18n.global.t('growth.page.m') +
      [
        '',
        i18n.global.t('growth.page.1'),
        i18n.global.t('growth.page.2'),
        i18n.global.t('growth.page.3')
      ][entry.target_level || 3],
    status: entry.status,
    failed_reason: entry.failed_reason
  }))
  for (const goal of store.goals) {
    const op = store.recommendations.find((entry) => entry.char_id === goal.char_id)
    rows.push({
      key: 'goal:' + goal.char_id + ':' + goal.module_id,
      kind: 'goal',
      char_id: goal.char_id,
      name: op?.name || goal.char_id,
      label: goalLabel(op, goal),
      status: 'manual',
      failed_reason: ''
    })
  }
  const rank = new Map(queueOrderKeys.value.map((key, index) => [key, index]))
  return rows.sort(
    (left, right) => (rank.get(left.key) ?? rank.size) - (rank.get(right.key) ?? rank.size)
  )
})

const trainingCard = computed(() => {
  const entry = planEntries.value.find((row) =>
    ['training', 'arranging', 'waiting_collect'].includes(row.status)
  )
  if (!entry) return null
  const op = store.recommendations.find((item) => item.char_id === entry.char_id) || null
  const rec = op?.recommendations?.find((item) => item.skill_index === entry.skill_index) || null
  const target = entry.target_level || 3
  const selected = rec ? selectedRecommendation(rec, target) : null
  return {
    entry,
    op,
    rec: selected,
    target,
    totalTime: selected?.total_time || 0
  }
})

const nextUpItem = computed(
  () =>
    queueItems.value.find(
      (row) => !['training', 'arranging', 'waiting_collect', 'failed'].includes(row.status)
    ) || null
)

const planMaterialStats = computed(() => {
  const resourceIds = new Set(['4001', 'growth_exp', '4006', '32001'])
  const rows = (planMaterials.value?.materials || []).filter((row) => !resourceIds.has(row.id))
  const missingRows = (planMaterials.value?.missing || []).filter((row) => !resourceIds.has(row.id))
  if (!rows.length) {
    return { ready: 0, total: 0, missing: 0, craftable: 0, percent: 0 }
  }
  const ready = rows.filter((row) => row.owned >= row.required).length
  const missing = missingRows.length
  const craftable = rows.filter((row) => row.owned < row.required && row.craftable).length
  return {
    ready,
    total: rows.length,
    missing,
    craftable,
    percent: rows.length ? (ready / rows.length) * 100 : 0
  }
})

const rosterStats = computed(() => {
  const totals = sumPersonalStatistics(store.personalStatistics, [1, 2, 3, 4, 5, 6])
  return {
    owned: totals.owned,
    elite2: totals.elite2,
    masteries: totals.skills[3],
    modules: totals.modules[1] + totals.modules[2] + totals.modules[3]
  }
})

// 值得练排序条件：默认按剩余专三率，可切剩余模组解锁率、稀有度、等级。
const pickSort = ref('mastery')

const recommendedCards = computed(() => {
  const cards = store.recommendations
    .map((op) => {
      const survey = surveyFor(op) || {}
      const target = recommendedTarget(op, survey)
      return {
        operator: op,
        survey,
        target,
        planned: false,
        plannedCount: plannedCountFor(op),
        score: target?.rate ?? null
      }
    })
    // 完成度只看本地剩余目标：已专三技能不再作为上榜理由；全部练完或已在计划中的干员不出现。
    .filter((card) => hasRemainingTarget(card.operator) && !card.plannedCount)
  return sortRecommendedCards(cards, pickSort.value).slice(0, 4)
})

const operatorCards = computed(() =>
  pagedOperators.value.map((op) => ({
    operator: op,
    survey: surveyFor(op),
    planned: hasPlannedGoal(op),
    plannedCount: plannedCountFor(op)
  }))
)

const selectedOperatorBase = computed(
  () => store.recommendations.find((op) => op.char_id === expandedOperator.value[0]) || null
)
const selectedOperator = computed(() => {
  const id = expandedOperator.value[0]
  if (!id) return null
  if (operatorDetail.value?.char_id === id) return operatorDetail.value
  return selectedOperatorBase.value
})
const selectedLevelGoalValue = computed(() =>
  selectedOperatorBase.value ? levelGoalFor(selectedOperatorBase.value) : null
)
const selectedRequiredLevel = computed(() =>
  selectedOperatorBase.value
    ? prerequisiteLevelGoal(
        selectedOperatorBase.value,
        hasPlannedSkill(selectedOperatorBase.value),
        store.goals
      )
    : null
)
const selectedPlannedCount = computed(() => plannedCountFor(selectedOperatorBase.value))

const selectedSkillRows = computed(() => {
  const op = selectedOperator.value
  const base = selectedOperatorBase.value
  if (!op || !base) return []
  const rows = op.recommendations || base.recommendations || []
  return rows.map((rec) => {
    const target = targetFor(base, rec)
    const key = planKey(base.char_id, rec.skill_index)
    const status = planStatus.value[key] || null
    const planned = isSkillPlanned(base.char_id, rec.skill_index)
    return {
      rec: selectedRecommendation(rec, target),
      target,
      planned,
      status,
      locked: isTargetLocked(base, rec),
      targetOptions: targetOptions(rec),
      disabled: batchAdding.value || (!planned && !!base.material_error),
      hasSupport: Boolean(status?.id)
    }
  })
})

// 已专三技能在档案里保留只读行，让顶部聚合数字与技能名对得上号。
const selectedCompletedSkills = computed(() => {
  const base = selectedOperatorBase.value
  if (!base) return []
  const survey = surveyFor(base)
  return operatorSkillRows(base)
    .filter((row) => row.current >= 3)
    .map((row) => ({ ...row, rate: surveySkillRate(survey, row.index) }))
})

const selectedModuleRows = computed(() => {
  const op = selectedOperator.value
  const base = selectedOperatorBase.value
  if (!op || !base) return []
  return (op.modules || []).map((module) => {
    const target = moduleTarget(base, module)
    const planned = isGoalPlanned(base.char_id, module.id)
    const summary = module.targets?.[target] || module.targets?.[module.max_level] || null
    return {
      module,
      target,
      planned,
      targetOptions: moduleTargetOptions(module),
      disabled: goalSaving.value || (module.current_level >= module.max_level && !planned),
      summary: summary?.opening_summary || null
    }
  })
})

const selectedBasicState = computed(() => {
  const base = selectedOperatorBase.value
  const op = selectedOperator.value
  if (!base && !op) return { supported: false }
  const target = op || base
  const supported = Boolean(target.supports_basic_skill7 || target.basic_skill_summary)
  if (!supported) return { supported: false }
  const explicit = isGoalPlanned(target.char_id, 'skill7')
  const planned = explicit || hasPlannedSkill(target)
  const prerequisite = target.basic_skill_prerequisite
  const pieces = []
  if (target.basic_skill_summary) {
    pieces.push(i18n.global.t('growth.page.basicSkillMaterialsAreCountedOncePer'))
  }
  if (prerequisite && target.elite < prerequisite.elite) {
    pieces.push(
      i18n.global.t('growth.page.minimumPrerequisite') +
        eliteLabel(prerequisite.elite) +
        ' ' +
        prerequisite.level +
        i18n.global.t('growth.page.levelsMaterialsAreIncludedAutomatically')
    )
  }
  if ((target.max_phase || 0) >= 2) {
    pieces.push(i18n.global.t('growth.page.masteryPlansIncludeThisPrerequisiteAutomatically'))
  }
  if (!pieces.length) pieces.push(i18n.global.t('growth.page.anIndependentBasicSkillGoalThatDoes'))
  return {
    supported: true,
    planned,
    checked: planned,
    disabled:
      goalSaving.value || hasPlannedSkill(target) || (!target.basic_skill_summary && !explicit),
    achieved: target.main_skill_level >= 7,
    materials: target.basic_skill_summary || null,
    note: pieces.join('')
  }
})

function applySelectedLevel(key) {
  // 等级目标的材料摘要只存在于按需详情里；用列表快照会误判「已经达成」。
  const op = selectedOperator.value || selectedOperatorBase.value
  if (op) return applyLevelTarget(op, key)
}
function toggleSelectedSkill(rec) {
  if (selectedOperatorBase.value) return toggleSkillPlan(selectedOperatorBase.value, rec)
}
function changeSelectedTarget(payload) {
  if (selectedOperatorBase.value) {
    return changeTarget(selectedOperatorBase.value, payload.rec, payload.value)
  }
}
function insertSelectedMasteryTask(rec) {
  if (selectedOperatorBase.value) return insertMasteryTask(selectedOperatorBase.value, rec)
}
function openSelectedSupports(rec) {
  if (selectedOperatorBase.value) return openSupports(selectedOperatorBase.value, rec)
}
function toggleSelectedModule(payload) {
  if (selectedOperatorBase.value) {
    return toggleGoal(selectedOperatorBase.value, payload.module.id, payload.value)
  }
}
function changeSelectedModuleTarget(payload) {
  if (selectedOperatorBase.value) {
    return changeModuleTarget(selectedOperatorBase.value, payload.module, payload.value)
  }
}
function toggleSelectedBasic(value) {
  if (selectedOperatorBase.value) {
    return toggleGoal(selectedOperatorBase.value, 'skill7', value)
  }
}

// ─── 初始化 ───
onMounted(async () => {
  const params = readQuery()
  await refreshPlanFromServer()
  void loadSurvey()
  await Promise.all([loadOperators(), store.fetchRecommendations()])
  const requestedOperator = params.get('op')
  if (requestedOperator && activeView.value === 'operators') {
    expandedOperator.value = [requestedOperator]
  }
  // 载入专精路线；打开设置时刷新拥有情况和解锁技能。
  if (!defaultsCache.value) {
    try {
      await loadRoute()
    } catch (e) {
      console.error('mount: loadRoute failed', e)
    }
  }
  await refreshT3Summary()
})

async function loadOperators() {
  try {
    const r = await axios.get(`${import.meta.env.VITE_HTTP_URL}/operator`)
    operatorOptions.value = (r.data || []).map((n) => ({ label: n, value: n }))
  } catch (e) {
    console.error('loadOperators: failed', e)
  }
}
</script>

<style scoped>
.growth-notice {
  display: flex;
  align-items: flex-start;
  gap: 12px;
  padding: 12px 16px;
  border-radius: 14px;
  background: var(--gp-warn-block);
  color: var(--gp-ink-2);
}

.growth-notice p {
  margin: 0;
  font-size: 12.5px;
  line-height: 1.6;
}

.growth-notice__stamp {
  flex: none;
  margin-top: 1px;
}

.growth-blocked {
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: 10px;
  padding: 30px 28px;
}

.growth-blocked h2 {
  margin: 0;
  font-size: 24px;
  font-weight: 700;
  letter-spacing: -0.02em;
}

.growth-blocked p {
  margin: 0;
  color: var(--gp-muted);
  font-size: 13px;
}

.growth-blocked__actions {
  display: flex;
  gap: 10px;
  flex-wrap: wrap;
  margin-top: 6px;
}

.growth-loading {
  display: flex;
  flex-direction: column;
  gap: 14px;
}

.growth-operators {
  display: grid;
  grid-template-columns: minmax(0, 1fr);
  gap: 14px;
  min-width: 0;
}

.growth-operators.has-dossier {
  align-items: start;
}

@media (min-width: 1121px) {
  .growth-operators.has-dossier {
    grid-template-columns: minmax(0, 1fr) 392px;
  }
}

.support-outer {
  margin-bottom: 8px;
}

.support-inner {
  margin-top: 4px;
}

.task-col {
  display: flex;
  align-items: center;
  gap: 8px;
  margin: 4px 0;
}

.ml {
  margin-left: 12px;
}

.mastery-route-tabs {
  position: relative;
}

/* ── 设置弹窗 ─────────────────────────────────────────── */
/* 弹窗整张纸统一暖色，内部区块用浅一档的纸面区分，不再出现白底嵌暖黄块。 */
.growth-modal {
  background: var(--gp-surface-2);
}

.growth-modal :deep(.n-card-header) {
  padding: 18px 24px 14px;
  border-bottom: 1px solid var(--gp-hair-soft);
  background: var(--gp-surface-2);
}

:global(.growth-modal > .n-card-content) {
  padding: 0;
}

.growth-modal :deep(.n-card__footer) {
  padding: 14px 24px;
  border-top: 1px solid var(--gp-hair-soft);
  background: var(--gp-surface-2);
}

.growth-modal__body {
  padding: 18px 24px;
}

.growth-modal__head h2 {
  margin: 4px 0 3px;
  font-size: 22px;
  font-weight: 700;
  letter-spacing: -0.02em;
  line-height: 1.2;
}

.growth-modal__head p {
  margin: 0;
  max-width: 58ch;
  color: var(--gp-muted);
  font-size: 11.5px;
  line-height: 1.6;
}

.growth-modal__foot {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  flex-wrap: wrap;
}

.growth-drawer__foot-left,
.growth-drawer__foot-right {
  display: flex;
  align-items: center;
  gap: 8px;
}

.growth-drawer__foot-note {
  font-size: 11.5px;
}

.route-drawer {
  display: grid;
  grid-template-columns: 124px minmax(0, 1fr);
  gap: 20px;
  align-items: start;
}

.route-drawer__rail {
  position: sticky;
  top: 0;
  display: flex;
  flex-direction: column;
  gap: 2px;
  padding: 4px;
  border-radius: 12px;
  background: var(--gp-surface-2);
}

.route-drawer__prof {
  height: 32px;
  padding: 0 10px;
  border: 0;
  border-radius: 8px;
  background: transparent;
  color: var(--gp-muted);
  font: inherit;
  font-size: 12px;
  font-weight: 650;
  text-align: left;
  cursor: pointer;
}

.route-drawer__prof:hover {
  color: var(--gp-ink);
  background: var(--gp-surface-3);
}

.route-drawer__prof.is-active {
  background: var(--gp-ink);
  color: var(--gp-page);
}

.route-drawer__body {
  display: flex;
  flex-direction: column;
  gap: 18px;
  min-width: 0;
}

.route-drawer__alert {
  font-size: 12px;
}

.route-section-head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 10px;
}

.route-section-head h3 {
  margin: 0;
  font-size: 15px;
  font-weight: 700;
}

.route-section-head p {
  margin: 3px 0 0;
  color: var(--gp-muted);
  font-size: 11px;
  line-height: 1.55;
}

.route-slot {
  display: flex;
  flex-direction: column;
  gap: 7px;
  padding: 10px 12px;
  margin-bottom: 8px;
  border-radius: 12px;
  background: var(--gp-surface);
  box-shadow: inset 0 0 0 1px var(--gp-hair-soft);
}

.route-slot__line {
  display: grid;
  grid-template-columns: 46px minmax(0, 1fr) auto;
  gap: 10px;
  align-items: center;
}

.route-slot__stage {
  display: grid;
  place-items: center;
  height: 40px;
  border-radius: 8px;
  background: var(--gp-surface-2);
  color: var(--gp-ink);
  font-size: 11px;
  font-weight: 700;
}

.route-slot__efficiency {
  display: flex;
  align-items: center;
  gap: 6px;
  flex: none;
  font-size: 11px;
}

.route-slot__swap {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
  padding-left: 56px;
}

.route-slot__swap :deep(.n-select) {
  width: 168px;
}

.route-flags {
  display: flex;
  align-items: center;
  gap: 18px;
  flex-wrap: wrap;
}

.route-reference {
  padding-top: 4px;
  border-top: 1px solid var(--gp-hair-soft);
}

.route-reference > summary {
  padding: 8px 0;
  color: var(--gp-muted);
  font-size: 12px;
  font-weight: 600;
  cursor: pointer;
}

.route-global {
  padding-top: 14px;
  border-top: 1px solid var(--gp-hair-soft);
}

.route-central {
  display: flex;
  align-items: center;
  gap: 10px;
  font-size: 12px;
}

.route-buffers {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(240px, 1fr));
  gap: 10px;
  margin-top: 12px;
}

.route-buffers__caption {
  display: flex;
  grid-column: 1 / -1;
  align-items: center;
  gap: 6px;
  margin: 0 0 2px;
  color: var(--gp-muted);
  font-size: 11px;
}

.route-buffer {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  padding: 8px 10px;
  border-radius: 10px;
  background: var(--gp-surface-2);
  font-size: 11.5px;
}

.workshop-drawer {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.workshop-threshold {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  flex-wrap: wrap;
  padding: 14px 16px;
  border-radius: 14px;
  background: var(--gp-surface);
  box-shadow: inset 0 0 0 1px var(--gp-hair-soft);
}

.workshop-threshold__copy h3 {
  margin: 0;
  font-size: 14px;
  font-weight: 700;
}

.workshop-threshold__copy p {
  margin: 3px 0 0;
  max-width: 46ch;
  color: var(--gp-muted);
  font-size: 11px;
  line-height: 1.55;
}

.workshop-threshold__controls {
  display: flex;
  align-items: center;
  gap: 8px;
}

.workshop-policy {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 12px;
}

.workshop-group {
  display: flex;
  flex-direction: column;
  gap: 8px;
  padding-bottom: 14px;
  border-bottom: 1px solid var(--gp-hair-soft);
}

.workshop-group:last-of-type {
  border-bottom: 0;
  padding-bottom: 0;
}

.workshop-group header {
  display: flex;
  align-items: center;
  gap: 8px;
}

.workshop-group h3 {
  margin: 0;
  font-size: 13px;
  font-weight: 700;
}

.workshop-advanced {
  border-top: 1px solid var(--gp-hair-soft);
  padding-top: 10px;
}

.workshop-advanced > summary {
  color: var(--gp-muted);
  font-size: 12px;
  font-weight: 600;
  cursor: pointer;
}

.workshop-recommendations {
  display: flex;
  flex-direction: column;
  gap: 12px;
  margin-top: 10px;
}

.workshop-recommendations h4 {
  margin: 0 0 4px;
  font-size: 12px;
  font-weight: 700;
}

.workshop-recommendations p {
  margin: 2px 0;
  color: var(--gp-muted);
  font-size: 11px;
  line-height: 1.55;
}

@media (max-width: 760px) {
  .route-drawer {
    grid-template-columns: 1fr;
  }

  .route-drawer__rail {
    position: static;
    flex-direction: row;
    overflow-x: auto;
    scrollbar-width: none;
  }

  .route-drawer__rail::-webkit-scrollbar {
    display: none;
  }

  .route-drawer__prof {
    flex: none;
    text-align: center;
  }

  .route-slot__line {
    grid-template-columns: 1fr;
  }

  .route-slot__stage {
    place-items: start;
    height: auto;
    padding: 2px 8px;
    justify-self: start;
  }

  .route-slot__swap {
    padding-left: 0;
  }

  .route-slot__swap :deep(.n-select) {
    width: 100%;
  }

  .growth-modal :deep(.n-card-header),
  .growth-modal :deep(.n-card__footer) {
    padding-left: 16px;
    padding-right: 16px;
  }

  .growth-modal__body {
    padding-left: 16px;
    padding-right: 16px;
  }
}
</style>
