<script setup>
import { storeToRefs } from 'pinia'
import { useConfigStore } from '@/stores/config'
import { usePlanStore } from '@/stores/plan'

const config_store = useConfigStore()
const { plan_file } = storeToRefs(config_store)
const { build_config } = config_store

const plan_store = usePlanStore()
const {
  ling_xi,
  max_resting_count,
  resting_priority,
  exhaust_require,
  rest_in_full,
  operators,
  workaholic
} = storeToRefs(plan_store)
const { load_plan } = plan_store

import { inject, ref } from 'vue'
const axios = inject('axios')

import { file_dialog } from '@/utils/dialog'

async function open_plan_file() {
  const file_path = await file_dialog()
  if (file_path) {
    plan_file.value = file_path
    await axios.post(`${import.meta.env.VITE_HTTP_URL}/conf`, build_config())
    await load_plan()
  }
}

import { toBlob } from 'html-to-image'
import { useMessage } from 'naive-ui'

const plan_editor = ref(null)

const generating_image = ref(false)

const message = useMessage()
const loading = ref(null)

async function screenshot() {
  generating_image.value = true
  loading.value = message.loading('正在生成图片……', { duration: 0 })
  if (
    /webkit/i.test(navigator.userAgent) &&
    /gecko/i.test(navigator.userAgent) &&
    /safari/i.test(navigator.userAgent)
  ) {
    await toBlob(plan_editor.value.outer)
  }
  const blob = await toBlob(plan_editor.value.outer, { pixelRatio: 3, backgroundColor: 'white' })
  loading.value.destroy()
  generating_image.value = false
  return blob
}

async function save() {
  const blob = await screenshot()
  const form_data = new FormData()
  form_data.append('img', blob)
  const resp = await axios.post(`${import.meta.env.VITE_HTTP_URL}/dialog/save-img`, form_data)
  message.info(resp.data)
}

async function copy() {
  const blob = await screenshot()
  const form_data = new FormData()
  form_data.append('img', blob)
  const resp = await axios.post(`${import.meta.env.VITE_HTTP_URL}/copy-img`, form_data)
  message.info(resp.data)
}
</script>

<template>
  <div class="home-container external-container no-grow">
    <table>
      <tr>
        <td>排班表：</td>
        <td>
          <n-input v-model:value="plan_file"></n-input>
        </td>
        <td>
          <n-button @click="open_plan_file">...</n-button>
        </td>
        <td>
          <div v-if="generating_image">正在生成图片……</div>
          <template v-else>
            <n-button @click="copy">复制图片</n-button>
            <n-button @click="save">保存图片</n-button>
          </template>
        </td>
      </tr>
    </table>
  </div>
  <plan-editor ref="plan_editor" />
  <div class="home-container external-container no-grow">
    <n-divider />
  </div>
  <div class="home-container external-container no-grow">
    <table>
      <tr>
        <td>
          令夕模式（令夕上班时起作用）<help-text>
            <div>启动Mower前需要手动对齐心情</div>
            <div>感知：夕心情-令心情=12</div>
            <div>烟火：令心情-夕心情=12</div>
            <div>均衡：夕令心情一样</div>
          </help-text>
        </td>
        <td colspan="3">
          <n-radio-group v-model:value="ling_xi">
            <n-space>
              <n-radio :value="'1'">感知信息</n-radio>
              <n-radio :value="'2'">人间烟火</n-radio>
              <n-radio :value="'3'">均衡模式</n-radio>
            </n-space>
          </n-radio-group>
        </td>
      </tr>
      <tr>
        <td>
          最大组人数<help-text> <div>请查阅文档</div></help-text>
        </td>
        <td>
          <n-input v-model:value="max_resting_count"></n-input>
        </td>
      </tr>
      <tr>
        <td>
          需要回满心情的干员<help-text> <div>请查阅文档</div> </help-text>
        </td>
        <td colspan="3">
          <n-select multiple filterable tag :options="operators" v-model:value="rest_in_full" />
        </td>
      </tr>
      <tr>
        <td>
          需要用尽心情的干员<help-text> <div>仅推荐写入具有暖机技能的干员</div></help-text>
        </td>
        <td colspan="3">
          <n-select multiple filterable tag :options="operators" v-model:value="exhaust_require" />
        </td>
      </tr>
      <tr>
        <td>
          0心情工作的干员<help-text> <div>心情涣散状态任能触发技能的干员</div></help-text>
        </td>
        <td colspan="3">
          <n-select multiple filterable tag :options="operators" v-model:value="workaholic" />
        </td>
      </tr>
      <tr>
        <td>
          宿舍低优先级干员<help-text> <div>请查阅文档</div></help-text>
        </td>
        <td colspan="3">
          <n-select multiple filterable tag :options="operators" v-model:value="resting_priority" />
        </td>
      </tr>
    </table>
  </div>
</template>

<style scoped lang="scss">
.no-grow {
  flex-grow: 0;
  width: 900px;
}
</style>
