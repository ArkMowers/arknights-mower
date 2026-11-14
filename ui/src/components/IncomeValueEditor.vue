<script setup>
import { computed, inject, reactive, ref, watch, onBeforeUnmount } from 'vue'
import { incomeSettingsUrl } from '@/utils/incomeSettings'
import { createIncomeSanityValuation, sanityItems } from '@/riic/incomeSanity'
import { potentialPresets, yellowValuePresets } from '@/riic/incomeCertificates'

const props = defineProps({ valuation: Object, recruitment: Array, disabled: Boolean })
const emit = defineEmits(['saved', 'busy'])
const axios = inject('axios')
const material = ref('中级作战记录')
const materialValue = ref(null)
const busy = ref(false)
const error = ref('')
const saved = ref('')
const options = reactive({ potential_preset: 'default', yellow_preset: 'vouchers' })
const unitValues = reactive({
  fragment: null,
  recycle: null,
  recruitment_certificates: null,
  yellow_certificate: null,
  green_certificate: null,
  credit: null,
  credit_daily_limit: null
})
const unitFields = [
  { key: 'fragment', label: '源石碎片（理智/个）', placeholder: '留空时未估值' },
  { key: 'recycle', label: '回收站产出（理智/次）', placeholder: '留空时按材料概率表估值' },
  {
    key: 'recruitment_certificates',
    label: '刷新新增黄票期望（黄票/次）',
    placeholder: '留空按潜能预设估算；填写则覆盖黄票期望'
  },
  {
    key: 'yellow_certificate',
    label: '黄票有效单价（理智/张）',
    placeholder: '留空按兑换预设估值；溢出时可填 0'
  },
  {
    key: 'green_certificate',
    label: '绿票有效单价（理智/张）',
    placeholder: '留空按 50 绿票换 30 合成玉；可填 0'
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
const materialOptions = computed(() =>
  ['龙门币', ...Object.keys(props.valuation?.prices ?? {})].map((name) => ({
    label: name,
    value: name
  }))
)
const preview = computed(() =>
  createIncomeSanityValuation(
    {
      ...props.valuation,
      income_unit_values: { ...unitValues },
      income_options: { ...options }
    },
    props.recruitment
  )
)
const prices = computed(() => preview.value.unitValues)
const certificates = computed(() => preview.value.certificateModel)
function selectPotentialPreset(value) {
  options.potential_preset = value
  unitValues.recruitment_certificates = null
}
function selectYellowPreset(value) {
  options.yellow_preset = value
  unitValues.yellow_certificate = null
}
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
    options.potential_preset = value?.income_options?.potential_preset ?? 'default'
    options.yellow_preset = value?.income_options?.yellow_preset ?? 'vouchers'
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
      : { income_unit_values: { ...unitValues }, income_options: { ...options } }
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
          :options="materialOptions"
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
      <label
        ><span>办公室潜能估值预设</span>
        <n-select
          :value="options.potential_preset"
          :options="potentialPresets"
          :disabled="disabled || busy || !valuation"
          @update:value="selectPotentialPreset"
        />
      </label>
      <label
        ><span>黄票兑换预设</span>
        <n-select
          :value="options.yellow_preset"
          :options="yellowValuePresets"
          :disabled="disabled || busy || !valuation"
          @update:value="selectYellowPreset"
        />
      </label>
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
      公招刷新收益 = 新增黄票期望 × 黄票单价 + 新增绿票期望 ×
      绿票单价。仅刷新无保底标签，以三星结果为对照；按公开标签统计近似，不是实测净增或官方概率，不计掉标签及无保底时的高星结果。
      <n-a
        href="https://ark.yituliu.cn/survey/maarecruitdata"
        target="_blank"
        rel="noopener noreferrer"
        >一图流标签统计</n-a
      >
    </p>
    <p>
      默认预设按三星 0 黄票/10 绿票、四星 1 黄票/30 绿票、五星 5 黄票、六星 10 黄票；满潜改为五星
      13、六星 25 黄票。
      森空岛预设按当前公招池内同星级干员等权估计，未拥有按首次入职，已拥有按潜能近似重复获取次数，并计可兑换的多余信物。潜能不能区分通用信物提升、未使用信物或中坚获取次数，因此只作近似；不模拟潜能随招募变化。
    </p>
    <n-alert v-if="!certificates.rewards" type="warning"
      >缺少可用的公招池潜能数据，当前预设无法完整估值。请同步森空岛后重新读取缓存，或选择其他预设。</n-alert
    >
    <p>
      抽卡券按 258 黄票换 38 抽；通用信物按一枚六星皇家信物 135 黄票或 720
      采购凭证折算，使用当前采购凭证材料单价，不按持有黄票超过 258 自动切换。 绿票按 50 张换 30
      合成玉，忽略前置兑换。合成玉直接使用当前材料表单价，不计算抽卡回流，也不模拟兑换库存。
      <n-a href="https://prts.wiki/w/采购中心/凭证交易所" target="_blank" rel="noopener noreferrer"
        >凭证兑换规则</n-a
      >
    </p>
    <p>
      估值预览（保存后生效）：每次刷新新增 {{ display(certificates.refreshYellow) }} 黄票、{{
        display(certificates.refreshGreen)
      }}
      绿票； 黄票 {{ display(certificates.yellow) }} 理智/张，绿票
      {{ display(certificates.green) }} 理智/张。
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
