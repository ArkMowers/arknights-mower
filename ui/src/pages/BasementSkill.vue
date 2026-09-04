<template>
  <h3>做了筛选名称,筛选描述，没做其他的效果显示，会有的.jpg</h3>
  <n-space>
    <div>名称搜索：</div>
    <n-input v-model:value="name_select" type="text" placeholder="名称搜索" />
    <div>描述搜索（如用拼音，全拼）：</div>
    <n-input v-model:value="des_select" type="text" placeholder="名称搜索" />
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
          <th>技能枚举</th>
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
import CustomComponent from '@/components/buffer.vue'
import { ref, computed, onMounted } from 'vue'
import { useBasementSkill } from '@/stores/basementSkill'
import { match } from 'pinyin-pro'

const { skill, load } = useBasementSkill()
onMounted(load)

const skill_items = computed(() =>
  Array.from({ length: skill.value.length }, (_, i) => {
    const name = skill.value[i].name
    const span = skill.value[i].span
    const childSkill = skill.value[i].child_skill
    return {
      key: `${i}`,
      value: i,
      avatar: name,
      span: span,
      childSkill: childSkill
    }
  })
)

const name_select = ref('')
const buiding_select = ref('')
const des_select = ref('')
const filteredItems = computed(() => {
  const nameValue = name_select.value
  const buidingValue = buiding_select.value
  const desValue = des_select.value
  if (!nameValue && !buidingValue && !desValue) {
    return skill_items.value
  }
  return skill_items.value.filter((item) => {
    const itemName = item['avatar']
    const itemDesMatches = item.childSkill.some((skill) => {
      const itemDes = skill.des
      return (
        !desValue || itemDes.includes(desValue) || match(itemDes, desValue, { precision: 'every' })
      )
    })
    return (
      (!desValue || itemDesMatches) &&
      (!nameValue ||
        (itemName && itemName.includes(nameValue)) ||
        match(itemName, nameValue, { precision: 'start' }))
    )
  })
})
</script>
