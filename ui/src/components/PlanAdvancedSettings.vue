<script setup>
import { useConfigStore } from '@/stores/config'
import { storeToRefs } from 'pinia'
import { inject } from 'vue'

const { disabled } = defineProps({ disabled: Boolean })
const freeRoomExclusions = defineModel('freeRoomExclusions', { type: Array })
const mobile = inject('mobile')
const configStore = useConfigStore()
const {
  product_switching,
  drone_count_limit,
  drone_interval,
  resting_threshold,
  version_update_resting_threshold,
  version_update_threshold_advance_hours,
  free_room,
  merge_interval,
  group_rest_in_full_on_mood_gap,
  group_mood_gap_max_extra_wait_hours,
  fia_fool,
  assistant_follows_schedule,
  fia_threshold,
  rescue_threshold,
  favorite
} = storeToRefs(configStore)
</script>

<template>
  <div class="advanced-settings" :inert="disabled">
    <n-form
      :label-placement="mobile ? 'top' : 'left'"
      label-width="190"
      label-align="left"
      :show-feedback="false"
    >
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
      <n-form-item :show-label="false">
        <n-checkbox v-model:checked="product_switching.grandet_mode">
          葛朗台切产物
          <help-text>
            开启时按损耗容限节省无人机，并等待当前一份自然完成；关闭时直接使用足量无人机完成当前一份后切换。
          </help-text>
        </n-checkbox>
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
      <n-form-item>
        <template #label>
          <span>葛朗台无人机损耗容限</span>
          <help-text>
            允许最后一架无人机浪费的加速时间。默认 30 秒，即当前一份余下至少 2 分 30
            秒时使用无人机完成，否则等待自然完成。
          </help-text>
        </template>
        <mower-input-number
          v-model:value="product_switching.drone_loss_seconds"
          :disabled="!product_switching.grandet_mode"
          :min="0"
          :max="180"
        >
          <template #suffix>秒</template>
        </mower-input-number>
      </n-form-item>
      <n-form-item>
        <template #label>
          <span>葛朗台切产物缓冲时间</span>
          <help-text>
            当前一份完成后，在制造计划取消确认页等待这段时间再确认。默认 2 秒。
          </help-text>
        </template>
        <mower-input-number
          v-model:value="product_switching.waiting_seconds"
          :disabled="!product_switching.grandet_mode"
          :min="0"
          :max="60"
        >
          <template #suffix>秒</template>
        </mower-input-number>
      </n-form-item>
      <n-form-item>
        <template #label>
          <span>无人机使用阈值</span>
          <help-text>
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
          <span>宿舍保留干员</span>
          <help-text
            >名单内干员保留 Free
            宿舍床位，不因满心情而离宿，仍按正常回班及个人心情上限规则离宿。</help-text
          >
        </template>
        <slick-operator-select
          v-model="freeRoomExclusions"
          :disabled="disabled"
        ></slick-operator-select>
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
            >默认开启。组内高优先干员的预计心情恢复时间差超过上限时，延后整组回班；2 电站上限为 1.5
            小时，其他情况为 1
            小时。关闭后按组内最早恢复时间安排回班；单独设置“回满”的干员仍会回满。</help-text
          >
        </n-checkbox>
      </n-form-item>
      <n-form-item>
        <template #label>
          <span>组内心情差距额外等待上限</span>
          <help-text
            >仅对上方“组内心情差距过大时延后回班”生效。以不延后时的预计回班时间为起点；0
            表示不限时。单独设置“回满”的干员不受此限制。</help-text
          >
        </template>
        <mower-input-number
          v-model:value="group_mood_gap_max_extra_wait_hours"
          :disabled="!group_rest_in_full_on_mood_gap"
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
.threshold {
  display: flex;
  align-items: center;
  gap: 14px;
  width: 100%;
}
</style>
