<script setup>
import { i18n } from '@/i18n'
import { render_op_option, render_op_label, filterOperatorOption } from '@/utils/op_select'
const { t } = i18n.global
const model = defineModel({ default: () => [] })
defineProps({ options: { type: Array, default: () => [] } })
function update(index, key, value) {
  model.value = model.value.map((item, i) => (i === index ? { ...item, [key]: value } : item))
}
</script>

<template>
  <n-flex vertical style="width: 100%">
    <n-flex v-for="(item, index) in model" :key="index" align="center" :wrap="false">
      <span>{{ index + 1 }}</span>
      <n-select
        :value="item.name"
        :options="options"
        filterable
        tag
        :placeholder="t('maaActivities.operatorChineseName')"
        :filter="filterOperatorOption"
        :render-label="render_op_label"
        :render-option="render_op_option"
        :consistent-menu-width="false"
        @update:value="update(index, 'name', $event)"
      />
      <n-checkbox
        :checked="item.use_support"
        @update:checked="update(index, 'use_support', $event)"
        >{{ t('maaActivities.support') }}</n-checkbox
      >
      <n-button @click="model = model.filter((_, i) => i !== index)">{{
        t('maaActivities.remove')
      }}</n-button>
    </n-flex>
    <n-button
      v-if="model.length < 3"
      @click="model = [...model, { name: '', use_support: false }]"
      >{{ t('maaActivities.addRecruitPriority') }}</n-button
    >
    <n-text depth="3">{{ t('maaActivities.recruitHelp') }}</n-text>
  </n-flex>
</template>
