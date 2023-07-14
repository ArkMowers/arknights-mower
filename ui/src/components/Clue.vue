<script setup>
import { storeToRefs } from 'pinia'
import { useConfigStore } from '@/stores/config'

const store = useConfigStore()
const { enable_party, shop_list, maa_mall_buy, maa_mall_blacklist } = storeToRefs(store)

import { ref } from 'vue'
const ignore_blacklist = ref('true')

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
  <n-card>
    <template #header>
      <n-checkbox v-model:checked="enable_party">
        <div class="card-title">线索收集</div>
      </n-checkbox>
    </template>
    <p>开启线索收集后，将调用Maa进行信用商店购物。</p>
    <n-h4>信用商店购物逻辑</n-h4>
    <ol>
      <li>首先购买“优先购买”物品；</li>
      <li>再购买“黑名单”以外的物品。</li>
    </ol>
    <n-h4>信用溢出时的购物设置</n-h4>
    <n-radio-group v-model:value="ignore_blacklist" class="ignore-blacklist">
      <n-radio value="false">停止购买</n-radio>
      <n-radio value="true">无视黑名单继续购买，直至不再溢出</n-radio>
    </n-radio-group>
    <n-h4>优先购买物品与黑名单物品</n-h4>
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
        <td>优先购买</td>
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
        <td>黑名单</td>
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
  margin: 0 0 8px 0;
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
    width: 60px;
  }
}

.ignore-blacklist {
  margin-bottom: 10px;
  display: flex;
  gap: 12px;
}
</style>
