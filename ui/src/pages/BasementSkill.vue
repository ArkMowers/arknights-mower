<template>
  <h3>只做了筛选名称，没做其他的效果显示，会有的.jpg</h3>
  <n-space>
    <div>名称搜索：</div>
    <n-input v-model:value="name_select" type="text" placeholder="名称搜索" />
  </n-space>

  <n-virtual-list
    ref="virtualListInst"
    :item-size="42"
    :items="filteredItems"
    item-resizable
    visible-items-tag="table"
    style="width: 90%; height: 70vh; border-style: none"
  >
    <template #default="{ item, index }">
      <thead>
        <tr v-if="index === 0">
          <th>干员名</th>
          <th>技能序号</th>
          <th>等级</th>
          <th>技能名称</th>
          <th>进驻场所</th>
          <th>描述</th>
        </tr>
        <CustomComponent :avatar="item.avatar" :span="item.span" :childSkill="item.childSkill" />
      </thead>
    </template>
  </n-virtual-list>
</template>

<script setup>
import skill from '@/pages/skill.json'
import CustomComponent from '@/components/buffer.vue'
import { ref, computed } from 'vue'
const skillData = ref(skill)
const skillData_length = skillData.value.length
const items = Array.from({ length: skillData_length }, (_, i) => {
  // 确保 skillData.value[i] 存在并且有 child_skill 属性

  const name = skillData.value[i].name
  const span = skillData.value[i].span
  const childSkill = skillData.value[i].child_skill
  return {
    key: `${i}`,
    value: i,
    avatar: name,
    span: span,
    childSkill: childSkill
  }
})
import { match } from 'pinyin-pro'

const name_select = ref('')
const buiding_select = ref('')
const filteredItems = computed(() => {
  const nameValue = name_select.value
  const buidingValue = buiding_select.value
  if (!nameValue && !buidingValue) {
    return items
  }
  return items.filter((item) => {
    const itemName = item['avatar']
    const itemRoomType = item['roomType']
    return (
      !nameValue ||
      (itemName && itemName.includes(nameValue)) ||
      match(itemName, nameValue, { precision: 'start' })
    )
  })
})
</script>
