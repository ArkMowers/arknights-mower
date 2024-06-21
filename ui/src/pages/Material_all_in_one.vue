<template>
  <n-data-table
    :columns="columns"
    :data="data"
    :pagination="pagination"
    :bordered="false"
    style="width: 40%"
  />
</template>

<script setup>
import { h } from 'vue'
import { NButton, useMessage } from 'naive-ui'
import event_data1 from '@/pages/stage_data/event_data.json'

const createColumns = () => [
  {
    title: 'Name',
    key: 'name'
  },
  {
    title: 'ID',
    key: 'id'
  },
  {
    title: '周一',
    key: '周一'
  },
  {
    title: '周二',
    key: '周二'
  },
  {
    title: '周三',
    key: '周三'
  },
  {
    title: '周四',
    key: '周四'
  },
  {
    title: '周五',
    key: '周五'
  },
  {
    title: '周六',
    key: '周六'
  },
  {
    title: '周日',
    key: '周日'
  }
]

const columns = createColumns()

const pagination = false

const data = event_data1
</script>
