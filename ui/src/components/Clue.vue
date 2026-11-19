<script setup>
import { publicAsset } from '@/utils/publicAsset'
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
  maa_mall_enable,
  credit_shop_value_threshold,
  maa_credit_fight,
  credit_fight,
  visit_friend_enable
} = storeToRefs(config_store)

import { computed, h, inject } from 'vue'

const mobile = inject('mobile')
const title = computed(
  () =>
    ({ visit: '访问好友', 'credit-fight': '信用作战', shop: '信用商店' })[props.task] ||
    '获取信用及购物'
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
    {
      default: () => option.label,
      avatar: () => h(NAvatar, { src: publicAsset(`/shop/${option.label}.png`) })
    }
  )
}

function render_label(option) {
  return h(
    'div',
    { style: { display: 'flex', 'align-items': 'center', gap: '6px', padding: '2px 0' } },
    [h(NAvatar, { src: publicAsset(`/shop/${option.label}.png`) }), option.label]
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
      线索搜集与赠送在
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
        <p v-if="visit_friend_enable || !showEnable" data-task-editor="visit">
          由 Mower 访问好友并收取信用。
        </p>
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
        label-width="96"
        label-align="left"
      >
        <n-form-item label="性价比阈值">
          <n-space align="center" :size="8">
            <mower-input-number
              :value="credit_shop_value_threshold"
              @update:value="update_value_threshold"
              :min="0"
              :step="0.001"
              :precision="3"
              :show-button="false"
              :input-props="{ 'aria-label': '购物性价比阈值' }"
              style="width: 120px"
            />
            <span>理智/信用</span>
            <help-text>
              <div>由 Mower 按性价比购物，关闭线索搜集不影响自动购物。</div>
              <div>先买优先商品，再从非黑名单商品中按性价比挑选。</div>
              <div>阈值越高，购买越挑剔；信用超过 300 时会计算等效性价比，减少溢出。</div>
              <div>参考阈值：二电 0.045（默认）、三电 0.036；带线索号分别为 0.043、0.032。</div>
              <div>优先购买建议只设招聘许可，黑名单建议只设理智价值为 0 的物品。</div>
              <div>
                同时开启领取信息板信用和访问好友时按需领取信用，购物缺信用时先领上周结算，仍不够再领本周信用。
              </div>
              <div>交流能在凌晨 03:45 前结束且收入够用时，会先等交流结束。</div>
              <div>开启线索搜集和领取信息板信用时，周日会优先领取即将过期的上周结算。</div>
            </help-text>
          </n-space>
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
