<script setup>
import { computed, inject, reactive, ref, watch, onBeforeUnmount } from 'vue'
import { incomeSettingsUrl } from '@/utils/incomeSettings'
import { createIncomeSanityValuation, sanityItems } from '@/riic/incomeSanity'

const props = defineProps({ valuation: Object, disabled: Boolean })
const emit = defineEmits(['saved', 'busy'])
const axios = inject('axios')
const material = ref('中级作战记录')
const materialValue = ref(null)
const busy = ref(false)
const error = ref('')
const saved = ref('')
const unitValues = reactive({
  fragment: null,
  recycle: null,
  recruitment_certificates: null,
  yellow_certificate: null,
  credit: null,
  credit_daily_limit: null
})
const unitFields = [
  { key: 'fragment', label: '源石碎片（理智/个）', placeholder: '留空时未估值' },
  { key: 'recycle', label: '回收站产出（理智/次）', placeholder: '留空时按材料概率表估值' },
  {
    key: 'recruitment_certificates',
    label: '刷新新增黄票期望（黄票/次）',
    placeholder: '默认参考值 0.2，可按潜能与招募策略修改'
  },
  {
    key: 'yellow_certificate',
    label: '黄票有效单价（理智/张）',
    placeholder: '默认约 66.279；溢出时可填 0'
  },
  {
    key: 'credit',
    label: '信用点有效单价（理智/点）',
    placeholder: '留空沿用购买门槛，溢出时可填 0'
  },
  {
    key: 'credit_daily_limit',
    label: '每日有效信用额度（信用/天）',
    placeholder: '扣除其他信用收入后填写；留空不设上限'
  }
]
const options = computed(() =>
  ['龙门币', ...Object.keys(props.valuation?.prices ?? {})].map((name) => ({
    label: name,
    value: name
  }))
)
const prices = computed(() => createIncomeSanityValuation(props.valuation).unitValues)
watch(
  [() => props.valuation, material],
  () => {
    materialValue.value =
      material.value === '龙门币'
        ? props.valuation?.lmd_sanity
        : props.valuation?.prices?.[material.value]
  },
  { immediate: true }
)
watch(
  () => props.valuation,
  (value) => {
    for (const key of Object.keys(unitValues))
      unitValues[key] = value?.income_unit_values?.[key] ?? null
  },
  { immediate: true }
)

let alive = true
let controller
onBeforeUnmount(() => {
  alive = false
  controller?.abort()
})

async function saveValues(kind) {
  if (busy.value || props.disabled || !props.valuation) return
  const patch =
    kind === 'material'
      ? material.value === '龙门币'
        ? { lmd_sanity: materialValue.value }
        : { prices: { [material.value]: materialValue.value } }
      : { income_unit_values: { ...unitValues } }
  busy.value = true
  emit('busy', true)
  error.value = ''
  saved.value = ''
  try {
    controller = new AbortController()
    const { data } = await axios.put(incomeSettingsUrl, patch, {
      timeout: 15000,
      signal: controller.signal
    })
    if (!alive) return
    emit('saved', data)
    saved.value = '理智价值已保存，后续演算使用新值。'
  } catch (reason) {
    if (!alive) return
    error.value = reason.response?.data?.error || '理智价值保存失败，请重试'
  } finally {
    busy.value = false
    if (alive) emit('busy', false)
  }
}
const display = (value) =>
  value === null
    ? '未估值'
    : Number(value.toFixed(6)).toLocaleString('zh-CN', { maximumFractionDigits: 6 })
</script>

