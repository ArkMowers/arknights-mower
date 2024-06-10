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
    :single-line="false"
    style="width: 95%"
    striped
  />
</template>

<script setup>
import skillData from '@/pages/skill.json'
import { ref } from 'vue'
import { NAvatar, NTag } from 'naive-ui'
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

  // 减少不必要的计算
  return skillData.filter((item) => {
    // 缓存重复计算
    const itemName = item['name']
    const itemRoomType = item['roomType']

    // 使用 || 运算符短路来避免不必要的函数调用
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

const 计算合并 = (key) => {
  return (rowData, rowIndex) => {
    const currentValue = rowData[key]
    let span = 1
    if (rowIndex === 0 || filteredItems.value[rowIndex - 1][key] !== currentValue) {
      for (let i = rowIndex + 1; i < filteredItems.value.length; i++) {
        if (filteredItems.value[i][key] === currentValue) {
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
    rowSpan: 计算合并('name'),
    render(row) {
      return h(
        'a',
        {
          href: `https://prts.wiki/w/${row.name}`,
          target: '_blank',
          style: {
            display: 'flex',
            alignItems: 'center',
            textDecoration: 'none', // 隐藏链接的下划线
            color: 'black' // 设置为透明
          }
        },
        [
          h(NAvatar, { round: true, src: `avatar/${row.name}.webp`, lazy: true }),
          h('span', { style: { marginLeft: '8px' } }, row.name)
        ]
      )
    }
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
    minWidth: 150,
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
      return h('span', {
        innerHTML: row.des
      })
    }
  },

  {
    title: '技能类型',
    key: 'buffCategory',
    minWidth: 100,
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
