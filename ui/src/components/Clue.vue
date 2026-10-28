<script setup>
import { i18n } from '@/i18n'
const { t } = i18n.global

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
    ({
      get visit() {
        return t('tasks.visitFriends')
      },
      get 'credit-fight'() {
        return t('tasks.creditFight')
      },
      get shop() {
        return t('tasks.creditStore')
      }
    })[props.task] || t('tasks.creditAndShopping')
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
  {
    get label() {
      return t('tasks.firstSquad')
    },
    value: 1
  },
  {
    get label() {
      return t('tasks.secondSquad')
    },
    value: 2
  },
  {
    get label() {
      return t('tasks.thirdSquad')
    },
    value: 3
  },
  {
    get label() {
      return t('tasks.fourthSquad')
    },
    value: 4
  }
]
</script>

<template>
  <n-card :title="title">
    <p v-if="task === 'all'">
      {{ t('tasks.clueSettingsBefore')
      }}<n-button
        text
        type="primary"
        :aria-label="t('tasks.configureClues')"
        @click="emit('configure-clue')"
        >{{ t('tasks.clueCollectionExchange') }}</n-button
      >{{ t('tasks.configuredIn') }}
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
            <div class="item">{{ t('tasks.visitFriends') }}</div>
          </n-checkbox>
        </n-form-item>
        <n-form-item
          v-if="visit_friend_enable || !showEnable"
          :label="t('tasks.handler')"
          data-task-editor="visit"
        >
          <n-radio-group v-model:value="visit_friend_mode" :aria-label="t('tasks.visitRunner')">
            <n-space>
              <n-radio value="maa">MAA</n-radio>
              <n-radio value="mower">Mower</n-radio>
            </n-space>
          </n-radio-group>
          <help-text>
            <div>{{ t('tasks.maaVisitHelp') }}</div>
            <div>{{ t('tasks.mowerVisitHelp') }}</div>
          </help-text>
        </n-form-item>
      </template>
      <template v-if="task === 'all' || task === 'credit-fight'">
        <n-form-item v-if="showEnable" :show-label="false">
          <n-checkbox v-model:checked="maa_credit_fight">
            <div class="item">{{ t('tasks.creditFight') }}</div>
          </n-checkbox>
        </n-form-item>
        <n-form-item data-task-editor="credit-fight">
          <template #label>
            <span>{{ t('tasks.squad') }}</span>
            <help-text :label="t('tasks.creditFightSquadHelp')">
              <div>{{ t('tasks.creditFightOF1') }}</div>
              <div>{{ t('tasks.useSelectedSquad') }}</div>
            </help-text>
          </template>
          <n-select :options="squads" v-model:value="credit_fight.squad" />
        </n-form-item>
      </template>
    </n-form>
    <template v-if="task === 'all' || task === 'shop'">
      <n-divider v-if="task === 'all'" />
      <n-checkbox v-if="showEnable" v-model:checked="maa_mall_enable" class="maa-shop">
        <div class="item">{{ t('tasks.creditStorePurchases') }}</div>
      </n-checkbox>
      <help-text>
        <span>{{ t('tasks.valueReference') }}</span>
        <n-button
          text
          tag="a"
          href="https://github.com/Bidgecfah/Rhodes-Island-Bureau-of-Price"
          target="_blank"
          type="primary"
          >{{ t('tasks.itemValueSite') }}</n-button
        >
        <p>{{ t('tasks.tradeOrderValueNotice') }}</p>
      </help-text>
      <n-form
        v-if="maa_mall_enable || !showEnable"
        data-task-editor="shop"
        :label-placement="mobile ? 'top' : 'left'"
        :show-feedback="false"
        label-width="72"
        label-align="left"
      >
        <n-form-item :label="t('tasks.handler')">
          <n-radio-group v-model:value="maa_mall_mode" :aria-label="t('tasks.shoppingRunner')">
            <n-space>
              <n-radio value="maa">MAA</n-radio>
              <n-radio value="mower">Mower</n-radio>
            </n-space>
          </n-radio-group>
          <help-text>
            <div>{{ t('tasks.maaShoppingHelp') }}</div>
            <div>{{ t('tasks.mowerShoppingHelp') }}</div>
          </help-text>
        </n-form-item>
        <n-form-item :label="t('tasks.shoppingSettings')" v-if="maa_mall_mode === 'mower'">
          <n-space align="center" :size="[24, 12]">
            <n-space align="center" :size="0">
              <n-tooltip :disabled="mower_visit_enabled">
                <template #trigger>
                  <span style="display: inline-block">
                    <n-checkbox
                      v-model:checked="clue_credit_on_demand"
                      :disabled="!mower_visit_enabled"
                      >{{ t('tasks.collectCreditOnDemand') }}</n-checkbox
                    >
                  </span> </template
                >{{ t('tasks.requiresMowerVisit') }}</n-tooltip
              >
              <help-text>
                <div>{{ t('tasks.requiresVisitAndShop') }}</div>
                <div>{{ t('tasks.creditOnDemandHelp') }}</div>
                <div>{{ t('tasks.creditWaitClueParty') }}</div>
                <div>{{ t('tasks.creditSundaySettlement') }}</div>
              </help-text>
            </n-space>
            <n-tooltip :disabled="mower_visit_enabled">
              <template #trigger>
                <span style="display: inline-block">
                  <n-checkbox
                    v-model:checked="credit_shop_by_value"
                    :disabled="!mower_visit_enabled"
                    >{{ t('tasks.valueShopping') }}</n-checkbox
                  >
                </span> </template
              >{{ t('tasks.requiresMowerVisit') }}</n-tooltip
            >
            <n-space align="center" :size="8">
              <span>{{ t('tasks.threshold') }}</span>
              <mower-input-number
                :value="credit_shop_value_threshold"
                @update:value="update_value_threshold"
                :disabled="!value_shopping_enabled"
                :min="0"
                :step="0.001"
                :precision="3"
                :show-button="false"
                :input-props="{ 'aria-label': t('tasks.shoppingValueThreshold') }"
                style="width: 120px"
              />
              <span>{{ t('tasks.sanityPerCredit') }}</span>
              <help-text>
                <div>{{ t('tasks.shoppingPriorityHelp') }}</div>
                <div>{{ t('tasks.shoppingThresholdHelp') }}</div>
                <div>{{ t('tasks.shoppingThresholdReference') }}</div>
                <div>{{ t('tasks.shoppingListAdvice') }}</div>
              </help-text>
            </n-space>
          </n-space>
        </n-form-item>
        <n-form-item :label="t('tasks.shoppingSettings')" v-if="maa_mall_mode === 'maa'">
          <n-space :size="24">
            <n-checkbox v-model:checked="maa_mall_only_buy_discount">{{
              t('tasks.discountOnly')
            }}</n-checkbox>
            <n-checkbox v-model:checked="maa_mall_reserve_max_credit">{{
              t('tasks.retainCredit300')
            }}</n-checkbox>
          </n-space>
          <help-text>
            <div>{{ t('tasks.secondRoundOnly') }}</div>
          </help-text>
        </n-form-item>
        <n-form-item :label="t('tasks.creditOverflow')">
          <n-radio-group
            v-model:value="maa_mall_ignore_blacklist_when_full"
            :disabled="value_shopping_enabled"
          >
            <n-space>
              <n-radio :value="false">{{ t('tasks.stopPurchases') }}</n-radio>
              <n-radio :value="true">{{ t('tasks.ignoreBlocklistOverflow') }}</n-radio>
            </n-space>
          </n-radio-group>
          <help-text v-if="value_shopping_enabled">
            <div>{{ t('tasks.valueShoppingOverrides') }}</div>
          </help-text>
        </n-form-item>
        <n-form-item :label="t('tasks.priorityPurchases')">
          <n-select
            multiple
            filterable
            tag
            :options="shop_list"
            v-model:value="maa_mall_buy"
            :aria-label="t('tasks.priorityPurchases')"
            :render-tag="render_tag"
            :render-label="render_label"
          />
        </n-form-item>
        <n-form-item :label="t('tasks.blocklist')">
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
