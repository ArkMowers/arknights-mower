<script setup>
import { storeToRefs } from 'pinia'
import { useConfigStore } from '@/stores/config'
import { usePlanStore } from '@/stores/plan'

const config_store = useConfigStore()
const {
  enable_party,
  shop_list,
  maa_mall_buy,
  maa_mall_blacklist,
  maa_mall_ignore_blacklist_when_full,
  maa_enable,
  maa_credit_fight,
  leifeng_mode,
  credit_fight
} = storeToRefs(config_store)

const plan_store = usePlanStore()
const { operators } = storeToRefs(plan_store)

import { h, inject } from 'vue'

const mobile = inject('mobile')

import { NTag, NAvatar } from 'naive-ui'

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
import { render_op_label } from '@/utils/op_select'

const deploy_directions = [
  { label: '向上', value: 'Up' },
  { label: '向下', value: 'Down' },
  { label: '向左', value: 'Left' },
  { label: '向右', value: 'Right' }
]
</script>

<template>
  <n-card title="线索收集与信用">
    <n-space vertical>
      <n-checkbox v-model:checked="enable_party">线索收集</n-checkbox>
      <n-checkbox v-model:checked="leifeng_mode">
        雷锋模式 <help-text>关闭则超过9个线索才送好友</help-text>
      </n-checkbox>
    </n-space>
    <n-divider />
    <n-form :label-placement="mobile ? 'top' : 'left'" :show-feedback="false" class="rogue">
      <n-form-item :show-label="false">
        <n-checkbox v-model:checked="maa_credit_fight">信用作战（OF-1）</n-checkbox>
      </n-form-item>
      <n-form-item label="干员">
        <n-select
          filterable
          :options="operators"
          v-model:value="credit_fight.operator"
          :filter="(p, o) => pinyin_match(o.label, p)"
          :render-label="render_op_label"
        />
      </n-form-item>
      <n-form-item label="部署">
        <div style="width: 40px; text-align: right">X</div>
        <n-input-number style="margin: 0 8px" v-model:value="credit_fight.x" :show-button="false" />
        <div style="width: 40px; text-align: right">Y</div>
        <n-input-number style="margin: 0 8px" v-model:value="credit_fight.y" :show-button="false" />
        <n-select
          style="width: 200px"
          :options="deploy_directions"
          v-model:value="credit_fight.direction"
        />
      </n-form-item>
    </n-form>
    <n-divider />
    <n-checkbox v-model:checked="maa_enable" class="maa-shop">信用商店购物</n-checkbox>
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
      :label-placement="mobile ? 'top' : 'left'"
      :show-feedback="false"
      label-width="72"
      label-align="left"
    >
      <n-form-item label="信用溢出">
        <n-radio-group v-model:value="maa_mall_ignore_blacklist_when_full">
          <n-space>
            <n-radio :value="false">停止购买</n-radio>
            <n-radio :value="true">无视黑名单继续购买，直至不再溢出</n-radio>
          </n-space>
        </n-radio-group>
      </n-form-item>
      <n-form-item label="优先购买">
        <n-radio-group v-model:value="maa_mall_ignore_blacklist_when_full">
          <n-select
            multiple
            filterable
            tag
            :options="shop_list"
            v-model:value="maa_mall_buy"
            :render-tag="render_tag"
            :render-label="render_label"
          />
        </n-radio-group>
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
.card-title {
  font-weight: 500;
  font-size: 18px;
}

p {
  margin: 2px 0;
}

h4 {
  margin: 12px 0 8px 0;
}

ol {
  margin: 0 0 8px 0;
  padding-left: 24px;
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
</style>
