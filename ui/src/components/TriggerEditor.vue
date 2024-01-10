<script setup>
const props = defineProps(['data'])
const emit = defineEmits(['update'])
import { ref, watch } from 'vue'
const left = ref(props.data.left)
const operator = ref(props.data.operator)
const right = ref(props.data.right)

function generate() {
  const result = { left: left.value, operator: operator.value, right: right.value }
  emit('update', result)
}

watch([left, operator, right], () => {
  generate()
})

const le_options = [
  { label: '表达式', value: 'expression' },
  { label: '值', value: 'string' }
]
</script>

<template>
  <n-table size="small" :single-line="false">
    <tr>
      <th>
        <div class="label">
          左
          <n-select
            :default-value="typeof left == 'object' ? 'expression' : 'string'"
            :on-update:value="
              (v) => {
                left = v == 'string' ? '' : { left: '', operator: '', right: '' }
              }
            "
            :options="le_options"
          />
        </div>
      </th>
      <td>
        <trigger-editor v-if="typeof left == 'object'" :data="left" @update="(d) => (left = d)" />
        <div class="label" v-else>
          <trigger-string
            :data="left"
            @update="
              (v) => {
                left = v
              }
            "
          />
        </div>
      </td>
    </tr>
    <tr>
      <th>运算符</th>
      <td>
        <n-input v-model:value="operator" />
      </td>
    </tr>
    <tr>
      <th>
        <div class="label">
          右
          <n-select
            :default-value="typeof right == 'object' ? 'expression' : 'string'"
            :on-update:value="
              (v) => {
                right = v == 'string' ? '' : { left: '', operator: '', right: '' }
              }
            "
            :options="le_options"
          />
        </div>
      </th>
      <td>
        <trigger-editor
          v-if="typeof right == 'object'"
          :data="right"
          @update="(d) => (right = d)"
        />
        <div class="label" v-else>
          <trigger-string
            :data="right"
            @update="
              (v) => {
                right = v
              }
            "
          />
        </div>
      </td>
    </tr>
  </n-table>
</template>

<style scoped lang="scss">
.n-table {
  min-width: 100%;

  th {
    width: 124px;
    box-sizing: border-box;
  }
}

.label {
  display: flex;
  flex-direction: row;
  align-items: center;
  gap: 6px;
}
</style>
