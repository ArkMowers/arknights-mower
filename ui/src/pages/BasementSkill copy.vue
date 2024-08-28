<template>
  <n-space>
    <div>名称搜索：</div>
    <n-input v-model:value="name_select" type="text" placeholder="名称搜索" />
    <div>驻站搜索：</div>
    <n-input v-model:value="buiding_select" type="text" placeholder="驻站搜索" />
  </n-space>
  <n-data-table
    size="small"
    :columns="createColumns"
    :data="filteredItems"
    style="width: 95%"
    max-height="80vh"
  />
</template>

<script setup>
import skillData from '@/pages/skill.json'
import CustomComponent from '@/components/buffer.vue'
import { ref, computed } from 'vue'
import { NAvatar, NButton, NTag } from 'naive-ui'
import { match } from 'pinyin-pro'

const name_select = ref('')
const buiding_select = ref('')
const filteredItems = computed(() => {
  const nameValue = name_select.value
  const buidingValue = buiding_select.value

  if (!nameValue && !buidingValue) {
    // 如果输入值都为空，则直接返回原始数据
    return skillData
  }

  return skillData.filter((item) => {
    // 缓存重复计算
    const itemName = item['name']
    const itemRoomType = item['roomType']

    return (
      (!nameValue ||
        (itemName && itemName.includes(nameValue)) ||
        match(itemName, nameValue, { precision: 'start' })) &&
      (!buidingValue ||
        (itemRoomType && itemRoomType.includes(buidingValue)) ||
        match(itemRoomType, buidingValue, { precision: 'start' }))
    )
  })
})

const 计算合并 = (key, additionalKey) => {
  return (rowData, rowIndex) => {
    const currentValue = rowData[key]
    const currentAdditionalValue = rowData[additionalKey]
    let span = 1
    if (
      rowIndex === 0 ||
      filteredItems.value[rowIndex - 1][key] !== currentValue ||
      filteredItems.value[rowIndex - 1][additionalKey] !== currentAdditionalValue
    ) {
      for (let i = rowIndex + 1; i < filteredItems.value.length; i++) {
        if (
          filteredItems.value[i][key] === currentValue &&
          filteredItems.value[i][additionalKey] === currentAdditionalValue
        ) {
          span++
        } else {
          break
        }
      }
    } else {
      return 0
    }
    return span
  }
}

const createColumns = [
  {
    title: '干员名称',
    key: 'name',
    minWidth: 157,
    align: 'left',
    rowSpan: 计算合并('name_key', 'name'),
    render(row) {
      return h(
        'div',
        {
          style: {
            display: 'flex',
            alignItems: 'center'
          }
        },
        [
          h(NAvatar, { round: true, src: `avatar/${row.name}.webp`, lazy: true }),
          h(
            NButton,
            {
              text: true,
              tag: 'a',
              href: `https://prts.wiki/w/${row.name}`,
              target: '_blank',
              style: { marginLeft: '8px' }
            },
            {
              default: () => row.name // 使用函数插槽
            }
          )
        ]
      )
    }
  },
  {
    title: '技能序号',
    key: 'skill_key',
    align: 'center',
    rowSpan: 计算合并('name_key', 'skill_key')
  },
  {
    title: '精英化 等级',
    key: 'phase_level',
    minWidth: 100,
    align: 'center'
  },

  {
    title: '技能',
    key: 'skill',
    minWidth: 100,
    align: 'center',
    render(row) {
      return h(
        NTag,
        {
          type: 'info',
          bordered: false,
          color: { color: row.buffColor, textColor: row.textColor }
        },
        {
          default: () => row.skillname,
          avatar: () =>
            h(NAvatar, {
              round: true,
              lazy: true,
              src: `building_skill/${row.skillIcon}.png`
            })
        }
      )
    }
  },

  {
    title: '进驻建筑',
    key: 'roomType',
    minWidth: 100,
    align: 'center',
    rowSpan: 计算合并('name_key', 'roomType'),
    render(row) {
      return h(
        NTag,
        {
          type: 'info',
          bordered: false,
          color: { color: row.buffColor, textColor: row.textColor }
        },
        {
          default: () => row.roomType
        }
      )
    }
  },
  {
    title: '技能描述',
    key: 'des',
    maxWidth: 500,
    align: 'left',
    render(row) {
      return h(CustomComponent, { dataId: row.des, buffer: row.buffer, buffer_des: row.buffer_des })
    }
  },

  {
    title: '技能类型',
    key: 'buffCategory',
    minWidth: 100,
    rowSpan: 计算合并('name_key', 'buffCategory'),
    render(row) {
      return h(
        NTag,
        {
          type: 'info',
          bordered: false
        },
        {
          default: () => row.buffCategory
        }
      )
    }
  }
]
</script>
<style scoped>
:deep(td) {
  border-top: 2px solid rgba(128, 128, 128, 0.1) !important;
  border-bottom: 2px solid rgba(128, 128, 128, 0.1) !important;
  padding: 0%;
}
</style>
