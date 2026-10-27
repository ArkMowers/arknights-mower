<script setup>
import { i18n } from '@/i18n'
const { t } = i18n.global
import { useConfigStore } from '@/stores/config'
import { storeToRefs } from 'pinia'
import { computed, inject } from 'vue'
import { usePlanStore } from '@/stores/plan'
import GroupRestingThresholds from './GroupRestingThresholds.vue'

const { disabled } = defineProps({ disabled: Boolean })
const mobile = inject('mobile')
const configStore = useConfigStore()
const planStore = inject('planStore', null) || usePlanStore()
const {
  product_switching,
  drone_count_limit,
  drone_interval,
  resting_threshold,
  group_resting_thresholds,
  version_update_resting_threshold,
  version_update_threshold_advance_hours,
  free_room,
  dorm_isolation,
  merge_interval,
  test_mood_calculation,
  group_rest_in_full_on_mood_gap,
  group_mood_gap_threshold_minutes,
  group_mood_gap_max_extra_wait_hours,
  group_mood_gap_exclusions,
  fia_fool,
  assistant_follows_schedule,
  fia_threshold,
  rescue_threshold,
  favorite
} = storeToRefs(configStore)

const excludedGroupOptions = computed(() =>
  [...new Set([...planStore.all_groups, ...group_mood_gap_exclusions.value])].map((group) => ({
    label: group,
    value: group
  }))
)
</script>

