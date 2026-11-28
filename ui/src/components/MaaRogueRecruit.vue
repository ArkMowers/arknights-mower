<script setup>
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
        placeholder="干员中文名"
        @update:value="update(index, 'name', $event)"
      />
      <n-checkbox :checked="item.use_support" @update:checked="update(index, 'use_support', $event)"
        >助战</n-checkbox
      >
      <n-button @click="model = model.filter((_, i) => i !== index)">移除</n-button>
    </n-flex>
    <n-button v-if="model.length < 3" @click="model = [...model, { name: '', use_support: false }]"
      >添加招募顺位</n-button
    >
    <n-text depth="3">最多三名，按顺序招募，职业不能相同。留空列表沿用原开局干员设置。</n-text>
  </n-flex>
</template>
