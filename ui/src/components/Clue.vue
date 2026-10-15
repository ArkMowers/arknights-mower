<script setup>
import { useConfigStore } from '@/stores/config'
import { usePlanStore } from '@/stores/plan'
import { storeToRefs } from 'pinia'

const config_store = useConfigStore()
const {
  shop_list,
  maa_mall_buy,
  maa_mall_blacklist,
  maa_mall_ignore_blacklist_when_full,
  maa_mall_only_buy_discount,
  maa_mall_reserve_max_credit,
  maa_mall_enable,
  maa_mall_mode,
  clue_credit_on_demand,
  credit_shop_by_value,
  credit_shop_value_threshold,
  maa_credit_fight,
  credit_fight,
  visit_friend_enable,
  visit_friend_mode
} = storeToRefs(config_store)

const plan_store = usePlanStore()
const { operators } = storeToRefs(plan_store)

import { computed, h, inject, ref } from 'vue'

const mobile = inject('mobile')
const mower_visit_enabled = computed(
  () => visit_friend_enable.value && visit_friend_mode.value === 'mower'
)
const value_shopping_enabled = computed(
  () =>
    credit_shop_by_value.value &&
    maa_mall_enable.value &&
    maa_mall_mode.value === 'mower' &&
    mower_visit_enabled.value
)

function update_value_threshold(value) {
  if (Number.isFinite(value) && value >= 0) {
    credit_shop_value_threshold.value = value
  }
}

import { NAvatar, NTag } from 'naive-ui'

function render_tag({ option, handleClose }) {
  return h(
    NTag,
    {
      type: option.type,
      closable: true,
      onMousedown: (e) => {
        e.preventDefault()
      },
      onClose: (e) => {
        e.stopPropagation()
        handleClose()
      }
    },
    { default: () => option.label, avatar: () => h(NAvatar, { src: `/shop/${option.label}.png` }) }
  )
}

function render_label(option) {
  return h(
    'div',
    { style: { display: 'flex', 'align-items': 'center', gap: '6px', padding: '2px 0' } },
    [h(NAvatar, { src: `/shop/${option.label}.png` }), option.label]
  )
}

import { pinyin_match } from '@/utils/common'
import { render_op_option, render_op_label } from '@/utils/op_select'

const deploy_directions = [
  { label: '向上', value: 'Up' },
  { label: '向下', value: 'Down' },
  { label: '向左', value: 'Left' },
  { label: '向右', value: 'Right' }
]

const squads = [
  { label: '第一编队', value: 1 },
  { label: '第二编队', value: 2 },
  { label: '第三编队', value: 3 },
  { label: '第四编队', value: 4 }
]

const show_map = ref(false)
</script>

