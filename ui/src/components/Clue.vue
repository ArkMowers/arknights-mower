<script setup>
defineOptions({ name: 'CreditSettings' })
const props = defineProps({
  task: { type: String, default: 'all' },
  showEnable: { type: Boolean, default: true }
})
const emit = defineEmits(['configure-clue'])

import { useConfigStore } from '@/stores/config'
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

import { computed, h, inject } from 'vue'

const mobile = inject('mobile')
const title = computed(
  () =>
    ({ visit: '访问好友', 'credit-fight': '信用作战', shop: '信用商店' })[props.task] ||
    '获取信用及购物'
)
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

const squads = [
  { label: '第一编队', value: 1 },
  { label: '第二编队', value: 2 },
  { label: '第三编队', value: 3 },
  { label: '第四编队', value: 4 }
]
</script>

<template>
  <n-card :title="title">
    <p v-if="task === 'all'">
      线索收集与赠送在
      <n-button text type="primary" aria-label="配置线索搜集与交流" @click="emit('configure-clue')"
        >线索搜集与交流</n-button
      >
      中配置。
    </p>
    <n-form
      v-if="['all', 'credit-fight', 'visit'].includes(task)"
      :label-placement="mobile ? 'top' : 'left'"
      :show-feedback="false"
      class="rogue"
    >
      <template v-if="task === 'all' || task === 'visit'">
        <n-form-item v-if="showEnable" :show-label="false">
          <n-checkbox v-model:checked="visit_friend_enable">
            <div class="item">访问好友</div>
          </n-checkbox>
        </n-form-item>
        <n-form-item
          v-if="visit_friend_enable || !showEnable"
          label="处理方式"
          data-task-editor="visit"
        >
          <n-radio-group v-model:value="visit_friend_mode" aria-label="访友执行方式">
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
      </template>
      <template v-if="task === 'all' || task === 'credit-fight'">
        <n-form-item v-if="showEnable" :show-label="false">
          <n-checkbox v-model:checked="maa_credit_fight">
            <div class="item">信用作战</div>
          </n-checkbox>
        </n-form-item>
        <n-form-item data-task-editor="credit-fight">
          <template #label>
            <span>编队</span>
            <help-text label="信用作战编队说明">
              <div>借助战打OF-1</div>
              <div>使用指定编队</div>
            </help-text>
          </template>
          <n-select :options="squads" v-model:value="credit_fight.squad" />
        </n-form-item>
      </template>
    </n-form>
    <template v-if="task === 'all' || task === 'shop'">
      <n-divider v-if="task === 'all'" />
      <n-checkbox v-if="showEnable" v-model:checked="maa_mall_enable" class="maa-shop">
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
        v-if="maa_mall_enable || !showEnable"
        data-task-editor="shop"
        :label-placement="mobile ? 'top' : 'left'"
        :show-feedback="false"
        label-width="72"
        label-align="left"
      >
        <n-form-item label="处理方式">
          <n-radio-group v-model:value="maa_mall_mode" aria-label="购物执行方式">
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
                <div>需同时开启 Mower 访友和 Mower 购物。</div>
                <div>购物缺信用时再领取信息板，先领上周结算，仍不够再领本周信用。</div>
                <div>交流能在凌晨 03:45 前结束且收入够用时，会先等交流结束。</div>
                <div>周日会优先领取即将过期的上周结算。</div>
              </help-text>
            </n-space>
            <n-tooltip :disabled="mower_visit_enabled">
              <template #trigger>
                <span style="display: inline-block">
                  <n-checkbox
                    v-model:checked="credit_shop_by_value"
                    :disabled="!mower_visit_enabled"
                  >
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
                <div>先买优先商品，再从非黑名单商品中按性价比挑选。</div>
                <div>阈值越高，购买越挑剔；信用超过 300 时会计算等效性价比，减少溢出。</div>
                <div>参考阈值：二电 0.045（默认）、三电 0.036；带线索号分别为 0.043、0.032。</div>
                <div>优先购买建议只设招聘许可，黑名单建议只设理智价值为 0 的物品。</div>
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
            aria-label="优先购买"
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
    </template>
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
