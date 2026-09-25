<script setup>
import { useConfigStore } from '@/stores/config'
import { usePlanStore } from '@/stores/plan'
import { storeToRefs } from 'pinia'
import { inject } from 'vue'

const { disabled } = defineProps({ disabled: Boolean })
const freeRoomExclusions = defineModel('freeRoomExclusions', { type: Array })
const mobile = inject('mobile')
const configStore = useConfigStore()
const planStore = usePlanStore()
const {
  product_switching,
  drone_count_limit,
  drone_interval,
  reload_room,
  resting_threshold,
  version_update_resting_threshold,
  version_update_threshold_advance_hours,
  free_room,
  experimental_dorm_logic,
  dorm_order,
  merge_interval,
  fia_fool,
  refresh_backup_plan_after_mood,
  assistant_follows_schedule,
  fia_threshold,
  rescue_threshold,
  favorite
} = storeToRefs(configStore)
const { left_side_facility } = planStore
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
          <help-text
            >仅测试宿舍逻辑生效。0
            表示不限制；达到上限后等待当前一份自然完成，再确认切换。</help-text
          >
        </template>
        <mower-input-number
          v-model:value="product_switching.max_drones_per_switch"
          :disabled="!experimental_dorm_logic"
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
        <n-checkbox
          v-model:checked="product_switching.use_drones_when_leaving_orirock"
          :disabled="!experimental_dorm_logic"
        >
          切出源石碎片时使用无人机
          <help-text>
            仅测试宿舍逻辑生效。关闭后会等当前一份源石碎片自然完成，再切换至其他产物；若这次切换属于换班，将等切换完成后再换人。
          </help-text>
        </n-checkbox>
      </n-form-item>
      <n-form-item :show-label="false">
        <n-checkbox
          v-model:checked="product_switching.direct_when_drones_insufficient"
          :disabled="!experimental_dorm_logic"
        >
          允许无人机不足时直接切换产物
          <help-text>
            仅测试宿舍逻辑生效。开启时会取消制造站当前一份的进度；关闭时若换班需要切产物，将保留原班，并按制造进度和无人机恢复情况预计可切时间，届时复核后换班。
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
            测试宿舍逻辑开启时，当前一份完成后在制造计划取消确认页等待这段时间再确认；关闭时沿用原有等待流程。默认
            2 秒。
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
      <n-form-item label="搓玉补货房间">
        <n-select
          multiple
          filterable
          tag
          :options="left_side_facility"
          v-model:value="reload_room"
        />
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
        <n-checkbox v-model:checked="experimental_dorm_logic">
          测试宿舍逻辑
          <help-text>
            <template v-if="experimental_dorm_logic">
              已开启：按层级和心情分床，支持候补补床、临时 Free
              床位及新入住者单回竞争，日常保留床位。
            </template>
            <template v-else> 已关闭：使用原宿舍规则，休息优先名单按填写顺序分床。 </template>
            <p>两种模式均按「心情－个人下限」排序下班。</p>
          </help-text>
        </n-checkbox>
      </n-form-item>
      <n-form-item :show-label="false">
        <n-checkbox v-model:checked="free_room">
          宿舍不养闲人
          <help-text>
            <template v-if="experimental_dorm_logic">
              按宿舍优先级补床，支持待命候补和新入住者单回竞争；保留恢复中的主班、候补及固定宿舍岗位。
            </template>
            <template v-else>
              将未满心情的空闲干员补入可释放床位；加工干员优先级由自动加工设置控制。
            </template>
          </help-text>
        </n-checkbox>
      </n-form-item>
      <n-form-item v-if="free_room && experimental_dorm_logic">
        <template #label>
          <span>不养闲人排除干员</span>
          <help-text
            >开启不养闲人时，回满仍留宿，不让床，至上班离宿；个人及令夕上限优先。</help-text
          >
        </template>
        <slick-operator-select
          v-model="freeRoomExclusions"
          :disabled="disabled"
        ></slick-operator-select>
      </n-form-item>
      <n-form-item v-if="!experimental_dorm_logic">
        <template #label>
          <span>宿舍优先级排序</span>
          <help-text>稳定版全局设置，对主表及全部副表共同生效。</help-text>
        </template>
        <slick-dorm-select v-model="dorm_order"></slick-dorm-select>
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
        <n-checkbox v-model:checked="fia_fool">
          菲亚防呆
          <help-text
            >当菲亚替换干员心情均超过90%时菲亚等待半小时，不确定菲亚替换心情消耗请启用本选项</help-text
          >
        </n-checkbox>
      </n-form-item>
      <n-form-item v-if="!experimental_dorm_logic" :show-label="false">
        <n-checkbox v-model:checked="refresh_backup_plan_after_mood">
          读取心情后先刷新副表
          <help-text
            >默认开启。缓存清零重启时，会先读取心情并按载入心情数据模式自动重启，再触发副表和后续排班；若关闭，则沿用普通首次规划流程。</help-text
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