<template>
  <n-card title="获取信用及购物">
    开趴相关已移至 mower设置-基建设置 当中
    <n-form :label-placement="mobile ? 'top' : 'left'" :show-feedback="false" class="rogue">
      <n-form-item :show-label="false">
        <n-checkbox v-model:checked="maa_credit_fight">
          <div class="item">信用作战</div>
        </n-checkbox>
        <help-text>
          <div>借助战打OF-1</div>
          <div>使用指定编队</div>
        </help-text>
      </n-form-item>
      <n-form-item label="编队">
        <n-select :options="squads" v-model:value="credit_fight.squad" />
      </n-form-item>
      <n-form-item :show-label="false">
        <n-checkbox v-model:checked="visit_friend_enable">
          <div class="item">访问好友</div>
        </n-checkbox>
      </n-form-item>
      <n-form-item v-if="visit_friend_enable" label="处理方式">
        <n-radio-group v-model:value="visit_friend_mode">
          <n-space>
            <n-radio value="maa">MAA</n-radio>
            <n-radio value="mower">Mower</n-radio>
          </n-space>
        </n-radio-group>
        <help-text>
          <div>MAA：在执行日常任务时由 MAA 进入好友列表拜访并收取信用。</div>
          <div>Mower：在轮询基建调度之余由 Mower 原生进入好友列表拜访并收取信用。</div>
        </help-text>
      </n-form-item>
      <!--<n-form-item label="干员">
        <n-select
          filterable
          :options="operators"
          v-model:value="credit_fight.operator"
          :filter="(p, o) => pinyin_match(o.label, p)"
          :render-label="render_op_label"
          :render-option="render_op_option"
        />
      </n-form-item>
      <n-form-item label="部署">
        <div style="width: 40px; text-align: right">X</div>
        <mower-input-number style="margin: 0 8px" v-model:value="credit_fight.x" :show-button="false" />
        <div style="width: 40px; text-align: right">Y</div>
        <mower-input-number style="margin: 0 8px" v-model:value="credit_fight.y" :show-button="false" />
        <n-select
          style="width: 250px; margin-right: 8px"
          :options="deploy_directions"
          v-model:value="credit_fight.direction"
        />
        <n-button @click="show_map = !show_map">{{ show_map ? '隐藏' : '显示' }}OF-1地图</n-button>
      </n-form-item>
      <n-form-item :show-label="false" v-if="show_map">
        <n-image src="/map-OF-1.webp" width="100%" />
      </n-form-item>-->
    </n-form>
    <n-divider />
    <n-checkbox v-model:checked="maa_mall_enable" class="maa-shop">
      <div class="item">信用商店购物</div>
    </n-checkbox>
    <help-text>
      <span>性价比参考：</span>
      <n-button
        text
        tag="a"
        href="https://github.com/Bidgecfah/Rhodes-Island-Bureau-of-Price"
        target="_blank"
        type="primary"
      >
        罗德岛物价局
      </n-button>
      <p>注意：跑单时赤金与作战记录均大幅升值</p>
    </help-text>
    <n-form
      v-if="maa_mall_enable"
      :label-placement="mobile ? 'top' : 'left'"
      :show-feedback="false"
      label-width="72"
      label-align="left"
    >
      <n-form-item label="处理方式">
        <n-radio-group v-model:value="maa_mall_mode">
          <n-space>
            <n-radio value="maa">MAA</n-radio>
            <n-radio value="mower">Mower</n-radio>
          </n-space>
        </n-radio-group>
        <help-text>
          <div>MAA：在执行日常任务时由 MAA 进入采购中心进行信用收取和购物。</div>
          <div>Mower：在会客室线索流程处理完成后由 Mower 原生进入信用商店进行收取和购物。</div>
        </help-text>
      </n-form-item>
      <n-form-item label="购物设置" v-if="maa_mall_mode === 'mower'">
        <n-space align="center" :size="[24, 12]">
          <n-space align="center" :size="0">
            <n-tooltip :disabled="mower_visit_enabled">
              <template #trigger>
                <span style="display: inline-block">
                  <n-checkbox
                    v-model:checked="clue_credit_on_demand"
                    :disabled="!mower_visit_enabled"
                  >
                    按需领取信用
                  </n-checkbox>
                </span>
              </template>
              需要开启 Mower 访问好友
            </n-tooltip>
            <help-text>
              <div>默认关闭，仅在 Mower 访友和 Mower 购物均启用时生效。</div>
              <div>
                访友保持原调度。当天尝试过访友（成功或失败均可）后，线索流程才进入商店；
                访友后不会立即购物。访友尝试记录随运行存档保存。
              </div>
              <div>买不起非黑名单商品时，先领取上周结算，仍缺信用才领取本周部分。</div>
              <div>
                同时开启按性价比购物时，缺口只计算剩余优先商品和原始性价比高于阈值的非黑名单商品。
                因溢出抵扣才达标的商品不计入缺口。
              </div>
              <div>
                若本日交流的 210 信用足以补齐剩余商品缺口，则暂缓领取；交流须在下次刷新前的 03:45
                之前结束。
              </div>
              <div>周日 04:00 至周一 04:00，线索流程优先领取即将过期的上周结算。</div>
              <div>
                每日 03:45 至 04:00 不开始新的线索流程：交流领取和手动线索任务延后，定期整理跳过。
                已开始的流程继续执行。此时才启动程序，不保证领取到刷新前即将过期的信用。
              </div>
              <div>
                关闭此功能或改用其他处理方式时，信息板恢复原有领取流程；购物仍按所选方式执行。
              </div>
            </help-text>
          </n-space>
          <n-tooltip :disabled="mower_visit_enabled">
            <template #trigger>
              <span style="display: inline-block">
                <n-checkbox v-model:checked="credit_shop_by_value" :disabled="!mower_visit_enabled">
                  按性价比购物
                </n-checkbox>
              </span>
            </template>
            需要开启 Mower 访问好友
          </n-tooltip>
          <n-space align="center" :size="8">
            <span>阈值</span>
            <mower-input-number
              :value="credit_shop_value_threshold"
              @update:value="update_value_threshold"
              :disabled="!value_shopping_enabled"
              :min="0"
              :step="0.001"
              :precision="3"
              :show-button="false"
              :input-props="{ 'aria-label': '购物性价比阈值' }"
              style="width: 120px"
            />
            <span>理智/信用</span>
            <help-text>
              <div>默认阈值为二电的 0.045。</div>
              <div>参考阈值：二电带线索号 0.043、三电 0.036、三电带线索号 0.032。</div>
              <div>
                不建议设置过多优先购买或黑名单商品。优先购买仅推荐设置招聘许可，黑名单仅推荐设置理智价值为
                0 的物品。
              </div>
              <div>若你对物品的估值与当前价值表不同，请自行调整材料价值表和购物阈值。</div>
              <div>优先商品按实际售价从低到高购买；未买完前不购买其他商品。</div>
              <div>
                普通商品排除黑名单后，按整份理智价值与售价之比排序；高于阈值才购买，首件买不起即停止。
                理智价值使用当前保存的材料价值表。
              </div>
              <div>
                原始性价比达标的商品买完后，若信用超过
                300，再以售价扣除溢出信用后的有效成本重新排序。
                实际购买仍支付全价，每买一件重新计算。
              </div>
              <div>
                开启按需领取信用后，按上述目标商品的总缺口判断是否等待交流收入或领取信用板；
                关闭时只使用商店实际余额。优先购买和黑名单仍可编辑。
              </div>
            </help-text>
          </n-space>
        </n-space>
      </n-form-item>
      <n-form-item label="购物设置" v-if="maa_mall_mode === 'maa'">
        <n-space :size="24">
          <n-checkbox v-model:checked="maa_mall_only_buy_discount">只购买折扣物品</n-checkbox>
          <n-checkbox v-model:checked="maa_mall_reserve_max_credit">
            保留最大信用点（低于 300 停止购买）
          </n-checkbox>
        </n-space>
        <help-text>
          <div>两个设置均仅作用于第二轮购买。</div>
        </help-text>
      </n-form-item>
      <n-form-item label="信用溢出">
        <n-radio-group
          v-model:value="maa_mall_ignore_blacklist_when_full"
          :disabled="value_shopping_enabled"
        >
          <n-space>
            <n-radio :value="false">停止购买</n-radio>
            <n-radio :value="true">无视黑名单继续购买，直至不再溢出</n-radio>
          </n-space>
        </n-radio-group>
        <help-text v-if="value_shopping_enabled">
          <div>开启按性价比购物时，此处不可设置；关闭后可继续使用原设置。</div>
        </help-text>
      </n-form-item>
      <n-form-item label="优先购买">
        <n-select
          multiple
          filterable
          tag
          :options="shop_list"
          v-model:value="maa_mall_buy"
          :render-tag="render_tag"
          :render-label="render_label"
        />
      </n-form-item>
      <n-form-item label="黑名单">
        <n-select
          multiple
          filterable
          tag
          :options="shop_list"
          v-model:value="maa_mall_blacklist"
          :render-tag="render_tag"
          :render-label="render_label"
        />
      </n-form-item>
    </n-form>
  </n-card>
</template>

<style scoped lang="scss">
p {
  margin: 2px 0;
}

h4 {
  margin: 12px 0 8px 0;
}

table {
  width: 100%;
}

td {
  &:nth-child(1) {
    width: 80px;
  }
}

.ignore-blacklist {
  margin-bottom: 10px;
  display: flex;
  gap: 12px;
}

.h4 {
  font-size: 16px;
  font-weight: 500;
}

.maa-shop {
  margin: 8px 0;
}

.item {
  font-weight: 500;
  font-size: 16px;
}
</style>
