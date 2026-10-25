<script setup>
import { useConfigStore } from '@/stores/config'
import { storeToRefs } from 'pinia'
import { computed, inject } from 'vue'
import { usePlanStore } from '@/stores/plan'

const { disabled } = defineProps({ disabled: Boolean })
const mobile = inject('mobile')
const configStore = useConfigStore()
const planStore = inject('planStore', null) || usePlanStore()
const {
  product_switching,
  drone_count_limit,
  drone_interval,
  resting_threshold,
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
        <n-checkbox v-model:checked="test_mood_calculation">
          实时心情计算调控
          <help-text
            >默认关闭。开启后使用与收益演算相同的技能规则计算普通基建调度心情；启动时读取实际驻员和心情，后续在正常进房时校准。已同步
            BOX
            的干员按实际练度选择已解锁技能，缺少练度缓存时按满练技能计算。宿舍氛围按对应等级的满氛围计算。</help-text
          >
        </n-checkbox>
      </n-form-item>
      <n-form-item :show-label="false">
        <n-checkbox v-model:checked="product_switching.enable">
          自动切换产物与订单
          <help-text>
            开启后根据副表切换制造产物或贸易站订单类型，同时会读取设施类型、产物与订单类型，并显示对应的副表条件选项。
            开启后推荐提高无人机使用阈值。
          </help-text>
        </n-checkbox>
      </n-form-item>
      <template v-if="product_switching.enable">
        <n-form-item :show-label="false">
          <n-checkbox v-model:checked="product_switching.grandet_mode">
            葛朗台切产物
            <help-text>
              开启时按损耗容限节省无人机，并等待当前一份自然完成；关闭时直接使用足量无人机完成当前一份后切换。
            </help-text>
          </n-checkbox>
        </n-form-item>
        <n-form-item>
          <template #label>
            <span>切产物单次无人机上限</span>
            <help-text>0 表示不限制；达到上限后等待当前一份自然完成，再确认切换。</help-text>
          </template>
          <mower-input-number
            v-model:value="product_switching.max_drones_per_switch"
            :min="0"
            :max="200"
          >
            <template #suffix>架</template>
          </mower-input-number>
        </n-form-item>
        <n-form-item v-if="product_switching.grandet_mode" :show-label="false">
          <n-checkbox v-model:checked="product_switching.use_drones_when_leaving_orirock">
            切出源石碎片时使用无人机
            <help-text>
              关闭后会等当前一份源石碎片自然完成，再切换至其他产物；若这次切换属于换班，将等切换完成后再换人。
            </help-text>
          </n-checkbox>
        </n-form-item>
        <n-form-item :show-label="false">
          <n-checkbox v-model:checked="product_switching.direct_when_drones_insufficient">
            允许无人机不足时直接切换产物
            <help-text>
              开启时会取消制造站当前一份的进度；关闭时若换班需要切产物，将保留原班，并按制造进度和无人机恢复情况预计可切时间，届时复核后换班。
            </help-text>
          </n-checkbox>
        </n-form-item>
        <n-form-item v-if="product_switching.grandet_mode">
          <template #label>
            <span class="label-with-help">
              <span>葛朗台无人机损耗容限</span>
              <help-text>
                允许最后一架无人机浪费的加速时间。默认 30 秒，即当前一份余下至少 2 分 30
                秒时使用无人机完成，否则等待自然完成。
              </help-text>
            </span>
          </template>
          <mower-input-number
            v-model:value="product_switching.drone_loss_seconds"
            :min="0"
            :max="180"
          >
            <template #suffix>秒</template>
          </mower-input-number>
        </n-form-item>
        <n-form-item v-if="product_switching.grandet_mode">
          <template #label>
            <span class="label-with-help">
              <span>葛朗台切产物缓冲时间</span>
              <help-text>
                当前一份完成后，在制造计划取消确认页等待这段时间再确认。默认 2 秒。
              </help-text>
            </span>
          </template>
          <mower-input-number v-model:value="product_switching.waiting_seconds" :min="0" :max="60">
            <template #suffix>秒</template>
          </mower-input-number>
        </n-form-item>
      </template>
      <n-form-item>
        <template #label>
          <span>无人机使用阈值</span>
          <help-text>
            <div>普通制造站加速仅使用超过阈值的无人机，与跑单房间和自动切产物开关无关。</div>
            <div>如加速贸易，推荐大于 贸易站数*10 + 92</div>
            <div>如加速制造，推荐大于 贸易站数*10</div>
          </help-text>
        </template>
        <mower-input-number v-model:value="drone_count_limit" />
      </n-form-item>
      <n-form-item>
        <template #label>
          <span>无人机加速间隔</span>
          <help-text>
            <div>可填小数</div>
          </help-text>
        </template>
        <mower-input-number v-model:value="drone_interval">
          <template #suffix>小时</template>
        </mower-input-number>
      </n-form-item>
      <n-form-item>
        <template #label>
          <span>心情阈值</span>
          <help-text>
            <div>2电站推荐不低于65%</div>
            <div>3电站推荐不低于50%</div>
            <div>即将大更新推荐设置成80%</div>
          </help-text>
        </template>
        <div class="threshold">
          <n-slider
            v-model:value="resting_threshold"
            :step="5"
            :min="50"
            :max="80"
            :format-tooltip="(v) => `${v}%`"
          />
          <mower-input-number v-model:value="resting_threshold" :step="5" :min="50" :max="80">
            <template #suffix>%</template>
          </mower-input-number>
        </div>
      </n-form-item>
      <n-form-item>
        <template #label>
          <span>版本维护心情阈值</span>
          <help-text>
            <div>检测到需要更新客户端的大版本维护后，在维护前指定时长内临时使用此阈值</div>
            <div>只修改运行中的排班阈值，不覆盖上方的日常心情阈值</div>
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
          <span>版本维护阈值提前时长</span>
          <help-text>维护开始前多久切换到版本维护心情阈值</help-text>
        </template>
        <mower-input-number
          v-model:value="version_update_threshold_advance_hours"
          :step="1"
          :min="0"
          :max="168"
        >
          <template #suffix>小时</template>
        </mower-input-number>
      </n-form-item>

      <n-form-item :show-label="false">
        <n-checkbox v-model:checked="free_room">
          宿舍不养闲人
          <help-text>
            开启后创建满心情清退任务。关闭后仍安排恢复、补床和优先级接管；个人及令夕上限仍生效。
          </help-text>
        </n-checkbox>
      </n-form-item>

      <n-form-item>
        <template #label>
          <span>宿舍隔离</span>
          <help-text>
            可添加多个分组，每组人数不限。入住前优先分开同组干员，可跨宿舍交换普通位住客，必要时让新入住者由单回位改住普通位。
            满足隔离后仍按恢复优先级分配单回位，固定驻员、已有单回位住客及预约保持保护。无法分开时允许同宿，不阻止入宿，也不在入住完成后另行纠错。干员可以加入多个分组。
          </help-text>
        </template>
        <div class="isolation-groups">
          <div v-for="(_group, index) in dorm_isolation" :key="index" class="isolation-group">
            <span class="group-label">分组 {{ index + 1 }}</span>
            <slick-operator-select
              v-model="dorm_isolation[index]"
              :disabled="disabled"
              select_placeholder="选择需要分开住宿的干员"
            />
            <n-button :disabled="disabled" @click="dorm_isolation.splice(index, 1)">
              删除
            </n-button>
          </div>
          <n-button :disabled="disabled" dashed @click="dorm_isolation.push([])">
            添加分组
          </n-button>
        </div>
      </n-form-item>

      <n-form-item v-if="free_room">
        <template #label>
          <span>任务合并间隔</span>
          <help-text>
            <div>可填小数</div>
            <div>将不养闲人任务合并至下一个指定间隔内的任务</div>
          </help-text>
        </template>
        <mower-input-number v-model:value="merge_interval">
          <template #suffix>分钟</template>
        </mower-input-number>
      </n-form-item>
      <n-form-item :show-label="false">
        <n-checkbox v-model:checked="group_rest_in_full_on_mood_gap">
          组内心情差距过大时延后回班
          <help-text
            >默认开启。单绑、非候补工作主班的最晚与最早预计恢复完成时间之差超过下方阈值后，本轮等这些主班全部回满再回班。候补、替班和多绑主班不延长这项等待；明确设置“回满”的主班仍须全部回满。组内等待受下方额外等待上限限制，单独设置“回满”的主班不受该上限限制。</help-text
          >
        </n-checkbox>
      </n-form-item>
      <n-form-item v-if="group_rest_in_full_on_mood_gap">
        <template #label>
          <span class="label-with-help">
            <span>延后回班排除组</span>
            <help-text>
              可多选或输入组名，选项包含主表和副表的组。选中的组按普通规则回班，本轮已触发的组内恢复时间差等待也会取消；个人“回满”要求继续生效。此设置同时用于收益模拟。
            </help-text>
          </span>
        </template>
        <n-select
          v-model:value="group_mood_gap_exclusions"
          :options="excludedGroupOptions"
          multiple
          filterable
          tag
          clearable
          placeholder="不排除任何组"
        />
      </n-form-item>
      <n-form-item v-if="group_rest_in_full_on_mood_gap" label="组内恢复时间差阈值">
        <mower-input-number
          v-model:value="group_mood_gap_threshold_minutes"
          :min="1"
          :max="1440"
          :step="5"
        >
          <template #suffix>分钟</template>
        </mower-input-number>
      </n-form-item>
      <n-form-item v-if="group_rest_in_full_on_mood_gap">
        <template #label>
          <span class="label-with-help">
            <span>额外等待上限</span>
            <help-text>
              仅限制组内恢复时间差触发的等待。从本轮不延后时的预计回班时间起计算，重复规划和已回满成员离宿不重新计时。0
              表示不限时；单独设置“回满”的干员仍须回满。开启不养闲人后，先回满的成员可按原有清退规则离宿，其余成员继续休息。
            </help-text>
          </span>
        </template>
        <mower-input-number
          v-model:value="group_mood_gap_max_extra_wait_hours"
          :min="0"
          :max="24"
          :step="0.5"
        >
          <template #suffix>小时</template>
        </mower-input-number>
      </n-form-item>
      <n-form-item :show-label="false">
        <n-checkbox v-model:checked="fia_fool">
          菲亚防呆
          <help-text
            >当菲亚替换干员心情均超过90%时菲亚等待半小时，不确定菲亚替换心情消耗请启用本选项</help-text
          >
        </n-checkbox>
      </n-form-item>

      <n-form-item :show-label="false">
        <n-checkbox v-model:checked="assistant_follows_schedule">
          训练室协助位总是跟随排班
          <help-text
            >勾选后专精时的协助位不会使用设置的专精工具人，在基建排班时会根据排班表来替换训练室的协助位。</help-text
          >
        </n-checkbox>
      </n-form-item>
      <n-form-item>
        <template #label>
          <span>菲亚阈值</span>
          <help-text>
            <div>开启防呆设计时，菲亚只充心情在90%以下的干员，且此处设置无效</div>
            <div>
              不开启防呆设计时，菲亚优先充心情在该阈值以下的干员，若心情均高于该阈值则充心情最低者
            </div>
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
          <span>急救阈值</span>
          <help-text>
            <div>整体心情低于换班阈值乘急救阈值后，将忽视高优人数安排休息任务。</div>
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
          <span>替换组心情监视</span>
          <help-text>填入需要查看心情曲线的替换组干员</help-text>
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
