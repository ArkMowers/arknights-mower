<script setup>
import { storeToRefs } from 'pinia'
import { useConfigStore } from '@/stores/config'

const store = useConfigStore()
const {
  enable_party,
  shop_list,
  maa_mall_buy,
  maa_mall_blacklist,
  maa_mall_ignore_blacklist_when_full,
  maa_enable,
  maa_credit_fight
} = storeToRefs(store)

import { h } from 'vue'
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
</script>

<template>
  <n-card title="线索收集与信用">
    <template #header>
      <n-checkbox v-model:checked="enable_party">
        <div class="card-title">线索收集</div>
      </n-checkbox>
    </template>
    <n-h4>信用设置</n-h4>
    <n-space vertical>
      <n-checkbox v-model:checked="maa_enable">调用Maa进行信用商店购物</n-checkbox>
      <n-checkbox v-model:checked="maa_credit_fight">调用Maa进行信用作战</n-checkbox>
    </n-space>
    <n-h4>优先购买与黑名单</n-h4>
    <p>
      信用商店性价比可参考<n-button
        text
        tag="a"
        href="https://yituliu.site/"
        target="_blank"
        type="primary"
        >明日方舟一图流</n-button
      >。注意跑单时赤金与作战记录均大幅升值。
    </p>
    <table>
      <tr>
        <td>信用溢出：</td>
        <td>
          <n-radio-group v-model:value="maa_mall_ignore_blacklist_when_full">
            <n-space>
              <n-radio :value="false">停止购买</n-radio>
              <n-radio :value="true">无视黑名单继续购买，直至不再溢出</n-radio>
            </n-space>
          </n-radio-group>
        </td>
      </tr>
      <tr>
        <td>优先购买：</td>
        <td>
          <n-select
            multiple
            filterable
            tag
            :options="shop_list"
            v-model:value="maa_mall_buy"
            :render-tag="render_tag"
            :render-label="render_label"
          />
        </td>
      </tr>
      <tr>
        <td>黑名单：</td>
        <td>
          <n-select
            multiple
            filterable
            tag
            :options="shop_list"
            v-model:value="maa_mall_blacklist"
            :render-tag="render_tag"
            :render-label="render_label"
          />
        </td>
      </tr>
    </table>
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
</style>