<template>
  <div class="advanced-settings" :inert="disabled">
    <n-form
      :label-placement="mobile ? 'top' : 'left'"
      label-width="190"
      label-align="left"
      :show-feedback="false"
    >
      <n-form-item :show-label="false">
        <n-checkbox v-model:checked="test_mood_calculation"
          >{{ t('plans.calculatedMorale')
          }}<help-text>{{ t('plans.calculatedMoraleHelp') }}</help-text>
        </n-checkbox>
      </n-form-item>
      <n-form-item :show-label="false">
        <n-checkbox v-model:checked="product_switching.enable"
          >{{ t('plans.productSwitching')
          }}<help-text>{{ t('plans.productSwitchingHelp') }}</help-text>
        </n-checkbox>
      </n-form-item>
      <template v-if="product_switching.enable">
        <n-form-item :show-label="false">
          <n-checkbox v-model:checked="product_switching.grandet_mode"
            >{{ t('plans.economicalSwitching')
            }}<help-text>{{ t('plans.economicalSwitchingHelp') }}</help-text>
          </n-checkbox>
        </n-form-item>
        <n-form-item>
          <template #label>
            <span>{{ t('plans.maxDronesSwitch') }}</span>
            <help-text>{{ t('plans.maxDronesSwitchHelp') }}</help-text>
          </template>
          <mower-input-number
            v-model:value="product_switching.max_drones_per_switch"
            :min="0"
            :max="200"
          >
            <template #suffix>{{ t('plans.dronesUnit') }}</template>
          </mower-input-number>
        </n-form-item>
        <n-form-item v-if="product_switching.grandet_mode" :show-label="false">
          <n-checkbox v-model:checked="product_switching.use_drones_when_leaving_orirock"
            >{{ t('plans.dronesLeavingShards')
            }}<help-text>{{ t('plans.dronesLeavingShardsHelp') }}</help-text>
          </n-checkbox>
        </n-form-item>
        <n-form-item :show-label="false">
          <n-checkbox v-model:checked="product_switching.direct_when_drones_insufficient"
            >{{ t('plans.directProductSwitch')
            }}<help-text>{{ t('plans.directProductSwitchHelp') }}</help-text>
          </n-checkbox>
        </n-form-item>
        <n-form-item v-if="product_switching.grandet_mode">
          <template #label>
            <span class="label-with-help">
              <span>{{ t('plans.droneLossTolerance') }}</span>
              <help-text>{{ t('plans.droneLossToleranceHelp') }}</help-text>
            </span>
          </template>
          <mower-input-number
            v-model:value="product_switching.drone_loss_seconds"
            :min="0"
            :max="180"
          >
            <template #suffix>{{ t('plans.seconds') }}</template>
          </mower-input-number>
        </n-form-item>
        <n-form-item v-if="product_switching.grandet_mode">
          <template #label>
            <span class="label-with-help">
              <span>{{ t('plans.productSwitchBuffer') }}</span>
              <help-text>{{ t('plans.productSwitchBufferHelp') }}</help-text>
            </span>
          </template>
          <mower-input-number v-model:value="product_switching.waiting_seconds" :min="0" :max="60">
            <template #suffix>{{ t('plans.seconds') }}</template>
          </mower-input-number>
        </n-form-item>
      </template>
      <n-form-item>
        <template #label>
          <span>{{ t('plans.droneThreshold') }}</span>
          <help-text>
            <div>{{ t('plans.droneMinimumHelp') }}</div>
            <div>{{ t('plans.factoryDroneThresholdHelp') }}</div>
            <div>{{ t('plans.tradeDroneThresholdHelp') }}</div>
            <div>{{ t('plans.manufactureDroneThresholdHelp') }}</div>
          </help-text>
        </template>
        <mower-input-number v-model:value="drone_count_limit" :min="20" />
      </n-form-item>
      <n-form-item>
        <template #label>
          <span>{{ t('plans.droneInterval') }}</span>
          <help-text>
            <div>{{ t('plans.decimalHelp') }}</div>
          </help-text>
        </template>
        <mower-input-number v-model:value="drone_interval">
          <template #suffix>{{ t('plans.hours') }}</template>
        </mower-input-number>
      </n-form-item>
      <n-form-item>
        <template #label>
          <span>{{ t('plans.moraleThreshold') }}</span>
          <help-text>
            <div>{{ t('plans.twoPowerHelp') }}</div>
            <div>{{ t('plans.threePowerHelp') }}</div>
            <div>{{ t('plans.maintenanceThresholdRecommendation') }}</div>
          </help-text>
        </template>
        <div class="threshold">
          <n-slider
            v-model:value="resting_threshold"
            :step="5"
            :min="35"
            :max="80"
            :format-tooltip="(v) => `${v}%`"
          />
          <mower-input-number v-model:value="resting_threshold" :step="5" :min="35" :max="80">
            <template #suffix>%</template>
          </mower-input-number>
        </div>
      </n-form-item>
      <n-form-item>
        <template #label>
          <span>{{ t('groupResting.title') }}</span>
          <help-text :label="t('groupResting.helpTitle')">
            <div>{{ t('groupResting.productSwitchingHelp') }}</div>
            <div>{{ t('groupResting.inheritanceHelp') }}</div>
            <div>{{ t('groupResting.shiftOffHelp') }}</div>
            <div>{{ t('groupResting.maintenanceHelp') }}</div>
          </help-text>
        </template>
        <GroupRestingThresholds
          v-model="group_resting_thresholds"
          :groups="planStore.all_groups"
          :default-threshold="resting_threshold"
          :disabled="disabled"
        />
      </n-form-item>
      <n-form-item>
        <template #label>
          <span>{{ t('plans.maintenanceMoraleThreshold') }}</span>
          <help-text>
            <div>{{ t('plans.maintenanceMoraleHelp') }}</div>
            <div>{{ t('groupResting.maintenanceRuntimeHelp') }}</div>
          </help-text>
        </template>
        <div class="threshold">
          <n-slider
            v-model:value="version_update_resting_threshold"
            :step="5"
            :min="50"
            :max="100"
            :format-tooltip="(v) => `${v}%`"
          />
          <mower-input-number
            v-model:value="version_update_resting_threshold"
            :step="5"
            :min="50"
            :max="100"
          >
            <template #suffix>%</template>
          </mower-input-number>
        </div>
      </n-form-item>
      <n-form-item>
        <template #label>
          <span>{{ t('plans.maintenanceLeadTime') }}</span>
          <help-text>{{ t('plans.maintenanceLeadTimeHelp') }}</help-text>
        </template>
        <mower-input-number
          v-model:value="version_update_threshold_advance_hours"
          :step="1"
          :min="0"
          :max="168"
        >
          <template #suffix>{{ t('plans.hours') }}</template>
        </mower-input-number>
      </n-form-item>

      <n-form-item :show-label="false">
        <n-checkbox v-model:checked="free_room"
          >{{ t('plans.releaseIdle') }}<help-text>{{ t('plans.releaseIdleHelp') }}</help-text>
        </n-checkbox>
      </n-form-item>

      <n-form-item>
        <template #label>
          <span>{{ t('plans.dormIsolation') }}</span>
          <help-text>{{ t('plans.dormIsolationHelp') }}</help-text>
        </template>
        <div class="isolation-groups">
          <div v-for="(_group, index) in dorm_isolation" :key="index" class="isolation-group">
            <span class="group-label">{{
              t('plans.isolationGroupNumber', { number: index + 1 })
            }}</span>
            <slick-operator-select
              v-model="dorm_isolation[index]"
              :disabled="disabled"
              :select_placeholder="t('plans.chooseIsolationOperators')"
            />
            <n-button :disabled="disabled" @click="dorm_isolation.splice(index, 1)">{{
              t('plans.delete')
            }}</n-button>
          </div>
          <n-button :disabled="disabled" dashed @click="dorm_isolation.push([])">{{
            t('plans.addGroup')
          }}</n-button>
        </div>
      </n-form-item>

      <n-form-item v-if="free_room">
        <template #label>
          <span>{{ t('plans.mergeInterval') }}</span>
          <help-text>
            <div>{{ t('plans.decimalHelp') }}</div>
            <div>{{ t('plans.mergeIntervalHelp') }}</div>
          </help-text>
        </template>
        <mower-input-number v-model:value="merge_interval">
          <template #suffix>{{ t('plans.minutes') }}</template>
        </mower-input-number>
      </n-form-item>
      <n-form-item :show-label="false">
        <n-checkbox v-model:checked="group_rest_in_full_on_mood_gap"
          >{{ t('plans.waitForGroup') }}<help-text>{{ t('plans.waitForGroupHelp') }}</help-text>
        </n-checkbox>
      </n-form-item>
      <n-form-item v-if="group_rest_in_full_on_mood_gap">
        <template #label>
          <span class="label-with-help">
            <span>{{ t('plans.waitExcludedGroups') }}</span>
            <help-text>{{ t('plans.waitExcludedGroupsHelp') }}</help-text>
          </span>
        </template>
        <n-select
          v-model:value="group_mood_gap_exclusions"
          :options="excludedGroupOptions"
          multiple
          filterable
          tag
          clearable
          :placeholder="t('plans.noExcludedGroups')"
        />
      </n-form-item>
      <n-form-item v-if="group_rest_in_full_on_mood_gap" :label="t('plans.recoveryGapThreshold')">
        <mower-input-number
          v-model:value="group_mood_gap_threshold_minutes"
          :min="1"
          :max="1440"
          :step="5"
        >
          <template #suffix>{{ t('plans.minutes') }}</template>
        </mower-input-number>
      </n-form-item>
      <n-form-item v-if="group_rest_in_full_on_mood_gap">
        <template #label>
          <span class="label-with-help">
            <span>{{ t('plans.extraWaitLimit') }}</span>
            <help-text>{{ t('plans.extraWaitLimitHelp') }}</help-text>
          </span>
        </template>
        <mower-input-number
          v-model:value="group_mood_gap_max_extra_wait_hours"
          :min="0"
          :max="24"
          :step="0.5"
        >
          <template #suffix>{{ t('plans.hours') }}</template>
        </mower-input-number>
      </n-form-item>
      <n-form-item :show-label="false">
        <n-checkbox v-model:checked="fia_fool"
          >{{ t('plans.fiammettaGuard') }}<help-text>{{ t('plans.fiammettaGuardHelp') }}</help-text>
        </n-checkbox>
      </n-form-item>

      <n-form-item :show-label="false">
        <n-checkbox v-model:checked="assistant_follows_schedule"
          >{{ t('plans.trainingFollowsPlan')
          }}<help-text>{{ t('plans.trainingFollowsPlanHelp') }}</help-text>
        </n-checkbox>
      </n-form-item>
      <n-form-item>
        <template #label>
          <span>{{ t('plans.fiammettaThreshold') }}</span>
          <help-text>
            <div>{{ t('plans.fiammettaGuardThresholdHelp') }}</div>
            <div>{{ t('plans.fiammettaThresholdHelp') }}</div>
          </help-text>
        </template>
        <div class="threshold">
          <n-slider
            v-model:value="fia_threshold"
            :step="5"
            :min="50"
            :max="90"
            :format-tooltip="(v) => `${v}%`"
          />
          <mower-input-number v-model:value="fia_threshold" :step="5" :min="50" :max="90">
            <template #suffix>%</template>
          </mower-input-number>
        </div>
      </n-form-item>
      <n-form-item>
        <template #label>
          <span>{{ t('plans.rescueThreshold') }}</span>
          <help-text>
            <div>{{ t('plans.rescueThresholdHelp') }}</div>
          </help-text>
        </template>
        <div class="threshold">
          <n-slider
            v-model:value="rescue_threshold"
            :step="5"
            :min="0"
            :max="90"
            :format-tooltip="(v) => `${v}%`"
          />
          <mower-input-number v-model:value="rescue_threshold" :step="5" :min="0" :max="90">
            <template #suffix>%</template>
          </mower-input-number>
        </div>
      </n-form-item>
      <n-form-item>
        <template #label>
          <span>{{ t('plans.replacementMoraleMonitor') }}</span>
          <help-text>{{ t('plans.replacementMoraleMonitorHelp') }}</help-text>
        </template>
        <slick-operator-select v-model="favorite"></slick-operator-select>
      </n-form-item>
    </n-form>
  </div>
</template>

<style scoped>
.advanced-settings {
  max-width: 760px;
}
.advanced-settings[inert] {
  opacity: 0.6;
}
.label-with-help {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  white-space: nowrap;
}
.threshold {
  display: flex;
  align-items: center;
  gap: 14px;
  width: 100%;
}
.isolation-groups {
  display: flex;
  flex-direction: column;
  gap: 10px;
  width: 100%;
  min-width: 0;
}
.isolation-group {
  display: flex;
  align-items: center;
  gap: 8px;
}
.isolation-group > .width100 {
  flex: 1;
  min-width: 0;
}
.group-label {
  flex-shrink: 0;
}
@media (max-width: 600px) {
  .isolation-group {
    flex-wrap: wrap;
  }
  .isolation-group > .width100 {
    flex-basis: calc(100% - 70px);
  }
}
</style>
