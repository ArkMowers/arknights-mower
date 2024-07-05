<script setup>
import { useConfigStore } from '@/stores/config'
import { usePlanStore } from '@/stores/plan'
import { storeToRefs } from 'pinia'

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

import { h, inject, ref } from 'vue'

const mobile = inject('mobile')

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
import { render_op_label } from '@/utils/op_select'

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
  <n-card title="线索收集与信用">
    <n-flex>
      <n-checkbox v-model:checked="enable_party"><div class="item">线索收集</div></n-checkbox>
      <n-checkbox v-model:checked="leifeng_mode">
        雷锋模式
        <help-text>
          <div>开启时，向好友赠送多余的线索；</div>
          <div>关闭则超过9个线索才送好友。</div>
        </help-text>
      </n-checkbox>
    </n-flex>
    <n-divider />
    <n-form :label-placement="mobile ? 'top' : 'left'" :show-feedback="false" class="rogue">
      <n-form-item :show-label="false">
        <n-checkbox v-model:checked="maa_credit_fight">
          <div class="item">信用作战</div>
        </n-checkbox>
        <help-text>
          <div>借助战打OF-1</div>
          <div>使用指定编队中的指定干员</div>
        </help-text>
      </n-form-item>
      <n-form-item label="编队">
        <n-select :options="squads" v-model:value="credit_fight.squad" />
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
          style="width: 250px; margin-right: 8px"
          :options="deploy_directions"
          v-model:value="credit_fight.direction"
        />
        <n-button @click="show_map = !show_map">{{ show_map ? '隐藏' : '显示' }}OF-1地图</n-button>
      </n-form-item>
      <n-form-item :show-label="false" v-if="show_map">
        <n-image src="/map-OF-1.webp" width="100%" />
      </n-form-item>
    </n-form>
    <n-divider />
    <n-checkbox v-model:checked="maa_enable" class="maa-shop">
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

.item {
  font-weight: 500;
  font-size: 16px;
}
</style>