<template>
  <div class="sanity-values">
    <p>
      理智算法仅用于排班的“计算收益”，不用于基建报表，使用以下单价乘以演算已有的净产出。修改材料价值也会影响共享此设置的回收站、养成统计与信用购物；已完成的收益记录保留原单价。
    </p>
    <div class="material-price">
      <label
        ><span>材料</span
        ><n-select
          v-model:value="material"
          :options="options"
          filterable
          :disabled="disabled || busy || !valuation"
      /></label>
      <label
        ><span>理智/单位</span
        ><n-input-number
          v-model:value="materialValue"
          :min="material === '龙门币' ? 0.000000001 : 0"
          :max="1000000"
          :show-button="false"
          :disabled="disabled || busy || !valuation"
      /></label>
      <n-button :disabled="disabled || busy || !valuation" @click="saveValues('material')"
        >保存材料价值</n-button
      >
    </div>
    <div class="unit-values">
      <label v-for="field in unitFields" :key="field.key">
        <span>{{ field.label }}</span>
        <n-input-number
          v-model:value="unitValues[field.key]"
          :min="0"
          :max="1000000"
          :show-button="false"
          clearable
          :placeholder="field.placeholder"
          :disabled="disabled || busy || !valuation"
        />
      </label>
    </div>
    <p>
      公招刷新收益 = 新增黄票期望 × 黄票有效单价。黄票默认按 258 张换 38 抽、每抽 600 合成玉、每源石
      180 合成玉或 135 理智折算；不计抽卡回流。黄票溢出时可将单价设为 0。
    </p>
    <p>
      刷新新增黄票默认参考值为 0.2：假设只刷新无保底标签、四星满潜，五星和六星分别按 5、10
      黄票估值；不是实测净收益或官方概率。
      <n-a href="https://www.bilibili.com/read/cv27513934" target="_blank" rel="noopener noreferrer"
        >参考推导</n-a
      >
      ·
      <n-a
        href="https://ark.yituliu.cn/survey/maarecruitdata"
        target="_blank"
        rel="noopener noreferrer"
        >一图流公招标签统计</n-a
      >
    </p>
    <p>
      会客室日均信用 = 自搜线索数 × 40（搜集 20、赠送 20）+ 连续交流
      210。假设自搜线索全部送出、好友持续补齐交流所需线索；未建会客室不计交流。
      信用默认沿用当前购买性价比门槛（{{ valuation?.credit_shop_value_threshold ?? '未读取' }}
      理智/信用），作为参考边际单价；它不是实测平均兑换收益，可自行修改或设为
      0。每日有效额度应扣除其他信用收入已覆盖的需求；超过额度的部分不计价值，留空表示不设上限。不模拟商店、折扣和实际交流完成时刻。
      <n-a href="https://prts.wiki/w/信用" target="_blank" rel="noopener noreferrer"
        >信用奖励来源</n-a
      >
    </p>
    <p>
      回收站默认使用当前材料价值与普通池、额外池的长期期望；只折算现有产出次数，不生成材料库存。以上留空项使用自动估值；没有自动估值的项目会在结果中标明。
    </p>
    <n-button :disabled="disabled || busy || !valuation" @click="saveValues('units')"
      >保存产出估值</n-button
    >
    <n-alert v-if="error" type="error">{{ error }}</n-alert>
    <n-text v-if="saved" type="success">{{ saved }}</n-text>
    <n-collapse>
      <n-collapse-item title="当前理智单价" name="unit-prices">
        <dl>
          <template v-for="item in sanityItems" :key="item.key"
            ><dt>{{ item.label }}（理智/{{ item.unit }}）</dt>
            <dd>{{ display(prices[item.key]) }}</dd></template
          >
        </dl>
      </n-collapse-item>
    </n-collapse>
  </div>
</template>

<style scoped>
.sanity-values {
  display: grid;
  gap: 14px;
  min-width: 0;
}
p {
  margin: 0;
  font-size: 13px;
  line-height: 1.7;
  opacity: 0.75;
}
.material-price,
.unit-values {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 12px;
  align-items: end;
}
.material-price > button {
  justify-self: start;
}
label {
  display: grid;
  gap: 6px;
  min-width: 0;
  font-size: 13px;
}
dl {
  display: grid;
  grid-template-columns: 1fr auto;
  gap: 8px;
  margin: 0;
  font-size: 13px;
}
dd {
  margin: 0;
  font-variant-numeric: tabular-nums;
}
@media (max-width: 600px) {
  .material-price,
  .unit-values {
    grid-template-columns: minmax(0, 1fr);
  }
}
</style>
